"""Create a LangSmith corrections/few-shot dataset for RoboGrammar evaluators."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.upload_to_langsmith import DATASET_NAME, DEFAULT_DATASET_PATH, load_entries
from evals.run_langsmith_trace_evaluators import EVALUATOR_VERSION

CORRECTIONS_DATASET_NAME = "robogrammar-current-evaluator-corrections"
CORRECTIONS_DESCRIPTION = (
    "Few-shot correction examples for the current RoboGrammar LangSmith evaluator. "
    "Inputs use the evaluator evidence variable; outputs provide corrected "
    "hallucination, task_alignment, and few_shot_explanation fields."
)

_HALLUCINATION_TAGS = {
    "hallucination_misspell",
    "hallucination_invent",
    "hallucination_orphan",
    "missing_nodes",
    "abstraction_mismatch",
    "partial_rules",
}
_LOW_ALIGNMENT_TAGS = {
    "hallucination_misspell",
    "hallucination_invent",
    "hallucination_orphan",
    "recursion_no_base",
    "recursion_self_only",
    "recursion_overuse",
    "abstraction_mismatch",
    "infeasible_topology",
    "infeasible_load",
    "family_confusion",
    "ambiguous_morphology",
    "missing_nodes",
    "partial_rules",
    "constraint_violation",
}


def build_correction_examples(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_build_correction_example(entry) for entry in entries]


def _build_correction_example(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry["id"])
    tag = str(entry["tag"])
    invalid_nodes = list(entry.get("expected_invalid_nodes", []))
    compile_safe = bool(entry["expected_compile_safe"])
    behavior = str(entry["expected_behavior"])
    hallucination = _hallucination_label(tag, invalid_nodes, compile_safe, behavior)
    task_alignment = _task_alignment_label(tag, compile_safe, behavior)
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{CORRECTIONS_DATASET_NAME}:{entry_id}")),
        "inputs": {
            "evidence": {
                "prompt": entry["prompt"],
                "expected_rules": entry["expected_rules"],
                "observed_rules": entry["expected_rules"],
                "invalid_nodes": invalid_nodes,
                "compile_safe": compile_safe,
                "expected_behavior": behavior,
                "tag": tag,
                "subtag": entry.get("subtag", ""),
                "source_family": entry.get("source_family", ""),
            }
        },
        "outputs": {
            "hallucination": hallucination,
            "task_alignment": task_alignment,
            "few_shot_explanation": _few_shot_explanation(entry),
        },
        "metadata": {
            "source_dataset": DATASET_NAME,
            "source_eval_id": entry_id,
            "correction_dataset_for": "robogrammar-current-evaluator",
            "evaluator_version": EVALUATOR_VERSION,
            "tag": tag,
            "difficulty": entry["difficulty"],
            "expected_behavior": behavior,
        },
    }


def get_or_create_corrections_dataset(client: Client):
    try:
        return client.create_dataset(
            dataset_name=CORRECTIONS_DATASET_NAME,
            description=CORRECTIONS_DESCRIPTION,
            metadata={
                "dataset_role": "corrections",
                "source_dataset": DATASET_NAME,
                "evaluator": "robogrammar-current-evaluator",
                "evaluator_version": EVALUATOR_VERSION,
                "few_shot_variables": [
                    "evidence",
                    "hallucination",
                    "task_alignment",
                    "few_shot_explanation",
                ],
            },
        )
    except Exception:
        return client.read_dataset(dataset_name=CORRECTIONS_DATASET_NAME)


def upload_correction_examples(
    client: Client,
    dataset_id: object,
    examples: list[dict[str, Any]],
) -> None:
    for start in range(0, len(examples), 100):
        chunk = examples[start : start + 100]
        client.create_examples(dataset_id=dataset_id, examples=chunk, max_concurrency=3)
        uploaded = min(start + len(chunk), len(examples))
        print(f"Uploaded corrections {uploaded}/{len(examples)} examples")


def dataset_url(dataset_id: object) -> str:
    return f"https://smith.langchain.com/datasets/{dataset_id}"


def _hallucination_label(
    tag: str,
    invalid_nodes: list[str],
    compile_safe: bool,
    behavior: str,
) -> float:
    if tag in _HALLUCINATION_TAGS or invalid_nodes:
        return 1.0
    if behavior == "reject" and not compile_safe:
        return 1.0
    return 0.0


def _task_alignment_label(tag: str, compile_safe: bool, behavior: str) -> float:
    if behavior == "produce" and compile_safe and tag not in _LOW_ALIGNMENT_TAGS:
        return 1.0
    if behavior == "flag_infeasible":
        return 0.25
    if tag == "valid_complex":
        return 1.0
    return 0.0


def _few_shot_explanation(entry: dict[str, Any]) -> str:
    notes = str(entry.get("notes") or "").strip()
    tag = str(entry["tag"])
    behavior = str(entry["expected_behavior"])
    suffix = f"Expected behavior is {behavior} for tag {tag}."
    return f"{notes} {suffix}".strip() if notes else suffix


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    entries = load_entries(DEFAULT_DATASET_PATH)
    examples = build_correction_examples(entries)
    client = Client()
    dataset = get_or_create_corrections_dataset(client)
    upload_correction_examples(client, dataset.id, examples)
    print(f"Final corrections count: {len(examples)}")
    print(f"Corrections dataset URL: {dataset_url(dataset.id)}")


if __name__ == "__main__":
    main()
