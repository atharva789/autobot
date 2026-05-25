"""Summarize LangSmith RoboGrammar loop-comparison experiment metrics."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv
from langsmith import Client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / ".env", override=False)
    client = Client()
    summaries = {
        project: summarize_project(
            client,
            project,
            max_pages=args.max_pages,
            page_size=args.page_size,
        )
        for project in args.project
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summaries, indent=2, sort_keys=True))
    print(json.dumps(summaries, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", action="append", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Maximum LangSmith pages to fetch per project. 0 means all pages.",
    )
    parser.add_argument("--page-size", type=int, default=100)
    return parser.parse_args()


def summarize_project(
    client: Client,
    project_name: str,
    *,
    max_pages: int = 0,
    page_size: int = 100,
) -> dict[str, Any]:
    root_runs = [
        run
        for run in _iter_project_runs(
            client,
            project_name,
            max_pages=max_pages,
            page_size=page_size,
        )
        if getattr(run, "parent_run_id", None) is None and run.name == "Target"
    ]
    task_scores: list[float] = []
    compiler_scores: list[float] = []
    run_statuses: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    errors = 0
    trace_ids = 0
    attempts: list[int] = []
    comments: dict[str, list[str]] = {
        "task_alignment": [],
        "compiler_validity": [],
    }
    for run in root_runs:
        run_statuses[str(getattr(run, "status", None))] += 1
        if getattr(run, "error", None):
            errors += 1
        outputs = run.outputs or {}
        statuses["compile_safe" if outputs.get("compile_safe") else "compile_unsafe"] += 1
        if outputs.get("langsmith_trace_id"):
            trace_ids += 1
        if isinstance(outputs.get("attempts"), int):
            attempts.append(outputs["attempts"])
        feedback = getattr(run, "feedback_stats", None) or {}
        _append_score(task_scores, feedback, "task_alignment")
        _append_score(compiler_scores, feedback, "compiler_validity")
        for key in comments:
            stats = feedback.get(key) or {}
            for comment in stats.get("comments") or []:
                if len(comments[key]) < 10:
                    comments[key].append(str(comment))
    return {
        "project_name": project_name,
        "root_runs": len(root_runs),
        "pages_requested": max_pages if max_pages else "all",
        "errors": errors,
        "run_statuses": dict(run_statuses),
        "mean_task_alignment": round(mean(task_scores), 4) if task_scores else None,
        "mean_compiler_validity": round(mean(compiler_scores), 4) if compiler_scores else None,
        "compile_statuses": dict(statuses),
        "langsmith_trace_ids_present": trace_ids,
        "attempts": {
            "count": len(attempts),
            "mean": round(mean(attempts), 4) if attempts else None,
            "min": min(attempts) if attempts else None,
            "max": max(attempts) if attempts else None,
        },
        "sample_comments": comments,
    }


def _iter_project_runs(
    client: Client,
    project_name: str,
    *,
    max_pages: int,
    page_size: int,
):
    offset = 0
    pages = 0
    while True:
        runs = list(
            client.list_runs(
                project_name=project_name,
                is_root=1,
                offset=offset,
                limit=page_size,
            )
        )
        if not runs:
            break
        yield from runs
        pages += 1
        if max_pages and pages >= max_pages:
            break
        offset += len(runs)


def _append_score(scores: list[float], feedback: dict[str, Any], key: str) -> None:
    stats = feedback.get(key)
    if not isinstance(stats, dict):
        return
    avg = stats.get("avg")
    if isinstance(avg, int | float):
        scores.append(float(avg))


if __name__ == "__main__":
    main()
