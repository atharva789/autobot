from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evals.aggregate_loop_comparison_chunks import aggregate_chunks, _resolve_chunk_paths


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def test_aggregate_chunks_combines_loop_metrics(tmp_path: Path) -> None:
    chunk = tmp_path / "chunk.json"
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    _write_json(
        chunk,
        {
            "dataset": "robogrammar-structural-rules-evals",
            "examples": 2,
            "example_offset": 25,
            "provider": "claude-code",
            "model": "claude-sonnet-4-5",
            "loops": {
                "grammar": {
                    "status": "completed",
                    "experiment_name": "grammar-exp",
                },
                "compiler_centric": {
                    "status": "completed",
                    "experiment_name": "centric-exp",
                },
                "compiler_feedback": {
                    "status": "interrupted",
                    "experiment_name": "feedback-exp",
                },
            },
        },
    )
    _write_json(
        metrics_dir / "grammar-exp-metrics-first-page.json",
        {
            "grammar-exp": {
                "root_runs": 2,
                "errors": 0,
                "compile_statuses": {"compile_safe": 2},
                "mean_task_alignment": 0.75,
                "mean_compiler_validity": 1.0,
            }
        },
    )
    _write_json(
        metrics_dir / "centric-exp-metrics-first-page.json",
        {
            "root_runs": 2,
            "errors": 1,
            "compile_statuses": {"compile_safe": 1, "compile_unsafe": 1},
            "mean_task_alignment": 0.5,
            "mean_compiler_validity": 0.5,
        },
    )

    summary = aggregate_chunks([chunk], metrics_dir=metrics_dir, expected_examples=2)

    grammar = summary["totals"]["grammar"]
    assert grammar["completed_chunks"] == 1
    assert grammar["examples"] == 2
    assert grammar["root_runs"] == 2
    assert grammar["compile_safe"] == 2
    assert grammar["mean_task_alignment"] == 0.75
    assert grammar["mean_compiler_validity"] == 1.0

    centric = summary["totals"]["compiler_centric"]
    assert centric["errors"] == 1
    assert centric["compile_safe"] == 1
    assert centric["compile_unsafe"] == 1
    assert centric["mean_task_alignment"] == 0.5

    feedback = summary["totals"]["compiler_feedback"]
    assert feedback["chunks"] == 1
    assert feedback["completed_chunks"] == 0
    assert feedback["experiments"] == ["feedback-exp"]
    assert feedback["mean_task_alignment"] is None
    assert summary["coverage"]["complete"] is False
    assert summary["coverage"]["comparable_examples"] == 0
    assert summary["coverage"]["incomplete_chunks"] == [
        {
            "path": str(chunk),
            "example_offset": 25,
            "examples": 2,
            "loop_statuses": {
                "grammar": "completed",
                "compiler_centric": "completed",
                "compiler_feedback": "interrupted",
            },
        }
    ]


def test_aggregate_chunks_reports_missing_loop() -> None:
    chunk = Path("chunk.json")
    payload = {
        "examples": 1,
        "loops": {
            "grammar": {
                "status": "completed",
                "experiment_name": "grammar-exp",
            }
        },
    }

    summary = aggregate_chunks_from_payload(chunk, payload)

    assert summary["chunks"][0]["loops"]["compiler_centric"]["status"] == "missing"
    assert summary["totals"]["compiler_centric"]["chunks"] == 1
    assert summary["totals"]["compiler_centric"]["completed_chunks"] == 0


def test_aggregate_chunks_treats_legacy_experiment_name_as_completed() -> None:
    summary = aggregate_chunks_from_payload(
        Path("legacy.json"),
        {
            "examples": 1,
            "loops": {
                "grammar": {
                    "experiment_name": "grammar-exp",
                }
            },
        },
    )

    assert summary["chunks"][0]["loops"]["grammar"]["status"] == "completed"
    assert summary["totals"]["grammar"]["completed_chunks"] == 1


def test_aggregate_chunks_normalizes_first_page_metric_schema(tmp_path: Path) -> None:
    chunk = tmp_path / "chunk.json"
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    _write_json(
        chunk,
        {
            "examples": 100,
            "loops": {
                "grammar": {
                    "status": "completed",
                    "experiment_name": "grammar-exp",
                }
            },
        },
    )
    _write_json(
        metrics_dir / "grammar-exp-metrics-first-page.json",
        {
            "root_runs_first_page": 100,
            "errors_first_page": 0,
            "compile_statuses_first_page": {"compile_safe": 81, "compile_unsafe": 19},
            "mean_task_alignment_first_page": 0.7357,
            "mean_compiler_validity_first_page": 0.8351,
        },
    )

    summary = aggregate_chunks([chunk], metrics_dir=metrics_dir)

    grammar = summary["totals"]["grammar"]
    assert grammar["root_runs"] == 100
    assert grammar["compile_safe"] == 81
    assert grammar["compile_unsafe"] == 19
    assert grammar["mean_task_alignment"] == 0.7357
    assert grammar["mean_compiler_validity"] == 0.8351


def test_resolve_chunk_paths_accepts_explicit_paths_and_globs(tmp_path: Path) -> None:
    first = tmp_path / "chunk_000.json"
    second = tmp_path / "chunk_025.json"
    first.write_text("{}")
    second.write_text("{}")

    paths = _resolve_chunk_paths(
        [str(second)],
        [str(tmp_path / "chunk_*.json")],
    )

    assert paths == [first, second]


def test_aggregate_chunks_marks_full_comparable_coverage_complete(tmp_path: Path) -> None:
    chunk = tmp_path / "chunk.json"
    _write_json(
        chunk,
        {
            "examples": 2,
            "loops": {
                "grammar": {"status": "completed", "experiment_name": "grammar-exp"},
                "compiler_centric": {
                    "status": "completed",
                    "experiment_name": "centric-exp",
                },
                "compiler_feedback": {
                    "status": "completed",
                    "experiment_name": "feedback-exp",
                },
            },
        },
    )

    summary = aggregate_chunks([chunk], expected_examples=2)

    assert summary["coverage"] == {
        "expected_examples": 2,
        "chunk_count": 1,
        "chunk_offsets": [0],
        "comparable_chunks": 1,
        "comparable_examples": 2,
        "incomplete_chunks": [],
        "complete": True,
    }


def test_cli_require_complete_exit_codes(tmp_path: Path) -> None:
    chunk = tmp_path / "chunk.json"
    _write_json(
        chunk,
        {
            "examples": 2,
            "loops": {
                "grammar": {"status": "completed", "experiment_name": "grammar-exp"},
                "compiler_centric": {
                    "status": "completed",
                    "experiment_name": "centric-exp",
                },
                "compiler_feedback": {
                    "status": "completed",
                    "experiment_name": "feedback-exp",
                },
            },
        },
    )
    command = [
        sys.executable,
        "evals/aggregate_loop_comparison_chunks.py",
        "--chunk",
        str(chunk),
        "--require-complete",
    ]

    complete = subprocess.run(
        [*command, "--expected-examples", "2"],
        check=False,
        capture_output=True,
        text=True,
    )
    incomplete = subprocess.run(
        [*command, "--expected-examples", "3"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert complete.returncode == 0
    assert json.loads(complete.stdout)["coverage"]["complete"] is True
    assert incomplete.returncode == 1
    assert json.loads(incomplete.stdout)["coverage"]["complete"] is False


def aggregate_chunks_from_payload(path: Path, payload: dict[str, object]) -> dict[str, object]:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        chunk_path = Path(tmpdir) / path
        _write_json(chunk_path, payload)
        return aggregate_chunks([chunk_path])
