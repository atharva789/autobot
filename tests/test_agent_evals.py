from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import jsonschema
from click.testing import CliRunner


def _agent_evals():
    spec = importlib.util.find_spec("packages.research.agent_evals")
    assert spec is not None, "packages.research.agent_evals is not implemented"
    return importlib.import_module("packages.research.agent_evals")


def _task_payload() -> dict[str, object]:
    return {
        "task_id": "joint-repair",
        "version": 1,
        "title": "Repair a joint",
        "family": "repair",
        "prompt": "Repair robot.json.",
        "starter_dir": "public/starter",
        "required_outputs": ["robot.json"],
        "allowed_tools": ["python"],
        "constraints": [
            {
                "constraint_id": "joint-axis-norm",
                "quantity": "axis norm",
                "operator": "==",
                "value": 1.0,
                "unit": "dimensionless",
            }
        ],
        "time_limit_seconds": 60,
        "grader_entrypoint": "protected/grader.py",
        "reference_dir": "protected/reference",
        "seeded_failure_dir": "protected/seeded_failure",
        "seeded_failure_grade_id": "joint-parent",
    }


def _profile_payload() -> dict[str, object]:
    return {
        "profile_id": "codex-baseline",
        "harness": "codex",
        "model_id": "same-model",
        "command": ["codex", "exec", "-"],
        "instructions": "",
        "skills": [],
        "mcps": [],
        "tools": ["shell", "edit"],
        "environment_keys": ["API_TOKEN"],
        "time_limit_seconds": 60,
        "observable_cost_usd": None,
    }


def _write_single_task_suite(
    root: Path,
    *,
    profile_id: str,
    command: list[str],
    time_limit_seconds: int = 2,
) -> Path:
    public = root / "tasks" / "joint-repair" / "public"
    starter = public / "starter"
    starter.mkdir(parents=True)
    (starter / "robot.txt").write_text("starter")
    payload = _task_payload()
    payload.update(
        {
            "starter_dir": "starter",
            "required_outputs": ["robot.txt"],
            "grader_entrypoint": "protected/joint-repair/grader.py",
            "reference_dir": "protected/joint-repair/reference",
            "seeded_failure_dir": "protected/joint-repair/seeded_failure",
        }
    )
    (public / "task.json").write_text(json.dumps(payload))
    protected = root / "protected" / "joint-repair"
    reference = protected / "reference"
    seeded = protected / "seeded_failure"
    reference.mkdir(parents=True)
    seeded.mkdir()
    (reference / "robot.txt").write_text("reference")
    (seeded / "robot.txt").write_text("seeded failure")
    (protected / "grader.py").write_text(
        "def grade(workspace):\n"
        "    passed = (workspace / 'robot.txt').read_text() == 'reference'\n"
        "    return [{'grade_id': 'joint-parent', 'category': 'structural', "
        "'status': 'pass' if passed else 'fail', 'assertion': 'reference bytes'}]\n"
    )
    profiles = root / "profiles"
    profiles.mkdir()
    profile = _profile_payload()
    profile.update(
        {
            "profile_id": profile_id,
            "harness": "command",
            "model_id": "python-fixture",
            "command": command,
            "instructions": "work only in the visible workspace",
            "environment_keys": [],
            "time_limit_seconds": time_limit_seconds,
        }
    )
    (profiles / f"{profile_id}.json").write_text(json.dumps(profile))
    return root


def test_task_fingerprint_is_canonical() -> None:
    module = _agent_evals()
    payload = _task_payload()
    reversed_payload = dict(reversed(list(payload.items())))

    left = module.EvalTask.from_dict(payload)
    right = module.EvalTask.from_dict(reversed_payload)

    assert left.fingerprint == right.fingerprint
    assert len(left.fingerprint) == 64


def test_profile_manifest_omits_secret_values() -> None:
    module = _agent_evals()
    profile = module.SystemProfile.from_dict(_profile_payload())

    manifest = profile.to_dict(environment={"API_TOKEN": "super-secret"})

    encoded = json.dumps(manifest, sort_keys=True)
    assert "super-secret" not in encoded
    assert manifest["environment"] == {"API_TOKEN": {"present": True}}


def test_profile_manifest_rejects_unknown_fields() -> None:
    module = _agent_evals()
    payload = _profile_payload()
    payload["secret"] = "must not be silently accepted"

    with pytest.raises(ValueError, match="unknown profile fields"):
        module.SystemProfile.from_dict(payload)


