"""Run retrospective LangSmith evaluators over existing RoboGrammar traces."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client

from packages.research.experiment.prompt_oracle import infer_expected_robo_grammar
from packages.research.experiment.run_debug import (
    LangSmithTraceReader,
    extract_prompt_from_trace,
    extract_robo_grammar_from_trace,
)

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "evals" / "grammar_vocab_snapshot.json"
EVALUATOR_VERSION = "2026-05-24.v1"


@dataclass(frozen=True)
class TraceEvidence:
    run_id: str
    trace_id: str
    run_name: str
    prompt: str | None
    observed_rules: dict[str, list[str]]
    expected_rules: dict[str, list[str]]
    invalid_nodes: list[str]
    compile_safe: bool | None
    error: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedbackPayload:
    key: str
    score: float | None
    comment: str
    value: dict[str, Any]


def load_vocab(path: Path = VOCAB_PATH) -> set[str]:
    data = json.loads(path.read_text())
    return {
        str(node["short_form_name"])
        for node in data.get("nodes", [])
        if isinstance(node, dict) and node.get("short_form_name")
    }


def build_trace_evidence(
    run: Any,
    trace: dict[str, Any],
    *,
    vocab: set[str],
) -> TraceEvidence:
    prompt = extract_prompt_from_trace(trace)
    observed = extract_robo_grammar_from_trace(trace)
    expected = infer_expected_robo_grammar(prompt) if prompt else {}
    invalid_nodes = _invalid_rule_nodes(observed, vocab)
    compile_safe = _compile_safe_from_trace(trace)
    if compile_safe is None and observed:
        compile_safe = not invalid_nodes
    error = _run_error(
        run,
        trace,
        compile_safe=compile_safe,
        observed_rules=observed,
    )
    return TraceEvidence(
        run_id=str(getattr(run, "id", "")),
        trace_id=str(getattr(run, "trace_id", "") or trace.get("trace_id") or ""),
        run_name=str(getattr(run, "name", "")),
        prompt=prompt,
        observed_rules=observed,
        expected_rules=expected,
        invalid_nodes=invalid_nodes,
        compile_safe=compile_safe,
        error=error,
        metadata={
            "start_time": str(getattr(run, "start_time", "") or ""),
            "run_type": str(getattr(run, "run_type", "") or ""),
        },
    )


def evaluate_hallucination(
    evidence: TraceEvidence,
    *,
    judge_result: dict[str, Any] | None = None,
) -> FeedbackPayload:
    deterministic_score = 1.0 if _has_hallucination(evidence) else 0.0
    llm_score = _float_or_none((judge_result or {}).get("hallucination_score"))
    score = deterministic_score
    if deterministic_score:
        score = max(deterministic_score, llm_score or 0.0)
    reasons = _hallucination_reasons(evidence)
    if deterministic_score and judge_result and judge_result.get("explanation"):
        reasons.append(str(judge_result["explanation"]))
    comment = "No hallucinated grammar claims found." if not reasons else " ".join(reasons)
    return FeedbackPayload(
        key="hallucination",
        score=round(score, 4),
        comment=comment[:1000],
        value={
            "evaluator_version": EVALUATOR_VERSION,
            "deterministic_score": deterministic_score,
            "llm_score": llm_score,
            "invalid_nodes": evidence.invalid_nodes,
            "compile_safe": evidence.compile_safe,
            "observed_rule_count": len(evidence.observed_rules),
        },
    )


def evaluate_task_alignment(
    evidence: TraceEvidence,
    *,
    judge_result: dict[str, Any] | None = None,
) -> FeedbackPayload:
    deterministic_score = _top_level_f1(evidence.expected_rules, evidence.observed_rules)
    llm_score = _float_or_none((judge_result or {}).get("task_alignment_score"))
    score = llm_score if llm_score is not None else deterministic_score
    expected_top = evidence.expected_rules.get("S", [])
    observed_top = evidence.observed_rules.get("S", [])
    reachable_rules = _reachable_rule_names(evidence.observed_rules)
    unreachable_rules = sorted(set(evidence.observed_rules) - reachable_rules)
    comment = (
        f"Top-level expected S={expected_top}; observed S={observed_top}; "
        f"deterministic F1={deterministic_score:.3f}."
    )
    if judge_result and judge_result.get("alignment_explanation"):
        comment += " " + str(judge_result["alignment_explanation"])
    return FeedbackPayload(
        key="task_alignment",
        score=round(score, 4),
        comment=comment[:1000],
        value={
            "evaluator_version": EVALUATOR_VERSION,
            "deterministic_top_level_f1": deterministic_score,
            "llm_score": llm_score,
            "expected_top_level": expected_top,
            "observed_top_level": observed_top,
            "reachable_rule_names": sorted(reachable_rules),
            "unreachable_rule_names": unreachable_rules,
        },
    )


def run_retro_eval(
    *,
    project_name: str,
    limit: int | None,
    use_llm: bool,
    dry_run: bool,
    trace_id: str | None = None,
) -> dict[str, Any]:
    client = Client()
    reader = LangSmithTraceReader(project_name=project_name, env_path=ROOT / ".env")
    vocab = load_vocab()
    runs = _select_runs(
        client,
        project_name=project_name,
        limit=limit,
        trace_id=trace_id,
    )
    judge = OpenAIJudge() if use_llm else None
    created_or_updated = 0
    scores: dict[str, list[float]] = {"hallucination": [], "task_alignment": []}
    failures: list[str] = []

    _ensure_feedback_configs(client, dry_run=dry_run)
    for index, run in enumerate(runs, start=1):
        trace_id = str(getattr(run, "trace_id", "") or getattr(run, "id", ""))
        try:
            trace = reader.fetch_trace(trace_id)
            evidence = build_trace_evidence(run, trace, vocab=vocab)
            judge_result = judge.evaluate(evidence) if judge else None
            feedbacks = [
                evaluate_hallucination(evidence, judge_result=judge_result),
                evaluate_task_alignment(evidence, judge_result=judge_result),
            ]
            for feedback in feedbacks:
                if feedback.score is not None:
                    scores[feedback.key].append(feedback.score)
                if not dry_run:
                    _upsert_feedback(client, run, feedback)
                    created_or_updated += 1
            print(
                f"Evaluated {index}/{len(runs)} trace={trace_id} "
                f"hallucination={feedbacks[0].score} task_alignment={feedbacks[1].score}"
            )
        except Exception as exc:
            failures.append(f"{trace_id}: {exc.__class__.__name__}: {exc}")
            print(f"FAILED {index}/{len(runs)} trace={trace_id}: {exc}")

    summary = {
        "project": project_name,
        "trace_id": trace_id,
        "runs": len(runs),
        "feedback_rows_written": created_or_updated,
        "dry_run": dry_run,
        "use_llm": use_llm,
        "mean_scores": {
            key: (sum(values) / len(values) if values else None)
            for key, values in scores.items()
        },
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


class OpenAIJudge:
    def __init__(self, *, model: str | None = None) -> None:
        from openai import OpenAI

        self.model = model or os.environ.get("LANGSMITH_EVAL_LLM_MODEL") or os.environ.get(
            "OPENAI_MODEL", "gpt-4o-mini"
        )
        self.client = OpenAI()

    def evaluate(self, evidence: TraceEvidence) -> dict[str, Any] | None:
        prompt = (
            "You are a RoboGrammar trace evaluator. Judge only against the evidence. "
            "Hallucination means the trace produced or endorsed grammar nodes not in "
            "the provided vocabulary/compile evidence, or claimed success despite "
            "invalid nodes. Do not call extra valid rule expansions hallucinations. "
            "Task alignment means the top-level S morphology and task-relevant "
            "contact/manipulation/sensing structures match the natural-language task. "
            "Only grammar rules reachable from S are part of the realized robot; "
            "unreachable definitions do not count as assembled legs, tails, sensors, "
            "or task hardware. Use deterministic_top_level_f1 as a sanity anchor, "
            "and do not assign high task alignment when task-critical modules are "
            "missing from S unless observed S contains an explicit valid equivalent. "
            "Return JSON only.\n\n"
            f"Evidence:\n{json.dumps(_evidence_for_judge(evidence), sort_keys=True)}"
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "hallucination_score": {"type": "number", "minimum": 0, "maximum": 1},
                "task_alignment_score": {"type": "number", "minimum": 0, "maximum": 1},
                "explanation": {"type": "string"},
                "alignment_explanation": {"type": "string"},
            },
            "required": [
                "hallucination_score",
                "task_alignment_score",
                "explanation",
                "alignment_explanation",
            ],
        }
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "robogrammar_trace_eval",
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)


def _upsert_feedback(client: Client, run: Any, feedback: FeedbackPayload) -> None:
    feedback_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"il-ideation:{EVALUATOR_VERSION}:{feedback.key}:{getattr(run, 'id')}",
    )
    kwargs = {
        "score": feedback.score,
        "value": feedback.value,
        "comment": feedback.comment,
    }
    try:
        client.read_feedback(feedback_id)
    except Exception:
        client.create_feedback(
            run_id=getattr(run, "id"),
            trace_id=getattr(run, "trace_id", None),
            session_id=getattr(run, "session_id", None),
            start_time=getattr(run, "start_time", None),
            key=feedback.key,
            feedback_id=feedback_id,
            source_info={
                "evaluator": "evals/run_langsmith_trace_evaluators.py",
                "evaluator_version": EVALUATOR_VERSION,
            },
            **kwargs,
        )
    else:
        client.update_feedback(feedback_id, **kwargs)


def _ensure_feedback_configs(client: Client, *, dry_run: bool) -> None:
    if dry_run:
        return
    configs = {
        cfg.feedback_key
        for cfg in client.list_feedback_configs(
            feedback_key=["hallucination", "task_alignment"],
            limit=20,
        )
    }
    if "hallucination" not in configs:
        client.create_feedback_config(
            "hallucination",
            feedback_config={"type": "continuous", "min": 0, "max": 1},
            is_lower_score_better=True,
        )
    if "task_alignment" not in configs:
        client.create_feedback_config(
            "task_alignment",
            feedback_config={"type": "continuous", "min": 0, "max": 1},
            is_lower_score_better=False,
        )


def _select_runs(
    client: Client,
    *,
    project_name: str,
    limit: int | None,
    trace_id: str | None,
) -> list[Any]:
    if trace_id:
        return list(
            client.list_runs(
                project_name=project_name,
                trace_id=trace_id,
                is_root=True,
                limit=1,
            )
        )
    return list(client.list_runs(project_name=project_name, is_root=True, limit=limit))


def _invalid_rule_nodes(rules: dict[str, list[str]], vocab: set[str]) -> list[str]:
    invalid: set[str] = set()
    for lhs, rhs in rules.items():
        if lhs not in vocab:
            invalid.add(lhs)
        for node in rhs:
            if node not in vocab:
                invalid.add(node)
    return sorted(invalid)


def _compile_safe_from_trace(trace: dict[str, Any]) -> bool | None:
    for observation in reversed(trace.get("observations", [])):
        output = observation.get("output")
        if isinstance(output, dict) and "compile_safe" in output:
            return bool(output["compile_safe"])
        if isinstance(output, dict) and isinstance(output.get("output"), dict):
            nested = output["output"]
            if "compile_safe" in nested:
                return bool(nested["compile_safe"])
    return None


def _run_error(
    run: Any,
    trace: dict[str, Any],
    *,
    compile_safe: bool | None = None,
    observed_rules: dict[str, list[str]] | None = None,
) -> str | None:
    error = getattr(run, "error", None)
    if error:
        return str(error)
    if compile_safe is True and observed_rules:
        return None
    for observation in trace.get("observations", []):
        status = observation.get("statusMessage")
        if status:
            return str(status)
    return None


def _has_hallucination(evidence: TraceEvidence) -> bool:
    return bool(
        evidence.invalid_nodes
        or evidence.error
        or (evidence.compile_safe is False and evidence.observed_rules)
    )


def _hallucination_reasons(evidence: TraceEvidence) -> list[str]:
    reasons: list[str] = []
    if evidence.invalid_nodes:
        reasons.append(
            "Invalid GrammarNodes were produced: " + ", ".join(evidence.invalid_nodes) + "."
        )
    if evidence.compile_safe is False and evidence.observed_rules:
        reasons.append("The trace reported compile_safe=False for generated structural rules.")
    if evidence.error:
        reasons.append(f"The run errored: {evidence.error[:240]}.")
    return reasons


def _top_level_f1(
    expected: dict[str, list[str]],
    observed: dict[str, list[str]],
) -> float:
    expected_counts = Counter(expected.get("S", []))
    observed_counts = Counter(observed.get("S", []))
    if not expected_counts and not observed_counts:
        return 0.0
    keys = set(expected_counts) | set(observed_counts)
    true_positives = sum(min(expected_counts[key], observed_counts[key]) for key in keys)
    false_positives = sum(max(0, observed_counts[key] - expected_counts[key]) for key in keys)
    false_negatives = sum(max(0, expected_counts[key] - observed_counts[key]) for key in keys)
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _reachable_rule_names(rules: dict[str, list[str]]) -> set[str]:
    reachable: set[str] = set()
    stack = ["S"] if "S" in rules else []
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        for child in rules.get(node, []):
            if child in rules and child not in reachable:
                stack.append(child)
    return reachable


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _evidence_for_judge(evidence: TraceEvidence) -> dict[str, Any]:
    reachable_rules = _reachable_rule_names(evidence.observed_rules)
    return {
        "run_id": evidence.run_id,
        "run_name": evidence.run_name,
        "prompt": evidence.prompt,
        "expected_rules": evidence.expected_rules,
        "observed_rules": evidence.observed_rules,
        "deterministic_top_level_f1": _top_level_f1(
            evidence.expected_rules,
            evidence.observed_rules,
        ),
        "reachable_rule_names": sorted(reachable_rules),
        "unreachable_rule_names": sorted(set(evidence.observed_rules) - reachable_rules),
        "invalid_nodes": evidence.invalid_nodes,
        "compile_safe": evidence.compile_safe,
        "error": evidence.error,
    }


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.environ.get("LANGSMITH_PROJECT"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--trace-id", default=None)
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.project:
        raise SystemExit("LANGSMITH_PROJECT or --project is required.")
    run_retro_eval(
        project_name=args.project,
        limit=args.limit,
        use_llm=args.use_llm,
        dry_run=args.dry_run,
        trace_id=args.trace_id,
    )


if __name__ == "__main__":
    main()
