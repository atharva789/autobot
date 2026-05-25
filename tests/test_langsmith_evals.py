from __future__ import annotations

from evals.create_evaluator_corrections_dataset import build_correction_examples
from evals.run_langsmith_trace_evaluators import (
    TraceEvidence,
    build_trace_evidence,
    evaluate_hallucination,
    evaluate_task_alignment,
)
from evals.upload_to_langsmith import build_examples


def test_upload_examples_match_langsmith_dataset_contract() -> None:
    examples = build_examples(
        [
            {
                "id": "valid_001",
                "prompt": "Design a quadruped robot.",
                "expected_rules": {"S": ["BODY", "LEG_PAIR", "LEG_PAIR"]},
                "tag": "valid_baseline",
                "subtag": "quadruped",
                "expected_compile_safe": True,
                "expected_invalid_nodes": [],
                "expected_behavior": "produce",
                "difficulty": "easy",
                "notes": "Baseline quadruped.",
                "source_family": "quadruped",
            }
        ]
    )

    assert examples == [
        {
            "id": "e4438c90-5cdc-5b76-a2cf-725d8f1e37e9",
            "inputs": {"prompt": "Design a quadruped robot."},
            "outputs": {
                "expected_rules": {"S": ["BODY", "LEG_PAIR", "LEG_PAIR"]},
                "expected_compile_safe": True,
                "expected_behavior": "produce",
            },
            "metadata": {
                "tag": "valid_baseline",
                "subtag": "quadruped",
                "difficulty": "easy",
                "source_family": "quadruped",
                "notes": "Baseline quadruped.",
                "expected_invalid_nodes": [],
                "id": "valid_001",
            },
        }
    ]


def test_correction_examples_use_current_evaluator_variables() -> None:
    examples = build_correction_examples(
        [
            {
                "id": "hallucination_001",
                "prompt": "Design a robot with jetpack appendages.",
                "expected_rules": {"S": ["BODY", "JETPACK"]},
                "tag": "hallucination_invent",
                "subtag": "invented_node",
                "expected_compile_safe": False,
                "expected_invalid_nodes": ["JETPACK"],
                "expected_behavior": "reject",
                "difficulty": "easy",
                "notes": "Invented node should be treated as hallucination.",
                "source_family": "quadruped",
            }
        ]
    )

    example = examples[0]

    assert example["inputs"]["evidence"]["prompt"] == "Design a robot with jetpack appendages."
    assert example["inputs"]["evidence"]["invalid_nodes"] == ["JETPACK"]
    assert example["outputs"] == {
        "hallucination": 1.0,
        "task_alignment": 0.0,
        "few_shot_explanation": (
            "Invented node should be treated as hallucination. "
            "Expected behavior is reject for tag hallucination_invent."
        ),
    }
    assert example["metadata"]["source_dataset"] == "robogrammar-structural-rules-evals"


def test_hallucination_evaluator_flags_invalid_grammar_nodes() -> None:
    evidence = TraceEvidence(
        run_id="run-1",
        trace_id="trace-1",
        run_name="agent_loop.grammar",
        prompt="Design a quadruped robot.",
        observed_rules={"S": ["BODY", "JETPACK"]},
        expected_rules={"S": ["BODY", "LEG_PAIR", "LEG_PAIR"]},
        invalid_nodes=["JETPACK"],
        compile_safe=False,
        error=None,
    )

    result = evaluate_hallucination(evidence)

    assert result.key == "hallucination"
    assert result.score == 1.0
    assert "JETPACK" in result.comment


def test_hallucination_evaluator_does_not_let_judge_relabel_valid_rules() -> None:
    evidence = TraceEvidence(
        run_id="run-1",
        trace_id="trace-1",
        run_name="agent_loop.grammar",
        prompt="Design a quadruped robot.",
        observed_rules={"S": ["BODY"]},
        expected_rules={"S": ["BODY", "LEG_PAIR", "LEG_PAIR"]},
        invalid_nodes=[],
        compile_safe=True,
        error=None,
    )

    result = evaluate_hallucination(
        evidence,
        judge_result={
            "hallucination_score": 0.6,
            "explanation": "The rules are not task aligned.",
        },
    )

    assert result.score == 0.0


def test_task_alignment_scores_top_level_task_match() -> None:
    evidence = TraceEvidence(
        run_id="run-1",
        trace_id="trace-1",
        run_name="agent_loop.grammar",
        prompt="Design a compact quadruped that can climb rocky terrain.",
        observed_rules={
            "S": ["BODY", "CLIMBING_LEG_PAIR", "CLIMBING_LEG_PAIR", "TAIL"],
            "CLIMBING_LEG_PAIR": ["LEG", "LEG"],
            "LEG": ["HIP_STACK", "thigh_link", "knee_joint", "shank_link", "foot_pad"],
        },
        expected_rules={
            "S": ["BODY", "CLIMBING_LEG_PAIR", "CLIMBING_LEG_PAIR", "TAIL"]
        },
        invalid_nodes=[],
        compile_safe=True,
        error=None,
    )

    result = evaluate_task_alignment(evidence)

    assert result.key == "task_alignment"
    assert result.score == 1.0


def test_task_alignment_marks_rules_unreachable_from_s() -> None:
    evidence = TraceEvidence(
        run_id="run-1",
        trace_id="trace-1",
        run_name="agent_loop.grammar",
        prompt="Design a stair-climbing quadruped.",
        observed_rules={
            "S": ["BODY"],
            "LEG": ["HIP_STACK", "foot_pad"],
            "TAIL": ["tail_link"],
        },
        expected_rules={
            "S": ["BODY", "CLIMBING_LEG_PAIR", "CLIMBING_LEG_PAIR", "TAIL"]
        },
        invalid_nodes=[],
        compile_safe=True,
        error=None,
    )

    result = evaluate_task_alignment(evidence)

    assert result.value["reachable_rule_names"] == ["S"]
    assert result.value["unreachable_rule_names"] == ["LEG", "TAIL"]


def test_hallucination_ignores_recovered_child_error_when_final_rules_compile() -> None:
    class Run:
        id = "run-1"
        trace_id = "trace-1"
        name = "robogrammar.structural_rule_graph"
        run_type = "chain"
        start_time = "2026-05-24T00:00:00Z"
        error = None

    trace = {
        "trace_id": "trace-1",
        "observations": [
            {
                "name": "build_structural_rules",
                "output": {"structural_rules": {"S": ["BODY"]}},
            },
            {
                "name": "ChatOpenAI",
                "statusMessage": "APITimeoutError('Request timed out.')",
            },
            {
                "name": "compile_structural_rules",
                "output": {"compile_safe": True, "invalid_grammar_nodes": []},
            },
        ],
    }

    evidence = build_trace_evidence(Run(), trace, vocab={"S", "BODY"})
    result = evaluate_hallucination(evidence)

    assert evidence.error is None
    assert result.score == 0.0
