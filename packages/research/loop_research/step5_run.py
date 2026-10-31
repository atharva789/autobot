"""Generates the committed run log for build-order step 5 (plan.md §7): "G2/G3 structural diff.
Gate: separates control from per-schema hand-written scaffolds."

Two things happen here, both against the static negative control -- the real loop is step 7 and
does not exist yet, so G2/G3 can only be *exercised* today, not used to judge a real scaffold:

1. Derive tau (eval-contract.md): run the control against dev-a and each of G2's four permutation
   mutants of dev-a (link_scaled, limits_altered, dof_removed, topology_swapped) to get
   D_control_max, and diff the two hand-written baselines (dev-a vs dev-b) to get
   D_handwritten_min. tau is the midpoint between them.

2. Score the control with G2 (all four classes) and G3 (dev-a vs dev-b) against that tau. Per the
   required-outcome table, both must FAIL. If they do not, the gates are broken (R7) and this
   script says so loudly rather than reporting a passing run.

Usage:
    python -m packages.research.loop_research.step5_run
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from packages.research.loop_research.baselines import (
    DEV_A_SCHEMA,
    DEV_B_SCHEMA,
    build_dev_a_baseline,
    build_dev_b_baseline,
)
from packages.research.loop_research.permutations import PERMUTATION_CLASSES, build_permutation
from packages.research.loop_research.scaffold import ExperimentRun, GateResult
from packages.research.loop_research.static_scaffold_loop import CONTROL_NAME, run_static_scaffold_loop
from packages.research.loop_research.structural_diff import structural_diff
from packages.research.loop_research.structural_gates import run_g2, run_g3
from packages.research.loop_research.tau import TauUndefinedError, derive_tau

_RUNS_ROOT = Path(".runs/loop_research")
_TASK = "lift the payload to shelf height"

# dof_removed targets j_shoulder specifically (not permutations.py's j_wrist default): the
# control's fixed scaffold (static_scaffold_loop.py) references joint.j_shoulder.qpos, so this is
# the one class where the dof_removed hard check ("no surviving symbol may reference the deleted
# joint") has something real to catch, rather than trivially passing because the control never
# mentioned that joint to begin with.
_DOF_REMOVED_JOINT = "j_shoulder"


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    original_xml = DEV_A_SCHEMA.read_text()
    control_original = run_static_scaffold_loop(DEV_A_SCHEMA, _TASK)

    g2_inputs = []  # (permutation_class, mutant_scaffold, mutant_digest, extra_kwargs)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for permutation_class in PERMUTATION_CLASSES:
            kwargs = {"joint_name": _DOF_REMOVED_JOINT} if permutation_class == "dof_removed" else {}
            mutant_xml = build_permutation(original_xml, permutation_class, **kwargs)
            mutant_path = tmp_dir / f"dev-a.{permutation_class}.xml"
            mutant_path.write_text(mutant_xml)
            mutant_scaffold = run_static_scaffold_loop(mutant_path, _TASK)
            g2_inputs.append((permutation_class, mutant_scaffold, _digest(mutant_xml)))

    control_dev_b = run_static_scaffold_loop(DEV_B_SCHEMA, _TASK)

    # --- calibration: D_control_max, D_handwritten_min, tau -------------------------------------

    control_diffs = [structural_diff(control_original, mutant) for _, mutant, _ in g2_inputs]
    control_diffs.append(structural_diff(control_original, control_dev_b))
    d_control_max = max(control_diffs)

    baseline_a, baseline_b = build_dev_a_baseline(), build_dev_b_baseline()
    d_handwritten_min = structural_diff(baseline_a, baseline_b)

    try:
        tau = derive_tau(d_control_max, d_handwritten_min)
        tau_error = None
    except TauUndefinedError as exc:
        tau = None
        tau_error = str(exc)

    run_id = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime()) + f"_step5_{uuid.uuid4().hex[:6]}"

    if tau_error is not None:
        run = ExperimentRun(
            run_id=run_id,
            git_sha=_git_sha(),
            trigger="routine",
            status="aborted_error",
            scaffolds=(control_original.scaffold_id, baseline_a.scaffold_id, baseline_b.scaffold_id),
            batches=(),
            gates=(),
            cost={"usd_total": 0.0, "usd_ceiling": 0.0, "ceiling_hit": False, "note": "no model calls"},
            replay={"prompt_version": "n/a", "model_id": CONTROL_NAME, "seed": 0},
            control={
                "loop": CONTROL_NAME,
                "d_control_max": round(d_control_max, 4),
                "d_handwritten_min": round(d_handwritten_min, 4),
                "tau_error": tau_error,
            },
        )
        run_path = run.write(_RUNS_ROOT, [control_original, baseline_a, baseline_b])
        print(f"run: {run_path}")
        print(f"ABORTED: {tau_error}")
        return 1

    gates: list[GateResult] = []
    for permutation_class, mutant_scaffold, mutant_digest in g2_inputs:
        kwargs = {"deleted_joint": _DOF_REMOVED_JOINT} if permutation_class == "dof_removed" else {}
        gate = run_g2(
            control_original, mutant_scaffold, permutation_class=permutation_class, tau=tau, **kwargs
        )
        gates.append(gate)

    gate_g3_control = run_g3(control_original, control_dev_b, tau=tau)
    gates.append(gate_g3_control)

    # Not part of the required-outcome table (that's control-only), but this is the very
    # comparison tau was calibrated from -- recording it lets a human sanity-check the derivation
    # without recomputing it by hand.
    gate_g3_baselines = run_g3(baseline_a, baseline_b, tau=tau)

    control_g2_all_fail = all(not g.passed for g in gates if g.gate == "G2")
    control_g3_fail = not gate_g3_control.passed
    required_outcome_met = control_g2_all_fail and control_g3_fail

    run = ExperimentRun(
        run_id=run_id,
        git_sha=_git_sha(),
        trigger="routine",
        status="completed",
        scaffolds=(control_original.scaffold_id, baseline_a.scaffold_id, baseline_b.scaffold_id),
        batches=(),
        gates=tuple(gates) + (gate_g3_baselines,),
        cost={
            "usd_total": 0.0,
            "usd_ceiling": 0.0,
            "ceiling_hit": False,
            "note": "structural diff is arithmetic over already-produced scaffolds; no model calls",
        },
        replay={
            "dev_a_schema_digest": _digest(original_xml),
            "dev_b_schema_digest": _digest(DEV_B_SCHEMA.read_text()),
            "prompt_version": "n/a",
            "model_id": CONTROL_NAME,
            "seed": 0,
        },
        control={
            "loop": CONTROL_NAME,
            "d_control_max": round(d_control_max, 4),
            "d_handwritten_min": round(d_handwritten_min, 4),
            "tau": round(tau, 4),
            "tau_formula": "D_control_max + 0.5 * (D_handwritten_min - D_control_max)",
            "g2_by_class": {
                g.gate + ":" + g.detail["permutation"]: {"passed": g.passed, "structural_diff": g.score}
                for g in gates
                if g.gate == "G2"
            },
            "g3_dev_a_vs_dev_b": {"passed": gate_g3_control.passed, "structural_diff": gate_g3_control.score},
            "g3_baselines_dev_a_vs_dev_b": {
                "passed": gate_g3_baselines.passed,
                "structural_diff": gate_g3_baselines.score,
                "note": "this is the D_handwritten_min comparison tau was derived from",
            },
            "required_outcome_met": required_outcome_met,
        },
    )
    run_path = run.write(_RUNS_ROOT, [control_original, baseline_a, baseline_b])

    print(f"run: {run_path}")
    print(f"D_control_max={d_control_max:.4f}  D_handwritten_min={d_handwritten_min:.4f}  tau={tau:.4f}")
    for g in gates:
        if g.gate == "G2":
            label = g.detail["permutation"]
        else:
            # Note, not a bug: the control's own schema_id field never changes (that's the whole
            # point of the negative control), so g.detail's self-reported "dev-a vs dev-a" is
            # accurate to what the control *claims* -- it was actually run against dev-a vs dev-b.
            label = "dev-a vs dev-b (control's self-reported schema_id stays 'dev-a' either way)"
        print(f"{g.gate} [{label}]: {'PASS' if g.passed else 'FAIL'} (D={g.score}, tau={g.threshold})")
    print(f"required outcome (control fails G2 x4 and G3): {'MET' if required_outcome_met else 'NOT MET -- gates are broken'}")
    return 0 if required_outcome_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
