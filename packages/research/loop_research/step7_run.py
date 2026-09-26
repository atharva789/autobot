"""Generates the committed run log for build-order step 7 (plan.md §7): "The real loop, cheap
tier. Gate: passes G1-G3 on dev schemas."

Runs `run_scaffold_loop` (scaffold_loop.py) -- the real, model-driven loop, not the static
negative control -- independently on `dev-a`, `dev-b`, and each of G2's four permutation mutants
of `dev-a`. Six independent loop runs, none sharing a prompt context with another (loop-contract.md
C6: "Independent gate arms ... must never share a prompt context; a model shown four schemas side
by side can differentiate its four outputs deliberately, which games the divergence gates").

Scores the results with G1 (dev-a's final scaffold) and G2/G3, against tau already derived and
committed by build-order step 5 -- eval-contract.md's tau is a fixed calibration from the negative
control vs. hand-written baselines, not something each new loop run recomputes for itself. This
script reads it from the most recent committed `*_step5_*` run log rather than hand-copying the
number, so a stale copy can't silently drift from what was actually derived.

The negative control also runs on the same cadence (R7; data-model.md invariant 4: "control is
required on every run") -- not to re-derive anything, but because a control that only ran once,
long ago, is not the same evidence as a control that still fails on demand today.

Local substitute mode (routines/registry.md; no OpenAI credits exist yet): the real loop runs
against the local `claude-code` CLI provider. `max_revisions`/`episodes_per_batch`/`step_budget`
below are scaled down from `ScaffoldLoopConfig`'s own contract defaults for today's wall-clock --
the same kind of scaling step2_run.py's `episodes=8` and step5_run.py's permutation-only scope
already apply to their own rollouts. The dataclass defaults themselves are untouched.

Usage:
    python -m packages.research.loop_research.step7_run
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from packages.research.loop_research.baselines import DEV_A_SCHEMA, DEV_B_SCHEMA
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.permutations import PERMUTATION_CLASSES, build_permutation
from packages.research.loop_research.scaffold import ExperimentRun, GateResult, RolloutBatch
from packages.research.loop_research.scaffold_loop import (
    LOOP_NAME,
    ScaffoldLoopConfig,
    ScaffoldLoopResult,
    run_scaffold_loop,
)
from packages.research.loop_research.static_scaffold_loop import CONTROL_NAME, run_static_scaffold_loop
from packages.research.loop_research.structural_gates import run_g2, run_g3

_RUNS_ROOT = Path(".runs/loop_research")
_TASK = "lift the payload to shelf height"
_DOF_REMOVED_JOINT = "j_shoulder"

# Practical, documented scaling for today's local run against a real (if free) CLI provider --
# see module docstring. `ScaffoldLoopConfig`'s own dataclass defaults are unchanged.
#
# Two configs, deliberately: G3 (dev-a vs dev-b) gets one real revision each, so today's run
# demonstrates the loop actually consuming RolloutBatch evidence (C3/R2), not just one-shot
# generation. G2 (original vs each of four permutation mutants) uses a *separate*,
# revision-matched dev-a run at max_revisions=0 paired with zero-revision mutant runs -- G2 must
# isolate "did the schema change the output", and comparing a once-revised original against
# never-revised mutants would conflate revision drift with schema-conditioning, which is exactly
# the confound G2 exists to rule out. Revision-consuming behavior itself is proven twice here (on
# the schema that actually needs it) and is separately covered, deterministically, by
# tests/test_loop_research_step7.py's stubbed multi-revision test -- it does not need re-proving
# on all six arms to be real.
_CONFIG_G3 = ScaffoldLoopConfig(max_revisions=1, episodes_per_batch=4, step_budget=60, seed=7)
_CONFIG_G2 = ScaffoldLoopConfig(max_revisions=0, episodes_per_batch=4, step_budget=60, seed=11)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _latest_tau() -> tuple[float, str]:
    step5_runs = sorted(p for p in _RUNS_ROOT.glob("*_step5_*") if (p / "run.json").exists())
    if not step5_runs:
        raise RuntimeError("No committed step-5 run log found; tau has not been derived yet.")
    latest = step5_runs[-1]
    payload = json.loads((latest / "run.json").read_text())
    tau = payload["control"]["tau"]
    return float(tau), str(latest / "run.json")


def _final_scaffold(result: ScaffoldLoopResult):
    return result.scaffolds[-1] if result.scaffolds else None


def main() -> int:
    tau, tau_source = _latest_tau()

    dev_a_result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=_CONFIG_G3)
    dev_b_result = run_scaffold_loop(DEV_B_SCHEMA, _TASK, config=_CONFIG_G3)
    dev_a_g2_baseline_result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=_CONFIG_G2)

    original_xml = DEV_A_SCHEMA.read_text()
    permutation_results: dict[str, ScaffoldLoopResult] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for permutation_class in PERMUTATION_CLASSES:
            kwargs = {"joint_name": _DOF_REMOVED_JOINT} if permutation_class == "dof_removed" else {}
            mutant_xml = build_permutation(original_xml, permutation_class, **kwargs)
            mutant_path = tmp_dir / f"dev-a.{permutation_class}.xml"
            mutant_path.write_text(mutant_xml)
            permutation_results[permutation_class] = run_scaffold_loop(mutant_path, _TASK, config=_CONFIG_G2)

    dev_a_final = _final_scaffold(dev_a_result)
    dev_b_final = _final_scaffold(dev_b_result)
    dev_a_g2_baseline_final = _final_scaffold(dev_a_g2_baseline_result)

    aborted_arms: list[dict] = []
    for label, result in (
        ("dev-a", dev_a_result),
        ("dev-b", dev_b_result),
        ("dev-a-g2-baseline", dev_a_g2_baseline_result),
        *permutation_results.items(),
    ):
        if not result.scaffolds:
            aborted_arms.append({"arm": label, "status": result.status, "detail": dict(result.cost)})

    gates: list[GateResult] = []
    real_g1 = None
    if dev_a_final is not None:
        _, dev_a_entities = load_model_and_entities(DEV_A_SCHEMA)
        real_g1 = run_g1(dev_a_final, dev_a_entities)
        gates.append(real_g1)

    real_g2_gates: list[GateResult] = []
    if dev_a_g2_baseline_final is not None:
        for permutation_class, result in permutation_results.items():
            mutant_final = _final_scaffold(result)
            if mutant_final is None:
                continue
            kwargs = {"deleted_joint": _DOF_REMOVED_JOINT} if permutation_class == "dof_removed" else {}
            gate = run_g2(
                dev_a_g2_baseline_final, mutant_final, permutation_class=permutation_class, tau=tau, **kwargs
            )
            real_g2_gates.append(gate)
    gates.extend(real_g2_gates)

    real_g3 = None
    if dev_a_final is not None and dev_b_final is not None:
        real_g3 = run_g3(dev_a_final, dev_b_final, tau=tau)
        gates.append(real_g3)

    # --- negative control, same cadence (R7 / data-model.md invariant 4) --------------------------
    control_dev_a = run_static_scaffold_loop(DEV_A_SCHEMA, _TASK)
    control_dev_b = run_static_scaffold_loop(DEV_B_SCHEMA, _TASK)
    _, dev_a_entities = load_model_and_entities(DEV_A_SCHEMA)
    _, dev_b_entities = load_model_and_entities(DEV_B_SCHEMA)

    control_g1_dev_a = run_g1(control_dev_a, dev_a_entities)
    control_g1_dev_b = run_g1(control_dev_a, dev_b_entities)  # same fixed scaffold, dev-b's table

    control_mutant_scaffolds: dict[str, object] = {}
    control_g2_gates: list[GateResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for permutation_class in PERMUTATION_CLASSES:
            kwargs = {"joint_name": _DOF_REMOVED_JOINT} if permutation_class == "dof_removed" else {}
            mutant_xml = build_permutation(original_xml, permutation_class, **kwargs)
            mutant_path = tmp_dir / f"dev-a.{permutation_class}.control.xml"
            mutant_path.write_text(mutant_xml)
            mutant_scaffold = run_static_scaffold_loop(mutant_path, _TASK)
            control_mutant_scaffolds[permutation_class] = mutant_scaffold
            gate_kwargs = {"deleted_joint": _DOF_REMOVED_JOINT} if permutation_class == "dof_removed" else {}
            control_g2_gates.append(
                run_g2(control_dev_a, mutant_scaffold, permutation_class=permutation_class, tau=tau, **gate_kwargs)
            )

    control_g3 = run_g3(control_dev_a, control_dev_b, tau=tau)

    control_required_outcome_met = (
        control_g1_dev_a.passed
        and not control_g1_dev_b.passed
        and all(not g.passed for g in control_g2_gates)
        and not control_g3.passed
    )

    # --- assemble and write ------------------------------------------------------------------------

    all_scaffolds = [
        *dev_a_result.scaffolds,
        *dev_b_result.scaffolds,
        *dev_a_g2_baseline_result.scaffolds,
        *[s for result in permutation_results.values() for s in result.scaffolds],
        control_dev_a,
        control_dev_b,
        *control_mutant_scaffolds.values(),
    ]
    all_batches: list[RolloutBatch] = [
        *dev_a_result.batches,
        *dev_b_result.batches,
        *dev_a_g2_baseline_result.batches,
        *[b for result in permutation_results.values() for b in result.batches],
    ]

    real_loop_g1_g3_met = (
        not aborted_arms
        and real_g1 is not None
        and real_g1.passed
        and all(g.passed for g in real_g2_gates)
        and real_g3 is not None
        and real_g3.passed
    )

    total_calls = {"cheap": 0, "frontier": 0}
    for result in (dev_a_result, dev_b_result, dev_a_g2_baseline_result, *permutation_results.values()):
        for tier, count in result.cost.get("calls_by_tier", {}).items():
            total_calls[tier] = total_calls.get(tier, 0) + count

    run_id = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime()) + f"_step7_{uuid.uuid4().hex[:6]}"
    run = ExperimentRun(
        run_id=run_id,
        git_sha=_git_sha(),
        trigger="routine",
        status="completed" if not aborted_arms else "aborted_error",
        scaffolds=tuple(s.scaffold_id for s in all_scaffolds),
        batches=tuple(b.batch_id for b in all_batches),
        gates=tuple(gates) + tuple(control_g2_gates) + (control_g1_dev_a, control_g1_dev_b, control_g3),
        cost={
            "usd_total": 0.0,
            "usd_ceiling": _CONFIG_G3.usd_ceiling,
            "ceiling_hit": False,
            "calls_by_tier": total_calls,
            "note": "local claude-code/haiku substitute provider (subscription auth); no API spend",
        },
        replay={
            "loop": LOOP_NAME,
            "task_text": _TASK,
            "prompt_version": _CONFIG_G3.prompt_version,
            "cheap_model": _CONFIG_G3.cheap_model,
            "frontier_model": _CONFIG_G3.frontier_model,
            "g3_config": {
                "seed": _CONFIG_G3.seed,
                "max_revisions": _CONFIG_G3.max_revisions,
                "episodes_per_batch": _CONFIG_G3.episodes_per_batch,
                "step_budget": _CONFIG_G3.step_budget,
            },
            "g2_config": {
                "seed": _CONFIG_G2.seed,
                "max_revisions": _CONFIG_G2.max_revisions,
                "episodes_per_batch": _CONFIG_G2.episodes_per_batch,
                "step_budget": _CONFIG_G2.step_budget,
            },
        },
        control={
            "real_loop": {
                "aborted_arms": aborted_arms,
                "g1_dev_a": None if real_g1 is None else {"passed": real_g1.passed, "score": real_g1.score},
                "g2_by_class": {
                    g.detail["permutation"]: {"passed": g.passed, "structural_diff": g.score}
                    for g in real_g2_gates
                },
                "g3_dev_a_vs_dev_b": None if real_g3 is None else {"passed": real_g3.passed, "structural_diff": real_g3.score},
                "g1_g2_g3_met": real_loop_g1_g3_met,
            },
            "negative_control": {
                "loop": CONTROL_NAME,
                "tau": tau,
                "tau_source": tau_source,
                "g1_dev_a": {"passed": control_g1_dev_a.passed, "score": control_g1_dev_a.score},
                "g1_dev_b": {"passed": control_g1_dev_b.passed, "score": control_g1_dev_b.score},
                "g2_by_class": {
                    g.detail["permutation"]: {"passed": g.passed, "structural_diff": g.score}
                    for g in control_g2_gates
                },
                "g3_dev_a_vs_dev_b": {"passed": control_g3.passed, "structural_diff": control_g3.score},
                "required_outcome_met": control_required_outcome_met,
            },
        },
    )
    run_path = run.write(_RUNS_ROOT, all_scaffolds)
    run_dir = run_path.parent
    if all_batches:
        (run_dir / "batches").mkdir(exist_ok=True)
        for batch in all_batches:
            (run_dir / "batches" / f"{batch.batch_id}.json").write_text(
                json.dumps(asdict(batch), indent=2), encoding="utf-8"
            )

    print(f"run: {run_path}")
    print(f"tau={tau} (from {tau_source})")
    if aborted_arms:
        print(f"ABORTED ARMS: {aborted_arms}")
    if real_g1 is not None:
        print(f"real loop G1 (dev-a): {'PASS' if real_g1.passed else 'FAIL'} (score {real_g1.score})")
    for g in real_g2_gates:
        print(f"real loop G2 [{g.detail['permutation']}]: {'PASS' if g.passed else 'FAIL'} (D={g.score}, tau={g.threshold})")
    if real_g3 is not None:
        print(f"real loop G3 (dev-a vs dev-b): {'PASS' if real_g3.passed else 'FAIL'} (D={real_g3.score}, tau={real_g3.threshold})")
    print(f"real loop G1-G3 all met: {real_loop_g1_g3_met}")
    print(f"negative control required outcome met (must stay True): {control_required_outcome_met}")
    return 0 if (real_loop_g1_g3_met and control_required_outcome_met) else 1


if __name__ == "__main__":
    raise SystemExit(main())
