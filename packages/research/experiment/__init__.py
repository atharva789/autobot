"""Experiment tracking, task registries, and comparison."""

from packages.research.experiment.comparison import (
    ComparisonRow,
    compare_runs,
    compare_runs_by_prompt_label,
    format_comparison_table,
    format_grouped_comparison_tables,
)
from packages.research.experiment.types import (
    BatchDebugReport,
    ConfusionMatrix,
    Experiment,
    ExperimentRun,
    LangfuseRunRef,
    RoboGrammarEval,
    ReproEnvelope,
    RunDebugReport,
    TestPrompt,
    TestPromptLabel,
)

__all__ = [
    "ComparisonRow",
    "BatchDebugReport",
    "ConfusionMatrix",
    "Experiment",
    "ExperimentRun",
    "ExperimentRunner",
    "LangfuseRunRef",
    "RoboGrammarEval",
    "ReproEnvelope",
    "RunDebugAPI",
    "RunDebugReport",
    "TaskRegistry",
    "TestPrompt",
    "TestPromptLabel",
    "compare_runs",
    "compare_runs_by_prompt_label",
    "format_comparison_table",
    "format_grouped_comparison_tables",
]


def __getattr__(name: str) -> object:
    if name == "ExperimentRunner":
        from packages.research.experiment.runner import ExperimentRunner

        return ExperimentRunner
    if name == "TaskRegistry":
        from packages.research.experiment.task_registry import TaskRegistry

        return TaskRegistry
    if name == "RunDebugAPI":
        from packages.research.experiment.run_debug import RunDebugAPI

        return RunDebugAPI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
