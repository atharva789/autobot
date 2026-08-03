"""Generates the committed run log for build-order step 2 (plan.md §7): "Four structurally
different schemas. Gate: all compile, baselines run."

Compiles both locked dev schemas (dev-a, dev-b) against their frozen hand-written baselines
(baselines.py), runs G1 on each, runs a short rollout batch with a simple scripted probe policy
per schema, and writes everything to .runs/loop_research/<run-id>/.

"Baselines run" means the rollout executes to completion and returns a structurally valid
RolloutBatch -- it does not mean the baseline succeeds at the task. Grasping success under a
hand-scripted (non-learned) policy is not required by this gate and is not claimed here; the
holdout schemas and the negative control (steps 4+) are the run(s) actually falsifying anything.

Usage:
    python -m packages.research.loop_research.step2_run
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import numpy as np

from packages.research.loop_research.baselines import (
    DEV_A_SCHEMA,
    DEV_B_SCHEMA,
    build_dev_a_baseline,
    build_dev_b_baseline,
)
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.mujoco_compiler import compile_scaffold
from packages.research.loop_research.rollout import run_batch
from packages.research.loop_research.scaffold import ExperimentRun

_RUNS_ROOT = Path(".runs/loop_research")


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _dev_a_probe_policy(constants, step):
    # Zero-torque baseline: dev-a's actuators are motors (raw torque), so an untuned constant
    # or scripted signal has no principled target -- this only exercises the rollout mechanics
    # (compiles, steps, terminates, batches), which is what step 2's gate asks for.
    return np.zeros(6)


def _dev_b_probe_policy(constants, step):
    # Scripted two-phase descend-then-lift. dev-b's actuators are position servos, so this is a
    # real scripted controller, not a placeholder -- but there is no attach/weld mechanism, so
    # whether friction alone carries the payload up is an open, unclaimed question; the batch's
    # actual termination histogram is the evidence, not this docstring.
    x, y = 0.15, 0.10
    if step < 150:
        return np.array([x, y, 0.06, 0.05])
    return np.array([x, y, 0.43, 0.05])


def _run_one(schema_path: Path, build_baseline, probe_policy, n_actuators_hint: str):
    scaffold = build_baseline()
    model, entities = load_model_and_entities(schema_path)

    gate = run_g1(scaffold, entities)

    compiled_factory = lambda: compile_scaffold(scaffold, model, entities)  # noqa: E731
    batch = run_batch(
        scaffold,
        model,
        compiled_factory,
        probe_policy,
        batch_id=f"rb_{uuid.uuid4().hex[:12]}",
        episodes=8,
        max_steps=300,
        seed=7,
    )
    return scaffold, gate, batch


def main() -> int:
    dev_a_scaffold, dev_a_gate, dev_a_batch = _run_one(
        DEV_A_SCHEMA, build_dev_a_baseline, _dev_a_probe_policy, "6 motors"
    )
    dev_b_scaffold, dev_b_gate, dev_b_batch = _run_one(
        DEV_B_SCHEMA, build_dev_b_baseline, _dev_b_probe_policy, "4 position servos"
    )

    run_id = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime()) + f"_step2_{uuid.uuid4().hex[:6]}"
    run = ExperimentRun(
        run_id=run_id,
        git_sha=_git_sha(),
        trigger="routine",
        status="completed",
        scaffolds=(dev_a_scaffold.scaffold_id, dev_b_scaffold.scaffold_id),
        batches=(dev_a_batch.batch_id, dev_b_batch.batch_id),
        gates=(dev_a_gate, dev_b_gate),
        cost={
            "usd_total": 0.0,
            "usd_ceiling": 0.0,
            "ceiling_hit": False,
            "note": "hand-written baselines, no model calls; rollouts run locally, no OpenAI spend",
        },
        replay={
            "dev_a_schema_digest": dev_a_scaffold.schema_digest,
            "dev_b_schema_digest": dev_b_scaffold.schema_digest,
            "prompt_version": "n/a",
            "model_id": "human",
            "seed": 7,
        },
        manifest_path=None,
        control={"note": "negative control not yet implemented (build order step 4)"},
    )

    run_path = run.write(_RUNS_ROOT, [dev_a_scaffold, dev_b_scaffold])
    run_dir = run_path.parent
    (run_dir / "batches").mkdir(exist_ok=True)
    for batch in (dev_a_batch, dev_b_batch):
        (run_dir / "batches" / f"{batch.batch_id}.json").write_text(
            json.dumps(asdict(batch), indent=2), encoding="utf-8"
        )

    print(f"run: {run_path}")
    for name, gate, batch in (("dev-a", dev_a_gate, dev_a_batch), ("dev-b", dev_b_gate, dev_b_batch)):
        print(f"{name}: G1={'PASS' if gate.passed else 'FAIL'} (score {gate.score}) "
              f"rollout success_rate={batch.success_rate} histogram={batch.termination_histogram}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
