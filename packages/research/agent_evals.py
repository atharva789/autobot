"""Local evidence contracts for agentic robot-design evaluations.

The POC intentionally starts as one module. Split it only after a stable second
responsibility is demonstrated by implementation pain.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import importlib.util
import json
import mimetypes
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


GRADE_STATUSES = frozenset({"pass", "fail", "error", "unrun"})
GRADE_CATEGORIES = frozenset(
    {"structural", "file-format", "compile", "simulator-load", "static", "behavior"}
)
TRIAL_STATES = frozenset({"passed", "failed", "error", "timeout", "unrun"})
TASK_FAMILIES = frozenset({"repair", "constrained-modification", "executed-behavior"})
PROFILE_HARNESSES = frozenset(
    {"fixture-reference", "fixture-seeded-failure", "codex", "claude-code", "command"}
)
TASK_FIELDS = frozenset(
    {
        "task_id",
        "version",
        "title",
        "family",
        "prompt",
        "starter_dir",
        "required_outputs",
        "allowed_tools",
        "constraints",
        "time_limit_seconds",
        "grader_entrypoint",
        "reference_dir",
        "seeded_failure_dir",
        "seeded_failure_grade_id",
    }
)
CONSTRAINT_FIELDS = frozenset(
    {"constraint_id", "quantity", "operator", "value", "unit"}
)
PROFILE_FIELDS = frozenset(
    {
        "profile_id",
        "harness",
        "model_id",
        "command",
        "instructions",
        "skills",
        "mcps",
        "tools",
        "environment_keys",
        "time_limit_seconds",
        "observable_cost_usd",
    }
)
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EXECUTION_STATES = frozenset({"completed", "error", "timeout", "unrun"})
EXECUTION_MODES = frozenset({"fixture", "live"})
SAFE_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "COLORTERM",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
)


class EvidenceManifestError(ValueError):
    """A bundle manifest cannot be parsed as the evidence contract."""


def _primitive(value: Any) -> Any:
    """Return a JSON-compatible value with stable container ordering semantics."""

    if dataclasses.is_dataclass(value):
        return _primitive(dataclasses.asdict(value))
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """Serialize one value for hashing and deterministic evidence comparison."""

    return json.dumps(
        _primitive(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_bytes(value: bytes) -> str:
    """Return the full lowercase SHA-256 digest for bytes."""

    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    """Return the SHA-256 digest for canonical JSON."""

    return sha256_bytes(canonical_json(value).encode("utf-8"))


def resolve_within(root: Path, relative_path: str | Path) -> Path:
    """Resolve one relative path and reject traversal outside ``root``."""

    relative = Path(relative_path)
    if relative.is_absolute():
        raise ValueError("path escapes its root")
    root_resolved = root.resolve()
    candidate = (root_resolved / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("path escapes its root") from exc
    return candidate


def validate_workspace_location(workspace: Path, denied_roots: Sequence[Path]) -> Path:
    """Ensure a trial workspace does not overlap any protected root."""

    resolved = workspace.resolve()
    for denied_root in denied_roots:
        denied = denied_root.resolve()
        if resolved == denied or resolved.is_relative_to(denied) or denied.is_relative_to(resolved):
            raise ValueError(f"workspace overlaps denied root: {denied}")
    return resolved


def snapshot_workspace(source: Path, destination: Path) -> tuple["Artifact", ...]:
    """Copy a symlink-free workspace and return its immutable file manifest."""

    source_resolved = source.resolve()
    if not source_resolved.is_dir():
        raise ValueError(f"workspace source is not a directory: {source}")
    if destination.exists():
        raise ValueError(f"snapshot destination already exists: {destination}")
    for path in source_resolved.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"workspace contains symlink: {path.relative_to(source_resolved)}")
        if not path.is_dir() and not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError(
                f"workspace contains non-regular file: {path.relative_to(source_resolved)}"
            )
        if path.is_file() and path.stat().st_nlink > 1:
            raise ValueError(f"workspace contains hard link: {path.relative_to(source_resolved)}")
    shutil.copytree(source_resolved, destination)
    return tuple(
        Artifact.from_path(destination, path)
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    )


def verify_artifacts(root: Path, artifacts: Sequence["Artifact"]) -> None:
    """Raise if saved artifact bytes, sizes, or paths have changed."""

    expected = {artifact.path: artifact for artifact in artifacts}
    current_paths = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if set(current_paths) != set(expected):
        raise ValueError("artifact drift: file set changed")
    for relative, path in current_paths.items():
        current = Artifact.from_path(root, path)
        if current.sha256 != expected[relative].sha256 or current.size_bytes != expected[relative].size_bytes:
            raise ValueError(f"artifact drift: {relative} changed")


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically write canonical JSON in the target directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(canonical_json(value))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    """Atomically write exact bytes in the target directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _string_tuple(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{key} must not contain duplicates")
    return tuple(value)


@dataclass(frozen=True)
class EvalTask:
    """Visible and protected contract references for one robotics eval task."""

    task_id: str
    version: int
    title: str
    family: str
    prompt: str
    starter_dir: str
    required_outputs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    constraints: tuple[Mapping[str, Any], ...]
    time_limit_seconds: int
    grader_entrypoint: str
    reference_dir: str
    seeded_failure_dir: str
    seeded_failure_grade_id: str

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("task version must be positive")
        if self.family not in TASK_FAMILIES:
            raise ValueError(f"unknown task family: {self.family}")
        if self.time_limit_seconds < 1 or self.time_limit_seconds > 3600:
            raise ValueError("task time limit must be between 1 and 3600 seconds")
        if not self.required_outputs:
            raise ValueError("task requires at least one output")
        if not self.constraints:
            raise ValueError("task requires at least one visible constraint")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvalTask":
        unknown = set(payload) - TASK_FIELDS
        missing = TASK_FIELDS - set(payload)
        if unknown:
            raise ValueError(f"unknown task fields: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing task fields: {sorted(missing)}")
        version = payload.get("version")
        time_limit = payload.get("time_limit_seconds")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("version must be an integer")
        if not isinstance(time_limit, int) or isinstance(time_limit, bool):
            raise ValueError("time_limit_seconds must be an integer")
        raw_constraints = payload.get("constraints")
        if not isinstance(raw_constraints, list) or not raw_constraints:
            raise ValueError("constraints must be a non-empty list")
        constraints: list[Mapping[str, Any]] = []
        for index, constraint in enumerate(raw_constraints):
            if not isinstance(constraint, dict):
                raise ValueError(f"constraint {index} must be an object")
            unknown_constraint = set(constraint) - CONSTRAINT_FIELDS
            missing_constraint = CONSTRAINT_FIELDS - set(constraint)
            if unknown_constraint or missing_constraint:
                raise ValueError(
                    f"constraint {index} fields invalid: "
                    f"missing={sorted(missing_constraint)} unknown={sorted(unknown_constraint)}"
                )
            for key in ("constraint_id", "quantity", "operator", "unit"):
                if not isinstance(constraint[key], str) or not constraint[key]:
                    raise ValueError(f"constraint {index} {key} must be a non-empty string")
            constraints.append(dict(constraint))
        return cls(
            task_id=_require_string(payload, "task_id"),
            version=version,
            title=_require_string(payload, "title"),
            family=_require_string(payload, "family"),
            prompt=_require_string(payload, "prompt"),
            starter_dir=_require_string(payload, "starter_dir"),
            required_outputs=_string_tuple(payload, "required_outputs"),
            allowed_tools=_string_tuple(payload, "allowed_tools"),
            constraints=tuple(constraints),
            time_limit_seconds=time_limit,
            grader_entrypoint=_require_string(payload, "grader_entrypoint"),
            reference_dir=_require_string(payload, "reference_dir"),
            seeded_failure_dir=_require_string(payload, "seeded_failure_dir"),
            seeded_failure_grade_id=_require_string(payload, "seeded_failure_grade_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return _primitive(self)

    @property
    def fingerprint(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True)
class SystemProfile:
    """Complete public agent configuration without secret environment values."""

    profile_id: str
    harness: str
    model_id: str
    command: tuple[str, ...]
    instructions: str
    skills: tuple[str, ...]
    mcps: tuple[str, ...]
    tools: tuple[str, ...]
    environment_keys: tuple[str, ...]
    time_limit_seconds: int
    observable_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.harness not in PROFILE_HARNESSES:
            raise ValueError(f"unknown profile harness: {self.harness}")
        if self.time_limit_seconds < 1 or self.time_limit_seconds > 3600:
            raise ValueError("profile time limit must be between 1 and 3600 seconds")
        if self.observable_cost_usd is not None and self.observable_cost_usd < 0:
            raise ValueError("observable cost must be nonnegative")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SystemProfile":
        unknown = set(payload) - PROFILE_FIELDS
        missing = PROFILE_FIELDS - set(payload)
        if unknown:
            raise ValueError(f"unknown profile fields: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing profile fields: {sorted(missing)}")
        time_limit = payload.get("time_limit_seconds")
        if not isinstance(time_limit, int) or isinstance(time_limit, bool):
            raise ValueError("time_limit_seconds must be an integer")
        cost = payload.get("observable_cost_usd")
        if cost is not None and (not isinstance(cost, (int, float)) or isinstance(cost, bool)):
            raise ValueError("observable_cost_usd must be numeric or null")
        profile_id = _require_string(payload, "profile_id")
        if not PROFILE_ID_PATTERN.fullmatch(profile_id):
            raise ValueError("profile_id must be lowercase kebab-case")
        instructions = payload.get("instructions")
        if not isinstance(instructions, str):
            raise ValueError("instructions must be a string")
        return cls(
            profile_id=profile_id,
            harness=_require_string(payload, "harness"),
            model_id=_require_string(payload, "model_id"),
            command=_string_tuple(payload, "command"),
            instructions=instructions,
            skills=_string_tuple(payload, "skills"),
            mcps=_string_tuple(payload, "mcps"),
            tools=_string_tuple(payload, "tools"),
            environment_keys=_string_tuple(payload, "environment_keys"),
            time_limit_seconds=time_limit,
            observable_cost_usd=float(cost) if cost is not None else None,
        )

    def _public_dict(self) -> dict[str, Any]:
        return _primitive(self)

    def to_dict(self, *, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
        manifest = self._public_dict()
        available = environment or {}
        manifest["environment"] = {
            key: {"present": key in available and bool(available[key])}
            for key in self.environment_keys
        }
        return manifest

    @property
    def fingerprint(self) -> str:
        return sha256_json(self._public_dict())


def load_profiles(suite_root: Path) -> tuple[SystemProfile, ...]:
    """Load unique public system-profile manifests from one eval suite."""

    profiles_root = suite_root.resolve() / "profiles"
    if not profiles_root.is_dir():
        raise ValueError(f"suite profiles directory does not exist: {profiles_root}")
    profiles: list[SystemProfile] = []
    seen_ids: set[str] = set()
    for profile_path in sorted(profiles_root.glob("*.json")):
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid profile manifest: {profile_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"profile manifest must be an object: {profile_path}")
        profile = SystemProfile.from_dict(payload)
        if profile.profile_id in seen_ids:
            raise ValueError(f"duplicate profile_id: {profile.profile_id}")
        seen_ids.add(profile.profile_id)
        profiles.append(profile)
    if not profiles:
        raise ValueError(f"suite contains no profile manifests: {profiles_root}")
    return tuple(profiles)


def profile_availability(profile: SystemProfile) -> tuple[bool, str | None]:
    """Report only locally provable profile availability without executing it."""

    if profile.harness.startswith("fixture-"):
        return True, None
    if not profile.command:
        return False, "profile command is empty"
    if shutil.which(profile.command[0]) is None:
        return False, f"missing executable: {profile.command[0]}"
    return True, None


@dataclass(frozen=True)
class ExecutionResult:
    """Raw agent-process outcome before protected grading."""

    mode: str
    state: str
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    error: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.mode not in EXECUTION_MODES:
            raise ValueError(f"unknown execution mode: {self.mode}")
        if self.state not in EXECUTION_STATES:
            raise ValueError(f"unknown execution state: {self.state}")
        if self.duration_seconds < 0:
            raise ValueError("execution duration must be nonnegative")


@dataclass(frozen=True)
class CapturedExecution:
    """A terminated execution plus its parent-frozen files and transcript."""

    execution: ExecutionResult
    artifacts: tuple[Artifact, ...]
    evidence_dir: Path
    artifact_dir: Path
    transcript_path: Path
    recovery_workspace_path: Path | None = None


@dataclass(frozen=True)
class CodexTranscript:
    """Lossless parse summary for one Codex JSONL stdout stream."""

    raw: str
    events: tuple[Mapping[str, Any], ...]
    state: str
    thread_id: str | None = None
    final_message: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None


def _execution_result(
    *,
    state: str,
    command: Sequence[str],
    started: float,
    exit_code: int | None = None,
    stdout: str = "",
    stderr: str = "",
    error_category: str | None = None,
    error_message: str | None = None,
    mode: str = "live",
) -> ExecutionResult:
    error = None
    if error_category is not None:
        error = {"category": error_category, "message": error_message or ""}
    return ExecutionResult(
        mode=mode,
        state=state,
        command=tuple(command),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=time.monotonic() - started,
        error=error,
    )


def _sandbox_profile(
    denied_roots: Sequence[Path],
    *,
    allow_network: bool,
    compatibility_mode: bool,
) -> str:
    """Build a constant-form Seatbelt profile whose paths arrive as parameters."""

    if compatibility_mode:
        rules = ["(version 1)", "(allow default)"]
    else:
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process*)",
            "(allow file-read*)",
            '(allow file-write* (subpath (param "WORKSPACE")))',
        ]
    if allow_network and not compatibility_mode:
        rules.extend(
            (
                "(allow network*)",
                "(allow system-socket)",
                "(allow mach*)",
                "(allow sysctl*)",
                "(allow ipc-posix*)",
            )
        )
    for index in range(len(denied_roots)):
        rules.append(
            f'(deny file-read* file-write* (subpath (param "DENIED_{index}")))'
        )
    return "\n".join(rules)


def run_sandboxed(
    command: Sequence[str],
    *,
    cwd: Path,
    stdin_text: str,
    denied_roots: Sequence[Path],
    timeout_seconds: float,
    environment: Mapping[str, str] | None = None,
    allow_network: bool = False,
    compatibility_mode: bool = False,
) -> ExecutionResult:
    """Run one argv through macOS Seatbelt without invoking a shell."""

    started = time.monotonic()
    original_command = tuple(command)
    workspace = validate_workspace_location(cwd, denied_roots)
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")
    if not original_command:
        return _execution_result(
            state="unrun",
            command=original_command,
            started=started,
            error_category="dependency",
            error_message="profile command is empty",
        )
    executable = original_command[0]
    executable_path = Path(executable)
    if executable_path.is_absolute():
        if not executable_path.exists():
            return _execution_result(
                state="unrun",
                command=original_command,
                started=started,
                error_category="dependency",
                error_message=f"missing executable: {executable}",
            )
        if not os.access(executable_path, os.X_OK):
            return _execution_result(
                state="error",
                command=original_command,
                started=started,
                error_category="permission",
                error_message=f"executable is not permitted: {executable}",
            )
        resolved_executable = executable_path.resolve()
    else:
        lookup_environment = os.environ if environment is None else environment
        discovered = shutil.which(executable, path=lookup_environment.get("PATH", ""))
        if discovered is None:
            return _execution_result(
                state="unrun",
                command=original_command,
                started=started,
                error_category="dependency",
                error_message=f"missing executable: {executable}",
            )
        resolved_executable = Path(discovered).resolve()
    effective_command = (str(resolved_executable), *original_command[1:])
    sandbox_executable = Path("/usr/bin/sandbox-exec")
    if not sandbox_executable.is_file() or not os.access(sandbox_executable, os.X_OK):
        return _execution_result(
            state="unrun",
            command=original_command,
            started=started,
            error_category="isolation-unavailable",
            error_message="missing executable: /usr/bin/sandbox-exec",
        )
    resolved_denied = tuple(Path(root).resolve() for root in denied_roots)
    sandbox_argv: list[str] = [str(sandbox_executable), "-D", f"WORKSPACE={workspace}"]
    for index, denied in enumerate(resolved_denied):
        sandbox_argv.extend(("-D", f"DENIED_{index}={denied}"))
    sandbox_argv.extend(
        (
            "-p",
            _sandbox_profile(
                resolved_denied,
                allow_network=allow_network,
                compatibility_mode=compatibility_mode,
            ),
            *effective_command,
        )
    )
    if environment is None:
        child_environment = {
            key: value for key, value in os.environ.items() if key in SAFE_ENVIRONMENT_KEYS
        }
        child_environment["TMPDIR"] = str(workspace)
    else:
        child_environment = dict(environment)
    try:
        process = subprocess.Popen(
            sandbox_argv,
            cwd=workspace,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_environment,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
    except PermissionError as exc:
        return _execution_result(
            state="error",
            command=effective_command,
            started=started,
            error_category="permission",
            error_message=str(exc),
        )
    except OSError as exc:
        return _execution_result(
            state="error",
            command=effective_command,
            started=started,
            error_category="execution",
            error_message=str(exc),
        )
    try:
        stdout, stderr = process.communicate(input=stdin_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        partial_stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        partial_stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            remaining_stdout, remaining_stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            remaining_stdout, remaining_stderr = process.communicate()
        return _execution_result(
            state="timeout",
            command=effective_command,
            started=started,
            exit_code=process.returncode,
            stdout=partial_stdout + (remaining_stdout or ""),
            stderr=partial_stderr + (remaining_stderr or ""),
            error_category="timeout",
            error_message=f"command exceeded {timeout_seconds} seconds",
        )
    if process.returncode != 0:
        return _execution_result(
            state="error",
            command=effective_command,
            started=started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            error_category="nonzero-exit",
            error_message=f"command exited with status {process.returncode}",
        )
    return _execution_result(
        state="completed",
        command=effective_command,
        started=started,
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def write_execution_transcript(result: ExecutionResult, path: Path) -> None:
    """Persist the exact argv and raw output without mutable formatting."""

    atomic_write_json(path, result)


def parse_codex_jsonl(raw: str) -> CodexTranscript:
    """Parse Codex JSONL without discarding unknown events or raw bytes."""

    events: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            return CodexTranscript(
                raw=raw,
                events=tuple(events),
                state="error",
                error={
                    "category": "transcript-protocol",
                    "message": f"invalid JSONL at line {line_number}: {exc.msg}",
                },
            )
        if not isinstance(event, dict):
            return CodexTranscript(
                raw=raw,
                events=tuple(events),
                state="error",
                error={
                    "category": "transcript-protocol",
                    "message": f"JSONL line {line_number} is not an object",
                },
            )
        events.append(event)
    thread_id: str | None = None
    final_message: str | None = None
    usage: Mapping[str, Any] = {}
    completed = False
    terminal_error: Mapping[str, Any] | None = None
    for event in events:
        event_type = event.get("type")
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
        elif event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict):
                if item.get("type") == "agent_message":
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        final_message = text_value
                elif item.get("type") == "error":
                    message = item.get("message")
                    if isinstance(message, str) and "Skill descriptions were shortened" in message:
                        terminal_error = {
                            "category": "profile-contamination",
                            "message": message,
                        }
        elif event_type == "turn.completed":
            completed = True
            if isinstance(event.get("usage"), dict):
                usage = dict(event["usage"])
        elif event_type in {"turn.failed", "error"}:
            terminal_error = {
                "category": "agent-failure",
                "message": canonical_json(event),
            }
    if terminal_error is not None:
        return CodexTranscript(
            raw=raw,
            events=tuple(events),
            state="error",
            thread_id=thread_id,
            final_message=final_message,
            usage=usage,
            error=terminal_error,
        )
    if not completed:
        return CodexTranscript(
            raw=raw,
            events=tuple(events),
            state="error",
            thread_id=thread_id,
            final_message=final_message,
            usage=usage,
            error={
                "category": "transcript-incomplete",
                "message": "Codex JSONL contains no turn.completed event",
            },
        )
    return CodexTranscript(
        raw=raw,
        events=tuple(events),
        state="completed",
        thread_id=thread_id,
        final_message=final_message,
        usage=usage,
    )


def execute_profile(
    profile: SystemProfile,
    source_dir: Path,
    workspace: Path,
    *,
    prompt: str,
    denied_roots: Sequence[Path],
    environment: Mapping[str, str] | None = None,
) -> ExecutionResult:
    """Copy a clean source tree, then materialize a fixture or run a live profile."""

    started = time.monotonic()
    snapshot_workspace(source_dir, workspace)
    if profile.harness.startswith("fixture-"):
        return _execution_result(
            state="completed",
            command=(),
            started=started,
            exit_code=None,
            mode="fixture",
        )
    visible_input = "\n\n".join(part for part in (profile.instructions, prompt) if part)
    host_environment = os.environ if environment is None else environment
    allowed_environment_keys = SAFE_ENVIRONMENT_KEYS | frozenset(profile.environment_keys)
    child_environment = {
        key: value
        for key, value in host_environment.items()
        if key in allowed_environment_keys
    }
    child_environment["TMPDIR"] = str(workspace.resolve())
    execution = run_sandboxed(
        profile.command,
        cwd=workspace,
        stdin_text=visible_input,
        denied_roots=denied_roots,
        timeout_seconds=profile.time_limit_seconds,
        environment=child_environment,
        allow_network=profile.harness in {"codex", "claude-code"},
        compatibility_mode=profile.harness in {"codex", "claude-code"},
    )
    if profile.harness == "codex" and execution.state == "completed":
        if "sandbox_apply: Operation not permitted" in execution.stderr:
            return dataclasses.replace(
                execution,
                state="error",
                error={
                    "category": "isolation-runtime",
                    "message": "Codex nested sandbox could not initialize inside the outer boundary",
                },
            )
        transcript = parse_codex_jsonl(execution.stdout)
        if transcript.state != "completed":
            return dataclasses.replace(execution, state="error", error=transcript.error)
    return execution


def capture_profile_execution(
    profile: SystemProfile,
    source_dir: Path,
    *,
    prompt: str,
    workspace_parent: Path,
    evidence_dir: Path,
    denied_roots: Sequence[Path],
    environment: Mapping[str, str] | None = None,
) -> CapturedExecution:
    """Run, terminate, freeze, and clean up one outcome in that order."""

    workspace_parent_resolved = workspace_parent.resolve()
    if not workspace_parent_resolved.is_dir():
        raise ValueError(f"workspace parent is not a directory: {workspace_parent}")
    if evidence_dir.exists():
        raise ValueError(f"evidence directory already exists: {evidence_dir}")
    evidence_dir.mkdir(parents=True)
    evidence_resolved = evidence_dir.resolve()
    container = Path(tempfile.mkdtemp(prefix="agent-eval-trial-", dir=workspace_parent_resolved))
    workspace = container / "workspace"
    effective_denied = tuple(denied_roots) + (evidence_resolved,)
    execution = execute_profile(
        profile,
        source_dir,
        workspace,
        prompt=prompt,
        denied_roots=effective_denied,
        environment=environment,
    )
    artifact_dir = evidence_resolved / "artifacts"
    transcript_path = evidence_resolved / "transcript.json"
    try:
        artifacts = snapshot_workspace(workspace, artifact_dir)
    except (OSError, ValueError, shutil.Error) as exc:
        failed_execution = dataclasses.replace(
            execution,
            state="error",
            error={
                "category": "artifact-freeze",
                "message": str(exc),
                "execution_state": execution.state,
            },
        )
        write_execution_transcript(failed_execution, transcript_path)
        return CapturedExecution(
            execution=failed_execution,
            artifacts=(),
            evidence_dir=evidence_resolved,
            artifact_dir=artifact_dir,
            transcript_path=transcript_path,
            recovery_workspace_path=workspace,
        )
    write_execution_transcript(execution, transcript_path)
    shutil.rmtree(container)
    return CapturedExecution(
        execution=execution,
        artifacts=artifacts,
        evidence_dir=evidence_resolved,
        artifact_dir=artifact_dir,
        transcript_path=transcript_path,
    )


@dataclass(frozen=True)
class Artifact:
    """One immutable file in a final workspace snapshot."""

    path: str
    sha256: str
    size_bytes: int
    media_type: str = "application/octet-stream"

    @classmethod
    def from_path(cls, root: Path, path: Path) -> "Artifact":
        root_resolved = root.resolve()
        path_resolved = path.resolve()
        try:
            relative = path_resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError("artifact path escapes its root") from exc
        data = path_resolved.read_bytes()
        media_type = mimetypes.guess_type(relative.name)[0] or "application/octet-stream"
        return cls(
            path=relative.as_posix(),
            sha256=sha256_bytes(data),
            size_bytes=len(data),
            media_type=media_type,
        )


@dataclass(frozen=True)
class GradeResult:
    """One normalized protected assertion and its direct evidence."""

    grade_id: str
    category: str
    status: str
    assertion: str
    artifact_digests: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    observed: Mapping[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    duration_seconds: float = 0.0
    grader_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.category not in GRADE_CATEGORIES:
            raise ValueError(
                f"unknown grade category: {self.category}; expected grade category contract"
            )
        if self.status not in GRADE_STATUSES:
            raise ValueError(f"unknown grade status: {self.status}; expected grade status contract")
        if self.duration_seconds < 0:
            raise ValueError("grade duration must be nonnegative")


@dataclass(frozen=True)
class TrialResult:
    """One immutable attempt by one complete system profile."""

    trial_id: str
    task_id: str
    task_fingerprint: str
    profile_id: str
    profile_fingerprint: str
    attempt: int
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float = 0.0
    exit_code: int | None = None
    transcript_path: str | None = None
    transcript_sha256: str | None = None
    grades_path: str | None = None
    grades_sha256: str | None = None
    artifacts: tuple[Artifact, ...] = ()
    grades: tuple[GradeResult, ...] = ()
    error: Mapping[str, Any] | None = None
    observable_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if self.state not in TRIAL_STATES:
            raise ValueError(f"unknown trial state: {self.state}")
        if self.attempt < 1:
            raise ValueError("trial attempt must be positive")
        if self.duration_seconds < 0:
            raise ValueError("trial duration must be nonnegative")


@dataclass(frozen=True)
class EvidenceBundle:
    """Canonical manifest for one task/profile group of trials."""

    schema_version: int
    bundle_id: str
    created_at: str
    task: Mapping[str, Any]
    profile: Mapping[str, Any]
    environment: Mapping[str, Any]
    trials: tuple[TrialResult, ...]


@dataclass(frozen=True)
class ReplayResult:
    """Deterministic replay outcome or an explicit dependency-drift refusal."""

    bundle_id: str
    state: str
    repeat_digests: tuple[str, ...]
    identical: bool
    drift: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.state not in {"passed", "drift"}:
            raise ValueError(f"unknown replay state: {self.state}")


@dataclass(frozen=True)
class _EvidenceInspection:
    """Verified paths and rows shared by comparison and deterministic replay."""

    bundle_id: str
    manifest: Mapping[str, Any]
    task_path: Path | None
    grader_path: Path | None
    trials: tuple[tuple[Mapping[str, Any], Path, tuple[Artifact, ...]], ...]
    drift: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class ComparisonResult:
    """Task-first comparison of two complete system profiles."""

    comparison_id: str
    left_profile: str
    right_profile: str
    source_revisions: Mapping[str, Any]
    trial_rows: tuple[Mapping[str, Any], ...]
    aggregates: Mapping[str, Any]


@dataclass(frozen=True)
class LoadedTask:
    """Validated task manifest plus contained public and protected paths."""

    manifest: EvalTask
    suite_root: Path
    public_dir: Path
    starter_dir: Path
    grader_path: Path
    reference_dir: Path
    seeded_failure_dir: Path
    fingerprint: str


@dataclass(frozen=True)
class LoadedSuite:
    """One task suite with unique task IDs."""

    root: Path
    tasks: tuple[LoadedTask, ...]

    def task(self, task_id: str) -> LoadedTask:
        for task in self.tasks:
            if task.manifest.task_id == task_id:
                return task
        raise KeyError(f"unknown task_id: {task_id}")


@dataclass(frozen=True)
class OracleValidation:
    """Reference and seeded-failure outcomes for one task."""

    task_id: str
    reference_state: str
    seeded_failure_state: str
    failed_grade_ids: tuple[str, ...]
    reference_grades: tuple[GradeResult, ...]
    seeded_failure_grades: tuple[GradeResult, ...]


def _tree_manifest(root: Path) -> tuple[dict[str, Any], ...]:
    if not root.is_dir():
        raise ValueError(f"expected directory does not exist: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"task tree contains symlink: {path}")
        if path.is_file():
            data = path.read_bytes()
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256_bytes(data),
                    "size_bytes": len(data),
                }
            )
    return tuple(rows)


def load_suite(suite_root: Path) -> LoadedSuite:
    """Load task manifests and prove every referenced path is contained."""

    root = suite_root.resolve()
    tasks_root = root / "tasks"
    if not tasks_root.is_dir():
        raise ValueError(f"suite tasks directory does not exist: {tasks_root}")
    loaded: list[LoadedTask] = []
    seen_ids: set[str] = set()
    for manifest_path in sorted(tasks_root.glob("*/public/task.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid task manifest: {manifest_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"task manifest must be an object: {manifest_path}")
        manifest = EvalTask.from_dict(payload)
        if manifest.task_id in seen_ids:
            raise ValueError(f"duplicate task_id: {manifest.task_id}")
        seen_ids.add(manifest.task_id)
        public_dir = manifest_path.parent.resolve()
        starter_dir = resolve_within(public_dir, manifest.starter_dir)
        grader_path = resolve_within(root, manifest.grader_entrypoint)
        reference_dir = resolve_within(root, manifest.reference_dir)
        seeded_failure_dir = resolve_within(root, manifest.seeded_failure_dir)
        if not starter_dir.is_dir():
            raise ValueError(f"starter directory missing for {manifest.task_id}: {starter_dir}")
        if not grader_path.is_file():
            raise ValueError(f"grader missing for {manifest.task_id}: {grader_path}")
        if not reference_dir.is_dir():
            raise ValueError(f"reference directory missing for {manifest.task_id}: {reference_dir}")
        if not seeded_failure_dir.is_dir():
            raise ValueError(
                f"seeded failure directory missing for {manifest.task_id}: {seeded_failure_dir}"
            )
        fingerprint = sha256_json(
            {
                "manifest": manifest.to_dict(),
                "starter": _tree_manifest(starter_dir),
                "grader": sha256_bytes(grader_path.read_bytes()),
                "reference": _tree_manifest(reference_dir),
                "seeded_failure": _tree_manifest(seeded_failure_dir),
            }
        )
        loaded.append(
            LoadedTask(
                manifest=manifest,
                suite_root=root,
                public_dir=public_dir,
                starter_dir=starter_dir,
                grader_path=grader_path,
                reference_dir=reference_dir,
                seeded_failure_dir=seeded_failure_dir,
                fingerprint=fingerprint,
            )
        )
    if not loaded:
        raise ValueError(f"suite contains no task manifests: {root}")
    return LoadedSuite(root=root, tasks=tuple(loaded))


def _load_grader(task: LoadedTask):
    module_name = f"agent_eval_grader_{task.manifest.task_id.replace('-', '_')}_{task.fingerprint[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, task.grader_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load grader for {task.manifest.task_id}")
    grader_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader_module)
    grade = getattr(grader_module, "grade", None)
    if not callable(grade):
        raise ValueError(f"grader for {task.manifest.task_id} must expose grade(workspace)")
    return grade


def _normalize_grades(task: LoadedTask, rows: Any) -> tuple[GradeResult, ...]:
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"grader for {task.manifest.task_id} returned no grade rows")
    normalized: list[GradeResult] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"grader for {task.manifest.task_id} returned a non-object grade")
        grade_id = _require_string(row, "grade_id")
        if grade_id in seen_ids:
            raise ValueError(f"duplicate grade_id for {task.manifest.task_id}: {grade_id}")
        seen_ids.add(grade_id)
        normalized.append(
            GradeResult(
                grade_id=grade_id,
                category=_require_string(row, "category"),
                status=_require_string(row, "status"),
                assertion=_require_string(row, "assertion"),
                artifact_digests=tuple(str(value) for value in row.get("artifact_digests", ())),
                parameters=dict(row.get("parameters", {})),
                observed=dict(row.get("observed", {})),
                raw_output=str(row.get("raw_output", "")),
                duration_seconds=float(row.get("duration_seconds", 0.0)),
                grader_fingerprint=sha256_bytes(task.grader_path.read_bytes()),
            )
        )
    return tuple(normalized)


def _grade_state(grades: Sequence[GradeResult]) -> str:
    if any(grade.status == "error" for grade in grades):
        return "error"
    if any(grade.status == "unrun" for grade in grades):
        return "unrun"
    if any(grade.status == "fail" for grade in grades):
        return "failed"
    return "passed"


def validate_task_oracles(task: LoadedTask) -> OracleValidation:
    """Execute one protected grader on its known pass and known failure."""

    grader = _load_grader(task)
    reference = _normalize_grades(task, grader(task.reference_dir))
    seeded = _normalize_grades(task, grader(task.seeded_failure_dir))
    failed_grade_ids = tuple(grade.grade_id for grade in seeded if grade.status == "fail")
    if _grade_state(reference) != "passed":
        raise ValueError(f"reference does not pass for task {task.manifest.task_id}")
    if task.manifest.seeded_failure_grade_id not in failed_grade_ids:
        raise ValueError(
            f"seeded failure for {task.manifest.task_id} did not fail "
            f"{task.manifest.seeded_failure_grade_id}"
        )
    return OracleValidation(
        task_id=task.manifest.task_id,
        reference_state="passed",
        seeded_failure_state=_grade_state(seeded),
        failed_grade_ids=failed_grade_ids,
        reference_grades=reference,
        seeded_failure_grades=seeded,
    )


def _installed_mujoco_version() -> str:
    try:
        return importlib.metadata.version("mujoco")
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def grade_frozen_outcome(
    task: LoadedTask,
    artifact_dir: Path,
    artifacts: Sequence[Artifact],
) -> tuple[GradeResult, ...]:
    """Run protected grading against immutable parent-frozen regular files."""

    artifact_root = artifact_dir.resolve()
    artifact_digests = tuple(artifact.sha256 for artifact in artifacts)
    grader_fingerprint = sha256_bytes(task.grader_path.read_bytes())
    try:
        verify_artifacts(artifact_root, artifacts)
    except (OSError, ValueError) as exc:
        return (
            GradeResult(
                grade_id="artifact.integrity",
                category="file-format",
                status="error",
                assertion="frozen artifact manifest matches the files presented for grading",
                artifact_digests=artifact_digests,
                raw_output=str(exc),
                grader_fingerprint=grader_fingerprint,
            ),
        )
    missing: list[GradeResult] = []
    for required_output in task.manifest.required_outputs:
        try:
            required_path = resolve_within(artifact_root, required_output)
        except ValueError as exc:
            missing.append(
                GradeResult(
                    grade_id=f"required.{required_output}",
                    category="file-format",
                    status="fail",
                    assertion=f"required output {required_output} stays inside the artifact root",
                    artifact_digests=artifact_digests,
                    raw_output=str(exc),
                    grader_fingerprint=grader_fingerprint,
                )
            )
            continue
        if required_path.is_symlink() or not required_path.is_file():
            missing.append(
                GradeResult(
                    grade_id=f"required.{required_output}",
                    category="file-format",
                    status="fail",
                    assertion=f"required regular artifact {required_output} exists",
                    artifact_digests=artifact_digests,
                    observed={"path": required_output, "present": False},
                    raw_output=f"missing required regular artifact: {required_output}",
                    grader_fingerprint=grader_fingerprint,
                )
            )
    if missing:
        return tuple(missing)
    started = time.monotonic()
    try:
        grader = _load_grader(task)
        normalized = _normalize_grades(task, grader(artifact_root))
    except Exception:
        return (
            GradeResult(
                grade_id="grader.execution",
                category="static",
                status="error",
                assertion="protected grader executes and returns the grade contract",
                artifact_digests=artifact_digests,
                raw_output=traceback.format_exc(),
                duration_seconds=time.monotonic() - started,
                grader_fingerprint=grader_fingerprint,
            ),
        )
    mujoco_version = _installed_mujoco_version()
    enriched: list[GradeResult] = []
    for grade in normalized:
        parameters = dict(grade.parameters)
        if grade.category in {"simulator-load", "behavior"}:
            parameters.setdefault("mujoco_version", mujoco_version)
        raw_output = grade.raw_output
        if not raw_output and grade.category in {"compile", "simulator-load", "behavior"}:
            raw_output = canonical_json(
                {"parameters": parameters, "observed": grade.observed}
            )
        enriched.append(
            dataclasses.replace(
                grade,
                artifact_digests=grade.artifact_digests or artifact_digests,
                parameters=parameters,
                raw_output=raw_output,
            )
        )
    try:
        verify_artifacts(artifact_root, artifacts)
    except (OSError, ValueError) as exc:
        enriched.append(
            GradeResult(
                grade_id="grader.artifact-integrity",
                category="file-format",
                status="error",
                assertion="protected grading does not mutate frozen artifacts",
                artifact_digests=artifact_digests,
                raw_output=str(exc),
                duration_seconds=time.monotonic() - started,
                grader_fingerprint=grader_fingerprint,
            )
        )
    return tuple(enriched)


def finalize_evidence_bundle(
    task: LoadedTask,
    profile: SystemProfile,
    captures: Sequence[CapturedExecution],
    bundle_dir: Path,
) -> EvidenceBundle:
    """Grade terminated captures and atomically publish one immutable manifest."""

    if not captures:
        raise ValueError("evidence bundle requires at least one capture")
    bundle_root = bundle_dir.resolve()
    manifest_path = bundle_root / "manifest.json"
    if manifest_path.exists():
        raise ValueError(f"bundle manifest already exists: {manifest_path}")
    bundle_root.mkdir(parents=True, exist_ok=True)
    for capture in captures:
        try:
            capture.evidence_dir.resolve().relative_to(bundle_root)
        except ValueError as exc:
            raise ValueError("capture evidence directory is outside the bundle") from exc

    task_path = bundle_root / "task.json"
    profile_path = bundle_root / "profile.json"
    grader_path = bundle_root / "grader" / "grader.py"
    environment_path = bundle_root / "environment.json"
    snapshot_paths = (task_path, profile_path, grader_path, environment_path)
    if any(path.exists() for path in snapshot_paths):
        raise ValueError("bundle dependency snapshot already exists")

    task_payload = task.manifest.to_dict()
    profile_payload = profile._public_dict()
    environment_payload = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "mujoco_version": _installed_mujoco_version(),
        "sandbox_backend": (
            "/usr/bin/sandbox-exec"
            if Path("/usr/bin/sandbox-exec").is_file()
            else "unavailable"
        ),
    }
    atomic_write_json(task_path, task_payload)
    atomic_write_json(profile_path, profile_payload)
    _atomic_write_bytes(grader_path, task.grader_path.read_bytes())
    atomic_write_json(environment_path, environment_payload)
    task_sha256 = sha256_bytes(task_path.read_bytes())
    profile_sha256 = sha256_bytes(profile_path.read_bytes())
    grader_sha256 = sha256_bytes(grader_path.read_bytes())
    environment_sha256 = sha256_bytes(environment_path.read_bytes())

    bundle_basis = {
        "task_fingerprint": task.fingerprint,
        "profile_fingerprint": profile.fingerprint,
        "dependency_snapshots": {
            "task": task_sha256,
            "profile": profile_sha256,
            "grader": grader_sha256,
            "environment": environment_sha256,
        },
        "captures": [
            {
                "state": capture.execution.state,
                "command": capture.execution.command,
                "exit_code": capture.execution.exit_code,
                "artifacts": capture.artifacts,
            }
            for capture in captures
        ],
    }
    bundle_uuid = uuid.uuid5(uuid.NAMESPACE_URL, sha256_json(bundle_basis))
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    trials: list[TrialResult] = []
    for attempt, capture in enumerate(captures, start=1):
        grades: tuple[GradeResult, ...] = ()
        state = capture.execution.state
        error = capture.execution.error
        if state == "completed":
            grades = grade_frozen_outcome(task, capture.artifact_dir, capture.artifacts)
            state = _grade_state(grades)
            if state == "error" and error is None:
                error = {
                    "category": "grading",
                    "message": "one or more protected grades returned error",
                }
        grades_path = capture.evidence_dir / "grades.json"
        atomic_write_json(grades_path, grades)
        try:
            transcript_path = capture.transcript_path.resolve().relative_to(bundle_root).as_posix()
        except ValueError as exc:
            raise ValueError("capture transcript is outside the bundle") from exc
        try:
            grades_relative_path = grades_path.resolve().relative_to(bundle_root).as_posix()
        except ValueError as exc:
            raise ValueError("capture grades are outside the bundle") from exc
        transcript_sha256 = sha256_bytes(capture.transcript_path.read_bytes())
        grades_sha256 = sha256_bytes(grades_path.read_bytes())
        trial_uuid = uuid.uuid5(
            bundle_uuid,
            canonical_json(
                {
                    "attempt": attempt,
                    "artifacts": capture.artifacts,
                    "execution_state": capture.execution.state,
                }
            ),
        )
        trials.append(
            TrialResult(
                trial_id=str(trial_uuid),
                task_id=task.manifest.task_id,
                task_fingerprint=task.fingerprint,
                profile_id=profile.profile_id,
                profile_fingerprint=profile.fingerprint,
                attempt=attempt,
                state=state,
                started_at=created_at,
                finished_at=created_at,
                duration_seconds=capture.execution.duration_seconds,
                exit_code=capture.execution.exit_code,
                transcript_path=transcript_path,
                transcript_sha256=transcript_sha256,
                grades_path=grades_relative_path,
                grades_sha256=grades_sha256,
                artifacts=capture.artifacts,
                grades=grades,
                error=error,
                observable_cost_usd=profile.observable_cost_usd,
            )
        )
    task_snapshot = {
        "task_id": task.manifest.task_id,
        "fingerprint": task.fingerprint,
        "version": task.manifest.version,
        "title": task.manifest.title,
        "family": task.manifest.family,
        "constraints": task.manifest.constraints,
        "snapshot_path": "task.json",
        "snapshot_sha256": task_sha256,
        "grader_path": "grader/grader.py",
        "grader_sha256": grader_sha256,
    }
    profile_snapshot = profile.to_dict(environment={})
    profile_snapshot["fingerprint"] = profile.fingerprint
    profile_snapshot["snapshot_path"] = "profile.json"
    profile_snapshot["snapshot_sha256"] = profile_sha256
    environment_snapshot = {
        **environment_payload,
        "snapshot_path": "environment.json",
        "snapshot_sha256": environment_sha256,
    }
    bundle = EvidenceBundle(
        schema_version=1,
        bundle_id=str(bundle_uuid),
        created_at=created_at,
        task=task_snapshot,
        profile=profile_snapshot,
        environment=environment_snapshot,
        trials=tuple(trials),
    )
    atomic_write_json(manifest_path, bundle)
    return bundle


def _snapshot_path_with_digest(
    bundle_root: Path,
    metadata: Mapping[str, Any],
    *,
    path_key: str,
    digest_key: str,
    category: str,
    drift: list[Mapping[str, Any]],
) -> Path | None:
    relative_path = metadata.get(path_key)
    expected_digest = metadata.get(digest_key)
    if not isinstance(relative_path, str) or not isinstance(expected_digest, str):
        drift.append(
            {
                "category": category,
                "message": f"missing {path_key} or {digest_key}",
            }
        )
        return None
    try:
        path = resolve_within(bundle_root, relative_path)
    except ValueError as exc:
        drift.append({"category": category, "message": str(exc), "path": relative_path})
        return None
    if not path.is_file() or path.is_symlink():
        drift.append(
            {"category": category, "message": "snapshot is missing", "path": relative_path}
        )
        return None
    observed_digest = sha256_bytes(path.read_bytes())
    if observed_digest != expected_digest:
        drift.append(
            {
                "category": category,
                "message": "snapshot digest changed",
                "path": relative_path,
                "expected": expected_digest,
                "observed": observed_digest,
            }
        )
        return None
    return path


def _artifact_from_manifest(row: Any) -> Artifact:
    if not isinstance(row, Mapping):
        raise ValueError("artifact manifest row must be an object")
    path = row.get("path")
    digest = row.get("sha256")
    size = row.get("size_bytes")
    media_type = row.get("media_type", "application/octet-stream")
    if not isinstance(path, str) or not path:
        raise ValueError("artifact path must be a non-empty string")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError(f"artifact {path} has an invalid digest")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError(f"artifact {path} has an invalid size")
    if not isinstance(media_type, str) or not media_type:
        raise ValueError(f"artifact {path} has an invalid media type")
    return Artifact(path=path, sha256=digest, size_bytes=size, media_type=media_type)


def _normalized_replay_grade(value: GradeResult | Mapping[str, Any]) -> dict[str, Any]:
    payload = _primitive(value)
    if not isinstance(payload, dict):
        raise ValueError("grade row must be an object")
    payload.pop("duration_seconds", None)
    return payload


def _inspect_evidence_bundle(
    bundle_dir: Path,
    *,
    check_simulator: bool,
    simulator_version: str | None = None,
) -> _EvidenceInspection:
    """Check frozen bundle bytes without executing protected grader code."""

    bundle_root = bundle_dir.resolve()
    manifest_path = bundle_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceManifestError(f"invalid evidence manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise EvidenceManifestError("evidence manifest must be an object")
    if manifest.get("schema_version") != 1:
        raise EvidenceManifestError("evidence manifest schema_version must be 1")
    raw_bundle_id = manifest.get("bundle_id")
    if not isinstance(raw_bundle_id, str):
        raise EvidenceManifestError("evidence manifest bundle_id must be a canonical UUID")
    try:
        parsed_bundle_id = uuid.UUID(raw_bundle_id)
    except ValueError as exc:
        raise EvidenceManifestError(
            "evidence manifest bundle_id must be a canonical UUID"
        ) from exc
    if str(parsed_bundle_id) != raw_bundle_id:
        raise EvidenceManifestError("evidence manifest bundle_id must be a canonical UUID")
    bundle_id = raw_bundle_id
    task_metadata = manifest.get("task")
    profile_metadata = manifest.get("profile")
    environment_metadata = manifest.get("environment")
    trial_rows = manifest.get("trials")
    if not isinstance(task_metadata, dict):
        raise EvidenceManifestError("evidence manifest task must be an object")
    if not isinstance(profile_metadata, dict):
        raise EvidenceManifestError("evidence manifest profile must be an object")
    if not isinstance(environment_metadata, dict):
        raise EvidenceManifestError("evidence manifest environment must be an object")
    if not isinstance(trial_rows, list) or not trial_rows:
        raise EvidenceManifestError("evidence manifest trials must be a non-empty list")
    for label, metadata in (("task", task_metadata), ("profile", profile_metadata)):
        fingerprint = metadata.get("fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise EvidenceManifestError(
                f"evidence manifest {label} fingerprint must be lowercase SHA-256"
            )

    drift: list[Mapping[str, Any]] = []
    task_path = _snapshot_path_with_digest(
        bundle_root,
        task_metadata,
        path_key="snapshot_path",
        digest_key="snapshot_sha256",
        category="task-drift",
        drift=drift,
    )
    grader_path = _snapshot_path_with_digest(
        bundle_root,
        task_metadata,
        path_key="grader_path",
        digest_key="grader_sha256",
        category="grader-drift",
        drift=drift,
    )
    profile_path = _snapshot_path_with_digest(
        bundle_root,
        profile_metadata,
        path_key="snapshot_path",
        digest_key="snapshot_sha256",
        category="profile-drift",
        drift=drift,
    )
    environment_path = _snapshot_path_with_digest(
        bundle_root,
        environment_metadata,
        path_key="snapshot_path",
        digest_key="snapshot_sha256",
        category="environment-drift",
        drift=drift,
    )

    if task_path is not None:
        try:
            task_payload = json.loads(task_path.read_text(encoding="utf-8"))
            if not isinstance(task_payload, dict):
                raise ValueError("task snapshot must be an object")
            task_snapshot = EvalTask.from_dict(task_payload)
            for key in ("task_id", "version", "title", "family", "constraints"):
                if task_metadata.get(key) != task_payload.get(key):
                    raise ValueError(f"task {key} differs from its snapshot")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            drift.append({"category": "task-drift", "message": str(exc)})
    if profile_path is not None:
        try:
            profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
            if not isinstance(profile_payload, dict):
                raise ValueError("profile snapshot must be an object")
            profile_snapshot = SystemProfile.from_dict(profile_payload)
            if profile_metadata.get("fingerprint") != profile_snapshot.fingerprint:
                raise ValueError("profile fingerprint differs from its snapshot")
            expected_profile = profile_snapshot.to_dict(environment={})
            for key, value in expected_profile.items():
                if profile_metadata.get(key) != value:
                    raise ValueError(f"profile {key} differs from its snapshot")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            drift.append({"category": "profile-drift", "message": str(exc)})
    if environment_path is not None:
        try:
            environment_payload = json.loads(environment_path.read_text(encoding="utf-8"))
            if not isinstance(environment_payload, dict):
                raise ValueError("environment snapshot must be an object")
            for key, value in environment_payload.items():
                if environment_metadata.get(key) != value:
                    raise ValueError(f"environment {key} differs from its snapshot")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            drift.append({"category": "environment-drift", "message": str(exc)})

    if check_simulator:
        expected_simulator = environment_metadata.get("mujoco_version")
        observed_simulator = simulator_version or _installed_mujoco_version()
        if not isinstance(expected_simulator, str) or expected_simulator != observed_simulator:
            drift.append(
                {
                    "category": "simulator-drift",
                    "message": "MuJoCo version changed",
                    "expected": expected_simulator,
                    "observed": observed_simulator,
                }
            )

    parsed_trials: list[tuple[Mapping[str, Any], Path, tuple[Artifact, ...]]] = []
    for index, trial in enumerate(trial_rows, start=1):
        if not isinstance(trial, dict):
            drift.append(
                {
                    "category": "missing-raw-evidence",
                    "message": f"trial {index} is not an object",
                }
            )
            continue
        attempt = trial.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt != index:
            drift.append(
                {
                    "category": "manifest-drift",
                    "message": f"trial {index} attempt must equal its one-based bundle position",
                    "expected": index,
                    "observed": attempt,
                }
            )
        trial_id = trial.get("trial_id")
        try:
            parsed_trial_id = uuid.UUID(trial_id) if isinstance(trial_id, str) else None
        except ValueError:
            parsed_trial_id = None
        if parsed_trial_id is None or str(parsed_trial_id) != trial_id:
            drift.append(
                {
                    "category": "manifest-drift",
                    "message": f"trial {index} trial_id must be a canonical UUID",
                }
            )
        expected_identity = {
            "task_id": task_metadata.get("task_id"),
            "task_fingerprint": task_metadata.get("fingerprint"),
            "profile_id": profile_metadata.get("profile_id"),
            "profile_fingerprint": profile_metadata.get("fingerprint"),
            "observable_cost_usd": profile_metadata.get("observable_cost_usd"),
        }
        for key, expected in expected_identity.items():
            if trial.get(key) != expected:
                drift.append(
                    {
                        "category": "manifest-drift",
                        "message": f"trial {index} {key} differs from bundle metadata",
                        "expected": expected,
                        "observed": trial.get(key),
                    }
                )
        transcript_relative = trial.get("transcript_path")
        grades_relative = trial.get("grades_path")
        if not isinstance(transcript_relative, str) or not isinstance(grades_relative, str):
            drift.append(
                {
                    "category": "missing-raw-evidence",
                    "message": f"trial {index} has no transcript or grades path",
                }
            )
            continue
        try:
            transcript_path = resolve_within(bundle_root, transcript_relative)
            evidence_dir = transcript_path.parent
            artifact_dir = resolve_within(evidence_dir, "artifacts")
            grades_path = resolve_within(bundle_root, grades_relative)
        except ValueError as exc:
            drift.append(
                {
                    "category": "missing-raw-evidence",
                    "message": str(exc),
                    "path": transcript_relative,
                }
            )
            continue
        raw_files = (
            (transcript_path, trial.get("transcript_sha256")),
            (grades_path, trial.get("grades_sha256")),
        )
        valid_transcript_file = False
        valid_grades_file = False
        for raw_path, expected_digest in raw_files:
            if not raw_path.is_file() or raw_path.is_symlink():
                drift.append(
                    {
                        "category": "missing-raw-evidence",
                        "message": "required raw evidence is missing",
                        "path": raw_path.relative_to(bundle_root).as_posix(),
                    }
                )
                continue
            observed_digest = sha256_bytes(raw_path.read_bytes())
            if not isinstance(expected_digest, str) or observed_digest != expected_digest:
                drift.append(
                    {
                        "category": "missing-raw-evidence",
                        "message": "raw evidence digest changed",
                        "path": raw_path.relative_to(bundle_root).as_posix(),
                        "expected": expected_digest,
                        "observed": observed_digest,
                    }
                )
                continue
            if raw_path == transcript_path:
                valid_transcript_file = True
            elif raw_path == grades_path:
                valid_grades_file = True
        transcript_payload: Mapping[str, Any] | None = None
        if valid_transcript_file:
            try:
                loaded_transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
                if not isinstance(loaded_transcript, dict):
                    raise ValueError("execution transcript must be an object")
                transcript_payload = loaded_transcript
                for key in ("duration_seconds", "exit_code"):
                    if trial.get(key) != transcript_payload.get(key):
                        raise ValueError(f"trial {key} differs from its transcript")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                drift.append(
                    {
                        "category": "manifest-drift",
                        "message": str(exc),
                        "path": transcript_relative,
                    }
                )
        if valid_grades_file:
            try:
                grades_payload = json.loads(grades_path.read_text(encoding="utf-8"))
                if grades_payload != trial.get("grades"):
                    raise ValueError("saved grades differ from manifest grades")
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                drift.append(
                    {
                        "category": "missing-raw-evidence",
                        "message": str(exc),
                        "path": grades_relative,
                    }
                )
        grade_rows = trial.get("grades")
        trial_state = trial.get("state")
        if not isinstance(grade_rows, list):
            drift.append(
                {
                    "category": "manifest-drift",
                    "message": f"trial {index} grades must be a list",
                }
            )
        elif grade_rows:
            statuses = [
                row.get("status") if isinstance(row, Mapping) else None for row in grade_rows
            ]
            if any(status not in GRADE_STATUSES for status in statuses):
                drift.append(
                    {
                        "category": "manifest-drift",
                        "message": f"trial {index} has an invalid grade status",
                    }
                )
            else:
                expected_state = (
                    "error"
                    if "error" in statuses
                    else "unrun"
                    if "unrun" in statuses
                    else "failed"
                    if "fail" in statuses
                    else "passed"
                )
                if trial_state != expected_state:
                    drift.append(
                        {
                            "category": "manifest-drift",
                            "message": f"trial {index} state differs from protected grades",
                            "expected": expected_state,
                            "observed": trial_state,
                        }
                    )
        else:
            execution_state = transcript_payload.get("state") if transcript_payload else None
            if trial_state in {"passed", "failed"}:
                drift.append(
                    {
                        "category": "manifest-drift",
                        "message": f"trial {index} has a graded state without grades",
                        "observed": trial_state,
                    }
                )
            elif execution_state in {"error", "timeout", "unrun"} and trial_state != execution_state:
                drift.append(
                    {
                        "category": "manifest-drift",
                        "message": f"trial {index} state differs from its transcript",
                        "expected": execution_state,
                        "observed": trial_state,
                    }
                )
        try:
            artifact_rows = trial.get("artifacts")
            if not isinstance(artifact_rows, list):
                raise ValueError("trial artifact manifest must be a list")
            artifacts = tuple(_artifact_from_manifest(row) for row in artifact_rows)
            verify_artifacts(artifact_dir, artifacts)
        except (OSError, ValueError) as exc:
            drift.append(
                {
                    "category": "artifact-drift",
                    "message": str(exc),
                    "attempt": trial.get("attempt", index),
                }
            )
            continue
        if transcript_payload is not None:
            expected_trial_id = str(
                uuid.uuid5(
                    parsed_bundle_id,
                    canonical_json(
                        {
                            "attempt": attempt,
                            "artifacts": artifact_rows,
                            "execution_state": transcript_payload.get("state"),
                        }
                    ),
                )
            )
            if trial_id != expected_trial_id:
                drift.append(
                    {
                        "category": "manifest-drift",
                        "message": f"trial {index} trial_id differs from its source revision",
                        "expected": expected_trial_id,
                        "observed": trial_id,
                    }
                )
        parsed_trials.append((trial, artifact_dir, artifacts))

    return _EvidenceInspection(
        bundle_id=bundle_id,
        manifest=manifest,
        task_path=task_path,
        grader_path=grader_path,
        trials=tuple(parsed_trials),
        drift=tuple(drift),
    )


def load_verified_evidence_manifest(bundle_dir: Path) -> dict[str, Any]:
    """Load a bundle manifest only when every referenced saved byte still matches."""

    inspection = _inspect_evidence_bundle(bundle_dir, check_simulator=False)
    if inspection.drift:
        raise ValueError(
            "evidence bundle drift: "
            + canonical_json({"bundle_id": inspection.bundle_id, "drift": inspection.drift})
        )
    return dict(inspection.manifest)


def replay_evidence_bundle(
    bundle_dir: Path,
    *,
    repeat: int = 1,
    simulator_version: str | None = None,
) -> ReplayResult:
    """Replay protected grading only when every recorded dependency still matches."""

    if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 1:
        raise ValueError("repeat must be positive")
    inspection = _inspect_evidence_bundle(
        bundle_dir,
        check_simulator=True,
        simulator_version=simulator_version,
    )
    bundle_id = inspection.bundle_id
    task_metadata = inspection.manifest["task"]
    task_path = inspection.task_path
    grader_path = inspection.grader_path
    parsed_trials = inspection.trials
    if inspection.drift or task_path is None or grader_path is None:
        return ReplayResult(
            bundle_id=bundle_id,
            state="drift",
            repeat_digests=(),
            identical=False,
            drift=inspection.drift,
        )

    try:
        task_payload = json.loads(task_path.read_text(encoding="utf-8"))
        if not isinstance(task_payload, dict):
            raise ValueError("task snapshot must be an object")
        task_manifest = EvalTask.from_dict(task_payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return ReplayResult(
            bundle_id=bundle_id,
            state="drift",
            repeat_digests=(),
            identical=False,
            drift=({"category": "task-drift", "message": str(exc)},),
        )
    repeat_digests: list[str] = []
    mismatch: list[Mapping[str, Any]] = []
    for replay_index in range(1, repeat + 1):
        with tempfile.TemporaryDirectory(prefix="agent-eval-replay-") as temporary_name:
            temporary_root = Path(temporary_name)
            replay_grader = temporary_root / "grader" / "grader.py"
            _atomic_write_bytes(replay_grader, grader_path.read_bytes())
            replay_task = LoadedTask(
                manifest=task_manifest,
                suite_root=temporary_root,
                public_dir=temporary_root,
                starter_dir=temporary_root,
                grader_path=replay_grader,
                reference_dir=temporary_root,
                seeded_failure_dir=temporary_root,
                fingerprint=str(task_metadata.get("fingerprint", "")),
            )
            outcomes: list[dict[str, Any]] = []
            for trial_index, (trial, artifact_dir, artifacts) in enumerate(
                parsed_trials,
                start=1,
            ):
                replay_artifacts = temporary_root / f"artifacts-{trial_index:03d}"
                copied_artifacts = snapshot_workspace(artifact_dir, replay_artifacts)
                replay_grades = grade_frozen_outcome(
                    replay_task,
                    replay_artifacts,
                    copied_artifacts,
                )
                normalized_grades = [
                    _normalized_replay_grade(grade) for grade in replay_grades
                ]
                original_grades = trial.get("grades")
                if not isinstance(original_grades, list):
                    mismatch.append(
                        {
                            "category": "missing-raw-evidence",
                            "message": "saved normalized grades are missing",
                            "attempt": trial.get("attempt"),
                        }
                    )
                    original_normalized: list[dict[str, Any]] = []
                else:
                    original_normalized = [
                        _normalized_replay_grade(grade) for grade in original_grades
                    ]
                replay_state = _grade_state(replay_grades)
                if replay_state != trial.get("state") or normalized_grades != original_normalized:
                    mismatch.append(
                        {
                            "category": "replay-mismatch",
                            "message": "replayed grades differ from the saved outcome",
                            "attempt": trial.get("attempt"),
                            "repeat": replay_index,
                        }
                    )
                outcomes.append(
                    {
                        "attempt": trial.get("attempt"),
                        "task_id": trial.get("task_id"),
                        "state": replay_state,
                        "grades": normalized_grades,
                    }
                )
            repeat_digests.append(sha256_json(outcomes))

    if len(set(repeat_digests)) != 1:
        mismatch.append(
            {
                "category": "replay-nondeterminism",
                "message": "normalized replay digests differ",
            }
        )
    if mismatch:
        return ReplayResult(
            bundle_id=bundle_id,
            state="drift",
            repeat_digests=tuple(repeat_digests),
            identical=False,
            drift=tuple(mismatch),
        )
    return ReplayResult(
        bundle_id=bundle_id,
        state="passed",
        repeat_digests=tuple(repeat_digests),
        identical=True,
    )


def _comparison_trial_row(value: Mapping[str, Any] | TrialResult) -> dict[str, Any]:
    row = _primitive(value)
    if not isinstance(row, dict):
        raise ValueError("comparison trial must be an object")
    for key in ("task_id", "task_fingerprint", "attempt", "state", "duration_seconds"):
        if key not in row:
            raise ValueError(f"comparison trial missing {key}")
    if row["state"] not in TRIAL_STATES:
        raise ValueError(f"comparison trial has unknown state: {row['state']}")
    if not isinstance(row["attempt"], int) or row["attempt"] < 1:
        raise ValueError("comparison trial attempt must be positive")
    return row


def _profile_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    state_counts = {state: 0 for state in sorted(TRIAL_STATES)}
    for row in rows:
        state_counts[str(row["state"])] += 1
    executed = [row for row in rows if row["state"] != "unrun"]
    passed = sum(row["state"] == "passed" for row in executed)
    task_ids = sorted({str(row["task_id"]) for row in rows})
    first_attempts = {
        str(row["task_id"]): row
        for row in rows
        if int(row["attempt"]) == 1
    }
    pass_at_1 = (
        sum(first_attempts.get(task_id, {}).get("state") == "passed" for task_id in task_ids)
        / len(task_ids)
        if task_ids
        else None
    )
    strict_passes = 0
    for task_id in task_ids:
        attempts = {
            int(row["attempt"]): row["state"]
            for row in rows
            if row["task_id"] == task_id
        }
        if all(attempts.get(attempt) == "passed" for attempt in (1, 2, 3)):
            strict_passes += 1
    costs = [row.get("observable_cost_usd") for row in rows]
    return {
        "trial_count": len(rows),
        "executed_count": len(executed),
        "state_counts": state_counts,
        "pass_rate": passed / len(executed) if executed else None,
        "pass_at_1": pass_at_1,
        "pass_power_3": strict_passes / len(task_ids) if task_ids else None,
        "runtime_seconds": sum(float(row["duration_seconds"]) for row in rows),
        "cost_usd": (
            sum(float(cost) for cost in costs if cost is not None)
            if costs and all(cost is not None for cost in costs)
            else None
        ),
    }


def compare_profile_trials(
    left_profile_id: str,
    right_profile_id: str,
    left_trials: Sequence[Mapping[str, Any] | TrialResult],
    right_trials: Sequence[Mapping[str, Any] | TrialResult],
    *,
    left_profile: Mapping[str, Any] | None = None,
    right_profile: Mapping[str, Any] | None = None,
) -> ComparisonResult:
    """Compare complete profiles without hiding task-level hard states."""

    left_rows = tuple(_comparison_trial_row(row) for row in left_trials)
    right_rows = tuple(_comparison_trial_row(row) for row in right_trials)
    if not left_rows or not right_rows:
        raise ValueError("comparison requires trials for both profiles")

    def index(rows: Sequence[Mapping[str, Any]], side: str) -> dict[tuple[str, int], Mapping[str, Any]]:
        indexed: dict[tuple[str, int], Mapping[str, Any]] = {}
        for row in rows:
            key = (str(row["task_id"]), int(row["attempt"]))
            if key in indexed:
                raise ValueError(f"duplicate {side} trial: {key[0]} attempt {key[1]}")
            indexed[key] = row
        return indexed

    left_index = index(left_rows, "left")
    right_index = index(right_rows, "right")

    def source_revision(
        profile_id: str,
        rows: Sequence[Mapping[str, Any]],
        snapshot: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        row_fingerprints = {
            str(row["profile_fingerprint"])
            for row in rows
            if isinstance(row.get("profile_fingerprint"), str)
        }
        if len(row_fingerprints) > 1:
            raise ValueError(f"incompatible profile revision within profile: {profile_id}")
        snapshot_fingerprint = (snapshot or {}).get("fingerprint")
        if (
            isinstance(snapshot_fingerprint, str)
            and row_fingerprints
            and snapshot_fingerprint not in row_fingerprints
        ):
            raise ValueError(f"profile fingerprint differs from trials: {profile_id}")
        profile_fingerprint = (
            snapshot_fingerprint
            if isinstance(snapshot_fingerprint, str)
            else next(iter(row_fingerprints), None)
        )
        return {
            "profile_id": profile_id,
            "profile_fingerprint": profile_fingerprint,
            "bundle_ids": sorted(
                {
                    str(row["bundle_id"])
                    for row in rows
                    if isinstance(row.get("bundle_id"), str)
                }
            ),
            "environment_sha256": sorted(
                {
                    str(row["environment_sha256"])
                    for row in rows
                    if isinstance(row.get("environment_sha256"), str)
                }
            ),
        }

    source_revisions = {
        "left": source_revision(left_profile_id, left_rows, left_profile),
        "right": source_revision(right_profile_id, right_rows, right_profile),
    }
    task_ids = sorted(
        {task_id for task_id, _ in left_index} | {task_id for task_id, _ in right_index}
    )
    for task_id in task_ids:
        left_fingerprints = {
            str(row["task_fingerprint"])
            for (candidate, _), row in left_index.items()
            if candidate == task_id
        }
        right_fingerprints = {
            str(row["task_fingerprint"])
            for (candidate, _), row in right_index.items()
            if candidate == task_id
        }
        if len(left_fingerprints) > 1 or len(right_fingerprints) > 1:
            raise ValueError(f"incompatible task revision within profile: {task_id}")
        if left_fingerprints and right_fingerprints and left_fingerprints != right_fingerprints:
            raise ValueError(f"incompatible task revision: {task_id}")
    comparison_rows: list[Mapping[str, Any]] = []
    hard_states = {"failed", "error", "timeout"}
    for key in sorted(set(left_index) | set(right_index)):
        left = left_index.get(key)
        right = right_index.get(key)
        left_state = str(left["state"]) if left is not None else "missing"
        right_state = str(right["state"]) if right is not None else "missing"
        if left_state == "passed" and right_state in hard_states:
            classification = "regression"
        elif right_state == "passed" and left_state in hard_states:
            classification = "improvement"
        elif left_state in {"missing", "unrun"} or right_state in {"missing", "unrun"}:
            classification = "incomplete"
        else:
            classification = "unchanged"
        comparison_rows.append(
            {
                "task_id": key[0],
                "task_fingerprint": (
                    str((left or right)["task_fingerprint"])
                ),
                "attempt": key[1],
                "left_state": left_state,
                "right_state": right_state,
                "left_duration_seconds": left.get("duration_seconds") if left else None,
                "right_duration_seconds": right.get("duration_seconds") if right else None,
                "left_cost_usd": left.get("observable_cost_usd") if left else None,
                "right_cost_usd": right.get("observable_cost_usd") if right else None,
                "left_bundle_id": left.get("bundle_id") if left else None,
                "right_bundle_id": right.get("bundle_id") if right else None,
                "left_profile_fingerprint": (
                    left.get("profile_fingerprint") if left else None
                ),
                "right_profile_fingerprint": (
                    right.get("profile_fingerprint") if right else None
                ),
                "left_environment_sha256": (
                    left.get("environment_sha256") if left else None
                ),
                "right_environment_sha256": (
                    right.get("environment_sha256") if right else None
                ),
                "classification": classification,
            }
        )

    def task_hard_state(rows: Sequence[Mapping[str, Any]], task_id: str) -> str:
        states = [row["state"] for row in rows if row["task_id"] == task_id]
        if not states or any(state == "unrun" for state in states):
            return "incomplete"
        if all(state == "passed" for state in states):
            return "passed"
        if any(state in hard_states for state in states):
            return "failed"
        return "incomplete"

    improvements: list[str] = []
    regressions: list[str] = []
    for task_id in task_ids:
        left_state = task_hard_state(left_rows, task_id)
        right_state = task_hard_state(right_rows, task_id)
        if left_state == "failed" and right_state == "passed":
            improvements.append(task_id)
        elif left_state == "passed" and right_state == "failed":
            regressions.append(task_id)
    sample_complete = all(
        sum(row["task_id"] == task_id for row in left_rows) >= 3
        and sum(row["task_id"] == task_id for row in right_rows) >= 3
        for task_id in task_ids
    )
    excluded_components = {
        "profile_id",
        "fingerprint",
        "environment",
        "snapshot_path",
        "snapshot_sha256",
    }
    left_snapshot = dict(left_profile or {})
    right_snapshot = dict(right_profile or {})
    changed_components = sorted(
        key
        for key in (set(left_snapshot) | set(right_snapshot)) - excluded_components
        if left_snapshot.get(key) != right_snapshot.get(key)
    )
    aggregates = {
        "left": _profile_metrics(left_rows),
        "right": _profile_metrics(right_rows),
        "improvements": improvements,
        "regressions": regressions,
        "changed_components": changed_components,
        "sample_complete": sample_complete,
        "no_meaningful_difference": (
            not sample_complete or (not improvements and not regressions)
        ),
    }
    comparison_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            sha256_json(
                {
                    "left_profile": left_profile_id,
                    "right_profile": right_profile_id,
                    "source_revisions": source_revisions,
                    "trial_rows": comparison_rows,
                    "aggregates": aggregates,
                }
            ),
        )
    )
    return ComparisonResult(
        comparison_id=comparison_id,
        left_profile=left_profile_id,
        right_profile=right_profile_id,
        source_revisions=source_revisions,
        trial_rows=tuple(comparison_rows),
        aggregates=aggregates,
    )


__all__ = [
    "Artifact",
    "ComparisonResult",
    "CapturedExecution",
    "CodexTranscript",
    "EvalTask",
    "EvidenceManifestError",
    "EvidenceBundle",
    "ExecutionResult",
    "GradeResult",
    "LoadedSuite",
    "LoadedTask",
    "OracleValidation",
    "ReplayResult",
    "SystemProfile",
    "TrialResult",
    "atomic_write_json",
    "canonical_json",
    "capture_profile_execution",
    "load_profiles",
    "load_suite",
    "load_verified_evidence_manifest",
    "profile_availability",
    "replay_evidence_bundle",
    "parse_codex_jsonl",
    "run_sandboxed",
    "resolve_within",
    "sha256_bytes",
    "sha256_json",
    "snapshot_workspace",
    "execute_profile",
    "grade_frozen_outcome",
    "finalize_evidence_bundle",
    "compare_profile_trials",
    "validate_workspace_location",
    "verify_artifacts",
    "write_execution_transcript",
    "validate_task_oracles",
]
