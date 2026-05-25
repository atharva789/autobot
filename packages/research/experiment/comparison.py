"""Cross-run comparison utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from packages.research.experiment.types import ExperimentRun

if TYPE_CHECKING:
    from packages.research.storage.store import SQLiteStore


@dataclass(frozen=True)
class ComparisonRow:
    """One row in a comparison table."""

    run_id: str
    strategy_name: str
    prompt_label: str
    prompt_preview: str
    total_designs: int
    compile_rate: float
    stability_rate: float
    mean_screening_score: float
    link_count_entropy: float
    wall_time_seconds: float
    estimated_cost_usd: float


def compare_runs(
    runs: list[ExperimentRun],
    store: SQLiteStore,
) -> list[ComparisonRow]:
    """Build comparison rows from a list of runs."""
    rows: list[ComparisonRow] = []
    for run in runs:
        metrics = run.metrics_report or store.load_run_metrics(run.run_id)
        rows.append(
            ComparisonRow(
                run_id=run.run_id,
                strategy_name=run.strategy_name,
                prompt_label=run.prompt_label or "unlabeled",
                prompt_preview=run.prompt[:60],
                total_designs=metrics.total_designs if metrics else 0,
                compile_rate=metrics.compile_rate if metrics else 0.0,
                stability_rate=metrics.stability_rate if metrics else 0.0,
                mean_screening_score=(
                    metrics.mean_screening_score if metrics else 0.0
                ),
                link_count_entropy=(
                    metrics.link_count_entropy if metrics else 0.0
                ),
                wall_time_seconds=(
                    metrics.wall_time_seconds if metrics else 0.0
                ),
                estimated_cost_usd=(
                    metrics.estimated_cost_usd if metrics else 0.0
                ),
            )
        )
    return rows


def compare_runs_by_prompt_label(
    runs: list[ExperimentRun],
    store: SQLiteStore,
) -> dict[str, list[ComparisonRow]]:
    """Build comparison rows grouped by TestPrompt label."""
    grouped: dict[str, list[ComparisonRow]] = {}
    for row in compare_runs(runs, store):
        grouped.setdefault(row.prompt_label, []).append(row)
    return grouped


def format_comparison_table(
    rows: list[ComparisonRow],
    *,
    include_label: bool = False,
) -> str:
    """Format comparison rows as an aligned text table."""
    if not rows:
        return "No runs to compare."

    headers = [
        "Run ID",
        "Strategy",
        "Designs",
        "Compile%",
        "Stable%",
        "Score",
        "Entropy",
        "Time(s)",
    ]
    if include_label:
        headers.insert(2, "Label")
    col_widths = [max(len(h), 10) for h in headers]

    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, col_widths))]
    lines.append("  ".join("-" * w for w in col_widths))

    for r in rows:
        cells = [
            r.run_id[:10],
            r.strategy_name[:10],
            str(r.total_designs),
            f"{r.compile_rate:.0%}",
            f"{r.stability_rate:.0%}",
            f"{r.mean_screening_score:.3f}",
            f"{r.link_count_entropy:.2f}",
            f"{r.wall_time_seconds:.1f}",
        ]
        if include_label:
            cells.insert(2, r.prompt_label[:24])
        lines.append(
            "  ".join(c.ljust(w) for c, w in zip(cells, col_widths))
        )

    return "\n".join(lines)


def format_grouped_comparison_tables(
    grouped_rows: dict[str, list[ComparisonRow]],
) -> str:
    """Format comparison rows as one compact table per prompt label."""
    if not grouped_rows:
        return "No runs to compare."
    sections: list[str] = []
    for label, rows in grouped_rows.items():
        sections.append(f"[{label}]")
        sections.append(format_comparison_table(rows))
    return "\n\n".join(sections)
