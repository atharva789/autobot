"""Run-level trace debugging for research experiments."""

from __future__ import annotations

import base64
import glob
import json
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from packages.research.experiment.prompt_oracle import infer_expected_robo_grammar
from packages.research.experiment.types import (
    BatchDebugReport,
    ConfusionMatrix,
    Experiment,
    ExperimentRun,
    LangfuseRunRef,
    RoboGrammarEval,
    RunDebugReport,
    ReproEnvelope,
    TestPromptLabel,
)
from packages.research.storage.store import SQLiteStore
from packages.research.strategy.protocol import StrategyConfig


class TraceReader(Protocol):
    """Minimal trace-source interface used by `RunDebugAPI`.

    Implement this protocol when tests or alternate backends need to provide
    Langfuse-like traces without using `LangfuseTraceReader`.
    """

    def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        """Return one trace payload with an `observations` list for `trace_id`."""
        ...


def _load_langfuse_env(env_path: Path | str | None = None) -> None:
    """Load trace backend credentials from `.env` without requiring shell exports.

    Args:
        env_path: Optional explicit `.env` file. If omitted, parent directories
            are searched from the current working directory.
    """

    try:
        from dotenv import load_dotenv
    except Exception:
        return

    if env_path is not None:
        load_dotenv(Path(env_path), override=False)
        return

    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        dotenv_path = candidate / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path, override=False)
            return


class LangSmithTraceReader:
    """Read LangSmith traces through the LangSmith Python client."""

    def __init__(
        self,
        *,
        project_name: str | None = None,
        env_path: Path | str | None = None,
    ) -> None:
        _load_langfuse_env(env_path)
        self.project_name = project_name or os.environ.get("LANGSMITH_PROJECT")
        try:
            from langsmith import Client
        except Exception as exc:
            raise RuntimeError("langsmith is required to read LangSmith traces.") from exc
        self.client = Client()

    def list_run_refs(
        self,
        *,
        limit: int | None = 20,
        page_size: int = 1000,
        from_start_time: str | datetime | None = None,
        to_start_time: str | datetime | None = None,
        observation_name: str | None = None,
        observation_type: str | None = None,
        environment: str | None = None,
    ) -> list[LangfuseRunRef]:
        if limit is not None and limit < 1:
            return []
        start_time = _parse_cloud_time(from_start_time)
        refs: list[LangfuseRunRef] = []
        seen: set[str] = set()
        query_limit = min(100, max(1, limit or page_size))
        for run in self.client.list_runs(
            project_name=self.project_name,
            is_root=True,
            start_time=start_time,
            limit=query_limit,
        ):
            if to_start_time is not None:
                run_start = getattr(run, "start_time", None)
                upper = _parse_cloud_time(to_start_time)
                if isinstance(run_start, datetime) and upper is not None and run_start > upper:
                    continue
            if environment:
                metadata = _run_metadata(run)
                if metadata.get("environment") != environment:
                    continue
            trace_id = str(getattr(run, "trace_id", "") or getattr(run, "id", ""))
            if not trace_id or trace_id in seen:
                continue
            if observation_name or observation_type:
                trace = self.fetch_trace(trace_id)
                observations = _observations(trace)
                if observation_name and not any(
                    observation.get("name") == observation_name for observation in observations
                ):
                    continue
                if observation_type and not any(
                    str(observation.get("type") or "").lower() == observation_type.lower()
                    for observation in observations
                ):
                    continue
            seen.add(trace_id)
            refs.append(
                LangfuseRunRef(
                    trace_id=trace_id,
                    last_observation_at=_cloud_time(getattr(run, "start_time", None)),
                    latest_observation_name=_optional_str(getattr(run, "name", None)),
                    latest_observation_id=_optional_str(getattr(run, "id", None)),
                )
            )
            if limit is not None and len(refs) >= limit:
                break
        return refs

    def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        runs = list(
            self.client.list_runs(
                project_name=self.project_name,
                trace_id=trace_id,
                limit=100,
            )
        )
        runs.sort(key=lambda run: _cloud_time(getattr(run, "start_time", None)))
        return {
            "trace_id": trace_id,
            "source": "langsmith",
            "observations": [_langsmith_run_to_observation(run) for run in runs],
        }


