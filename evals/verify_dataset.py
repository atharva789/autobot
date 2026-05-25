"""Verify every eval entry against the live grammar vocabulary.

Run:  python -m evals.verify_dataset [--snapshot evals/grammar_vocab_snapshot.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_vocab(snapshot_path: str) -> tuple[set[str], set[str], set[str]]:
    with open(snapshot_path) as f:
        data = json.load(f)
    nonterminals = {n["short_form_name"] for n in data["nodes"] if n["node_type"] == "nonterminal"}
    terminals = {n["short_form_name"] for n in data["nodes"] if n["node_type"] == "terminal"}
    all_nodes = nonterminals | terminals
    return nonterminals, terminals, all_nodes


def verify_entry(
    entry: dict,
    all_nodes: set[str],
    nonterminals: set[str],
    seen_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    eid = entry.get("id", "<missing>")

    if eid in seen_ids:
        errors.append(f"[{eid}] duplicate ID")
    seen_ids.add(eid)

    if not entry.get("prompt", "").strip():
        errors.append(f"[{eid}] empty prompt")

    rules = entry.get("expected_rules", {})
    if not isinstance(rules, dict):
        errors.append(f"[{eid}] expected_rules is not a dict")
        return errors

    expected_safe = entry.get("expected_compile_safe", None)
    expected_invalid = set(entry.get("expected_invalid_nodes", []))

    actual_invalid: list[str] = []
    for lhs, rhs in rules.items():
        if lhs not in all_nodes:
            actual_invalid.append(lhs)
        if not isinstance(rhs, list):
            errors.append(f"[{eid}] RHS for {lhs} is not a list")
            continue
        for node in rhs:
            if node not in all_nodes:
                actual_invalid.append(node)

    actual_invalid_set = set(actual_invalid)

    if expected_safe is True and actual_invalid:
        errors.append(
            f"[{eid}] marked compile_safe=True but has invalid nodes: {actual_invalid}"
        )

    if expected_safe is False and not actual_invalid and not expected_invalid:
        tag = entry.get("tag", "")
        if tag not in ("recursion_no_base", "recursion_self_only", "recursion_overuse",
                       "infeasible_topology", "infeasible_load", "ambiguous_morphology",
                       "partial_rules", "constraint_violation"):
            errors.append(
                f"[{eid}] marked compile_safe=False but all nodes are valid and no expected_invalid_nodes"
            )

    if expected_invalid and expected_invalid != actual_invalid_set:
        missing = expected_invalid - actual_invalid_set
        extra = actual_invalid_set - expected_invalid
        if missing:
            errors.append(
                f"[{eid}] expected_invalid_nodes lists {missing} but those are actually valid"
            )
        if extra:
            errors.append(
                f"[{eid}] has invalid nodes {extra} not listed in expected_invalid_nodes"
            )

    for lhs in rules:
        if lhs in all_nodes and lhs not in nonterminals and lhs == lhs.upper():
            pass
        elif lhs in all_nodes and lhs not in nonterminals:
            errors.append(f"[{eid}] LHS '{lhs}' is a terminal used as nonterminal")

    return errors


def verify_dataset(dataset_path: str, snapshot_path: str) -> int:
    nonterminals, terminals, all_nodes = load_vocab(snapshot_path)

    with open(dataset_path) as f:
        entries = json.load(f)

    if not isinstance(entries, list):
        print("ERROR: dataset root must be a JSON array")
        return 1

    seen_ids: set[str] = set()
    all_errors: list[str] = []
    tag_counts: Counter[str] = Counter()
    behavior_counts: Counter[str] = Counter()
    difficulty_counts: Counter[str] = Counter()

    for entry in entries:
        tag_counts[entry.get("tag", "<missing>")] += 1
        behavior_counts[entry.get("expected_behavior", "<missing>")] += 1
        difficulty_counts[entry.get("difficulty", "<missing>")] += 1
        errs = verify_entry(entry, all_nodes, nonterminals, seen_ids)
        all_errors.extend(errs)

    print(f"\n{'='*60}")
    print(f"  DATASET VERIFICATION REPORT")
    print(f"{'='*60}")
    print(f"  Total entries:  {len(entries)}")
    print(f"  Unique IDs:     {len(seen_ids)}")
    print(f"  Errors found:   {len(all_errors)}")
    print(f"\n  Tag distribution:")
    for tag, count in sorted(tag_counts.items()):
        print(f"    {tag:30s} {count:4d}")
    print(f"\n  Expected behavior:")
    for beh, count in sorted(behavior_counts.items()):
        print(f"    {beh:20s} {count:4d}")
    print(f"\n  Difficulty:")
    for diff, count in sorted(difficulty_counts.items()):
        print(f"    {diff:10s} {count:4d}")

    if all_errors:
        print(f"\n  ERRORS:")
        for err in all_errors[:50]:
            print(f"    {err}")
        if len(all_errors) > 50:
            print(f"    ... and {len(all_errors) - 50} more")

    print(f"\n  Vocabulary: {len(nonterminals)} NT + {len(terminals)} T = {len(all_nodes)} nodes")
    print(f"{'='*60}\n")

    return 1 if all_errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", default="evals/grammar_evals.json", nargs="?")
    parser.add_argument("--snapshot", default="evals/grammar_vocab_snapshot.json")
    args = parser.parse_args()
    sys.exit(verify_dataset(args.dataset, args.snapshot))
