"""Generates the committed run log for build-order step 4 (plan.md §7): "`static_scaffold_loop`
negative control. Gate: fails G1-G3; its margin sets tau."

Runs the negative control (static_scaffold_loop.py) against both locked dev schemas and scores it
with G1. The eval-contract.md required outcome table says the control must:

  G1  Fail on every schema except dev-a (its symbols only exist in dev-a)
  G2  Fail on all four permutation classes (D = 0 by construction; it cannot respond)
  G3  Fail (D = 0 across bodies)
  G4  Not run (never reaches it)

Only G1 is computable today: G2/G3 need the structural diff function D(a, b), which is build-order
step 5 and does not exist yet. What IS computable and recorded here without D(): the control
returns the identical scaffold object regardless of which schema or task text it is called with
(asserted in tests/test_loop_research_step4.py), which makes D = 0 under every term of the
eval-contract.md formula by construction (identical term names, identical symbol sets, identical
termination causes, identical weights) -- a fact independent of the formula's implementation. This
run log states that fact plainly and does not claim numeric G2/G3 scores, which do not exist yet.

Usage:
    python -m packages.research.loop_research.step4_run
"""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import replace
from pathlib import Path

from packages.research.loop_research.baselines import DEV_A_SCHEMA, DEV_B_SCHEMA
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.scaffold import ExperimentRun, GateResult
from packages.research.loop_research.static_scaffold_loop import CONTROL_NAME, run_static_scaffold_loop

_RUNS_ROOT = Path(".runs/loop_research")


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _g1_against(schema_path: Path, schema_id: str, task_text: str) -> GateResult:
    scaffold = run_static_scaffold_loop(schema_path, task_text)
    _, entities = load_model_and_entities(schema_path)
    gate = run_g1(scaffold, entities)
    return replace(gate, detail={**gate.detail, "schema_id": schema_id})


def main() -> int:
    gate_dev_a = _g1_against(DEV_A_SCHEMA, "dev-a", "lift the payload to shelf height")
    gate_dev_b = _g1_against(DEV_B_SCHEMA, "dev-b", "lift the payload to shelf height")

    control_scaffold = run_static_scaffold_loop(DEV_A_SCHEMA, "lift the payload to shelf height")

    run_id = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime()) + f"_step4_{uuid.uuid4().hex[:6]}"
    run = ExperimentRun(
        run_id=run_id,
        git_sha=_git_sha(),
        trigger="routine",
        status="completed",
        scaffolds=(control_scaffold.scaffold_id,),
        batches=(),
        gates=(gate_dev_a, gate_dev_b),
        cost={
            "usd_total": 0.0,
            "usd_ceiling": 0.0,
            "ceiling_hit": False,
            "note": "static control makes no model calls; G1 is a static parse, no OpenAI spend",
        },
        replay={
            "dev_a_schema_digest": control_scaffold.schema_digest,
            "prompt_version": "n/a",
            "model_id": CONTROL_NAME,
            "seed": 0,
        },
        manifest_path=None,
        control={
            "loop": CONTROL_NAME,
            "gates": [
                {"gate": "G1", "schema_id": "dev-a", "passed": gate_dev_a.passed, "score": gate_dev_a.score},
                {"gate": "G1", "schema_id": "dev-b", "passed": gate_dev_b.passed, "score": gate_dev_b.score},
            ],
            "g2_g3": (
                "not computed: structural diff D(a, b) is build-order step 5, not yet "
                "implemented. tests/test_loop_research_step4.py asserts the control returns an "
                "identical scaffold object for different (schema_path, task_text) inputs, which "
                "makes D = 0 under every term of eval-contract.md's formula by construction -- "
                "this is a structural fact, not a measured score, and no numeric G2/G3 result is "
                "claimed here."
            ),
            "g4": "not run -- G1 already fails on dev-b, per eval-contract.md's required outcome table",
            "required_outcome_met": (gate_dev_a.passed is True) and (gate_dev_b.passed is False),
        },
    )

    run_path = run.write(_RUNS_ROOT, [control_scaffold])

    print(f"run: {run_path}")
    print(f"G1 on dev-a: {'PASS' if gate_dev_a.passed else 'FAIL'} (score {gate_dev_a.score})")
    print(f"G1 on dev-b: {'PASS' if gate_dev_b.passed else 'FAIL'} (score {gate_dev_b.score})")
    ok = gate_dev_a.passed and not gate_dev_b.passed
    print(f"required outcome (pass dev-a, fail dev-b): {'MET' if ok else 'NOT MET -- gates are broken'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
