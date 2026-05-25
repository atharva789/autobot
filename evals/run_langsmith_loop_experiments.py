"""Run LangSmith experiments comparing RoboGrammar agent-loop variants."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client, evaluate

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.run_langsmith_model_experiments import (
    DATASET_NAME,
    _compact_rule_builder_prompt,
    _configure_provider,
    compiler_evaluator,
    summary_task_alignment,
    task_alignment_evaluator,
)

COMPILER_VERSION = "compile-result-state.2026-05-25"
NOTEBOOK_PATH = ROOT / "packages/research/notebooks/rl_playground.ipynb"


def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / ".env", override=False)
    _configure_provider(args.provider)

    client = Client()
    examples = _select_examples(
        client,
        dataset_name=args.dataset,
        limit=args.limit,
        offset=args.offset,
        expected_behavior=args.expected_behavior,
        tag=args.tag,
    )
    if not examples:
        raise SystemExit("No dataset examples matched the requested filters.")

    summary: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": args.dataset,
        "examples": len(examples),
        "example_offset": args.offset,
        "provider": args.provider,
        "model": os.environ.get("RESEARCH_LLM_MODEL"),
        "max_attempts": args.max_attempts,
        "loops": {},
    }
    current_loop: str | None = None

    def record_interruption(signum: int, _frame: Any) -> None:
        _mark_interrupted(summary, signum=signum, current_loop=current_loop)
        _write_summary(summary, args.output)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, record_interruption)
    signal.signal(signal.SIGINT, record_interruption)

    for loop_name in args.loop:
        current_loop = loop_name
        summary["loops"][loop_name] = {
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
        }
        _write_summary(summary, args.output)
        results = evaluate(
            _predict_loop(loop_name, args.max_attempts),
            data=examples,
            evaluators=[task_alignment_evaluator, compiler_evaluator],
            summary_evaluators=[summary_task_alignment],
            experiment_prefix=_experiment_prefix(loop_name, args.provider),
            description=(
                f"RoboGrammar loop comparison for {loop_name} using "
                f"{args.provider} with compiler-result state."
            ),
            metadata={
                "compiler_version": COMPILER_VERSION,
                "provider": args.provider,
                "model": os.environ.get("RESEARCH_LLM_MODEL"),
                "max_attempts": args.max_attempts,
                "dataset": args.dataset,
                "example_limit": args.limit,
                "example_offset": args.offset,
                "expected_behavior": args.expected_behavior,
                "tag": args.tag,
                "loop": loop_name,
                "notebook_path": str(NOTEBOOK_PATH.relative_to(ROOT)),
            },
            max_concurrency=args.max_concurrency,
            client=client,
            error_handling="log",
        )
        summary["loops"][loop_name].update({
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "experiment_name": getattr(results, "experiment_name", None),
        })
        _write_summary(summary, args.output)
        current_loop = None

    print(json.dumps(summary, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["claude-code", "qwen"],
        default="claude-code",
    )
    parser.add_argument(
        "--loop",
        action="append",
        choices=["grammar", "compiler_centric", "compiler_feedback"],
        default=[],
        help="Loop variant to run. Can be repeated.",
    )
    parser.add_argument("--dataset", default=DATASET_NAME)
    parser.add_argument("--limit", type=int, default=0, help="0 means all matching examples.")
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip this many matching examples before applying --limit.",
    )
    parser.add_argument(
        "--expected-behavior",
        default=None,
        help="Filter by expected_behavior. Omit for all dataset examples.",
    )
    parser.add_argument("--tag", default=None)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--max-concurrency", type=int, default=0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    if not args.loop:
        args.loop = ["grammar", "compiler_centric", "compiler_feedback"]
    if args.expected_behavior in {"", "all", "none"}:
        args.expected_behavior = None
    return args


def _select_examples(
    client: Client,
    *,
    dataset_name: str,
    limit: int,
    offset: int,
    expected_behavior: str | None,
    tag: str | None,
) -> list[Any]:
    selected: list[Any] = []
    skipped = 0
    matching_offset = offset
    page_offset = 0
    page_size = 100
    while True:
        page = list(
            client.list_examples(
                dataset_name=dataset_name,
                offset=page_offset,
                limit=page_size,
            )
        )
        if not page:
            break
        for example in page:
            outputs = example.outputs or {}
            metadata = example.metadata or {}
            if expected_behavior and outputs.get("expected_behavior") != expected_behavior:
                continue
            if tag and metadata.get("tag") != tag:
                continue
            if skipped < matching_offset:
                skipped += 1
                continue
            selected.append(example)
            if limit and len(selected) >= limit:
                return selected
        page_offset += len(page)
    return selected


def _predict_loop(loop_name: str, max_attempts: int):
    def predict(inputs: dict[str, Any]) -> dict[str, Any]:
        from packages.pipeline.schemas import TaskIntent
        from packages.research.agent_loops import AgentLoopConfig, run_agent_loop
        from packages.research.agent_loops.grammar_loop import StructuralRules
        from packages.research.local_chat_models import make_structured_llm

        class DeterministicEvaluatorAgent:
            def invoke(self, _messages: Any) -> None:
                return None

        class CompactRuleBuilderAgent:
            def __init__(self) -> None:
                self._llm = make_structured_llm(
                    os.environ.get("RESEARCH_LLM_MODEL"),
                    StructuralRules,
                )

            def invoke(self, _messages: Any) -> Any:
                if self._llm is None:
                    return None
                return self._llm.invoke(_compact_rule_builder_prompt(str(inputs["prompt"])))

        prompt = str(inputs["prompt"])
        config = AgentLoopConfig(
            population=1,
            max_attempts=max_attempts,
            confirmed_spec=TaskIntent(task_goal=prompt),
            rule_builder_agent=CompactRuleBuilderAgent(),
            evaluator_agent=DeterministicEvaluatorAgent(),
        )
        if loop_name == "grammar":
            result = run_agent_loop("grammar", prompt, config=config)
            hitl = result.hitl
        elif loop_name == "compiler_centric":
            helpers = _load_notebook_loop_helpers()
            context = helpers["make_structural_rule_loop_context"](
                confirmed_spec=config.confirmed_spec,
                rule_builder_agent=config.rule_builder_agent,
                evaluator_agent=config.evaluator_agent,
            )
            state = helpers["run_compiler_centric_loop"](
                prompt,
                context=context,
                population=config.population,
                max_attempts=config.max_attempts,
            )
            hitl = state["hitl"]
        elif loop_name == "compiler_feedback":
            helpers = _load_notebook_loop_helpers()
            context = helpers["make_structural_rule_loop_context"](
                confirmed_spec=config.confirmed_spec,
                rule_builder_agent=config.rule_builder_agent,
                evaluator_agent=config.evaluator_agent,
            )
            state = helpers["run_compiler_feedback_loop"](
                prompt,
                context=context,
                population=config.population,
                max_attempts=config.max_attempts,
            )
            hitl = state["hitl"]
        else:
            raise ValueError(f"Unsupported loop: {loop_name}")
        return _hitl_outputs(hitl)

    return predict


def _load_notebook_loop_helpers() -> dict[str, Any]:
    import nbformat

    namespace: dict[str, Any] = {}
    notebook = nbformat.read(NOTEBOOK_PATH, as_version=4)
    with contextlib.redirect_stdout(io.StringIO()):
        for cell_index in (3, 4, 5):
            source = "".join(notebook.cells[cell_index].source)
            exec(compile(source, f"{NOTEBOOK_PATH.name}:cell-{cell_index}", "exec"), namespace)
    return namespace


def _hitl_outputs(hitl: dict[str, Any]) -> dict[str, Any]:
    return {
        "structural_rules": hitl.get("structural_rules", {}),
        "compile_safe": hitl.get("compile_safe", False),
        "invalid_grammar_nodes": hitl.get("invalid_grammar_nodes", []),
        "unreachable_grammar_nodes": hitl.get("unreachable_grammar_nodes", []),
        "compile_error": hitl.get("compile_error"),
        "langsmith_trace_id": hitl.get("langsmith_trace_id"),
        "attempts": hitl.get("attempts"),
    }


def _experiment_prefix(loop_name: str, provider: str) -> str:
    provider_label = provider.replace("_", "-")
    return f"robogrammar-{COMPILER_VERSION}-{loop_name}-{provider_label}"


def _write_summary(summary: dict[str, Any], output: str | None) -> None:
    if not output:
        return
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def _mark_interrupted(
    summary: dict[str, Any],
    *,
    signum: int,
    current_loop: str | None,
) -> None:
    interrupted_at = datetime.now(UTC).isoformat()
    summary["interrupted_at"] = interrupted_at
    summary["interrupted_signal"] = signum
    if not current_loop:
        return
    loop_summary = summary.setdefault("loops", {}).setdefault(current_loop, {})
    loop_summary["status"] = "interrupted"
    loop_summary["interrupted_at"] = interrupted_at


if __name__ == "__main__":
    main()
