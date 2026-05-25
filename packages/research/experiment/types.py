"""Experiment, run, and reproducibility types."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.research.benchmark.metrics import MetricsReport
from packages.research.strategy.protocol import StrategyConfig

TestPromptLabel = Literal[
    "morphlogy-provided",
    "infer-morphology-single",
    "infer-morphology-family",
    "open-ended",
]


class TestPrompt(TypedDict):
    """Registered benchmark prompt plus optional expected RoboGrammar oracle.

    Use this shape with `TaskRegistry.register(...)` or
    `ExperimentRunner.run_suite(...)`. If `expected_robo_grammar` is omitted,
    the registry can infer a deterministic oracle for common prompt families.
    """

    prompt: str
    label: TestPromptLabel
    expected_robo_grammar: NotRequired[dict[str, list[str]]]


TestPrompt.__test__ = False


def _git_sha() -> str:
    """Return the current git commit SHA for reproducibility metadata."""

    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


@dataclass(frozen=True)
class ConfusionMatrix:
    """Multiset confusion counts for one generated RoboGrammar structure.

    Counts are computed over `(lhs, rhs_node)` structural-rule edges. Use the
    `precision`, `recall`, and `f1` properties for quick aggregate quality
    checks across one run or a batch.
    """

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0

    @property
    def precision(self) -> float:
        """Fraction of produced edges that were expected."""

        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        """Fraction of expected edges that were produced."""

        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall."""

        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0


@dataclass(frozen=True)
class RoboGrammarEval:
    """Expected-vs-observed structural-rule evaluation.

    Returned by `evaluate_robo_grammar(...)`; contains the normalized expected
    and observed rules, multiset confusion counts, and node-level failure rows
    that explain false positives and false negatives.
    """

    expected: dict[str, list[str]]
    observed: dict[str, list[str]]
    confusion: ConfusionMatrix
    node_failures: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RunDebugReport:
    """Trace-derived diagnostic report for one Langfuse or persisted run.

    `RunDebugAPI.debug_trace(...)` and `debug_run(...)` return this type. It
    compares expected RoboGrammar rules against rules extracted from the trace,
    lists node-level failures and proxy checks, and optionally includes Codex
    analysis when `use_codex=True`.
    """

    run_id: str
    strategy_name: str
    langfuse_trace_id: str | None
    expected_robo_grammar: dict[str, list[str]]
    observed_robo_grammar: dict[str, list[str]]
    confusion: ConfusionMatrix
    node_failures: list[dict[str, Any]] = field(default_factory=list)
    proxy_checks: list[dict[str, Any]] = field(default_factory=list)
    observation_count: int = 0
    codex_analysis: dict[str, Any] | None = None
    langsmith_trace_id: str | None = None

    def to_vertical_text(self, *, max_items: int = 8) -> str:
        """Return a notebook-friendly multiline summary.

        Args:
            max_items: Maximum list entries to print for long sections such as
                `node_failures`, `proxy_checks`, and Codex hypotheses.
        """

        lines = [
            "RunDebugReport",
            f"  run_id: {self.run_id}",
            f"  strategy_name: {self.strategy_name}",
            f"  langsmith_trace_id: {self.langsmith_trace_id}",
            f"  langfuse_trace_id: {self.langfuse_trace_id}",
            f"  observation_count: {self.observation_count}",
            "  confusion:",
            f"    true_positives: {self.confusion.true_positives}",
            f"    false_positives: {self.confusion.false_positives}",
            f"    false_negatives: {self.confusion.false_negatives}",
            f"    true_negatives: {self.confusion.true_negatives}",
            f"    precision: {self.confusion.precision:.3f}",
            f"    recall: {self.confusion.recall:.3f}",
            f"    f1: {self.confusion.f1:.3f}",
            "  expected_robo_grammar:",
            *_indent_json(self.expected_robo_grammar, 4),
            "  observed_robo_grammar:",
            *_indent_json(self.observed_robo_grammar, 4),
            _format_count_header("node_failures", self.node_failures, max_items),
            *_format_dict_items(self.node_failures, max_items=max_items, indent=4),
            _format_count_header("proxy_checks", self.proxy_checks, max_items),
            *_format_dict_items(self.proxy_checks, max_items=max_items, indent=4),
        ]
        if self.codex_analysis:
            summary = self.codex_analysis.get("summary")
            lines.extend(
                [
                    "  codex_analysis:",
                    f"    summary: {summary}" if summary else "    summary: None",
                ]
            )
            hypotheses = self.codex_analysis.get("failure_hypotheses")
            if isinstance(hypotheses, list):
                lines.append(_format_count_header("failure_hypotheses", hypotheses, max_items, indent=4))
                lines.extend(_format_scalar_items(hypotheses, max_items=max_items, indent=6))
        return "\n".join(lines)

    def __str__(self) -> str:
        """Render the report vertically for `print(report)`."""

        return self.to_vertical_text()

    def __repr__(self) -> str:
        """Render the report vertically in plain Python and notebook outputs."""

        return self.to_vertical_text()

    def _repr_pretty_(self, printer: Any, cycle: bool) -> None:
        """IPython pretty-printer hook used for final-cell notebook display."""

        if cycle:
            printer.text("RunDebugReport(...)")
            return
        printer.text(self.to_vertical_text())


