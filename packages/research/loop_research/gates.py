"""CLI: backfill G1 results for a committed run's scaffolds.

Invoked by the Actions workflow (build order step 6, `.github/workflows/loop-research.yml`) as a
step separate from the compute stack, `if: always()` — so a loop that crashes mid-run still leaves
a gradeable G1 result behind for whatever scaffolds it did manage to write, rather than a run
directory with scaffolds but no gates.

Only fills in gates that are missing; never overwrites an existing `(gate, scaffold_id)` result —
`gates.json` is append-only evidence, same as the rest of `.runs/loop_research/`
(data-model.md invariant 3).

Usage:
    python -m packages.research.loop_research.gates --run-id <run-id>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from packages.research.loop_research.baselines import DEV_A_SCHEMA, DEV_B_SCHEMA
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.scaffold import (
    CurriculumStage,
    GateResult,
    Provenance,
    RandomizationRange,
    RewardTerm,
    Termination,
    TrainingScaffold,
)

_RUNS_ROOT = Path(".runs/loop_research")
_SCHEMA_BY_ID = {"dev-a": DEV_A_SCHEMA, "dev-b": DEV_B_SCHEMA}


def load_scaffold(path: Path) -> TrainingScaffold:
    """Reconstructs a `TrainingScaffold` from its committed JSON form.

    JSON has no tuple type, so every field typed `tuple[...]` on the dataclasses (`symbols`,
    `range`, and the top-level term/stage lists themselves) round-trips as a `list` and must be
    converted back explicitly, or the reconstructed record fails `==` against the original despite
    holding the same data.
    """

    raw = json.loads(path.read_text(encoding="utf-8"))
    return TrainingScaffold(
        scaffold_id=raw["scaffold_id"],
        schema_id=raw["schema_id"],
        schema_digest=raw["schema_digest"],
        task_text=raw["task_text"],
        reward_terms=tuple(
            RewardTerm(**{**t, "symbols": tuple(t["symbols"])}) for t in raw["reward_terms"]
        ),
        terminations=tuple(
            Termination(**{**t, "symbols": tuple(t["symbols"])}) for t in raw["terminations"]
        ),
        curriculum=tuple(
            CurriculumStage(**{**c, "range": tuple(c["range"])}) for c in raw["curriculum"]
        ),
        randomization=tuple(
            RandomizationRange(**{**r, "range": tuple(r["range"])}) for r in raw["randomization"]
        ),
        provenance=Provenance(**raw["provenance"]),
        parent_scaffold_id=raw.get("parent_scaffold_id"),
        motivating_batch_id=raw.get("motivating_batch_id"),
    )


def backfill_g1(run_dir: Path) -> list[GateResult]:
    """Computes G1 for every scaffold under `run_dir/scaffolds/` not already covered by an
    existing G1 result in `gates.json`. Returns only the newly-added gates."""

    scaffold_dir = run_dir / "scaffolds"
    if not scaffold_dir.exists():
        return []

    gates_path = run_dir / "gates.json"
    existing = json.loads(gates_path.read_text(encoding="utf-8")) if gates_path.exists() else []
    covered = {(g["gate"], g["scaffold_id"]) for g in existing}

    new_gates: list[GateResult] = []
    for scaffold_path in sorted(scaffold_dir.glob("*.json")):
        scaffold = load_scaffold(scaffold_path)
        if ("G1", scaffold.scaffold_id) in covered:
            continue
        schema_path = _SCHEMA_BY_ID.get(scaffold.schema_id)
        if schema_path is None:
            continue  # unknown schema_id (e.g. step 1's throwaway fixture) -- not generically gate-able
        _, entities = load_model_and_entities(schema_path)
        new_gates.append(run_g1(scaffold, entities))

    if new_gates:
        gates_path.write_text(
            json.dumps(existing + [asdict(g) for g in new_gates], indent=2), encoding="utf-8"
        )
    return new_gates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = _RUNS_ROOT / args.run_id
    if not run_dir.exists():
        print(f"no run directory at {run_dir}; nothing to gate")
        return 0

    new_gates = backfill_g1(run_dir)
    for gate in new_gates:
        print(f"G1 [{gate.scaffold_id}]: {'PASS' if gate.passed else 'FAIL'} (score {gate.score})")
    if not new_gates:
        print(f"{run_dir}: no ungated scaffolds found (all covered, or none present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
