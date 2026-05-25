"""Aggregate chunked RoboGrammar loop-comparison summaries and metrics."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

LOOPS = ("grammar", "compiler_centric", "compiler_feedback")


def main() -> None:
    args = _parse_args()
    summary = aggregate_chunks(
        _resolve_chunk_paths(args.chunk or [], args.chunk_glob or []),
        metrics_dir=Path(args.metrics_dir) if args.metrics_dir else None,
        expected_examples=args.expected_examples,
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.require_complete and not summary["coverage"]["complete"]:
        raise SystemExit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk", action="append", default=[])
    parser.add_argument(
        "--chunk-glob",
        action="append",
        default=[],
        help="Glob for chunk JSON files, for example 'evals/results/*chunk*.json'.",
    )
    parser.add_argument(
        "--metrics-dir",
        default=None,
        help="Directory containing <experiment_name>-metrics*.json files.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--expected-examples",
        type=int,
        default=701,
        help="Expected comparable example count for completion coverage.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Exit non-zero unless coverage.complete is true.",
    )
    args = parser.parse_args()
    if not args.chunk and not args.chunk_glob:
        parser.error("at least one --chunk or --chunk-glob is required")
    return args


def _resolve_chunk_paths(chunks: list[str], globs: list[str]) -> list[Path]:
    paths = [Path(path) for path in chunks]
    for pattern in globs:
        paths.extend(Path(path) for path in glob.glob(pattern))
    unique = sorted({path for path in paths}, key=lambda path: str(path))
    if not unique:
        raise SystemExit("No chunk files matched the requested inputs.")
    return unique


def aggregate_chunks(
    chunk_paths: list[Path],
    *,
    metrics_dir: Path | None = None,
    expected_examples: int = 701,
) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    totals = {
        loop: {
            "chunks": 0,
            "completed_chunks": 0,
            "examples": 0,
            "root_runs": 0,
            "compile_safe": 0,
            "compile_unsafe": 0,
            "errors": 0,
            "task_alignment_weighted_sum": 0.0,
            "task_alignment_weight": 0,
            "compiler_validity_weighted_sum": 0.0,
            "compiler_validity_weight": 0,
            "experiments": [],
        }
        for loop in LOOPS
    }

    for path in chunk_paths:
        chunk = json.loads(path.read_text())
        chunk_summary = _summarize_chunk(path, chunk, metrics_dir=metrics_dir)
        chunks.append(chunk_summary)
        for loop, loop_summary in chunk_summary["loops"].items():
            total = totals[loop]
            total["chunks"] += 1
            if loop_summary["status"] == "completed":
                total["completed_chunks"] += 1
            total["examples"] += int(chunk_summary["examples"])
            experiment_name = loop_summary.get("experiment_name")
            if experiment_name:
                total["experiments"].append(experiment_name)
            metrics = loop_summary.get("metrics") or {}
            root_runs = int(metrics.get("root_runs") or 0)
            total["root_runs"] += root_runs
            total["errors"] += int(metrics.get("errors") or 0)
            compile_statuses = metrics.get("compile_statuses") or {}
            total["compile_safe"] += int(compile_statuses.get("compile_safe") or 0)
            total["compile_unsafe"] += int(compile_statuses.get("compile_unsafe") or 0)
            _add_weighted_metric(
                total,
                metrics,
                value_key="mean_task_alignment",
                sum_key="task_alignment_weighted_sum",
                weight_key="task_alignment_weight",
                weight=root_runs,
            )
            _add_weighted_metric(
                total,
                metrics,
                value_key="mean_compiler_validity",
                sum_key="compiler_validity_weighted_sum",
                weight_key="compiler_validity_weight",
                weight=root_runs,
            )

    return {
        "chunks": chunks,
        "coverage": _coverage_summary(chunks, expected_examples=expected_examples),
        "totals": {
            loop: _finalize_total(total)
            for loop, total in totals.items()
        },
    }


def _summarize_chunk(
    path: Path,
    chunk: dict[str, Any],
    *,
    metrics_dir: Path | None,
) -> dict[str, Any]:
    loops: dict[str, Any] = {}
    chunk_loops = chunk.get("loops") or {}
    for loop in LOOPS:
        loop_payload = chunk_loops.get(loop) or {}
        experiment_name = loop_payload.get("experiment_name")
        status = loop_payload.get("status")
        if status is None:
            status = "completed" if experiment_name else "missing"
        loops[loop] = {
            "status": status,
            "experiment_name": experiment_name,
            "metrics": _load_metrics(metrics_dir, experiment_name),
        }
    return {
        "path": str(path),
        "dataset": chunk.get("dataset"),
        "examples": int(chunk.get("examples") or 0),
        "example_offset": int(chunk.get("example_offset") or 0),
        "provider": chunk.get("provider"),
        "model": chunk.get("model"),
        "loops": loops,
    }


def _load_metrics(metrics_dir: Path | None, experiment_name: str | None) -> dict[str, Any] | None:
    if metrics_dir is None or not experiment_name:
        return None
    for path in (
        metrics_dir / f"{experiment_name}-metrics.json",
        metrics_dir / f"{experiment_name}-metrics-first-page.json",
    ):
        if path.exists():
            payload = json.loads(path.read_text())
            if experiment_name in payload:
                return _normalize_metrics(payload[experiment_name])
            return _normalize_metrics(payload)
    return None


def _normalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metrics)
    if "root_runs" not in normalized and "root_runs_first_page" in normalized:
        normalized["root_runs"] = normalized["root_runs_first_page"]
    if "errors" not in normalized and "errors_first_page" in normalized:
        normalized["errors"] = normalized["errors_first_page"]
    if (
        "compile_statuses" not in normalized
        and "compile_statuses_first_page" in normalized
    ):
        normalized["compile_statuses"] = normalized["compile_statuses_first_page"]
    if (
        "mean_task_alignment" not in normalized
        and "mean_task_alignment_first_page" in normalized
    ):
        normalized["mean_task_alignment"] = normalized["mean_task_alignment_first_page"]
    if (
        "mean_compiler_validity" not in normalized
        and "mean_compiler_validity_first_page" in normalized
    ):
        normalized["mean_compiler_validity"] = normalized[
            "mean_compiler_validity_first_page"
        ]
    return normalized


def _coverage_summary(
    chunks: list[dict[str, Any]],
    *,
    expected_examples: int,
) -> dict[str, Any]:
    comparable_examples = 0
    comparable_chunks = 0
    incomplete_chunks: list[dict[str, Any]] = []
    offsets: list[int] = []
    for chunk in chunks:
        offset = int(chunk["example_offset"])
        offsets.append(offset)
        loop_statuses = {
            loop: chunk["loops"][loop]["status"]
            for loop in LOOPS
        }
        if all(status == "completed" for status in loop_statuses.values()):
            comparable_chunks += 1
            comparable_examples += int(chunk["examples"])
        else:
            incomplete_chunks.append(
                {
                    "path": chunk["path"],
                    "example_offset": offset,
                    "examples": chunk["examples"],
                    "loop_statuses": loop_statuses,
                }
            )
    return {
        "expected_examples": expected_examples,
        "chunk_count": len(chunks),
        "chunk_offsets": sorted(offsets),
        "comparable_chunks": comparable_chunks,
        "comparable_examples": comparable_examples,
        "incomplete_chunks": incomplete_chunks,
        "complete": comparable_examples >= expected_examples and not incomplete_chunks,
    }


def _add_weighted_metric(
    total: dict[str, Any],
    metrics: dict[str, Any],
    *,
    value_key: str,
    sum_key: str,
    weight_key: str,
    weight: int,
) -> None:
    value = metrics.get(value_key)
    if isinstance(value, int | float) and weight:
        total[sum_key] += float(value) * weight
        total[weight_key] += weight


def _finalize_total(total: dict[str, Any]) -> dict[str, Any]:
    task_weight = int(total.pop("task_alignment_weight"))
    compiler_weight = int(total.pop("compiler_validity_weight"))
    task_sum = float(total.pop("task_alignment_weighted_sum"))
    compiler_sum = float(total.pop("compiler_validity_weighted_sum"))
    total["mean_task_alignment"] = (
        round(task_sum / task_weight, 4) if task_weight else None
    )
    total["mean_compiler_validity"] = (
        round(compiler_sum / compiler_weight, 4) if compiler_weight else None
    )
    return total


if __name__ == "__main__":
    main()
