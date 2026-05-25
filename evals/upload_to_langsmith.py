"""Upload the RoboGrammar structural-rule eval dataset to LangSmith."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langsmith import Client

DATASET_NAME = "robogrammar-structural-rules-evals"
DATASET_DESCRIPTION = (
    "RoboGrammar structural-rule evals covering valid generation, hallucinated "
    "grammar nodes, recursion failures, infeasible topologies, family confusion, "
    "ambiguity, missing nodes, partial rules, and constraint violations."
)
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = ROOT / "evals" / "grammar_evals.json"


def load_entries(path: Path = DEFAULT_DATASET_PATH) -> list[dict[str, Any]]:
    with path.open() as handle:
        entries = json.load(handle)
    if not isinstance(entries, list):
        raise ValueError(f"{path} must contain a JSON list.")
    return [entry for entry in entries if isinstance(entry, dict)]


def build_examples(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_build_example(entry) for entry in entries]


def _build_example(entry: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(entry["id"])
    example_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{DATASET_NAME}:{entry_id}")
    return {
        "id": str(example_id),
        "inputs": {"prompt": entry["prompt"]},
        "outputs": {
            "expected_rules": entry["expected_rules"],
            "expected_compile_safe": entry["expected_compile_safe"],
            "expected_behavior": entry["expected_behavior"],
        },
        "metadata": {
            "tag": entry["tag"],
            "subtag": entry.get("subtag", ""),
            "difficulty": entry["difficulty"],
            "source_family": entry.get("source_family", ""),
            "notes": entry.get("notes", ""),
            "expected_invalid_nodes": entry.get("expected_invalid_nodes", []),
            "id": entry_id,
        },
    }


def get_or_create_dataset(client: Client):
    try:
        return client.create_dataset(
            dataset_name=DATASET_NAME,
            description=DATASET_DESCRIPTION,
            metadata={"source": "evals/grammar_evals.json"},
        )
    except Exception:
        return client.read_dataset(dataset_name=DATASET_NAME)


def dataset_url(dataset_id: object) -> str:
    return f"https://smith.langchain.com/datasets/{dataset_id}"


def upload_examples(client: Client, dataset_id: object, examples: list[dict[str, Any]]) -> None:
    for start in range(0, len(examples), 100):
        chunk = examples[start : start + 100]
        client.create_examples(
            dataset_id=dataset_id,
            examples=chunk,
            max_concurrency=3,
        )
        uploaded = min(start + len(chunk), len(examples))
        print(f"Uploaded {uploaded}/{len(examples)} examples")


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    entries = load_entries()
    examples = build_examples(entries)
    client = Client()
    dataset = get_or_create_dataset(client)
    upload_examples(client, dataset.id, examples)
    print(f"Final count: {len(examples)}")
    print(f"Dataset URL: {dataset_url(dataset.id)}")


if __name__ == "__main__":
    main()
