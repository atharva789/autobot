"""Targeted re-verification of step 7's remaining gap: the G2 `dof_removed` permutation.

Not a re-run of the full `step7_run.py` six-arm grid. That already produced real, passing evidence
for dev-a, dev-b, and G2's other three permutation classes
(`.runs/loop_research/2026-08-09T14-00-56Z_step7_9d1e00/run.json`) -- nothing about
`scaffold_loop.py`'s initial-generation prompt changed today, only the compile-error repair path
added in scaffold_loop.py (2026-08-10), which only activates on a compile failure. Those five arms
did not fail to compile then and have no reason to behave differently today; re-running them would
burn real wall-clock re-deriving numbers that are already honestly committed, not producing new
evidence.

This script re-runs only the arm that aborted: dev-a's `dof_removed` permutation, for real, against
the local claude-code/haiku substitute provider, to check whether the new repair loop
(scaffold_loop.ScaffoldLoopConfig.max_compile_retries) closes the gap 2026-08-09 left open. It reuses
the already-committed `dev-a-g2-baseline` scaffold from that same run as the "original" side of the
G2 diff -- same reasoning: that scaffold's generation did not fail and is not re-derived.

Usage:
    python -m packages.research.loop_research.step7_dof_removed_recheck
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from packages.research.loop_research.baselines import DEV_A_SCHEMA
from packages.research.loop_research.permutations import build_permutation
from packages.research.loop_research.scaffold import ExperimentRun, scaffold_from_dict
from packages.research.loop_research.scaffold_loop import ScaffoldLoopConfig, run_scaffold_loop
from packages.research.loop_research.structural_gates import run_g2

_RUNS_ROOT = Path(".runs/loop_research")
_PRIOR_RUN = _RUNS_ROOT / "2026-08-09T14-00-56Z_step7_9d1e00"
_PRIOR_BASELINE_SCAFFOLD = _PRIOR_RUN / "scaffolds" / "sc_9a69529415bb.json"
_TASK = "lift the payload to shelf height"
_DOF_REMOVED_JOINT = "j_shoulder"
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
    latest = step5_runs[-1]
    payload = json.loads((latest / "run.json").read_text())
    return float(payload["control"]["tau"]), str(latest / "run.json")


def main() -> int:
    assert _PRIOR_BASELINE_SCAFFOLD.exists(), (
        f"expected the prior run's dev-a G2 baseline scaffold at {_PRIOR_BASELINE_SCAFFOLD}; "
        "re-derive from step7_run.py if the prior run was pruned"
    )
    baseline = scaffold_from_dict(json.loads(_PRIOR_BASELINE_SCAFFOLD.read_text()))
    baseline_source = str(_PRIOR_BASELINE_SCAFFOLD)

    tau, tau_source = _latest_tau()

    original_xml = DEV_A_SCHEMA.read_text()
    mutant_xml = build_permutation(original_xml, "dof_removed", joint_name=_DOF_REMOVED_JOINT)
    mutant_path = Path(".runs/loop_research/_scratch_dof_removed_recheck.xml")
    mutant_path.write_text(mutant_xml)
    try:
        started = time.time()
        result = run_scaffold_loop(mutant_path, _TASK, config=_CONFIG_G2)
        elapsed = round(time.time() - started, 2)
    finally:
        mutant_path.unlink(missing_ok=True)

    mutant_final = result.scaffolds[-1] if result.scaffolds else None

    gate = None
    if mutant_final is not None:
        gate = run_g2(
            baseline, mutant_final, permutation_class="dof_removed", tau=tau, deleted_joint=_DOF_REMOVED_JOINT
        )

    run_id = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime()) + f"_step7-dof-removed-recheck_{uuid.uuid4().hex[:6]}"
    run = ExperimentRun(
        run_id=run_id,
        git_sha=_git_sha(),
        trigger="routine",
        status=result.status,
        scaffolds=tuple(s.scaffold_id for s in result.scaffolds) + (baseline.scaffold_id,),
        batches=tuple(b.batch_id for b in result.batches),
        gates=(gate,) if gate is not None else (),
        cost={**result.cost, "wall_clock_s": elapsed},
        replay={
            "note": "targeted re-run of only the dof_removed arm; see module docstring",
            "prior_full_run": str(_PRIOR_RUN / "run.json"),
            "reused_baseline_scaffold": baseline_source,
            "task_text": _TASK,
            "config": {
                "seed": _CONFIG_G2.seed,
                "max_revisions": _CONFIG_G2.max_revisions,
                "episodes_per_batch": _CONFIG_G2.episodes_per_batch,
                "step_budget": _CONFIG_G2.step_budget,
                "max_compile_retries": _CONFIG_G2.max_compile_retries,
            },
        },
        control={
            "note": (
                "single-arm targeted recheck, not the full six-arm step-7 grid; the other five "
                "arms' evidence is unchanged and lives in the prior_run referenced above"
            ),
            "loop_status": result.status,
            "loop_cost": result.cost,
            "tau": tau,
            "tau_source": tau_source,
        },
    )
    run_path = run.write(_RUNS_ROOT, list(result.scaffolds) + [baseline])
    run_dir = run_path.parent
    if result.batches:
        (run_dir / "batches").mkdir(exist_ok=True)
        for batch in result.batches:
            (run_dir / "batches" / f"{batch.batch_id}.json").write_text(
                json.dumps(asdict(batch), indent=2), encoding="utf-8"
            )

    print(f"run: {run_path}")
    print(f"loop status: {result.status}  (wall_clock_s={elapsed})")
    print(f"cost: {result.cost}")
    if gate is not None:
        print(f"G2 [dof_removed]: {'PASS' if gate.passed else 'FAIL'} (D={gate.score}, tau={gate.threshold})")
    else:
        print("G2 [dof_removed]: not scored -- no scaffold produced")
    return 0 if (gate is not None and gate.passed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
