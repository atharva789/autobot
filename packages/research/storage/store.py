"""SQLite-backed experiment storage."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.research.benchmark.metrics import DesignMetrics, MetricsReport
from packages.research.experiment.types import (
    ConfusionMatrix,
    Experiment,
    ExperimentRun,
    ReproEnvelope,
    RunDebugReport,
    TestPrompt,
    TestPromptLabel,
)
from packages.research.strategy.protocol import StrategyConfig


class RunStore(Protocol):
    """Abstract interface for experiment persistence."""

    def save_experiment(self, exp: Experiment) -> None: ...
    def save_run(self, run: ExperimentRun) -> None: ...
    def save_designs(
        self, run_id: str, designs: list[RobotDesignIR]
    ) -> None: ...
    def save_metrics(self, run_id: str, report: MetricsReport) -> None: ...
    def load_experiment(self, experiment_id: str) -> Experiment | None: ...
    def find_experiment_by_name(self, name: str) -> Experiment | None: ...
    def load_run(self, run_id: str) -> ExperimentRun | None: ...
    def list_experiments(self) -> list[Experiment]: ...
    def list_runs(
        self, experiment_id: str, prompt_label: TestPromptLabel | None = None
    ) -> list[ExperimentRun]: ...
    def save_test_prompt(self, test_prompt: TestPrompt) -> TestPrompt: ...
    def list_test_prompts(
        self, label: TestPromptLabel | None = None
    ) -> list[TestPrompt]: ...
    def get_test_prompt(self, prompt: str) -> TestPrompt | None: ...
    def save_run_debug(self, run_id: str, debug: RunDebugReport) -> None: ...


_DEFAULT_DB_DIR = Path(__file__).parent.parent / ".runs"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class SQLiteStore:
    """SQLite-backed RunStore implementation."""

    def __init__(self, db_path: Path | None = None) -> None:
        db_dir = db_path.parent if db_path else _DEFAULT_DB_DIR
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path or (db_dir / "research.db")
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        schema = _SCHEMA_PATH.read_text()
        self._conn.executescript(schema)
        self._ensure_column("runs", "prompt_label", "TEXT")
        self._ensure_column("runs", "langsmith_trace_id", "TEXT")
        self._ensure_column("runs", "langfuse_trace_id", "TEXT")
        self._ensure_column("runs", "debug_json", "TEXT")
        self._ensure_column("test_prompts", "expected_robo_grammar_json", "TEXT")
        self._ensure_unique_test_prompts()

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        if column in {row["name"] for row in rows}:
            return
        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        self._conn.commit()

    def _ensure_unique_test_prompts(self) -> None:
        self._conn.execute(
            """DELETE FROM test_prompts
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM test_prompts
                GROUP BY prompt
            )"""
        )
        self._conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_test_prompts_prompt_unique
            ON test_prompts(prompt)"""
        )
        self._conn.commit()

    def save_experiment(self, exp: Experiment) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO experiments (experiment_id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (
                exp.experiment_id,
                exp.name,
                exp.description,
                exp.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def save_run(self, run: ExperimentRun) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO runs
            (run_id, experiment_id, strategy_name, strategy_version, prompt, prompt_label,
             config_json, repro_json, started_at, finished_at, error,
             langsmith_trace_id, langfuse_trace_id, debug_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_id,
                run.experiment_id,
                run.strategy_name,
                run.repro.strategy_version,
                run.prompt,
                run.prompt_label,
                _serialize(dataclasses.asdict(run.config)),
                _serialize(dataclasses.asdict(run.repro)),
                run.started_at.isoformat(),
                run.finished_at.isoformat() if run.finished_at else None,
                run.error,
                run.langsmith_trace_id,
                run.langfuse_trace_id,
                _debug_to_json(run.debug),
            ),
        )
        self._conn.commit()

    def save_designs(
        self, run_id: str, designs: list[RobotDesignIR]
    ) -> None:
        for i, ir in enumerate(designs):
            design_id = f"{run_id}__d{i}"
            self._conn.execute(
                """INSERT OR REPLACE INTO designs
                (design_id, run_id, design_name, ir_json, mjcf_xml, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    design_id,
                    run_id,
                    ir.name,
                    _serialize(_ir_to_dict(ir)),
                    None,
                    None,
                ),
            )
        self._conn.commit()

    def save_metrics(self, run_id: str, report: MetricsReport) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO run_metrics (run_id, report_json) VALUES (?, ?)",
            (run_id, _serialize(dataclasses.asdict(report))),
        )
        self._conn.commit()

    def load_experiment(self, experiment_id: str) -> Experiment | None:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_experiment(row)

    def find_experiment_by_name(self, name: str) -> Experiment | None:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_experiment(row)

    def load_run(self, run_id: str) -> ExperimentRun | None:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_run(row)

    def list_experiments(self) -> list[Experiment]:
        rows = self._conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_experiment(r) for r in rows]

    def list_runs(
        self, experiment_id: str, prompt_label: TestPromptLabel | None = None
    ) -> list[ExperimentRun]:
        if prompt_label is None:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE experiment_id = ? ORDER BY started_at DESC",
                (experiment_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM runs
                WHERE experiment_id = ? AND prompt_label = ?
                ORDER BY started_at DESC""",
                (experiment_id, prompt_label),
            ).fetchall()
        return [_row_to_run(r) for r in rows]

    def list_runs_by_label(self, experiment_id: str) -> dict[str, list[ExperimentRun]]:
        grouped: dict[str, list[ExperimentRun]] = {}
        for run in self.list_runs(experiment_id):
            grouped.setdefault(run.prompt_label or "unlabeled", []).append(run)
        return grouped

    def save_test_prompt(self, test_prompt: TestPrompt) -> TestPrompt:
        expected = test_prompt.get("expected_robo_grammar") or {}
        self._conn.execute(
            """INSERT OR IGNORE INTO test_prompts
            (prompt_id, prompt, label, expected_robo_grammar_json, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (
                _test_prompt_id(test_prompt),
                test_prompt["prompt"],
                test_prompt["label"],
                _serialize(expected),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        if expected:
            self._conn.execute(
                """UPDATE test_prompts
                SET expected_robo_grammar_json = ?
                WHERE prompt = ? AND (
                    expected_robo_grammar_json IS NULL
                    OR expected_robo_grammar_json = ''
                    OR expected_robo_grammar_json = '{}'
                )""",
                (_serialize(expected), test_prompt["prompt"]),
            )
        self._conn.commit()
        row = self._conn.execute(
            """SELECT prompt, label, expected_robo_grammar_json
            FROM test_prompts WHERE prompt = ?""",
            (test_prompt["prompt"],),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Failed to persist test prompt: {test_prompt['prompt']}"
            )
        return _row_to_test_prompt(row)

    def list_test_prompts(
        self, label: TestPromptLabel | None = None
    ) -> list[TestPrompt]:
        if label is None:
            rows = self._conn.execute(
                """SELECT prompt, label, expected_robo_grammar_json
                FROM test_prompts ORDER BY rowid ASC"""
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT prompt, label, expected_robo_grammar_json FROM test_prompts
                WHERE label = ?
                ORDER BY rowid ASC""",
                (label,),
            ).fetchall()
        return [_row_to_test_prompt(row) for row in rows]

    def get_test_prompt(self, prompt: str) -> TestPrompt | None:
        row = self._conn.execute(
            """SELECT prompt, label, expected_robo_grammar_json
            FROM test_prompts WHERE prompt = ?""",
            (prompt,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_test_prompt(row)

    def save_run_debug(self, run_id: str, debug: RunDebugReport) -> None:
        self._conn.execute(
            "UPDATE runs SET debug_json = ? WHERE run_id = ?",
            (_debug_to_json(debug), run_id),
        )
        self._conn.commit()

    def load_run_metrics(self, run_id: str) -> MetricsReport | None:
        row = self._conn.execute(
            "SELECT report_json FROM run_metrics WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return _deserialize_metrics(json.loads(row["report_json"]))

    def close(self) -> None:
        self._conn.close()


def _serialize(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


def _deserialize_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _row_to_test_prompt(row: sqlite3.Row) -> TestPrompt:
    expected = _deserialize_json_object(row["expected_robo_grammar_json"])
    return {
        "prompt": row["prompt"],
        "label": row["label"],
        "expected_robo_grammar": {
            str(lhs): [str(node) for node in rhs]
            for lhs, rhs in expected.items()
            if isinstance(rhs, list)
        },
    }


def _debug_to_json(debug: RunDebugReport | None) -> str | None:
    if debug is None:
        return None
    return _serialize(dataclasses.asdict(debug))


def _debug_from_json(raw: str | None) -> RunDebugReport | None:
    data = _deserialize_json_object(raw)
    if not data:
        return None
    confusion_data = data.get("confusion") if isinstance(data.get("confusion"), dict) else {}
    return RunDebugReport(
        run_id=str(data.get("run_id") or ""),
        strategy_name=str(data.get("strategy_name") or ""),
        langfuse_trace_id=data.get("langfuse_trace_id"),
        langsmith_trace_id=data.get("langsmith_trace_id"),
        expected_robo_grammar=_normalize_rules(data.get("expected_robo_grammar")),
        observed_robo_grammar=_normalize_rules(data.get("observed_robo_grammar")),
        confusion=ConfusionMatrix(
            true_positives=int(confusion_data.get("true_positives") or 0),
            false_positives=int(confusion_data.get("false_positives") or 0),
            false_negatives=int(confusion_data.get("false_negatives") or 0),
            true_negatives=int(confusion_data.get("true_negatives") or 0),
        ),
        node_failures=_list_of_dicts(data.get("node_failures")),
        proxy_checks=_list_of_dicts(data.get("proxy_checks")),
        observation_count=int(data.get("observation_count") or 0),
        codex_analysis=(
            data["codex_analysis"]
            if isinstance(data.get("codex_analysis"), dict)
            else None
        ),
    )


def _normalize_rules(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    rules: dict[str, list[str]] = {}
    for lhs, rhs in value.items():
        if isinstance(rhs, list):
            rules[str(lhs)] = [str(node) for node in rhs]
    return rules


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _test_prompt_id(test_prompt: TestPrompt) -> str:
    blob = json.dumps({"prompt": test_prompt["prompt"]}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _ir_to_dict(ir: RobotDesignIR) -> dict[str, Any]:
    return {
        "name": ir.name,
        "version": ir.version,
        "source_candidate_id": ir.source_candidate_id,
        "links": [dataclasses.asdict(link) for link in ir.links],
        "joints": [dataclasses.asdict(joint) for joint in ir.joints],
        "sensors": [dataclasses.asdict(s) for s in ir.sensors],
    }


def _row_to_experiment(row: sqlite3.Row) -> Experiment:
    return Experiment(
        experiment_id=row["experiment_id"],
        name=row["name"],
        description=row["description"] or "",
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_run(row: sqlite3.Row) -> ExperimentRun:
    config_data = json.loads(row["config_json"])
    repro_data = json.loads(row["repro_json"])

    return ExperimentRun(
        run_id=row["run_id"],
        experiment_id=row["experiment_id"],
        strategy_name=row["strategy_name"],
        prompt=row["prompt"],
        config=StrategyConfig(
            seed=config_data.get("seed", 42),
            model_id=config_data.get("model_id", ""),
            max_candidates=config_data.get("max_candidates", 6),
            extra=config_data.get("extra", {}),
        ),
        repro=ReproEnvelope(
            seed=repro_data.get("seed", 42),
            model_id=repro_data.get("model_id", ""),
            prompt_hash=repro_data.get("prompt_hash", ""),
            strategy_name=repro_data.get("strategy_name", ""),
            strategy_version=repro_data.get("strategy_version", ""),
            git_sha=repro_data.get("git_sha", ""),
            prompt_template_hashes=repro_data.get("prompt_template_hashes", {}),
        ),
        started_at=datetime.fromisoformat(row["started_at"]),
        finished_at=(
            datetime.fromisoformat(row["finished_at"])
            if row["finished_at"]
            else None
        ),
        error=row["error"],
        prompt_label=row["prompt_label"] if "prompt_label" in row.keys() else None,
        langsmith_trace_id=(
            row["langsmith_trace_id"] if "langsmith_trace_id" in row.keys() else None
        ),
        langfuse_trace_id=(
            row["langfuse_trace_id"] if "langfuse_trace_id" in row.keys() else None
        ),
        debug=(
            _debug_from_json(row["debug_json"])
            if "debug_json" in row.keys()
            else None
        ),
    )


def _deserialize_metrics(data: dict[str, Any]) -> MetricsReport:
    per_design = tuple(
        DesignMetrics(
            design_name=d.get("design_name", ""),
            ir_valid=d.get("ir_valid", False),
            ir_errors=tuple(d.get("ir_errors", ())),
            mjcf_compiles=d.get("mjcf_compiles", False),
            zero_ctrl_stable=d.get("zero_ctrl_stable", False),
            actuator_coverage=d.get("actuator_coverage", False),
            no_self_collision=d.get("no_self_collision", False),
            screening_score=d.get("screening_score", 0.0),
            stability_score=d.get("stability_score", 0.0),
            reachability_score=d.get("reachability_score", 0.0),
            task_sanity_score=d.get("task_sanity_score", 0.0),
            link_count=d.get("link_count", 0),
            joint_count=d.get("joint_count", 0),
            actuated_joint_count=d.get("actuated_joint_count", 0),
            actuated_joint_ratio=d.get("actuated_joint_ratio", 0.0),
        )
        for d in data.get("per_design", ())
    )
    return MetricsReport(
        per_design=per_design,
        total_designs=data.get("total_designs", 0),
        compile_rate=data.get("compile_rate", 0.0),
        stability_rate=data.get("stability_rate", 0.0),
        mean_screening_score=data.get("mean_screening_score", 0.0),
        median_screening_score=data.get("median_screening_score", 0.0),
        link_count_entropy=data.get("link_count_entropy", 0.0),
        joint_count_entropy=data.get("joint_count_entropy", 0.0),
        morphology_families=data.get("morphology_families", {}),
        wall_time_seconds=data.get("wall_time_seconds", 0.0),
        llm_calls=data.get("llm_calls", 0),
        estimated_cost_usd=data.get("estimated_cost_usd", 0.0),
    )
