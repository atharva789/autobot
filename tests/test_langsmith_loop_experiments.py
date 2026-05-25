from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from evals.run_langsmith_loop_experiments import (
    _mark_interrupted,
    _select_examples,
    _write_summary,
)
from evals.summarize_loop_experiment_metrics import summarize_project


@dataclass
class FakeExample:
    outputs: dict[str, object]
    metadata: dict[str, object]


class FakeExampleClient:
    def __init__(self, examples: list[FakeExample]) -> None:
        self.examples = examples
        self.calls: list[tuple[int, int]] = []

    def list_examples(
        self,
        *,
        dataset_name: str,
        offset: int,
        limit: int,
    ) -> list[FakeExample]:
        assert dataset_name == "dataset"
        self.calls.append((offset, limit))
        return self.examples[offset : offset + limit]


class FakeRun:
    parent_run_id = None
    name = "Target"
    error = None

    def __init__(
        self,
        *,
        status: str = "success",
        compile_safe: bool = True,
        task_score: float = 1.0,
        compiler_score: float = 1.0,
        trace_id: str | None = "trace",
        attempts: int | None = 1,
    ) -> None:
        self.status = status
        self.outputs = {
            "compile_safe": compile_safe,
            "langsmith_trace_id": trace_id,
        }
        if attempts is not None:
            self.outputs["attempts"] = attempts
        self.feedback_stats = {
            "task_alignment": {"avg": task_score, "comments": ["task"]},
            "compiler_validity": {"avg": compiler_score, "comments": ["compile"]},
        }


class FakeRunClient:
    def __init__(self, runs: list[FakeRun]) -> None:
        self.runs = runs
        self.calls: list[tuple[int, int]] = []

    def list_runs(
        self,
        *,
        project_name: str,
        is_root: int,
        offset: int,
        limit: int,
    ) -> list[FakeRun]:
        assert project_name == "project"
        assert is_root == 1
        self.calls.append((offset, limit))
        return self.runs[offset : offset + limit]


def test_select_examples_applies_offset_after_filters() -> None:
    client = FakeExampleClient(
        [
            FakeExample({"expected_behavior": "reject"}, {"tag": "keep"}),
            FakeExample({"expected_behavior": "produce"}, {"tag": "skip"}),
            FakeExample({"expected_behavior": "produce"}, {"tag": "keep"}),
            FakeExample({"expected_behavior": "produce"}, {"tag": "keep"}),
            FakeExample({"expected_behavior": "produce"}, {"tag": "keep"}),
        ]
    )

    selected = _select_examples(
        client,
        dataset_name="dataset",
        limit=2,
        offset=1,
        expected_behavior="produce",
        tag="keep",
    )

    assert selected == client.examples[3:5]


def test_write_summary_persists_partial_json(tmp_path: Path) -> None:
    output = tmp_path / "summary.json"

    _write_summary({"loops": {"grammar": {"status": "running"}}}, str(output))

    assert output.read_text() == '{\n  "loops": {\n    "grammar": {\n      "status": "running"\n    }\n  }\n}\n'


def test_mark_interrupted_marks_current_loop() -> None:
    summary = {
        "loops": {
            "grammar": {"status": "completed"},
            "compiler_centric": {"status": "running"},
        }
    }

    _mark_interrupted(summary, signum=15, current_loop="compiler_centric")

    assert summary["interrupted_signal"] == 15
    assert "interrupted_at" in summary
    assert summary["loops"]["grammar"] == {"status": "completed"}
    assert summary["loops"]["compiler_centric"]["status"] == "interrupted"
    assert (
        summary["loops"]["compiler_centric"]["interrupted_at"]
        == summary["interrupted_at"]
    )


def test_summarize_project_respects_max_pages() -> None:
    runs = [
        FakeRun(compile_safe=True, task_score=1.0, compiler_score=1.0, attempts=1),
        FakeRun(compile_safe=False, task_score=0.5, compiler_score=0.0, attempts=2),
        FakeRun(status="pending", compile_safe=True, task_score=0.25, compiler_score=1.0),
    ]
    client = FakeRunClient(runs)

    summary = summarize_project(client, "project", max_pages=1, page_size=2)

    assert client.calls == [(0, 2)]
    assert summary["root_runs"] == 2
    assert summary["pages_requested"] == 1
    assert summary["run_statuses"] == {"success": 2}
    assert summary["compile_statuses"] == {"compile_safe": 1, "compile_unsafe": 1}
    assert summary["mean_task_alignment"] == 0.75
    assert summary["mean_compiler_validity"] == 0.5
    assert summary["langsmith_trace_ids_present"] == 2
    assert summary["attempts"] == {"count": 2, "mean": 1.5, "min": 1, "max": 2}