def test_profile_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    module = _agent_evals()
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    payload = _profile_payload()
    (profiles / "first.json").write_text(json.dumps(payload))
    (profiles / "second.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="duplicate profile_id"):
        module.load_profiles(tmp_path)


def test_artifact_manifest_hashes_file_bytes(tmp_path: Path) -> None:
    module = _agent_evals()
    artifact_path = tmp_path / "robot.xml"
    artifact_path.write_bytes(b"<mujoco/>")

    artifact = module.Artifact.from_path(tmp_path, artifact_path)

    assert artifact.path == "robot.xml"
    assert artifact.size_bytes == len(b"<mujoco/>")
    assert artifact.sha256 == module.sha256_bytes(b"<mujoco/>")


@pytest.mark.parametrize("status", ["pass", "fail", "error", "unrun"])
def test_grade_accepts_only_contract_statuses(status: str) -> None:
    module = _agent_evals()

    grade = module.GradeResult(
        grade_id="load",
        category="simulator-load",
        status=status,
        assertion="model loads",
    )

    assert grade.status == status


def test_grade_rejects_unknown_status() -> None:
    module = _agent_evals()

    with pytest.raises(ValueError, match="grade status"):
        module.GradeResult(
            grade_id="load",
            category="simulator-load",
            status="maybe",
            assertion="model loads",
        )


def test_grade_rejects_unknown_category() -> None:
    module = _agent_evals()

    with pytest.raises(ValueError, match="grade category"):
        module.GradeResult(
            grade_id="load",
            category="simulator_load",
            status="pass",
            assertion="model loads",
        )


@pytest.mark.parametrize("state", ["passed", "failed", "error", "timeout", "unrun"])
def test_trial_accepts_only_contract_states(state: str) -> None:
    module = _agent_evals()

    trial = module.TrialResult(
        trial_id="00000000-0000-0000-0000-000000000000",
        task_id="joint-repair",
        task_fingerprint="a" * 64,
        profile_id="codex-baseline",
        profile_fingerprint="b" * 64,
        attempt=1,
        state=state,
    )

    assert trial.state == state


def test_trial_records_are_frozen() -> None:
    module = _agent_evals()
    trial = module.TrialResult(
        trial_id="00000000-0000-0000-0000-000000000000",
        task_id="joint-repair",
        task_fingerprint="a" * 64,
        profile_id="codex-baseline",
        profile_fingerprint="b" * 64,
        attempt=1,
        state="unrun",
    )

    with pytest.raises(FrozenInstanceError):
        trial.state = "passed"


def test_relative_path_rejects_parent_traversal(tmp_path: Path) -> None:
    module = _agent_evals()

    with pytest.raises(ValueError, match="escapes"):
        module.resolve_within(tmp_path, "../secret.txt")


def test_snapshot_rejects_symlinks(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    destination = tmp_path / "snapshot"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    os.symlink(outside, source / "robot.xml")

    with pytest.raises(ValueError, match="symlink"):
        module.snapshot_workspace(source, destination)


def test_snapshot_rejects_hard_links_that_can_smuggle_protected_bytes(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    protected = tmp_path / "protected-answer.txt"
    protected.write_text("answer key")
    os.link(protected, source / "robot.txt")

    with pytest.raises(ValueError, match="hard link"):
        module.snapshot_workspace(source, tmp_path / "snapshot")


def test_snapshot_rejects_non_regular_files(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    os.mkfifo(source / "agent-created-pipe")

    with pytest.raises(ValueError, match="non-regular"):
        module.snapshot_workspace(source, tmp_path / "snapshot")


def test_artifact_verification_detects_post_snapshot_mutation(tmp_path: Path) -> None:
    module = _agent_evals()
    artifact_path = tmp_path / "robot.xml"
    artifact_path.write_text("<mujoco/>")
    artifact = module.Artifact.from_path(tmp_path, artifact_path)
    artifact_path.write_text("<mujoco model='changed'/>")

    with pytest.raises(ValueError, match="artifact drift"):
        module.verify_artifacts(tmp_path, (artifact,))


def test_workspace_must_not_overlap_denied_root(tmp_path: Path) -> None:
    module = _agent_evals()
    denied = tmp_path / "repo"
    workspace = denied / "trial"
    workspace.mkdir(parents=True)

    with pytest.raises(ValueError, match="denied root"):
        module.validate_workspace_location(workspace, (denied,))


def test_manifest_write_is_canonical_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    module = _agent_evals()
    target = tmp_path / "manifest.json"

    module.atomic_write_json(target, {"z": 2, "a": 1})

    assert target.read_text() == module.canonical_json({"a": 1, "z": 2}) + "\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_task_manifest_rejects_unknown_fields() -> None:
    module = _agent_evals()
    payload = _task_payload()
    payload["mystery"] = "silently ignored"

    with pytest.raises(ValueError, match="unknown task fields"):
        module.EvalTask.from_dict(payload)


def test_task_manifest_requires_constraint_units() -> None:
    module = _agent_evals()
    payload = _task_payload()
    payload["constraints"][0]["unit"] = ""

    with pytest.raises(ValueError, match="unit"):
        module.EvalTask.from_dict(payload)


def test_suite_rejects_duplicate_task_ids(tmp_path: Path) -> None:
    module = _agent_evals()
    suite = tmp_path / "suite"
    for directory_name in ("first", "second"):
        public = suite / "tasks" / directory_name / "public"
        public.mkdir(parents=True)
        payload = _task_payload()
        payload["starter_dir"] = "starter"
        payload["grader_entrypoint"] = "protected/joint-repair/grader.py"
        payload["reference_dir"] = "protected/joint-repair/reference"
        payload["seeded_failure_dir"] = "protected/joint-repair/seeded_failure"
        (public / "task.json").write_text(json.dumps(payload))
        (public / "starter").mkdir()
    protected = suite / "protected" / "joint-repair"
    (protected / "reference").mkdir(parents=True)
    (protected / "seeded_failure").mkdir()
    (protected / "grader.py").write_text("def grade(workspace): return []\n")

    with pytest.raises(ValueError, match="duplicate task_id"):
        module.load_suite(suite)


def test_suite_rejects_missing_protected_reference(tmp_path: Path) -> None:
    module = _agent_evals()
    suite = tmp_path / "suite"
    public = suite / "tasks" / "joint-repair" / "public"
    public.mkdir(parents=True)
    payload = _task_payload()
    payload["starter_dir"] = "starter"
    payload["grader_entrypoint"] = "protected/joint-repair/grader.py"
    payload["reference_dir"] = "protected/joint-repair/reference"
    payload["seeded_failure_dir"] = "protected/joint-repair/seeded_failure"
    (public / "task.json").write_text(json.dumps(payload))
    (public / "starter").mkdir()
    protected = suite / "protected" / "joint-repair"
    protected.mkdir(parents=True)
    (protected / "seeded_failure").mkdir()
    (protected / "grader.py").write_text("def grade(workspace): return []\n")

    with pytest.raises(ValueError, match="reference"):
        module.load_suite(suite)


EXPECTED_TASK_IDS = {
    "ir-missing-parent",
    "ir-orphan-payload",
    "mjcf-payload-inertia",
    "mjcf-actuator-contract",
    "arm-reach-target",
    "payload-vertical-lift",
}
EXPECTED_PROFILE_IDS = {
    "reference",
    "seeded-failure",
    "codex-baseline",
    "codex-robotics-context",
}


def test_real_suite_contains_exactly_six_tasks() -> None:
    module = _agent_evals()
    suite = Path(__file__).parents[1] / "evals" / "robot_design"

    loaded = module.load_suite(suite)

    assert {task.manifest.task_id for task in loaded.tasks} == EXPECTED_TASK_IDS


def test_every_published_task_manifest_conforms_to_the_exported_schema() -> None:
    repository = Path(__file__).parents[1]
    suite_root = repository / "evals" / "robot_design"
    schema = json.loads(
        (
            repository
            / "specs"
            / "011-b2b-feasibility-evidence"
            / "contracts"
            / "eval-task.schema.json"
        ).read_text()
    )
    validator = jsonschema.Draft202012Validator(schema)

    for manifest_path in sorted(suite_root.glob("tasks/*/public/task.json")):
        validator.validate(json.loads(manifest_path.read_text()))


def test_exported_task_and_profile_schemas_require_the_runtime_contract_fields() -> None:
    module = _agent_evals()
    contracts = (
        Path(__file__).parents[1]
        / "specs"
        / "011-b2b-feasibility-evidence"
        / "contracts"
    )
    task_schema = json.loads((contracts / "eval-task.schema.json").read_text())
    profile_schema = json.loads((contracts / "system-profile.schema.json").read_text())

    assert set(task_schema["required"]) == module.TASK_FIELDS
    assert set(profile_schema["required"]) == module.PROFILE_FIELDS


def test_real_suite_contains_two_fixtures_and_two_controlled_codex_profiles() -> None:
    module = _agent_evals()
    suite = Path(__file__).parents[1] / "evals" / "robot_design"

    profiles = {profile.profile_id: profile for profile in module.load_profiles(suite)}

    assert set(profiles) == EXPECTED_PROFILE_IDS
    assert profiles["reference"].harness == "fixture-reference"
    assert profiles["seeded-failure"].harness == "fixture-seeded-failure"
    baseline = profiles["codex-baseline"]
    treatment = profiles["codex-robotics-context"]
    assert baseline.harness == treatment.harness == "codex"
    assert baseline.model_id == treatment.model_id
    assert baseline.command == treatment.command
    assert baseline.skills == treatment.skills == ()
    assert baseline.mcps == treatment.mcps == ()
    assert baseline.tools == treatment.tools
    assert baseline.time_limit_seconds == treatment.time_limit_seconds
    assert baseline.instructions != treatment.instructions
    assert "robotics" not in baseline.instructions.lower()
    assert "robotics" in treatment.instructions.lower()
    assert Path(baseline.command[0]).is_absolute()
    assert baseline.command[1:4] == ("exec", "--json", "--ephemeral")
    assert "--ignore-user-config" in baseline.command
    assert "--ignore-rules" in baseline.command
    assert "--strict-config" in baseline.command
    assert "--sandbox" in baseline.command
    assert baseline.command[-1] == "-"


@pytest.mark.parametrize("task_id", sorted(EXPECTED_TASK_IDS))
def test_task_reference_passes_and_seeded_failure_is_caught(task_id: str) -> None:
    module = _agent_evals()
    suite = module.load_suite(Path(__file__).parents[1] / "evals" / "robot_design")
    task = suite.task(task_id)

    validation = module.validate_task_oracles(task)

    assert validation.reference_state == "passed"
    assert validation.seeded_failure_state == "failed"
    assert task.manifest.seeded_failure_grade_id in validation.failed_grade_ids


def test_cli_lists_tasks_without_protected_paths() -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    result = CliRunner().invoke(
        cli,
        ["eval-tasks-list", "--suite", str(suite), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert {row["task_id"] for row in payload["tasks"]} == EXPECTED_TASK_IDS
    assert "protected" not in result.output

    human = CliRunner().invoke(cli, ["eval-tasks-list", "--suite", str(suite)])
    assert human.exit_code == 0, human.output
    assert "arm-reach-target v1 [executed-behavior]" in human.output
    assert "protected" not in human.output


def test_cli_verifies_reference_and_seeded_oracles() -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    result = CliRunner().invoke(
        cli,
        ["eval-verify-suite", "--suite", str(suite), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task_count"] == 6
    assert payload["reference_passes"] == 6
    assert payload["seeded_failures_caught"] == 6

    human = CliRunner().invoke(cli, ["eval-verify-suite", "--suite", str(suite)])
    assert human.exit_code == 0, human.output
    assert "Validated 6 tasks: references=6 seeded_failures=6" in human.output


def test_cli_lists_profiles_in_json_and_human_forms(tmp_path: Path) -> None:
    from packages.research.cli import cli

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    payload = _profile_payload()
    payload["harness"] = "fixture-reference"
    payload["model_id"] = "fixture"
    payload["command"] = []
    payload["environment_keys"] = []
    (profiles / "reference.json").write_text(json.dumps(payload))

    json_result = CliRunner().invoke(
        cli,
        ["eval-profiles-list", "--suite", str(tmp_path), "--json"],
    )
    human_result = CliRunner().invoke(
        cli,
        ["eval-profiles-list", "--suite", str(tmp_path)],
    )

    assert json_result.exit_code == 0, json_result.output
    rows = json.loads(json_result.output)["profiles"]
    assert rows == [
        {
            "available": True,
            "availability_reason": None,
            "fingerprint": rows[0]["fingerprint"],
            "harness": "fixture-reference",
            "mcps": [],
            "model_id": "fixture",
            "profile_id": "codex-baseline",
            "skills": [],
            "tools": ["shell", "edit"],
        }
    ]
    assert len(rows[0]["fingerprint"]) == 64
    assert human_result.exit_code == 0, human_result.output
    assert "codex-baseline [fixture-reference] fixture available" in human_result.output


def test_real_sandbox_allows_workspace_and_denies_every_sensitive_root(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    repository = tmp_path / "repository"
    protected = repository / "evals" / "protected"
    prior_trial = tmp_path / "prior-trial"
    result_root = tmp_path / "results"
    other_workspace = tmp_path / "other-workspace"
    workspace = tmp_path / "current-workspace"
    for root in (protected, prior_trial, result_root, other_workspace, workspace):
        root.mkdir(parents=True)
    sentinels = {
        "repository": repository / "repository-secret.txt",
        "protected": protected / "answer-key.txt",
        "prior_trial": prior_trial / "prior-secret.txt",
        "result_root": result_root / "result-secret.txt",
        "other_workspace": other_workspace / "other-secret.txt",
    }
    for name, path in sentinels.items():
        path.write_text(name)
    probe_script = """
import json
import pathlib
import sys

results = {}
for item in sys.argv[1:]:
    name, raw_path = item.split("=", 1)
    path = pathlib.Path(raw_path)
    try:
        path.read_text()
    except OSError as exc:
        read_state = f"denied:{exc.errno}"
    else:
        read_state = "readable"
    try:
        (path.parent / f"created-by-agent-{name}.txt").write_text("escaped")
    except OSError as exc:
        write_state = f"denied:{exc.errno}"
    else:
        write_state = "writable"
    results[name] = {"read": read_state, "write": write_state}
pathlib.Path("workspace-output.txt").write_text("allowed")
print(json.dumps(results, sort_keys=True))
"""

    result = module.run_sandboxed(
        (sys.executable, "-c", probe_script, *(f"{name}={path}" for name, path in sentinels.items())),
        cwd=workspace,
        stdin_text="",
        denied_roots=(repository, prior_trial, result_root, other_workspace),
        timeout_seconds=10,
    )

    assert result.state == "completed", result.stderr
    assert result.exit_code == 0
    assert (workspace / "workspace-output.txt").read_text() == "allowed"
    probes = json.loads(result.stdout)
    assert set(probes) == set(sentinels)
    assert all(row["read"].startswith("denied:") for row in probes.values())
    assert all(row["write"].startswith("denied:") for row in probes.values())
    assert all(path.read_text() == name for name, path in sentinels.items())
    assert not list(tmp_path.rglob("created-by-agent-*.txt"))


def test_sandbox_parameters_do_not_allow_profile_injection(tmp_path: Path) -> None:
    module = _agent_evals()
    denied = tmp_path / 'denied ") (allow file-read*) (literal "'
    workspace = tmp_path / "workspace"
    denied.mkdir()
    workspace.mkdir()
    sentinel = denied / "secret.txt"
    sentinel.write_text("secret")
    script = """
import pathlib
import sys
try:
    pathlib.Path(sys.argv[1]).read_text()
except OSError:
    print("denied")
else:
    print("readable")
"""

    result = module.run_sandboxed(
        (sys.executable, "-c", script, str(sentinel)),
        cwd=workspace,
        stdin_text="",
        denied_roots=(denied,),
        timeout_seconds=10,
    )

    assert result.state == "completed", result
    assert result.stdout.strip() == "denied"


def test_sandbox_denies_writes_everywhere_outside_workspace(tmp_path: Path) -> None:
    module = _agent_evals()
    workspace = tmp_path / "workspace"
    unrelated_host_directory = tmp_path / "unrelated-host-directory"
    workspace.mkdir()
    unrelated_host_directory.mkdir()
    escaped = unrelated_host_directory / "agent-write.txt"
    script = """
import pathlib
import sys
try:
    pathlib.Path(sys.argv[1]).write_text("escaped")
except OSError as exc:
    print(f"denied:{exc.errno}")
else:
    print("writable")
"""

    result = module.run_sandboxed(
        (sys.executable, "-c", script, str(escaped)),
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=10,
    )

    assert result.state == "completed", result
    assert result.stdout.strip().startswith("denied:")
    assert not escaped.exists()


def test_sandbox_denial_survives_aliases_metadata_mutation_and_descendants(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    protected = tmp_path / "protected"
    workspace = tmp_path / "workspace"
    protected.mkdir()
    workspace.mkdir()
    sentinel = protected / "secret.txt"
    sentinel.write_text("secret")
    script = """
import json
import os
import pathlib
import subprocess
import sys

sentinel = pathlib.Path(sys.argv[1])
alias = pathlib.Path("alias-to-protected")
alias.symlink_to(sentinel)
results = {}

def probe(name, operation):
    try:
        operation()
    except OSError as exc:
        results[name] = f"denied:{exc.errno}"
    else:
        results[name] = "allowed"

probe("read", sentinel.read_text)
probe("stat", sentinel.stat)
probe("list", lambda: list(sentinel.parent.iterdir()))
probe("append", lambda: sentinel.open("a").write("changed"))
probe("unlink", sentinel.unlink)
probe("rename", lambda: sentinel.rename(pathlib.Path("stolen.txt")))
probe("symlink-read", alias.read_text)
probe("hard-link", lambda: os.link(sentinel, pathlib.Path("hard-link")))
traversal = pathlib.Path.cwd() / ".." / "protected" / "secret.txt"
probe("traversal", traversal.read_text)
child = subprocess.run(
    [
        sys.executable,
        "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()",
        str(sentinel),
    ],
    text=True,
    capture_output=True,
    check=False,
)
results["descendant"] = "denied" if child.returncode != 0 else "allowed"
print(json.dumps(results, sort_keys=True))
"""

    result = module.run_sandboxed(
        (sys.executable, "-c", script, str(sentinel)),
        cwd=workspace,
        stdin_text="",
        denied_roots=(protected,),
        timeout_seconds=10,
    )

    assert result.state == "completed", result.stderr
    probes = json.loads(result.stdout)
    assert probes["descendant"] == "denied"
    assert all(
        outcome.startswith("denied:")
        for name, outcome in probes.items()
        if name != "descendant"
    )
    assert sentinel.read_text() == "secret"
    assert not (workspace / "hard-link").exists()


def test_installed_codex_runtime_starts_inside_strict_outer_sandbox(tmp_path: Path) -> None:
    module = _agent_evals()
    repository = Path(__file__).parents[1]
    profiles = {profile.profile_id: profile for profile in module.load_profiles(repository / "evals" / "robot_design")}
    codex = profiles["codex-baseline"].command[0]
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = module.run_sandboxed(
        (codex, "--version"),
        cwd=workspace,
        stdin_text="",
        denied_roots=(repository,),
        timeout_seconds=20,
        environment={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        },
        allow_network=True,
    )

    assert result.state == "completed", result.stderr
    assert result.stdout.startswith("codex-cli 0.144.5")


def test_codex_compatibility_sandbox_still_denies_enumerated_protected_roots(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    protected = tmp_path / "protected"
    workspace = tmp_path / "workspace"
    protected.mkdir()
    workspace.mkdir()
    sentinel = protected / "answer-key.txt"
    sentinel.write_text("secret")
    script = """
import pathlib
import sys
try:
    pathlib.Path(sys.argv[1]).read_text()
except OSError as exc:
    print(f"denied:{exc.errno}")
else:
    print("readable")
"""

    result = module.run_sandboxed(
        (sys.executable, "-c", script, str(sentinel)),
        cwd=workspace,
        stdin_text="",
        denied_roots=(protected,),
        timeout_seconds=10,
        compatibility_mode=True,
    )

    assert result.state == "completed", result.stderr
    assert result.stdout.strip().startswith("denied:")


def test_sandbox_rejects_workspace_overlapping_denied_root(tmp_path: Path) -> None:
    module = _agent_evals()
    repository = tmp_path / "repository"
    workspace = repository / "trial"
    workspace.mkdir(parents=True)

    with pytest.raises(ValueError, match="denied root"):
        module.run_sandboxed(
            (sys.executable, "-c", "print('should not run')"),
            cwd=workspace,
            stdin_text="",
            denied_roots=(repository,),
            timeout_seconds=10,
        )


def test_sandbox_records_exact_argv_and_transcript(tmp_path: Path) -> None:
    module = _agent_evals()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = (sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)")

    result = module.run_sandboxed(
        command,
        cwd=workspace,
        stdin_text="visible prompt",
        denied_roots=(),
        timeout_seconds=10,
    )
    transcript = tmp_path / "transcript.json"
    module.write_execution_transcript(result, transcript)

    assert result.state == "completed"
    assert result.command == (str(Path(command[0]).resolve()), *command[1:])
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"
    saved = json.loads(transcript.read_text())
    assert saved["command"] == [str(Path(command[0]).resolve()), *command[1:]]
    assert saved["stdout"] == "out\n"
    assert saved["stderr"] == "err\n"


def test_low_level_sandbox_default_does_not_inherit_ambient_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _agent_evals()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("AGENT_EVAL_AMBIENT_CANARY", "must-not-leak")

    result = module.run_sandboxed(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('AGENT_EVAL_AMBIENT_CANARY', 'absent'))",
        ],
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=5,
    )

    assert result.state == "completed", result.stderr
    assert result.stdout == "absent\n"


def test_sandbox_distinguishes_timeout_dependency_permission_and_nonzero(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    non_executable = tmp_path / "not-executable"
    non_executable.write_text("#!/bin/sh\nexit 0\n")

    timed_out = module.run_sandboxed(
        (sys.executable, "-c", "import time; time.sleep(2)"),
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=0.05,
    )
    missing = module.run_sandboxed(
        ("definitely-not-an-installed-agent-evals-command",),
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=1,
    )
    permission = module.run_sandboxed(
        (str(non_executable),),
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=1,
    )
    nonzero = module.run_sandboxed(
        (sys.executable, "-c", "import sys; sys.exit(17)"),
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=1,
    )

    assert timed_out.state == "timeout"
    assert timed_out.error["category"] == "timeout"
    assert missing.state == "unrun"
    assert missing.error["category"] == "dependency"
    assert permission.state == "error"
    assert permission.error["category"] == "permission"
    assert nonzero.state == "error"
    assert nonzero.exit_code == 17
    assert nonzero.error["category"] == "nonzero-exit"


def test_timeout_terminates_the_entire_child_process_group(tmp_path: Path) -> None:
    module = _agent_evals()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    escaped_write = workspace / "descendant-survived.txt"
    parent_script = """
import subprocess
import sys
import time

subprocess.Popen(
    [
        sys.executable,
        "-c",
        "import pathlib,sys,time; time.sleep(0.2); pathlib.Path(sys.argv[1]).write_text('escaped')",
        sys.argv[1],
    ]
)
time.sleep(5)
"""

    result = module.run_sandboxed(
        (sys.executable, "-c", parent_script, str(escaped_write)),
        cwd=workspace,
        stdin_text="",
        denied_roots=(),
        timeout_seconds=0.05,
    )
    time.sleep(0.4)

    assert result.state == "timeout"
    assert not escaped_write.exists()


def test_fixture_and_live_profiles_use_clean_independent_workspaces(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    (source / "robot.txt").write_text("starter")
    fixture_workspace = tmp_path / "fixture-workspace"
    live_workspace = tmp_path / "live-workspace"
    fixture_payload = _profile_payload()
    fixture_payload.update(
        {
            "profile_id": "reference",
            "harness": "fixture-reference",
            "model_id": "fixture",
            "command": [],
            "environment_keys": [],
        }
    )
    live_payload = _profile_payload()
    live_payload.update(
        {
            "profile_id": "local-command",
            "harness": "command",
            "model_id": "python-fixture",
            "command": [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('robot.txt').write_text('live')",
            ],
            "instructions": "Use the visible task only.",
            "environment_keys": [],
        }
    )

    fixture = module.execute_profile(
        module.SystemProfile.from_dict(fixture_payload),
        source,
        fixture_workspace,
        prompt="repair the robot",
        denied_roots=(),
    )
    live = module.execute_profile(
        module.SystemProfile.from_dict(live_payload),
        source,
        live_workspace,
        prompt="repair the robot",
        denied_roots=(),
    )

    assert fixture.mode == "fixture"
    assert fixture.state == "completed"
    assert fixture.command == ()
    assert (fixture_workspace / "robot.txt").read_text() == "starter"
    assert live.mode == "live"
    assert live.state == "completed"
    assert (live_workspace / "robot.txt").read_text() == "live"
    assert (source / "robot.txt").read_text() == "starter"


def test_live_profile_receives_only_declared_environment_values(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    workspace = tmp_path / "workspace"
    payload = _profile_payload()
    payload.update(
        {
            "profile_id": "environment-probe",
            "harness": "command",
            "model_id": "python-fixture",
            "command": [
                sys.executable,
                "-c",
                "import json,os; print(json.dumps(dict(os.environ), sort_keys=True))",
            ],
            "environment_keys": ["DECLARED_AGENT_TOKEN"],
        }
    )

    result = module.execute_profile(
        module.SystemProfile.from_dict(payload),
        source,
        workspace,
        prompt="inspect only the workspace",
        denied_roots=(),
        environment={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "DECLARED_AGENT_TOKEN": "allowed-value",
            "UNDECLARED_HOST_SECRET": "must-not-leak",
        },
    )

    assert result.state == "completed", result
    child_environment = json.loads(result.stdout)
    assert child_environment["DECLARED_AGENT_TOKEN"] == "allowed-value"
    assert "UNDECLARED_HOST_SECRET" not in child_environment
    assert Path(child_environment["TMPDIR"]).resolve() == workspace.resolve()


def test_capture_freezes_final_artifacts_writes_transcript_and_removes_workspace(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    (source / "robot.txt").write_text("starter")
    workspace_parent = tmp_path / "workspaces"
    workspace_parent.mkdir()
    evidence_dir = tmp_path / "evidence" / "trial-1"
    payload = _profile_payload()
    payload.update(
        {
            "profile_id": "capture-probe",
            "harness": "command",
            "model_id": "python-fixture",
            "command": [
                sys.executable,
                "-c",
                "import sys; from pathlib import Path; Path('robot.txt').write_text(sys.stdin.read())",
            ],
            "instructions": "profile instructions",
            "environment_keys": [],
        }
    )

    capture = module.capture_profile_execution(
        module.SystemProfile.from_dict(payload),
        source,
        prompt="visible task",
        workspace_parent=workspace_parent,
        evidence_dir=evidence_dir,
        denied_roots=(),
    )

    assert capture.execution.state == "completed", capture.execution
    assert capture.recovery_workspace_path is None
    assert list(workspace_parent.iterdir()) == []
    assert (evidence_dir / "artifacts" / "robot.txt").read_text() == (
        "profile instructions\n\nvisible task"
    )
    assert capture.artifacts == (
        module.Artifact.from_path(evidence_dir / "artifacts", evidence_dir / "artifacts" / "robot.txt"),
    )
    module.verify_artifacts(evidence_dir / "artifacts", capture.artifacts)
    transcript = json.loads((evidence_dir / "transcript.json").read_text())
    assert transcript["state"] == "completed"
    assert transcript["command"] == [
        str(Path(payload["command"][0]).resolve()),
        *payload["command"][1:],
    ]


def test_capture_preserves_workspace_when_final_freeze_is_unsafe(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    (source / "robot.txt").write_text("starter")
    workspace_parent = tmp_path / "workspaces"
    workspace_parent.mkdir()
    evidence_dir = tmp_path / "evidence" / "trial-unsafe"
    payload = _profile_payload()
    payload.update(
        {
            "profile_id": "unsafe-output-probe",
            "harness": "command",
            "model_id": "python-fixture",
            "command": [
                sys.executable,
                "-c",
                "import os; os.symlink('robot.txt', 'agent-link')",
            ],
            "environment_keys": [],
        }
    )

    capture = module.capture_profile_execution(
        module.SystemProfile.from_dict(payload),
        source,
        prompt="visible task",
        workspace_parent=workspace_parent,
        evidence_dir=evidence_dir,
        denied_roots=(),
    )

    assert capture.execution.state == "error"
    assert capture.execution.error["category"] == "artifact-freeze"
    assert capture.artifacts == ()
    assert capture.recovery_workspace_path is not None
    assert capture.recovery_workspace_path.is_dir()
    assert (capture.recovery_workspace_path / "agent-link").is_symlink()


def test_codex_jsonl_parser_preserves_events_and_terminal_evidence() -> None:
    module = _agent_evals()
    raw = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-123"}),
            json.dumps({"type": "future.unknown", "payload": {"kept": True}}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "finished"},
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 10, "output_tokens": 4},
                }
            ),
        ]
    )

    transcript = module.parse_codex_jsonl(raw)

    assert transcript.state == "completed"
    assert transcript.thread_id == "thread-123"
    assert transcript.final_message == "finished"
    assert transcript.usage == {"input_tokens": 10, "output_tokens": 4}
    assert transcript.events[1]["type"] == "future.unknown"
    assert transcript.error is None


def test_codex_jsonl_parser_marks_malformed_or_incomplete_streams() -> None:
    module = _agent_evals()

    malformed = module.parse_codex_jsonl('{"type":"thread.started"}\nnot-json\n')
    incomplete = module.parse_codex_jsonl(
        json.dumps({"type": "thread.started", "thread_id": "thread-123"})
    )

    assert malformed.state == "error"
    assert malformed.error["category"] == "transcript-protocol"
    assert malformed.raw == '{"type":"thread.started"}\nnot-json\n'
    assert incomplete.state == "error"
    assert incomplete.error["category"] == "transcript-incomplete"


def test_codex_jsonl_parser_rejects_unrequested_skill_contamination() -> None:
    module = _agent_evals()
    raw = "\n".join(
        [
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "error",
                        "message": "Skill descriptions were shortened to fit the skills context budget.",
                    },
                }
            ),
            json.dumps({"type": "turn.completed", "usage": {}}),
        ]
    )

    transcript = module.parse_codex_jsonl(raw)

    assert transcript.state == "error"
    assert transcript.error["category"] == "profile-contamination"


def test_codex_profile_requires_a_valid_completed_jsonl_turn(tmp_path: Path) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    payload = _profile_payload()
    payload.update(
        {
            "profile_id": "codex-protocol-probe",
            "harness": "codex",
            "model_id": "python-fixture",
            "command": [sys.executable, "-c", "print('not-json')"],
            "environment_keys": [],
        }
    )

    malformed = module.execute_profile(
        module.SystemProfile.from_dict(payload),
        source,
        tmp_path / "malformed-workspace",
        prompt="visible task",
        denied_roots=(),
    )
    payload["command"] = [
        sys.executable,
        "-c",
        "import json; print(json.dumps({'type':'turn.completed','usage':{}}))",
    ]
    completed = module.execute_profile(
        module.SystemProfile.from_dict(payload),
        source,
        tmp_path / "completed-workspace",
        prompt="visible task",
        denied_roots=(),
    )

    assert malformed.state == "error"
    assert malformed.error["category"] == "transcript-protocol"
    assert malformed.stdout == "not-json\n"
    assert completed.state == "completed"


def test_codex_profile_surfaces_nested_sandbox_failure_even_on_zero_exit(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    source = tmp_path / "source"
    source.mkdir()
    payload = _profile_payload()
    payload.update(
        {
            "profile_id": "codex-nested-sandbox-probe",
            "harness": "codex",
            "model_id": "python-fixture",
            "command": [
                sys.executable,
                "-c",
                "import json,sys; "
                "print(json.dumps({'type':'turn.completed','usage':{}})); "
                "print('sandbox-exec: sandbox_apply: Operation not permitted', file=sys.stderr)",
            ],
            "environment_keys": [],
        }
    )

    result = module.execute_profile(
        module.SystemProfile.from_dict(payload),
        source,
        tmp_path / "workspace",
        prompt="visible task",
        denied_roots=(),
    )

    assert result.state == "error"
    assert result.error["category"] == "isolation-runtime"
    assert "sandbox_apply" in result.stderr


def test_cli_runs_one_reference_fixture_and_freezes_its_outcome(tmp_path: Path) -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    output = tmp_path / "outcomes"

    result = CliRunner().invoke(
        cli,
        [
            "eval-run",
            "--suite",
            str(suite),
            "--task",
            "ir-missing-parent",
            "--profile",
            "reference",
            "--trials",
            "1",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["execution_count"] == 1
    row = payload["executions"][0]
    assert row["state"] == "passed"
    assert row["execution_state"] == "completed"
    assert row["mode"] == "fixture"
    assert row["command"] == []
    assert all(grade["status"] == "pass" for grade in row["grades"])
    assert "protected" not in result.output
    artifact_dir = output / "reference" / "ir-missing-parent" / "attempt-001" / "artifacts"
    assert (artifact_dir / "robot.json").is_file()
    assert (output / "reference" / "ir-missing-parent" / "attempt-001" / "transcript.json").is_file()
    assert (output / "reference" / "ir-missing-parent" / "manifest.json").is_file()


@pytest.mark.parametrize(
    ("profile_id", "command", "expected_execution_state", "expected_state", "expected_exit"),
    [
        (
            "live-success",
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path('robot.txt').write_text('changed')",
            ],
            "completed",
            "failed",
            0,
        ),
        (
            "live-timeout",
            [sys.executable, "-c", "import time; time.sleep(5)"],
            "timeout",
            "timeout",
            5,
        ),
        (
            "live-error",
            [sys.executable, "-c", "import sys; sys.exit(23)"],
            "error",
            "error",
            5,
        ),
        (
            "live-unrun",
            ["definitely-not-installed-agent-command"],
            "unrun",
            "unrun",
            4,
        ),
    ],
)
def test_cli_preserves_live_execution_states(
    tmp_path: Path,
    profile_id: str,
    command: list[str],
    expected_execution_state: str,
    expected_state: str,
    expected_exit: int,
) -> None:
    from packages.research.cli import cli

    suite = _write_single_task_suite(
        tmp_path / "suite",
        profile_id=profile_id,
        command=command,
        time_limit_seconds=1,
    )
    result = CliRunner().invoke(
        cli,
        [
            "eval-run",
            "--suite",
            str(suite),
            "--task",
            "joint-repair",
            "--profile",
            profile_id,
            "--trials",
            "1",
            "--output",
            str(tmp_path / "outcomes"),
            "--json",
        ],
    )

    assert result.exit_code == expected_exit, result.output
    payload = json.loads(result.output)
    assert payload["executions"][0]["state"] == expected_state
    assert payload["executions"][0]["execution_state"] == expected_execution_state
    if expected_state == "unrun":
        allowed = CliRunner().invoke(
            cli,
            [
                "eval-run",
                "--suite",
                str(suite),
                "--task",
                "joint-repair",
                "--profile",
                profile_id,
                "--trials",
                "1",
                "--output",
                str(tmp_path / "allowed-unrun-outcomes"),
                "--allow-unrun",
                "--json",
            ],
        )
        assert allowed.exit_code == 0, allowed.output
        assert json.loads(allowed.output)["executions"][0]["state"] == "unrun"


def test_cli_runs_fixture_suite_serially(tmp_path: Path) -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    result = CliRunner().invoke(
        cli,
        [
            "eval-run-suite",
            "--suite",
            str(suite),
            "--profile",
            "reference",
            "--profile",
            "seeded-failure",
            "--trials",
            "1",
            "--output",
            str(tmp_path / "suite-outcomes"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["execution_count"] == 12
    assert {row["state"] for row in payload["executions"]} == {"passed", "failed"}
    assert {row["execution_state"] for row in payload["executions"]} == {"completed"}
    assert {row["mode"] for row in payload["executions"]} == {"fixture"}


def test_grading_rejects_missing_required_artifact_and_ignores_agent_scores(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    suite = module.load_suite(Path(__file__).parents[1] / "evals" / "robot_design")
    task = suite.task("arm-reach-target")
    frozen = tmp_path / "artifacts"
    frozen.mkdir()
    (frozen / "grades.json").write_text(
        json.dumps({"arm-reaches-target": {"status": "pass", "score": 1.0}})
    )
    artifacts = (module.Artifact.from_path(frozen, frozen / "grades.json"),)

    grades = module.grade_frozen_outcome(task, frozen, artifacts)

    assert any(
        grade.grade_id == "required.robot.xml"
        and grade.category == "file-format"
        and grade.status == "fail"
        for grade in grades
    )
    assert not any(grade.status == "pass" for grade in grades)


def test_grading_runs_protected_code_on_frozen_bytes_with_complete_evidence(
    tmp_path: Path,
) -> None:
    module = _agent_evals()
    suite = module.load_suite(Path(__file__).parents[1] / "evals" / "robot_design")
    task = suite.task("arm-reach-target")
    frozen = tmp_path / "artifacts"
    artifacts = module.snapshot_workspace(task.reference_dir, frozen)

    grades = module.grade_frozen_outcome(task, frozen, artifacts)

    assert {grade.category for grade in grades} == {"simulator-load", "behavior"}
    assert all(grade.status == "pass" for grade in grades)
    assert all(grade.artifact_digests == (artifacts[0].sha256,) for grade in grades)
    assert all(len(grade.grader_fingerprint) == 64 for grade in grades)
    assert all(grade.raw_output for grade in grades)
    assert all("mujoco_version" in grade.parameters for grade in grades)
    module.verify_artifacts(frozen, artifacts)


def test_grading_converts_grader_exception_to_executed_error(tmp_path: Path) -> None:
    module = _agent_evals()
    suite_root = _write_single_task_suite(
        tmp_path / "suite",
        profile_id="local-command",
        command=[sys.executable, "-c", "pass"],
    )
    grader = suite_root / "protected" / "joint-repair" / "grader.py"
    grader.write_text("def grade(workspace):\n    raise RuntimeError('grader exploded')\n")
    task = module.load_suite(suite_root).task("joint-repair")
    frozen = tmp_path / "frozen"
    artifacts = module.snapshot_workspace(task.reference_dir, frozen)

    grades = module.grade_frozen_outcome(task, frozen, artifacts)

    assert len(grades) == 1
    assert grades[0].grade_id == "grader.execution"
    assert grades[0].status == "error"
    assert "RuntimeError: grader exploded" in grades[0].raw_output
    assert grades[0].artifact_digests == (artifacts[0].sha256,)


def test_grading_detects_a_grader_that_mutates_frozen_artifacts(tmp_path: Path) -> None:
    module = _agent_evals()
    suite_root = _write_single_task_suite(
        tmp_path / "suite",
        profile_id="local-command",
        command=[sys.executable, "-c", "pass"],
    )
    grader = suite_root / "protected" / "joint-repair" / "grader.py"
    grader.write_text(
        "def grade(workspace):\n"
        "    (workspace / 'robot.txt').write_text('mutated')\n"
        "    return [{'grade_id':'claimed-pass','category':'structural',"
        "'status':'pass','assertion':'untrusted mutation'}]\n"
    )
    task = module.load_suite(suite_root).task("joint-repair")
    frozen = tmp_path / "frozen"
    artifacts = module.snapshot_workspace(task.reference_dir, frozen)

    grades = module.grade_frozen_outcome(task, frozen, artifacts)

    assert grades[-1].grade_id == "grader.artifact-integrity"
    assert grades[-1].status == "error"
    assert "artifact drift" in grades[-1].raw_output


def test_all_published_grades_use_separate_contract_categories() -> None:
    module = _agent_evals()
    suite = module.load_suite(Path(__file__).parents[1] / "evals" / "robot_design")
    allowed = {"structural", "file-format", "compile", "simulator-load", "static", "behavior"}

    categories = {
        grade.category
        for task in suite.tasks
        for grade in module.grade_frozen_outcome(
            task,
            task.reference_dir,
            tuple(
                module.Artifact.from_path(task.reference_dir, path)
                for path in sorted(task.reference_dir.rglob("*"))
                if path.is_file()
            ),
        )
    }

    assert categories <= allowed
    assert {"structural", "file-format", "compile", "simulator-load", "static", "behavior"} <= categories


def test_at_least_two_seeded_failures_load_but_fail_robotics_semantics() -> None:
    module = _agent_evals()
    suite = module.load_suite(Path(__file__).parents[1] / "evals" / "robot_design")
    demonstrated = []
    for task in suite.tasks:
        validation = module.validate_task_oracles(task)
        load_passed = any(
            grade.category in {"simulator-load", "simulator_load"} and grade.status == "pass"
            for grade in validation.seeded_failure_grades
        )
        semantic_failed = any(
            grade.category in {"static", "behavior"} and grade.status == "fail"
            for grade in validation.seeded_failure_grades
        )
        if load_passed and semantic_failed:
            demonstrated.append(task.manifest.task_id)

    assert len(demonstrated) >= 2, demonstrated


@pytest.mark.parametrize(
    ("profile_id", "expected_state"),
    [("reference", "passed"), ("seeded-failure", "failed")],
)
def test_evidence_bundle_layout_conforms_to_schema_and_grades_frozen_outcome(
    tmp_path: Path,
    profile_id: str,
    expected_state: str,
) -> None:
    module = _agent_evals()
    repository = Path(__file__).parents[1]
    suite = module.load_suite(repository / "evals" / "robot_design")
    profiles = {profile.profile_id: profile for profile in module.load_profiles(suite.root)}
    task = suite.task("arm-reach-target")
    profile = profiles[profile_id]
    source = task.reference_dir if profile_id == "reference" else task.seeded_failure_dir
    workspace_parent = tmp_path / "workspaces"
    workspace_parent.mkdir()
    bundle_dir = tmp_path / "bundle"
    capture = module.capture_profile_execution(
        profile,
        source,
        prompt=task.manifest.prompt,
        workspace_parent=workspace_parent,
        evidence_dir=bundle_dir / "trials" / "attempt-001",
        denied_roots=(repository, bundle_dir),
    )

    bundle = module.finalize_evidence_bundle(task, profile, (capture,), bundle_dir)

    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    schema = json.loads(
        (repository / "specs" / "011-b2b-feasibility-evidence" / "contracts" / "evidence-bundle.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
        manifest
    )
    assert bundle.trials[0].state == expected_state
    assert manifest["trials"][0]["state"] == expected_state
    assert (bundle_dir / "trials" / "attempt-001" / "grades.json").is_file()
    assert (bundle_dir / "task.json").is_file()
    assert (bundle_dir / "profile.json").is_file()
    assert (bundle_dir / "grader" / "grader.py").is_file()
    assert (bundle_dir / "environment.json").is_file()
    assert all(grade.artifact_digests for grade in bundle.trials[0].grades)
    encoded_manifest = manifest_path.read_text()
    assert task.manifest.grader_entrypoint not in encoded_manifest
    assert task.manifest.reference_dir not in encoded_manifest
    assert task.manifest.seeded_failure_dir not in encoded_manifest
    with pytest.raises(ValueError, match="already exists"):
        module.finalize_evidence_bundle(task, profile, (capture,), bundle_dir)


def _comparison_trial(
    task_id: str,
    task_fingerprint: str,
    attempt: int,
    state: str,
    *,
    duration_seconds: float = 1.0,
    observable_cost_usd: float | None = 0.1,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "task_fingerprint": task_fingerprint,
        "attempt": attempt,
        "state": state,
        "duration_seconds": duration_seconds,
        "observable_cost_usd": observable_cost_usd,
    }


def test_comparison_keeps_task_trials_before_exact_aggregates() -> None:
    module = _agent_evals()
    left = []
    right = []
    for attempt in (1, 2, 3):
        left.extend(
            [
                _comparison_trial("task-a", "a" * 64, attempt, "passed"),
                _comparison_trial("task-b", "b" * 64, attempt, "failed"),
            ]
        )
        right.extend(
            [
                _comparison_trial("task-a", "a" * 64, attempt, "failed"),
                _comparison_trial("task-b", "b" * 64, attempt, "passed"),
            ]
        )

    comparison = module.compare_profile_trials(
        "left-profile",
        "right-profile",
        left,
        right,
        left_profile={"model_id": "same", "instructions": "old"},
        right_profile={"model_id": "same", "instructions": "new"},
    )

    assert len(comparison.trial_rows) == 6
    assert comparison.trial_rows[0]["task_id"] == "task-a"
    assert comparison.trial_rows[0]["attempt"] == 1
    assert comparison.aggregates["left"]["pass_rate"] == 0.5
    assert comparison.aggregates["right"]["pass_rate"] == 0.5
    assert comparison.aggregates["left"]["pass_at_1"] == 0.5
    assert comparison.aggregates["right"]["pass_power_3"] == 0.5
    assert comparison.aggregates["improvements"] == ["task-b"]
    assert comparison.aggregates["regressions"] == ["task-a"]
    assert comparison.aggregates["changed_components"] == ["instructions"]
    assert comparison.aggregates["sample_complete"] is True
    assert comparison.aggregates["no_meaningful_difference"] is False


def test_comparison_identity_changes_with_validated_source_revisions() -> None:
    module = _agent_evals()
    left = [
        _comparison_trial("task-a", "a" * 64, 1, "passed")
        | {
            "bundle_id": "00000000-0000-0000-0000-000000000001",
            "profile_fingerprint": "1" * 64,
            "environment_sha256": "2" * 64,
        }
    ]
    right = [
        _comparison_trial("task-a", "a" * 64, 1, "failed")
        | {
            "bundle_id": "00000000-0000-0000-0000-000000000002",
            "profile_fingerprint": "3" * 64,
            "environment_sha256": "4" * 64,
        }
    ]
    first = module.compare_profile_trials(
        "left",
        "right",
        left,
        right,
        left_profile={"fingerprint": "1" * 64, "instructions": "old-a"},
        right_profile={"fingerprint": "3" * 64, "instructions": "new-a"},
    )

    left[0]["bundle_id"] = "00000000-0000-0000-0000-000000000003"
    left[0]["profile_fingerprint"] = "5" * 64
    left[0]["environment_sha256"] = "6" * 64
    second = module.compare_profile_trials(
        "left",
        "right",
        left,
        right,
        left_profile={"fingerprint": "5" * 64, "instructions": "old-b"},
        right_profile={"fingerprint": "3" * 64, "instructions": "new-b"},
    )

    assert first.comparison_id != second.comparison_id
    assert first.source_revisions["left"]["bundle_ids"] == [
        "00000000-0000-0000-0000-000000000001"
    ]
    assert second.source_revisions["left"]["profile_fingerprint"] == "5" * 64


def test_comparison_preserves_errors_and_nullable_cost() -> None:
    module = _agent_evals()
    left = [_comparison_trial("task-a", "a" * 64, 1, "passed")]
    right = [
        _comparison_trial(
            "task-a",
            "a" * 64,
            1,
            "error",
            observable_cost_usd=None,
        )
    ]

    comparison = module.compare_profile_trials("left", "right", left, right)

    assert comparison.trial_rows[0]["right_state"] == "error"
    assert comparison.aggregates["right"]["pass_rate"] == 0.0
    assert comparison.aggregates["right"]["state_counts"]["error"] == 1
    assert comparison.aggregates["right"]["cost_usd"] is None
    assert comparison.aggregates["sample_complete"] is False
    assert comparison.aggregates["no_meaningful_difference"] is True


def test_comparison_rejects_incompatible_task_revisions() -> None:
    module = _agent_evals()
    left = [_comparison_trial("task-a", "a" * 64, 1, "passed")]
    right = [_comparison_trial("task-a", "b" * 64, 1, "passed")]

    with pytest.raises(ValueError, match="incompatible task revision"):
        module.compare_profile_trials("left", "right", left, right)


def test_cli_compares_saved_profiles_with_rows_before_aggregates(tmp_path: Path) -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    run_root = tmp_path / "runs"
    run_result = CliRunner().invoke(
        cli,
        [
            "eval-run-suite",
            "--suite",
            str(suite),
            "--profile",
            "reference",
            "--profile",
            "seeded-failure",
            "--trials",
            "1",
            "--output",
            str(run_root),
            "--json",
        ],
    )
    assert run_result.exit_code == 0, run_result.output

    comparison_path = tmp_path / "comparison.json"
    json_result = CliRunner().invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--output",
            str(comparison_path),
            "--json",
        ],
    )
    human_result = CliRunner().invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
        ],
    )

    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    assert len(payload["trial_rows"]) == 6
    assert payload["aggregates"]["left"]["pass_rate"] == 1.0
    assert payload["aggregates"]["right"]["pass_rate"] == 0.0
    assert payload["aggregates"]["regressions"] == sorted(EXPECTED_TASK_IDS)
    assert len(payload["source_revisions"]["left"]["bundle_ids"]) == 6
    assert len(payload["source_revisions"]["right"]["bundle_ids"]) == 6
    assert payload["trial_rows"][0]["left_bundle_id"] is not None
    assert payload["trial_rows"][0]["right_bundle_id"] is not None
    assert "snapshot_path" not in payload["aggregates"]["changed_components"]
    assert "snapshot_sha256" not in payload["aggregates"]["changed_components"]
    assert payload["aggregates"]["sample_complete"] is False
    assert json.loads(comparison_path.read_text()) == payload
    assert human_result.exit_code == 0, human_result.output
    assert human_result.output.index("arm-reach-target attempt=1") < human_result.output.index(
        "Aggregates:"
    )


def test_cli_compare_refuses_corrupted_or_missing_bundle_evidence(tmp_path: Path) -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    run_root = tmp_path / "runs"
    runner = CliRunner()
    run_result = runner.invoke(
        cli,
        [
            "eval-run-suite",
            "--suite",
            str(suite),
            "--profile",
            "reference",
            "--profile",
            "seeded-failure",
            "--trials",
            "1",
            "--output",
            str(run_root),
            "--json",
        ],
    )
    assert run_result.exit_code == 0, run_result.output

    bundle_root = run_root / "reference" / "arm-reach-target"
    manifest_path = bundle_root / "manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    manifest["trials"][0]["state"] = "failed"
    manifest_path.write_text(json.dumps(manifest))

    false_state = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert false_state.exit_code == 7
    assert "manifest-drift" in false_state.output

    manifest_path.write_bytes(original_manifest)
    manifest = json.loads(original_manifest)
    manifest["profile"]["instructions"] = "forged comparison profile"
    manifest_path.write_text(json.dumps(manifest))

    false_profile = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert false_profile.exit_code == 7
    assert "profile-drift" in false_profile.output

    manifest_path.write_bytes(original_manifest)
    manifest = json.loads(original_manifest)
    manifest["trials"][0]["attempt"] = 2
    manifest_path.write_text(json.dumps(manifest))
    false_attempt = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert false_attempt.exit_code == 7
    assert "manifest-drift" in false_attempt.output

    manifest_path.write_bytes(original_manifest)
    manifest = json.loads(original_manifest)
    del manifest["bundle_id"]
    manifest_path.write_text(json.dumps(manifest))
    missing_revision = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert missing_revision.exit_code == 2
    assert "bundle_id" in missing_revision.output

    manifest_path.write_bytes(original_manifest)
    artifact_path = bundle_root / "attempt-001" / "artifacts" / "robot.xml"
    original_artifact = artifact_path.read_bytes()
    artifact_path.write_bytes(original_artifact + b"\n<!-- corrupted -->\n")

    corrupted = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert corrupted.exit_code == 7
    assert "artifact-drift" in corrupted.output

    artifact_path.write_bytes(original_artifact)
    transcript_path = bundle_root / "attempt-001" / "transcript.json"
    transcript_path.unlink()

    missing = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert missing.exit_code == 7
    assert "missing-raw-evidence" in missing.output


def test_cli_compare_returns_seven_for_incompatible_task_revisions(tmp_path: Path) -> None:
    from packages.research.cli import cli

    suite = Path(__file__).parents[1] / "evals" / "robot_design"
    run_root = tmp_path / "runs"
    runner = CliRunner()
    run_result = runner.invoke(
        cli,
        [
            "eval-run-suite",
            "--suite",
            str(suite),
            "--profile",
            "reference",
            "--profile",
            "seeded-failure",
            "--trials",
            "1",
            "--output",
            str(run_root),
            "--json",
        ],
    )
    assert run_result.exit_code == 0, run_result.output

    manifest_path = run_root / "seeded-failure" / "arm-reach-target" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["task"]["fingerprint"] = "b" * 64
    for trial in manifest["trials"]:
        trial["task_fingerprint"] = "b" * 64
    manifest_path.write_text(json.dumps(manifest))

    result = runner.invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "reference,seeded-failure",
            "--json",
        ],
    )

    assert result.exit_code == 7
    assert "incompatible task revision" in result.output


def test_cli_compare_returns_two_for_malformed_bundle_manifest(tmp_path: Path) -> None:
    from packages.research.cli import cli

    run_root = tmp_path / "runs"
    manifest_path = run_root / "left" / "task-a" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{")
    output_path = tmp_path / "comparison.json"

    result = CliRunner().invoke(
        cli,
        [
            "eval-compare",
            "--run-root",
            str(run_root),
            "--profiles",
            "left,right",
            "--output",
            str(output_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "invalid evidence manifest" in result.output
    assert not output_path.exists()


def _build_replay_bundle(tmp_path: Path) -> tuple[object, Path]:
    module = _agent_evals()
    repository = Path(__file__).parents[1]
    suite = module.load_suite(repository / "evals" / "robot_design")
    profiles = {profile.profile_id: profile for profile in module.load_profiles(suite.root)}
    task = suite.task("arm-reach-target")
    profile = profiles["reference"]
    workspace_parent = tmp_path / "workspaces"
    workspace_parent.mkdir()
    bundle_dir = tmp_path / "bundle"
    capture = module.capture_profile_execution(
        profile,
        task.reference_dir,
        prompt=task.manifest.prompt,
        workspace_parent=workspace_parent,
        evidence_dir=bundle_dir / "trials" / "attempt-001",
        denied_roots=(repository, bundle_dir),
    )
    module.finalize_evidence_bundle(task, profile, (capture,), bundle_dir)
    return module, bundle_dir


def test_replay_is_identical_three_times_and_never_mutates_originals(tmp_path: Path) -> None:
    module, bundle_dir = _build_replay_bundle(tmp_path)
    before = {
        path.relative_to(bundle_dir).as_posix(): module.sha256_bytes(path.read_bytes())
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file()
    }

    replay = module.replay_evidence_bundle(bundle_dir, repeat=3)

    after = {
        path.relative_to(bundle_dir).as_posix(): module.sha256_bytes(path.read_bytes())
        for path in sorted(bundle_dir.rglob("*"))
        if path.is_file()
    }
    assert replay.state == "passed"
    assert replay.identical is True
    assert len(replay.repeat_digests) == 3
    assert len(set(replay.repeat_digests)) == 1
    assert replay.drift == ()
    assert after == before


@pytest.mark.parametrize(
    ("drift_kind", "expected_category"),
    [
        ("task", "task-drift"),
        ("grader", "grader-drift"),
        ("profile", "profile-drift"),
        ("artifact", "artifact-drift"),
        ("simulator", "simulator-drift"),
        ("missing-raw", "missing-raw-evidence"),
        ("transcript-content", "missing-raw-evidence"),
        ("grades-content", "missing-raw-evidence"),
    ],
)
def test_replay_refuses_every_dependency_drift(
    tmp_path: Path,
    drift_kind: str,
    expected_category: str,
) -> None:
    module, bundle_dir = _build_replay_bundle(tmp_path)
    simulator_version = None
    if drift_kind == "task":
        (bundle_dir / "task.json").write_text(
            (bundle_dir / "task.json").read_text() + "\n"
        )
    elif drift_kind == "grader":
        (bundle_dir / "grader" / "grader.py").write_text(
            (bundle_dir / "grader" / "grader.py").read_text() + "\n# drift\n"
        )
    elif drift_kind == "profile":
        (bundle_dir / "profile.json").write_text(
            (bundle_dir / "profile.json").read_text() + "\n"
        )
    elif drift_kind == "artifact":
        (bundle_dir / "trials" / "attempt-001" / "artifacts" / "robot.xml").write_text(
            "<mujoco model='drift'/>"
        )
    elif drift_kind == "simulator":
        simulator_version = "0.0.0-drift"
    elif drift_kind == "missing-raw":
        (bundle_dir / "trials" / "attempt-001" / "transcript.json").unlink()
    elif drift_kind == "transcript-content":
        transcript = bundle_dir / "trials" / "attempt-001" / "transcript.json"
        transcript.write_text(transcript.read_text() + "\n")
    elif drift_kind == "grades-content":
        grades = bundle_dir / "trials" / "attempt-001" / "grades.json"
        grades.write_text(grades.read_text() + "\n")

    replay = module.replay_evidence_bundle(
        bundle_dir,
        repeat=1,
        simulator_version=simulator_version,
    )

    assert replay.state == "drift"
    assert any(row["category"] == expected_category for row in replay.drift)


def test_cli_replay_reports_identical_json_and_human_output(tmp_path: Path) -> None:
    from packages.research.cli import cli

    _, bundle_dir = _build_replay_bundle(tmp_path)
    runner = CliRunner()

    json_result = runner.invoke(
        cli,
        [
            "eval-replay",
            "--run-root",
            str(bundle_dir),
            "--repeat",
            "3",
            "--assert-identical",
            "--json",
        ],
    )
    human_result = runner.invoke(
        cli,
        ["eval-replay", "--run-root", str(bundle_dir), "--repeat", "3"],
    )

    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    assert payload["state"] == "passed"
    assert payload["identical"] is True
    assert len(payload["repeat_digests"]) == 3
    assert human_result.exit_code == 0, human_result.output
    assert "identical=True" in human_result.output


def test_cli_replay_returns_six_for_drift_and_two_for_invalid_repeat(
    tmp_path: Path,
) -> None:
    from packages.research.cli import cli

    _, bundle_dir = _build_replay_bundle(tmp_path)
    (bundle_dir / "profile.json").write_text(
        (bundle_dir / "profile.json").read_text() + "\n"
    )
    runner = CliRunner()

    drift = runner.invoke(
        cli,
        [
            "eval-replay",
            "--run-root",
            str(bundle_dir),
            "--repeat",
            "1",
            "--assert-identical",
            "--json",
        ],
    )
    invalid = runner.invoke(
        cli,
        ["eval-replay", "--run-root", str(bundle_dir), "--repeat", "0"],
    )

    assert drift.exit_code == 6, drift.output
    assert json.loads(drift.output)["drift"][0]["category"] == "profile-drift"
    assert invalid.exit_code == 2


def test_one_file_control_validate_grade_compare_and_replay_outputs(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).parents[1]
    suite = repository / "evals" / "robot_design"
    control = suite / "control.py"
    task_payload = json.loads(
        (suite / "tasks" / "arm-reach-target" / "public" / "task.json").read_text()
    )

    def run_control(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(control), *arguments],
            cwd=repository,
            text=True,
            capture_output=True,
            check=False,
        )

    assert control.is_file()
    assert "packages.research.agent_evals" not in control.read_text()

    validation = run_control("validate", "--suite", str(suite))
    assert validation.returncode == 0, validation.stderr
    validation_payload = json.loads(validation.stdout)
    assert validation_payload["task_count"] == 6
    assert validation_payload["reference_passes"] == 6
    assert validation_payload["seeded_failures_caught"] == 6

    reference = run_control(
        "grade",
        "--suite",
        str(suite),
        "--task",
        "arm-reach-target",
        "--artifacts",
        str(suite / task_payload["reference_dir"]),
    )
    seeded = run_control(
        "grade",
        "--suite",
        str(suite),
        "--task",
        "arm-reach-target",
        "--artifacts",
        str(suite / task_payload["seeded_failure_dir"]),
    )
    assert reference.returncode == 0, reference.stderr
    assert seeded.returncode == 0, seeded.stderr
    reference_payload = json.loads(reference.stdout)
    seeded_payload = json.loads(seeded.stdout)
    assert reference_payload["state"] == "passed"
    assert seeded_payload["state"] == "failed"
    assert reference_payload["artifact_digest"] != seeded_payload["artifact_digest"]
    reference_path = tmp_path / "reference.json"
    seeded_path = tmp_path / "seeded.json"
    reference_path.write_text(reference.stdout)
    seeded_path.write_text(seeded.stdout)

    comparison = run_control(
        "compare",
        "--left",
        str(reference_path),
        "--right",
        str(seeded_path),
    )
    assert comparison.returncode == 0, comparison.stderr
    comparison_payload = json.loads(comparison.stdout)
    assert comparison_payload["regressions"] == ["arm-reach-target"]

    replay = run_control(
        "replay",
        "--record",
        str(reference_path),
        "--repeat",
        "3",
    )
    assert replay.returncode == 0, replay.stderr
    replay_payload = json.loads(replay.stdout)
    assert replay_payload["identical"] is True
    assert replay_payload["matches_record"] is True
    assert len(set(replay_payload["repeat_digests"])) == 1