class LangfuseTraceReader:
    """Read Langfuse Cloud traces through the public Observations API.

    Use this as the default `trace_reader` for `RunDebugAPI`. It reads
    `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and either `LANGFUSE_HOST` or
    `LANGFUSE_BASE_URL` from the environment or from a repo `.env` file.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
        env_path: Path | str | None = None,
    ) -> None:
        """Create a Langfuse trace reader.

        Args:
            host: Optional Langfuse base URL, e.g. `https://us.cloud.langfuse.com`.
            public_key: Optional Langfuse public key override.
            secret_key: Optional Langfuse secret key override.
            env_path: Optional `.env` path to load before reading env vars.
        """

        _load_langfuse_env(env_path)
        self.host = (
            host
            or os.environ.get("LANGFUSE_HOST")
            or os.environ.get("LANGFUSE_BASE_URL")
            or "https://cloud.langfuse.com"
        ).rstrip("/")
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")

    def list_run_refs(
        self,
        *,
        limit: int | None = 20,
        page_size: int = 1000,
        from_start_time: str | datetime | None = None,
        to_start_time: str | datetime | None = None,
        observation_name: str | None = None,
        observation_type: str | None = None,
        environment: str | None = None,
    ) -> list[LangfuseRunRef]:
        """List Langfuse trace IDs, newest first, grouped from observation rows.

        Args:
            limit: Maximum number of unique trace IDs to return. Use `None` to
                paginate all matching observation rows.
            page_size: Langfuse observations page size, capped at 1000.
            from_start_time: Optional ISO string or datetime lower bound.
            to_start_time: Optional ISO string or datetime upper bound.
            observation_name: Optional observation-name filter.
            observation_type: Optional observation type filter such as `GENERATION`.
            environment: Optional Langfuse environment filter.
        """

        if not self.public_key or not self.secret_key:
            raise RuntimeError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required to list runs."
            )
        if limit is not None and limit < 1:
            return []
        if page_size < 1:
            raise ValueError("page_size must be positive.")

        refs: dict[str, LangfuseRunRef] = {}
        cursor: str | None = None
        while True:
            query: dict[str, str] = {
                "fields": "core,basic",
                "limit": str(min(page_size, 1000)),
            }
            if cursor:
                query["cursor"] = cursor
            if from_start_time is not None:
                query["fromStartTime"] = _format_langfuse_time(from_start_time)
            if to_start_time is not None:
                query["toStartTime"] = _format_langfuse_time(to_start_time)
            if observation_name:
                query["name"] = observation_name
            if observation_type:
                query["type"] = observation_type
            if environment:
                query["environment"] = environment

            data = self._get_json(
                f"{self.host}/api/public/v2/observations?{urlencode(query)}"
            )
            page = data.get("data")
            if isinstance(page, list):
                for item in page:
                    if not isinstance(item, dict):
                        continue
                    trace_id = item.get("traceId") or item.get("trace_id")
                    if not isinstance(trace_id, str) or not trace_id:
                        continue
                    if trace_id in refs:
                        continue
                    refs[trace_id] = LangfuseRunRef(
                        trace_id=trace_id,
                        last_observation_at=str(item.get("startTime") or ""),
                        latest_observation_name=_optional_str(item.get("name")),
                        latest_observation_id=_optional_str(item.get("id")),
                    )
                    if limit is not None and len(refs) >= limit:
                        return list(refs.values())
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            cursor = meta.get("cursor") if isinstance(meta.get("cursor"), str) else None
            if not cursor:
                break
        return list(refs.values())

    def fetch_trace(self, trace_id: str) -> dict[str, Any]:
        """Fetch all observations for one Langfuse trace ID.

        Returns a dictionary shaped as `{"trace_id": trace_id,
        "observations": [...]}` sorted by observation `startTime`.
        """

        if not self.public_key or not self.secret_key:
            raise RuntimeError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required to read traces."
            )

        observations: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            query = {
                "fields": "core,basic,io,metadata,model,usage,metrics,prompt",
                "limit": "1000",
                "traceId": trace_id,
            }
            if cursor:
                query["cursor"] = cursor
            data = self._get_json(f"{self.host}/api/public/v2/observations?{urlencode(query)}")
            page = data.get("data")
            if isinstance(page, list):
                observations.extend(item for item in page if isinstance(item, dict))
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            cursor = meta.get("cursor") if isinstance(meta.get("cursor"), str) else None
            if not cursor:
                break
        observations.sort(key=lambda obs: str(obs.get("startTime") or ""))
        return {"trace_id": trace_id, "observations": observations}

    def _get_json(self, url: str) -> dict[str, Any]:
        """GET a Langfuse API URL using Basic auth and return a JSON object."""

        auth = base64.b64encode(
            f"{self.public_key}:{self.secret_key}".encode()
        ).decode()
        request = Request(url, headers={"Authorization": f"Basic {auth}"})
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode()
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}


class CodexTraceAnalyzer:
    """Optional Codex-based interpretation layer for trace debug reports.

    `RunDebugAPI.debug_trace(..., use_codex=True)` uses `analyze(...)` for one
    run. `RunDebugAPI.batch_debug_trace(...)` uses `analyze_batch(...)` once
    over all selected traces to find cross-run patterns.
    """

    def __init__(
        self,
        *,
        cwd: Path | None = None,
        timeout_seconds: int = 120,
        codex_command: str | None = None,
    ) -> None:
        """Create a Codex analyzer.

        Args:
            cwd: Working directory passed to `codex exec --cd`.
            timeout_seconds: Timeout for each `codex exec` subprocess call.
            codex_command: Optional executable path. If omitted, the analyzer
                resolves `CODEX_CLI`, `PATH`, Homebrew, and common NVM paths.
        """

        self.cwd = cwd or Path.cwd()
        self.timeout_seconds = timeout_seconds
        self.codex_command = codex_command or _resolve_codex_command()

    def analyze(
        self,
        *,
        run: ExperimentRun,
        trace: dict[str, Any],
        expected: dict[str, list[str]],
        observed: dict[str, list[str]],
        deterministic_failures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ask Codex to interpret one trace using deterministic debug evidence.

        Args:
            run: Synthetic or persisted run metadata for the trace.
            trace: Langfuse trace payload.
            expected: Expected RoboGrammar structural rules.
            observed: Rules extracted from the trace.
            deterministic_failures: Node-level FP/FN/compile/evaluator rows.

        Returns:
            A JSON-like dict with `summary`, `failure_hypotheses`,
            `node_failure_notes`, and `proxy_quality_notes`.
        """

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "failure_hypotheses": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "node_failure_notes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "pipeline_node": {"type": "string"},
                            "kind": {"type": "string"},
                            "grammar_node": {"type": ["string", "null"]},
                            "explanation": {"type": "string"},
                            "evidence": {"type": "string"},
                        },
                        "required": [
                            "pipeline_node",
                            "kind",
                            "grammar_node",
                            "explanation",
                            "evidence",
                        ],
                    },
                },
                "proxy_quality_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "summary",
                "failure_hypotheses",
                "node_failure_notes",
                "proxy_quality_notes",
            ],
        }
        prompt = (
            "Analyze this RoboGrammar Langfuse trace as a debugging assistant. "
            "Use the expected and observed structural rules as the ground truth. "
            "Identify which pipeline nodes likely caused false positives, false "
            "negatives, or weak evaluator proxy criteria. Return only JSON.\n\n"
            f"Run: {run.run_id} strategy={run.strategy_name} prompt={run.prompt!r}\n"
            f"Expected RoboGrammar: {json.dumps(expected, sort_keys=True)}\n"
            f"Observed RoboGrammar: {json.dumps(observed, sort_keys=True)}\n"
            f"Deterministic failures: {json.dumps(deterministic_failures, sort_keys=True)}\n"
            f"Trace observations: {json.dumps(trace.get('observations', []), default=str)[:60000]}"
        )
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "codex_trace_schema.json"
            schema_path.write_text(json.dumps(schema))
            try:
                result = subprocess.run(
                    [
                        self.codex_command,
                        "exec",
                        "--cd",
                        str(self.cwd),
                        "--sandbox",
                        "read-only",
                        "--output-schema",
                        str(schema_path),
                        "-",
                    ],
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                return {
                    "summary": "Codex trace analysis unavailable.",
                    "failure_hypotheses": [
                        f"Optional codex CLI was not found: {exc}. "
                        "Run debug_trace(..., use_codex=False) for deterministic analysis."
                    ],
                    "node_failure_notes": [],
                    "proxy_quality_notes": [],
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "summary": "Codex trace analysis timed out.",
                    "failure_hypotheses": [
                        f"Optional codex CLI exceeded {self.timeout_seconds}s: {exc}."
                    ],
                    "node_failure_notes": [],
                    "proxy_quality_notes": [],
                }
        if result.returncode != 0:
            return {
                "summary": "Codex trace analysis failed.",
                "failure_hypotheses": [result.stderr.strip() or result.stdout.strip()],
                "node_failure_notes": [],
                "proxy_quality_notes": [],
            }
        return _last_json_object(result.stdout)

    def analyze_batch(
        self,
        *,
        reports: list[RunDebugReport],
        traces: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ask Codex to analyze a whole batch of trace reports at once.

        Args:
            reports: Deterministic per-trace reports already computed by
                `RunDebugAPI.batch_debug_trace(...)`.
            traces: Raw trace payloads for the same trace IDs.

        Returns:
            A JSON-like dict with batch-level summary, cross-run patterns,
            node-failure patterns, proxy-quality patterns, and next actions.
        """

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "cross_run_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "node_failure_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "proxy_quality_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recommended_next_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "summary",
                "cross_run_patterns",
                "node_failure_patterns",
                "proxy_quality_patterns",
                "recommended_next_actions",
            ],
        }
        prompt = (
            "Analyze this batch of RoboGrammar Langfuse traces as a debugging "
            "data scientist. Use each run's expected-vs-observed grammar, "
            "confusion counts, deterministic node failures, proxy checks, and "
            "trace observations. Identify systematic cross-run failure patterns, "
            "not one-off per-run commentary. Return only JSON.\n\n"
            f"Batch summary: {json.dumps(_batch_summary_payload(reports), sort_keys=True)}\n"
            f"Runs: {json.dumps([_report_payload(report) for report in reports], default=str)[:90000]}\n"
            f"Trace observations: {json.dumps([_trace_payload(trace) for trace in traces], default=str)[:90000]}"
        )
        with tempfile.TemporaryDirectory() as tmp:
            schema_path = Path(tmp) / "codex_batch_trace_schema.json"
            schema_path.write_text(json.dumps(schema))
            try:
                result = subprocess.run(
                    [
                        self.codex_command,
                        "exec",
                        "--cd",
                        str(self.cwd),
                        "--sandbox",
                        "read-only",
                        "--output-schema",
                        str(schema_path),
                        "-",
                    ],
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                return {
                    "summary": "Codex batch trace analysis unavailable.",
                    "cross_run_patterns": [
                        f"Optional codex CLI was not found: {exc}."
                    ],
                    "node_failure_patterns": [],
                    "proxy_quality_patterns": [],
                    "recommended_next_actions": [],
                }
            except subprocess.TimeoutExpired as exc:
                return {
                    "summary": "Codex batch trace analysis timed out.",
                    "cross_run_patterns": [
                        f"Optional codex CLI exceeded {self.timeout_seconds}s: {exc}."
                    ],
                    "node_failure_patterns": [],
                    "proxy_quality_patterns": [],
                    "recommended_next_actions": [],
                }
        if result.returncode != 0:
            return {
                "summary": "Codex batch trace analysis failed.",
                "cross_run_patterns": [result.stderr.strip() or result.stdout.strip()],
                "node_failure_patterns": [],
                "proxy_quality_patterns": [],
                "recommended_next_actions": [],
            }
        return _last_json_object(result.stdout)


class RunDebugAPI:
    """User-facing API for cloud run discovery and trace debugging.

    Start with `RunDebugAPI()`, which reads LangSmith by default.
    Pass `use_langfuse=True` to read legacy Langfuse traces.
    Use `last_run_id()`, `last_k_run_ids(k)`, or `all_run_ids()` to discover
    cloud traces; use `debug_trace(trace_id)` for one trace and
    `batch_debug_trace(trace_ids)` for cross-run Codex analysis.
    """

    def __init__(
        self,
        *,
        store: SQLiteStore | None = None,
        trace_reader: TraceReader | None = None,
        codex_analyzer: CodexTraceAnalyzer | None = None,
        use_langfuse: bool = False,
    ) -> None:
        """Create the debug API.

        Args:
            store: Optional SQLite store for local experiment runs and prompt
                oracles. Defaults to the research SQLite store.
            trace_reader: Optional trace source. Defaults to `LangSmithTraceReader`.
            codex_analyzer: Optional Codex analyzer. Defaults to
                `CodexTraceAnalyzer`.
            use_langfuse: Use legacy Langfuse Cloud instead of LangSmith when
                `trace_reader` is omitted.
        """

        self.store = store or SQLiteStore()
        self.trace_reader = trace_reader or (
            LangfuseTraceReader() if use_langfuse else LangSmithTraceReader()
        )
        self.codex_analyzer = codex_analyzer or CodexTraceAnalyzer()
        self.use_langfuse = use_langfuse

    def debug_run(self, run_id: str, *, use_codex: bool = False) -> ExperimentRun:
        """Debug a persisted local `ExperimentRun` and save `run.debug`.

        Args:
            run_id: Local run ID stored in `SQLiteStore`.
            use_codex: When true, add Codex-written trace interpretation.

        Returns:
            The reloaded `ExperimentRun` with `debug` populated.
        """

        run = self.store.load_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run id: {run_id}")

        report = self._debug_loaded_run(run, use_codex=use_codex)
        self.store.save_run_debug(run.run_id, report)
        refreshed = self.store.load_run(run.run_id)
        if refreshed is None:
            raise RuntimeError(f"Debug report saved but run disappeared: {run.run_id}")
        return refreshed

    def langfuse_run_refs(
        self,
        *,
        limit: int | None = 20,
        page_size: int = 1000,
        from_start_time: str | datetime | None = None,
        to_start_time: str | datetime | None = None,
        observation_name: str | None = None,
        observation_type: str | None = None,
        environment: str | None = None,
    ) -> list[LangfuseRunRef]:
        """Return cloud trace references ordered by newest observation.

        This is the richer version of `list_run_ids(...)`: it includes latest
        observation timestamp, observation name, and observation ID for table
        displays or filtering.
        """

        list_run_refs = getattr(self.trace_reader, "list_run_refs", None)
        if not callable(list_run_refs):
            raise RuntimeError(
                "trace_reader must provide list_run_refs(); use LangSmithTraceReader "
                "or LangfuseTraceReader."
            )
        return list_run_refs(
            limit=limit,
            page_size=page_size,
            from_start_time=from_start_time,
            to_start_time=to_start_time,
            observation_name=observation_name,
            observation_type=observation_type,
            environment=environment,
        )

    def cloud_run_refs(self, **filters: Any) -> list[LangfuseRunRef]:
        """Return trace references from the configured cloud backend."""

        return self.langfuse_run_refs(**filters)

    def list_run_ids(self, *, limit: int | None = 20, **filters: Any) -> list[str]:
        """List cloud trace IDs newest-first.

        Args:
            limit: Maximum unique trace IDs. Use `None` for all matching pages.
            **filters: Passed through to `cloud_run_refs(...)`.
        """

        return [
            ref.trace_id for ref in self.cloud_run_refs(limit=limit, **filters)
        ]

    def last_run_id(self, **filters: Any) -> str | None:
        """Return the newest cloud trace ID, or `None` if no runs match."""

        refs = self.cloud_run_refs(limit=1, **filters)
        return refs[0].trace_id if refs else None

    def last_k_run_ids(self, k: int, **filters: Any) -> list[str]:
        """Return the `k` newest cloud trace IDs."""

        if k < 1:
            return []
        return self.list_run_ids(limit=k, **filters)

    def all_run_ids(self, **filters: Any) -> list[str]:
        """Return all matching cloud trace IDs by paginating observations."""

        return self.list_run_ids(limit=None, **filters)

    def debug_trace(
        self,
        trace_id: str,
        *,
        prompt: str | None = None,
        strategy_name: str = "grammar",
        prompt_label: TestPromptLabel | None = None,
        expected_robo_grammar: dict[str, list[str]] | None = None,
        run_id: str | None = None,
        persist: bool = False,
        use_codex: bool = False,
    ) -> RunDebugReport:
        """Debug one cloud trace directly.

        The prompt is normally inferred from graph/root observation input, so
        the trace ID is enough for RoboGrammar traces. Pass `prompt=` or
        `expected_robo_grammar=` only for unusual traces or custom oracles.

        Args:
            trace_id: Langfuse trace ID.
            prompt: Optional prompt override when inference fails.
            strategy_name: Strategy label used in the synthetic run metadata.
            prompt_label: Optional registered prompt label to guide oracle inference.
            expected_robo_grammar: Optional expected structural-rule oracle.
            run_id: Optional synthetic run ID; defaults to `trace_id`.
            persist: Save the synthetic run and debug report to `SQLiteStore`.
            use_codex: Add per-trace Codex interpretation.
        """

        trace = self.trace_reader.fetch_trace(trace_id)
        resolved_prompt = prompt or extract_prompt_from_trace(trace)
        if not resolved_prompt:
            raise ValueError(
                "Could not infer prompt from cloud trace input; pass prompt= explicitly."
            )

        now = datetime.now(timezone.utc)
        run = ExperimentRun(
            run_id=run_id or trace_id,
            experiment_id="cloud-trace",
            strategy_name=strategy_name,
            prompt=resolved_prompt,
            config=StrategyConfig(seed=0, model_id="", max_candidates=0),
            repro=ReproEnvelope(
                seed=0,
                model_id="",
                prompt_hash="",
                strategy_name=strategy_name,
                strategy_version="unknown",
            ),
            started_at=now,
            finished_at=now,
            prompt_label=prompt_label,
            langfuse_trace_id=trace_id if self.use_langfuse else None,
            langsmith_trace_id=None if self.use_langfuse else trace_id,
        )
        report = self._debug_loaded_run(
            run,
            trace=trace,
            expected_robo_grammar=expected_robo_grammar,
            use_codex=use_codex,
        )
        if persist:
            self.store.save_experiment(
                Experiment(experiment_id=run.experiment_id, name="cloud-trace")
            )
            self.store.save_run(run)
            self.store.save_run_debug(run.run_id, report)
        return report

    def batch_debug_trace(
        self,
        trace_ids: list[str] | tuple[str, ...],
        *,
        strategy_name: str = "grammar",
        prompt_labels: dict[str, TestPromptLabel] | None = None,
        expected_robo_grammars: dict[str, dict[str, list[str]]] | None = None,
    ) -> BatchDebugReport:
        """Debug many cloud traces and run one Codex analysis over the batch.

        Use this when you want cross-run failure patterns such as repeated
        evaluator misses, systematic builder over-generation, or weak proxy
        criteria. Per-run reports are computed deterministically first; Codex
        then receives the whole batch once.

        Args:
            trace_ids: Trace IDs to fetch and compare as one batch.
            strategy_name: Strategy label used in synthetic run metadata.
            prompt_labels: Optional mapping from trace ID to prompt label.
            expected_robo_grammars: Optional mapping from trace ID to explicit
                expected structural-rule oracle.
        """

        traces: list[dict[str, Any]] = []
        reports: list[RunDebugReport] = []
        for trace_id in trace_ids:
            trace = self.trace_reader.fetch_trace(trace_id)
            traces.append(trace)
            prompt = extract_prompt_from_trace(trace)
            if not prompt:
                raise ValueError(
                    f"Could not infer prompt from cloud trace {trace_id}; "
                    "debug traces individually with prompt= first."
                )
            now = datetime.now(timezone.utc)
            run = ExperimentRun(
                run_id=trace_id,
                experiment_id="cloud-trace",
                strategy_name=strategy_name,
                prompt=prompt,
                config=StrategyConfig(seed=0, model_id="", max_candidates=0),
                repro=ReproEnvelope(
                    seed=0,
                    model_id="",
                    prompt_hash="",
                    strategy_name=strategy_name,
                    strategy_version="unknown",
                ),
                started_at=now,
                finished_at=now,
                prompt_label=(prompt_labels or {}).get(trace_id),
                langfuse_trace_id=trace_id if self.use_langfuse else None,
                langsmith_trace_id=None if self.use_langfuse else trace_id,
            )
            reports.append(
                self._debug_loaded_run(
                    run,
                    trace=trace,
                    expected_robo_grammar=(expected_robo_grammars or {}).get(trace_id),
                    use_codex=False,
                )
            )
        analysis = self.codex_analyzer.analyze_batch(reports=reports, traces=traces)
        return BatchDebugReport(
            trace_ids=tuple(trace_ids),
            reports=tuple(reports),
            summary=self.summarize(reports),
            codex_batch_analysis=analysis,
        )

    def _debug_loaded_run(
        self,
        run: ExperimentRun,
        *,
        trace: dict[str, Any] | None = None,
        expected_robo_grammar: dict[str, list[str]] | None = None,
        use_codex: bool = False,
    ) -> RunDebugReport:
        """Build a `RunDebugReport` for an already-loaded run and trace.

        This internal helper centralizes oracle lookup, rule extraction,
        confusion counting, compile/evaluator failure extraction, proxy checks,
        and optional per-trace Codex analysis.
        """

        prompt_record = self.store.get_test_prompt(run.prompt)
        expected = expected_robo_grammar or (
            prompt_record.get("expected_robo_grammar")
            if prompt_record
            else infer_expected_robo_grammar(run.prompt, run.prompt_label)
        )
        expected = _normalize_rules(expected)

        run_trace_id = run.langsmith_trace_id or run.langfuse_trace_id
        trace = trace or (
            self.trace_reader.fetch_trace(run_trace_id)
            if run_trace_id
            else {"trace_id": None, "observations": []}
        )
        observations = _observations(trace)
        observed = extract_robo_grammar_from_trace(trace)
        grammar_eval = evaluate_robo_grammar(expected, observed)
        failures = [
            *grammar_eval.node_failures,
            *_compile_failures(observations),
            *_evaluator_failures(observations, grammar_eval.confusion),
        ]
        proxy_checks = _proxy_checks(observations, expected)
        codex_analysis = (
            self.codex_analyzer.analyze(
                run=run,
                trace=trace,
                expected=expected,
                observed=observed,
                deterministic_failures=failures,
            )
            if use_codex
            else None
        )
        return RunDebugReport(
            run_id=run.run_id,
            strategy_name=run.strategy_name,
            langfuse_trace_id=run.langfuse_trace_id,
            langsmith_trace_id=run.langsmith_trace_id,
            expected_robo_grammar=expected,
            observed_robo_grammar=observed,
            confusion=grammar_eval.confusion,
            node_failures=failures,
            proxy_checks=proxy_checks,
            observation_count=len(observations),
            codex_analysis=codex_analysis,
        )

    def debug_experiment(
        self,
        experiment_id: str,
        *,
        only_failed: bool = False,
        use_codex: bool = False,
    ) -> list[RunDebugReport]:
        """Debug every run in a persisted experiment.

        Args:
            experiment_id: Local experiment ID.
            only_failed: If true, include only reports with run errors or debug
                failures.
            use_codex: Add per-run Codex interpretation for each run.
        """

        reports: list[RunDebugReport] = []
        for run in self.store.list_runs(experiment_id):
            debugged = self.debug_run(run.run_id, use_codex=use_codex)
            if debugged.debug is None:
                continue
            if only_failed and run.error is None and not _report_failed(debugged.debug):
                continue
            reports.append(debugged.debug)
        return reports

    @staticmethod
    def summarize(reports: list[RunDebugReport]) -> dict[str, Any]:
        """Aggregate a list of run debug reports into counts and failure rates."""

        failed = [
            report
            for report in reports
            if report.confusion.false_positives or report.confusion.false_negatives
        ]
        by_node = Counter(
            failure.get("pipeline_node", "unknown")
            for report in reports
            for failure in report.node_failures
        )
        return {
            "runs": len(reports),
            "failed_runs": len(failed),
            "failure_rate": len(failed) / len(reports) if reports else 0.0,
            "false_positives": sum(r.confusion.false_positives for r in reports),
            "false_negatives": sum(r.confusion.false_negatives for r in reports),
            "node_failure_counts": dict(by_node),
        }

    @staticmethod
    def node_failure_rows(reports: list[RunDebugReport]) -> list[dict[str, Any]]:
        """Flatten report node failures into table-friendly row dictionaries."""

        rows: list[dict[str, Any]] = []
        for report in reports:
            for failure in report.node_failures:
                rows.append(
                    {
                        "run_id": report.run_id,
                        "strategy_name": report.strategy_name,
                        "langsmith_trace_id": report.langsmith_trace_id,
                        "langfuse_trace_id": report.langfuse_trace_id,
                        **failure,
                    }
                )
        return rows


def evaluate_robo_grammar(
    expected: dict[str, list[str]],
    observed: dict[str, list[str]],
    *,
    node_universe: set[str] | None = None,
) -> RoboGrammarEval:
    """Compare expected and observed RoboGrammar rules as multiset edges.

    Args:
        expected: Expected structural rules keyed by left-hand-side node.
        observed: Rules extracted from a trace or model output.
        node_universe: Optional set of all possible grammar nodes; when given,
            unused nodes contribute to `true_negatives`.

    Returns:
        `RoboGrammarEval` with confusion counts and node-level FP/FN rows.
    """

    expected_counts = _edge_counts(expected)
    observed_counts = _edge_counts(observed)
    keys = set(expected_counts) | set(observed_counts)
    true_positives = sum(min(expected_counts[key], observed_counts[key]) for key in keys)
    false_positives = sum(max(0, observed_counts[key] - expected_counts[key]) for key in keys)
    false_negatives = sum(max(0, expected_counts[key] - observed_counts[key]) for key in keys)
    used_nodes = {
        node
        for _lhs, node in keys
    }
    true_negatives = len((node_universe or set()) - used_nodes)
    failures: list[dict[str, Any]] = []
    for lhs, node in sorted(keys):
        expected_count = expected_counts[(lhs, node)]
        observed_count = observed_counts[(lhs, node)]
        if observed_count > expected_count:
            extra = observed_count - expected_count
            failures.append(
                {
                    "pipeline_node": "build_structural_rules",
                    "grammar_node": node,
                    "kind": "false_positive",
                    "expected_count": expected_count,
                    "observed_count": observed_count,
                    "message": f"build_structural_rules produced {extra} extra {node} edge(s).",
                }
            )
        elif expected_count > observed_count:
            missing = expected_count - observed_count
            failures.append(
                {
                    "pipeline_node": "build_structural_rules",
                    "grammar_node": node,
                    "kind": "false_negative",
                    "expected_count": expected_count,
                    "observed_count": observed_count,
                    "message": f"build_structural_rules missed {missing} expected {node} edge(s).",
                }
            )
    return RoboGrammarEval(
        expected=expected,
        observed=observed,
        confusion=ConfusionMatrix(
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            true_negatives=true_negatives,
        ),
        node_failures=failures,
    )


def extract_robo_grammar_from_trace(trace: dict[str, Any]) -> dict[str, list[str]]:
    """Extract the best available structural rules from a Langfuse trace.

    Preference order is resolver output, rule-builder output, then root graph
    output. Returns normalized `{lhs: [rhs_nodes...]}` rules or `{}`.
    """

    observations = _observations(trace)
    preferred_names = (
        "resolve_grammar_node_names",
        "build_structural_rules",
        "robogrammar.structural_rule_graph",
    )
    for name in preferred_names:
        for observation in reversed(observations):
            if observation.get("name") == name:
                rules = _rules_from_observation(observation)
                if rules:
                    return rules
    for observation in reversed(observations):
        rules = _rules_from_observation(observation)
        if rules:
            return rules
    return {}


def extract_prompt_from_trace(trace: dict[str, Any]) -> str | None:
    """Find the user prompt from Langfuse trace or observation IO.

    Searches trace-level input/metadata first, then observation input,
    metadata, and output. Handles dicts, lists, JSON strings, and strings with
    embedded JSON.
    """

    for value in (trace.get("input"), trace.get("metadata")):
        prompt = _prompt_from_value(_loads_maybe_json(value))
        if prompt:
            return prompt
    for observation in _observations(trace):
        for key in ("input", "metadata", "output"):
            prompt = _prompt_from_value(_loads_maybe_json(observation.get(key)))
            if prompt:
                return prompt
    return None


def _edge_counts(rules: dict[str, list[str]]) -> Counter[tuple[str, str]]:
    """Count `(lhs, rhs_node)` edges in normalized structural rules."""

    counts: Counter[tuple[str, str]] = Counter()
    for lhs, rhs in rules.items():
        for node in rhs:
            counts[(lhs, node)] += 1
    return counts


def _rules_from_observation(observation: dict[str, Any]) -> dict[str, list[str]]:
    """Extract normalized structural rules from one observation's output/input."""

    for key in ("output", "input"):
        rules = _extract_rules(_loads_maybe_json(observation.get(key)))
        if rules:
            return rules
    return {}


def _extract_rules(value: Any) -> dict[str, list[str]]:
    """Extract a structural-rule mapping from raw JSON-like observation data."""

    value = _loads_maybe_json(value)
    if isinstance(value, str):
        for parsed in _json_objects_from_text(value):
            rules = _extract_rules(parsed)
            if rules:
                return rules
        return {}
    if isinstance(value, list):
        for item in reversed(value):
            rules = _extract_rules(item)
            if rules:
                return rules
        return {}
    if not isinstance(value, dict):
        return {}
    if "structural_rules" in value:
        return _extract_rules(value["structural_rules"])
    for nested in value.values():
        rules = _extract_rules(nested)
        if rules:
            return rules
    return _normalize_rules(value)


def _normalize_rules(value: Any) -> dict[str, list[str]]:
    """Normalize a mapping into `{str(lhs): list[str(rhs_node)]}` rules."""

    if not isinstance(value, dict):
        return {}
    rules: dict[str, list[str]] = {}
    for lhs, rhs in value.items():
        if isinstance(rhs, list) and all(isinstance(item, str) for item in rhs):
            rules[str(lhs)] = [str(item) for item in rhs]
    return rules


def _json_objects_from_text(value: str) -> list[Any]:
    """Return JSON objects embedded in text such as fenced model messages."""

    decoder = json.JSONDecoder()
    parsed_values: list[Any] = []
    for index, char in enumerate(value):
        if char not in "[{":
            continue
        try:
            parsed, _end = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        parsed_values.append(parsed)
    return parsed_values


def _loads_maybe_json(value: Any) -> Any:
    """Parse a JSON string when possible; otherwise return the original value."""

    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _prompt_from_value(value: Any) -> str | None:
    """Recursively find prompt-like fields inside JSON-like values."""

    if isinstance(value, dict):
        role = str(value.get("role") or value.get("type") or "").lower()
        content = value.get("content")
        if role in {"human", "user"} and isinstance(content, str):
            prompt = _prompt_from_text_content(content)
            if prompt:
                return prompt
        for key in ("prompt", "raw_prompt", "query_text"):
            prompt = value.get(key)
            if isinstance(prompt, str) and prompt.strip():
                return prompt.strip()
        for nested in value.values():
            prompt = _prompt_from_value(_loads_maybe_json(nested))
            if prompt:
                return prompt
    if isinstance(value, list):
        items = sorted(
            value,
            key=lambda item: 0
            if isinstance(item, dict)
            and str(item.get("role") or item.get("type") or "").lower() in {"human", "user"}
            else 1,
        )
        for item in items:
            prompt = _prompt_from_value(_loads_maybe_json(item))
            if prompt:
                return prompt
    if isinstance(value, str):
        loaded = _loads_maybe_json(value)
        if loaded is not value:
            return _prompt_from_value(loaded)
        prompt = _prompt_from_text_content(value)
        if prompt:
            return prompt
        decoder = json.JSONDecoder()
        for index, char in enumerate(value):
            if char not in "[{":
                continue
            try:
                parsed, _end = decoder.raw_decode(value[index:])
            except json.JSONDecodeError:
                continue
            prompt = _prompt_from_value(parsed)
            if prompt:
                return prompt
    return None


def _prompt_from_text_content(value: str) -> str | None:
    """Extract a user task from plain chat-message text."""

    stripped = value.strip()
    for marker in ("Task:", "task:"):
        index = stripped.find(marker)
        if index < 0:
            continue
        candidate = stripped[index + len(marker) :].strip().splitlines()[0].strip()
        return candidate or None
    return None


def _format_langfuse_time(value: str | datetime) -> str:
    """Format a string/datetime for Langfuse datetime query parameters."""

    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _batch_summary_payload(reports: list[RunDebugReport]) -> dict[str, Any]:
    """Build the compact batch summary sent to Codex batch analysis."""

    by_node = Counter(
        failure.get("pipeline_node", "unknown")
        for report in reports
        for failure in report.node_failures
    )
    return {
        "runs": len(reports),
        "false_positives": sum(r.confusion.false_positives for r in reports),
        "false_negatives": sum(r.confusion.false_negatives for r in reports),
        "node_failure_counts": dict(by_node),
    }


def _report_payload(report: RunDebugReport) -> dict[str, Any]:
    """Convert a `RunDebugReport` into JSON-safe context for Codex."""

    return {
        "run_id": report.run_id,
        "strategy_name": report.strategy_name,
        "langsmith_trace_id": report.langsmith_trace_id,
        "langfuse_trace_id": report.langfuse_trace_id,
        "observation_count": report.observation_count,
        "expected_robo_grammar": report.expected_robo_grammar,
        "observed_robo_grammar": report.observed_robo_grammar,
        "confusion": {
            "true_positives": report.confusion.true_positives,
            "false_positives": report.confusion.false_positives,
            "false_negatives": report.confusion.false_negatives,
            "true_negatives": report.confusion.true_negatives,
            "precision": report.confusion.precision,
            "recall": report.confusion.recall,
            "f1": report.confusion.f1,
        },
        "node_failures": report.node_failures,
        "proxy_checks": report.proxy_checks,
    }


def _trace_payload(trace: dict[str, Any]) -> dict[str, Any]:
    """Trim a raw trace to observation fields useful for Codex analysis."""

    return {
        "trace_id": trace.get("trace_id"),
        "observations": [
            {
                "name": observation.get("name"),
                "type": observation.get("type"),
                "level": observation.get("level"),
                "statusMessage": observation.get("statusMessage"),
                "input": observation.get("input"),
                "output": observation.get("output"),
                "metadata": observation.get("metadata"),
            }
            for observation in _observations(trace)
        ],
    }


def _resolve_codex_command() -> str:
    """Resolve the Codex CLI executable for terminals and notebook kernels."""

    configured = os.environ.get("CODEX_CLI")
    if configured:
        return configured
    found = shutil.which("codex")
    if found:
        return found
    candidates = [
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
        Path.home() / ".local" / "bin" / "codex",
        Path.home() / ".codex" / "bin" / "codex",
    ]
    nvm_matches = sorted(
        glob.glob(str(Path.home() / ".nvm" / "versions" / "node" / "*" / "bin" / "codex")),
        reverse=True,
    )
    candidates.extend(Path(match) for match in nvm_matches)
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "codex"


def _optional_str(value: Any) -> str | None:
    """Convert non-None values to strings while preserving `None`."""

    return str(value) if value is not None else None


def _cloud_time(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value or "")


def _parse_cloud_time(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _run_metadata(run: Any) -> dict[str, Any]:
    metadata = getattr(run, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    extra = getattr(run, "extra", None)
    if isinstance(extra, dict) and isinstance(extra.get("metadata"), dict):
        return extra["metadata"]
    return {}


def _langsmith_run_to_observation(run: Any) -> dict[str, Any]:
    metadata = _run_metadata(run)
    run_type = str(getattr(run, "run_type", "") or "chain").upper()
    return {
        "id": str(getattr(run, "id", "") or ""),
        "traceId": str(getattr(run, "trace_id", "") or ""),
        "parentObservationId": _optional_str(getattr(run, "parent_run_id", None)),
        "name": str(getattr(run, "name", "") or ""),
        "type": run_type,
        "startTime": _cloud_time(getattr(run, "start_time", None)),
        "endTime": _cloud_time(getattr(run, "end_time", None)),
        "input": getattr(run, "inputs", None) or {},
        "output": getattr(run, "outputs", None) or {},
        "metadata": metadata,
        "level": "ERROR" if getattr(run, "error", None) else metadata.get("level", "DEFAULT"),
        "statusMessage": getattr(run, "error", None) or metadata.get("status_message", ""),
    }


def _observations(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Return observation dictionaries from supported trace payload shapes."""

    observations = trace.get("observations")
    if isinstance(observations, list):
        return [item for item in observations if isinstance(item, dict)]
    data = trace.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _compile_failures(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract compile-safety failures from `compile_structural_rules` spans."""

    failures: list[dict[str, Any]] = []
    for observation in observations:
        if observation.get("name") != "compile_structural_rules":
            continue
        output = _loads_maybe_json(observation.get("output"))
        if not isinstance(output, dict):
            continue
        invalid_nodes = output.get("invalid_grammar_nodes") or []
        compile_safe = bool(output.get("compile_safe"))
        if compile_safe and not invalid_nodes:
            continue
        failures.append(
            {
                "pipeline_node": "compile_structural_rules",
                "grammar_node": None,
                "kind": "compile_failure",
                "expected_count": 0,
                "observed_count": len(invalid_nodes) if isinstance(invalid_nodes, list) else 0,
                "message": "compile_structural_rules reported invalid grammar nodes.",
            }
        )
    return failures


def _evaluator_failures(
    observations: list[dict[str, Any]],
    confusion: ConfusionMatrix,
) -> list[dict[str, Any]]:
    """Infer evaluator false positives/negatives from criteria and oracle counts."""

    actual_failed = bool(confusion.false_positives or confusion.false_negatives)
    failures: list[dict[str, Any]] = []
    for observation in observations:
        if observation.get("name") != "evaluate_rules":
            continue
        output = _loads_maybe_json(observation.get("output"))
        criteria = output.get("criteria") if isinstance(output, dict) else None
        if not isinstance(criteria, list) or not criteria:
            continue
        evaluator_passed = all(bool(item.get("isSuccessful")) for item in criteria if isinstance(item, dict))
        if evaluator_passed and actual_failed:
            failures.append(
                {
                    "pipeline_node": "evaluate_rules",
                    "grammar_node": None,
                    "kind": "false_negative",
                    "expected_count": confusion.false_positives + confusion.false_negatives,
                    "observed_count": 0,
                    "message": "evaluate_rules passed a run with RoboGrammar oracle mismatches.",
                }
            )
        elif not evaluator_passed and not actual_failed:
            failures.append(
                {
                    "pipeline_node": "evaluate_rules",
                    "grammar_node": None,
                    "kind": "false_positive",
                    "expected_count": 0,
                    "observed_count": 1,
                    "message": "evaluate_rules flagged a run that matched the RoboGrammar oracle.",
                }
            )
    return failures


def _proxy_checks(
    observations: list[dict[str, Any]],
    expected: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Check whether checklist/evaluator criteria mention expected structures."""

    expected_tokens = _expected_proxy_tokens(expected)
    checks: list[dict[str, Any]] = []
    for observation in observations:
        if observation.get("name") not in {"make_initial_checklist", "evaluate_rules"}:
            continue
        output = _loads_maybe_json(observation.get("output"))
        criteria = output.get("criteria") if isinstance(output, dict) else None
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            description = str(criterion.get("description") or "")
            lowered = description.lower()
            matched = sorted(token for token in expected_tokens if token in lowered)
            checks.append(
                {
                    "pipeline_node": observation.get("name"),
                    "description": description,
                    "matched_expected_terms": matched,
                    "covers_expected_structure": bool(matched),
                }
            )
    return checks


def _expected_proxy_tokens(expected: dict[str, list[str]]) -> set[str]:
    """Derive lower-case semantic tokens from expected grammar nodes."""

    nodes = {node for rhs in expected.values() for node in rhs}
    tokens: set[str] = set()
    for node in nodes:
        lower = node.lower()
        tokens.update(part for part in lower.split("_") if part)
    if "CLIMBING_LEG_PAIR" in nodes:
        tokens.update({"climb", "stair", "contact"})
    if "LEG_PAIR" in nodes or "CLIMBING_LEG_PAIR" in nodes:
        tokens.update({"leg", "quadruped", "hexapod"})
    if "BODY_CHAIN" in nodes:
        tokens.update({"chain", "crawl", "pipe", "duct", "segment"})
    if "MANIPULATION_MODULE" in nodes:
        tokens.update({"manipulation", "grip", "object", "tool"})
    return tokens


def _report_failed(report: RunDebugReport) -> bool:
    """Return true when a debug report contains any failure evidence."""

    return bool(
        report.confusion.false_positives
        or report.confusion.false_negatives
        or report.node_failures
    )


def _last_json_object(stdout: str) -> dict[str, Any]:
    """Parse the last JSON object emitted by `codex exec` stdout."""

    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return {
        "summary": stdout.strip(),
        "failure_hypotheses": [],
        "node_failure_notes": [],
        "proxy_quality_notes": [],
    }
