"""Run LangSmith experiments for local RoboGrammar model backends."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client, evaluate

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.run_langsmith_trace_evaluators import _top_level_f1

DATASET_NAME = "robogrammar-structural-rules-evals"
COMPILER_VERSION = "reachable-compiler.2026-05-24"


def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / ".env", override=False)
    _configure_provider(args.provider)

    client = Client()
    examples = _select_examples(
        client,
        dataset_name=args.dataset,
        limit=args.limit,
        expected_behavior=args.expected_behavior,
        tag=args.tag,
    )
    if not examples:
        raise SystemExit("No dataset examples matched the requested filters.")

    provider_label = args.provider.replace("_", "-")
    results = evaluate(
        _predict_structural_rules(args.max_attempts),
        data=examples,
        evaluators=[task_alignment_evaluator, compiler_evaluator],
        summary_evaluators=[summary_task_alignment],
        experiment_prefix=f"robogrammar-{COMPILER_VERSION}-{provider_label}",
        description=(
            f"RoboGrammar task-alignment benchmark using {provider_label} "
            "with reachable-node compiler validation."
        ),
        metadata={
            "compiler_version": COMPILER_VERSION,
            "provider": args.provider,
            "model": os.environ.get("RESEARCH_LLM_MODEL"),
            "max_attempts": args.max_attempts,
            "dataset": args.dataset,
            "example_limit": args.limit,
            "expected_behavior": args.expected_behavior,
            "tag": args.tag,
        },
        max_concurrency=0,
        client=client,
        error_handling="log",
    )
    print(
        json.dumps(
            {
                "experiment_name": getattr(results, "experiment_name", None),
                "provider": args.provider,
                "examples": len(examples),
                "dataset": args.dataset,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["claude-code", "qwen"],
        required=True,
    )
    parser.add_argument("--dataset", default=DATASET_NAME)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--expected-behavior", default="produce")
    parser.add_argument("--tag", default=None)
    parser.add_argument("--max-attempts", type=int, default=2)
    return parser.parse_args()


def _configure_provider(provider: str) -> None:
    if provider == "claude-code":
        os.environ["RESEARCH_LLM_PROVIDER"] = "claude-code"
        os.environ.setdefault("RESEARCH_LLM_MODEL", "claude-sonnet-4-5")
        os.environ.setdefault("RESEARCH_LLM_TIMEOUT", "180")
        return
    if provider == "qwen":
        os.environ["RESEARCH_LLM_PROVIDER"] = "openai-compatible"
        os.environ["RESEARCH_LLM_MODEL"] = os.environ.get(
            "QWEN_MODEL_ID",
            "Qwen/Qwen3-1.7B",
        )
        os.environ.setdefault("RESEARCH_LLM_BASE_URL", "http://127.0.0.1:8001/v1")
        os.environ.setdefault("RESEARCH_LLM_API_KEY", "EMPTY")
        os.environ.setdefault("RESEARCH_LLM_MAX_TOKENS", "768")
        os.environ.setdefault("RESEARCH_LLM_TIMEOUT", "180")
        return
    raise ValueError(f"Unsupported provider: {provider}")


def _select_examples(
    client: Client,
    *,
    dataset_name: str,
    limit: int,
    expected_behavior: str | None,
    tag: str | None,
) -> list[Any]:
    selected: list[Any] = []
    dataset = client.read_dataset(dataset_name=dataset_name)
    for example in client.list_examples(dataset_id=dataset.id, limit=100):
        outputs = example.outputs or {}
        metadata = example.metadata or {}
        if expected_behavior and outputs.get("expected_behavior") != expected_behavior:
            continue
        if tag and metadata.get("tag") != tag:
            continue
        selected.append(example)
        if len(selected) >= limit:
            break
    return selected


def _predict_structural_rules(max_attempts: int):
    def predict(inputs: dict[str, Any]) -> dict[str, Any]:
        from packages.pipeline.schemas import TaskIntent
        from packages.research.local_chat_models import make_structured_llm
        from packages.research.agent_loops.grammar_loop import (
            StructuralRules,
            build_structural_rules,
            summarize_hitl_state,
        )

        class DeterministicEvaluatorAgent:
            def invoke(self, _messages: Any) -> None:
                return None

        class CompactRuleBuilderAgent:
            def __init__(self) -> None:
                self._llm = make_structured_llm(
                    os.environ.get("RESEARCH_LLM_MODEL"),
                    StructuralRules,
                )

            def invoke(self, messages: Any) -> Any:
                if self._llm is None:
                    return None
                return self._llm.invoke(_compact_rule_builder_prompt(str(inputs["prompt"])))

        state = build_structural_rules(
            prompt=str(inputs["prompt"]),
            confirmed_spec=TaskIntent(task_goal=str(inputs["prompt"])),
            rule_builder_agent=CompactRuleBuilderAgent(),
            evaluator_agent=DeterministicEvaluatorAgent(),
            population=1,
            max_attempts=max_attempts,
            require_human_confirmation=False,
        )
        hitl = summarize_hitl_state(state)
        return {
            "structural_rules": hitl.get("structural_rules", {}),
            "compile_safe": hitl.get("compile_safe", False),
            "invalid_grammar_nodes": hitl.get("invalid_grammar_nodes", []),
            "unreachable_grammar_nodes": hitl.get("unreachable_grammar_nodes", []),
            "compile_error": hitl.get("compile_error"),
            "langsmith_trace_id": hitl.get("langsmith_trace_id"),
        }

    return predict


def _compact_rule_builder_prompt(prompt: str) -> str:
    return "\n".join(
        [
            "Return only JSON shaped as {\"structural_rules\": dict[str, list[str]]}.",
            "Use only these RoboGrammar node IDs:",
            "S, BODY, BODY_CHAIN, BODY_SEG, LEG_PAIR, LEG, CLIMBING_LEG_PAIR,",
            "CLIMBING_LEG, HIP_STACK, TAIL, HEAD, ARM_PAIR, ARM, SPRAWLED_LEG_PAIR,",
            "hip_yaw, hip_roll, hip_pitch, thigh_link, knee_joint, shank_link,",
            "foot_pad, tail_yaw, tail_link, tail_tip, body_segment.",
            "Each RHS list item must be exactly one node ID, never a space-separated phrase.",
            "Every node you define must be reachable from S. Do not define dead rules.",
            "For quadrupeds or climbing tasks, S should include reachable leg pairs.",
            f"Task: {prompt}",
        ]
    )


def task_alignment_evaluator(run: Any, example: Any) -> dict[str, Any]:
    outputs = run.outputs or {}
    reference = example.outputs or {}
    expected_rules = reference.get("expected_rules") or {}
    observed_rules = outputs.get("structural_rules") or {}
    deterministic_score = _top_level_f1(expected_rules, observed_rules)
    invalid_nodes = list(outputs.get("invalid_grammar_nodes") or [])
    unreachable_nodes = list(outputs.get("unreachable_grammar_nodes") or [])
    score = deterministic_score
    if invalid_nodes:
        score = 0.0
    elif unreachable_nodes:
        score = min(score, 0.4)
    return {
        "key": "task_alignment",
        "score": round(score, 4),
        "comment": (
            f"Expected S={expected_rules.get('S', [])}; "
            f"observed S={observed_rules.get('S', [])}; "
            f"deterministic_top_level_f1={deterministic_score:.3f}; "
            f"invalid_nodes={invalid_nodes}; unreachable_nodes={unreachable_nodes}."
        ),
        "value": {
            "deterministic_top_level_f1": deterministic_score,
            "invalid_nodes": invalid_nodes,
            "unreachable_nodes": unreachable_nodes,
        },
    }


def compiler_evaluator(run: Any, _example: Any) -> dict[str, Any]:
    outputs = run.outputs or {}
    invalid_nodes = list(outputs.get("invalid_grammar_nodes") or [])
    unreachable_nodes = list(outputs.get("unreachable_grammar_nodes") or [])
    compile_error = outputs.get("compile_error")
    compile_safe = bool(outputs.get("compile_safe"))
    score = 1.0 if compile_safe and not invalid_nodes and not unreachable_nodes else 0.0
    return {
        "key": "compiler_validity",
        "score": score,
        "comment": (
            f"compile_safe={compile_safe}; invalid_nodes={invalid_nodes}; "
            f"unreachable_nodes={unreachable_nodes}; compile_error={compile_error}."
        ),
        "value": {
            "compile_safe": compile_safe,
            "invalid_nodes": invalid_nodes,
            "unreachable_nodes": unreachable_nodes,
            "compile_error": compile_error,
        },
    }


def summary_task_alignment(runs: list[Any], _examples: list[Any]) -> dict[str, Any]:
    scores: list[float] = []
    compiler_scores: list[float] = []
    compile_statuses: Counter[str] = Counter()
    for run in runs:
        feedback = getattr(run, "feedback_stats", None) or {}
        task_score = _feedback_average(feedback, "task_alignment")
        compiler_score = _feedback_average(feedback, "compiler_validity")
        if task_score is not None:
            scores.append(task_score)
        if compiler_score is not None:
            compiler_scores.append(compiler_score)
        outputs = run.outputs or {}
        compile_statuses["compile_safe" if outputs.get("compile_safe") else "compile_unsafe"] += 1
    return {
        "key": "summary_task_alignment",
        "score": round(sum(scores) / len(scores), 4) if scores else None,
        "value": {
            "mean_task_alignment": sum(scores) / len(scores) if scores else None,
            "mean_compiler_validity": (
                sum(compiler_scores) / len(compiler_scores) if compiler_scores else None
            ),
            "compile_statuses": dict(compile_statuses),
            "runs": len(runs),
        },
    }


def _feedback_average(feedback_stats: dict[str, Any], key: str) -> float | None:
    stats = feedback_stats.get(key)
    if not isinstance(stats, dict):
        return None
    avg = stats.get("avg")
    if isinstance(avg, int | float):
        return float(avg)
    return None


if __name__ == "__main__":
    main()