@dataclass(frozen=True)
class BatchDebugReport:
    """Batch-level trace diagnostics from one Codex pass over many runs.

    Returned by `RunDebugAPI.batch_debug_trace(trace_ids)`. Use `reports` for
    per-trace deterministic debug reports and `codex_batch_analysis` for
    cross-run patterns found by one batch-level Codex analysis.
    """

    trace_ids: tuple[str, ...]
    reports: tuple[RunDebugReport, ...]
    summary: dict[str, Any]
    codex_batch_analysis: dict[str, Any]

    def to_vertical_text(self, *, max_items: int = 8) -> str:
        """Return a notebook-friendly multiline batch summary.

        Args:
            max_items: Maximum number of trace IDs or pattern bullets to show
                before truncating with a remaining-count line.
        """

        lines = [
            "BatchDebugReport",
            f"  trace_ids: {len(self.trace_ids)}",
            *_format_scalar_items(list(self.trace_ids), max_items=max_items, indent=4),
            "  summary:",
            *_indent_json(self.summary, 4),
            "  codex_batch_analysis:",
            f"    summary: {self.codex_batch_analysis.get('summary')}",
        ]
        for key in (
            "cross_run_patterns",
            "node_failure_patterns",
            "proxy_quality_patterns",
            "recommended_next_actions",
        ):
            values = self.codex_batch_analysis.get(key)
            if isinstance(values, list):
                lines.append(_format_count_header(key, values, max_items, indent=4))
                lines.extend(_format_scalar_items(values, max_items=max_items, indent=6))
        return "\n".join(lines)

    def __str__(self) -> str:
        """Render the batch report vertically for `print(batch_report)`."""

        return self.to_vertical_text()

    def __repr__(self) -> str:
        """Render the batch report vertically in plain Python and notebooks."""

        return self.to_vertical_text()

    def _repr_pretty_(self, printer: Any, cycle: bool) -> None:
        """IPython pretty-printer hook used for final-cell notebook display."""

        if cycle:
            printer.text("BatchDebugReport(...)")
            return
        printer.text(self.to_vertical_text())


@dataclass(frozen=True)
class LangfuseRunRef:
    """A Langfuse trace/run reference ordered by its newest observation.

    Returned by `RunDebugAPI.langfuse_run_refs(...)`. Use `trace_id` with
    `debug_trace(...)` or `batch_debug_trace(...)`; use the timestamp/name
    fields for table displays and quick inspection.
    """

    trace_id: str
    last_observation_at: str
    latest_observation_name: str | None = None
    latest_observation_id: str | None = None


def _indent_json(value: Any, indent: int) -> list[str]:
    """Format a JSON-like value as indented lines for vertical report output."""

    prefix = " " * indent
    text = json.dumps(value, indent=2, sort_keys=True)
    return [f"{prefix}{line}" for line in text.splitlines()]


def _format_count_header(
    name: str,
    values: list[Any],
    max_items: int,
    *,
    indent: int = 2,
) -> str:
    """Return a compact section header that includes truncation information."""

    shown = min(len(values), max_items)
    suffix = f" showing {shown}/{len(values)}" if len(values) > max_items else str(len(values))
    return f"{' ' * indent}{name}: {suffix}"


def _format_dict_items(
    values: list[dict[str, Any]],
    *,
    max_items: int,
    indent: int,
) -> list[str]:
    """Format a list of dictionaries as numbered, indented report lines."""

    lines: list[str] = []
    prefix = " " * indent
    for index, item in enumerate(values[:max_items], start=1):
        lines.append(f"{prefix}- #{index}")
        for key, value in item.items():
            lines.append(f"{prefix}  {key}: {value}")
    if len(values) > max_items:
        lines.append(f"{prefix}... {len(values) - max_items} more")
    return lines


def _format_scalar_items(
    values: list[Any],
    *,
    max_items: int,
    indent: int,
) -> list[str]:
    """Format a list of scalar values as indented bullet lines."""

    prefix = " " * indent
    lines = [f"{prefix}- {value}" for value in values[:max_items]]
    if len(values) > max_items:
        lines.append(f"{prefix}... {len(values) - max_items} more")
    return lines


@dataclass(frozen=True)
class ReproEnvelope:
    """Everything needed to reproduce or audit a run.

    Persisted with each `ExperimentRun`; captures model, seed, prompt hashes,
    strategy identity, and git SHA so comparisons can be traced back to the
    exact strategy/prompt state.
    """

    seed: int
    model_id: str
    prompt_hash: str
    strategy_name: str
    strategy_version: str
    git_sha: str = field(default_factory=_git_sha)
    prompt_template_hashes: dict[str, str] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """Return a short stable hash of the reproducibility envelope."""

        blob = json.dumps(
            {k: getattr(self, k) for k in self.__dataclass_fields__},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ExperimentRun:
    """One invocation of a generation strategy on one prompt.

    `ExperimentRunner.run(...)` creates this object and `SQLiteStore` persists
    it. The optional `langsmith_trace_id` links the local run to cloud traces;
    `langfuse_trace_id` is retained only for legacy imported/debugged runs.
    the optional `debug` field stores a `RunDebugReport`.
    """

    run_id: str
    experiment_id: str
    strategy_name: str
    prompt: str
    config: StrategyConfig
    repro: ReproEnvelope
    started_at: datetime
    finished_at: datetime | None = None
    designs: tuple[RobotDesignIR, ...] = ()
    metrics_report: MetricsReport | None = None
    error: str | None = None
    prompt_label: TestPromptLabel | None = None
    langsmith_trace_id: str | None = None
    langfuse_trace_id: str | None = None
    debug: RunDebugReport | None = None


@dataclass(frozen=True)
class Experiment:
    """A named collection of runs, typically used for strategy comparisons."""

    experiment_id: str
    name: str
    description: str = ""
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    runs: tuple[ExperimentRun, ...] = ()
