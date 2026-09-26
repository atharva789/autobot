"""The negative control (spec.md §5, build-order step 4): `static_scaffold_loop`.

Deliberately ignores its `schema_path` and `task_text` arguments and returns one fixed
`TrainingScaffold`, hand-tuned only for dev-a's serial-arm topology. This is the project's "check
on the checker" (eval-contract.md): if this scaffold ever passes G1 on a schema other than dev-a,
or passes G2/G3, the gates are broken and no result from the real loop is admissible (spec.md §5,
R7).

C1 (loop-contract.md) forbids task-text branching in the *real* loop; this module is exempt by
definition -- it exists to prove the gates catch exactly that failure mode, not to satisfy C1.
Unlike the real loop (not yet built -- step 7), this control never calls a model: the fixed
scaffold is authored once, here, the same way a hand-written baseline is, and returned unchanged
on every call regardless of input. Zero cost, deterministic, trivially replayable.

Symbol choice is load-bearing. baselines.py's per-schema baselines deliberately reuse site names
(`grip_center`, `payload_center`, `shelf_target`) across dev-a and dev-b so G2/G3 comparisons are
meaningful. Reusing that same baseline here would make the control accidentally G1-pass on dev-b
too (those sites exist in both schemas) and understate what the gate is supposed to catch. This
scaffold instead references dev-a's serial-arm-specific joints, bodies, and actuators
(`j_shoulder`, `j_elbow`, `upper_arm`, `forearm`, `wrist`, `finger_left`, `m_shoulder`,
`s_touch_left`) -- none of which exist on dev-b's Cartesian-gantry topology -- so a schema-blind
template scaffold fails to resolve at all once the topology actually changes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from packages.research.loop_research.baselines import DEV_A_SCHEMA
from packages.research.loop_research.scaffold import (
    CurriculumStage,
    Provenance,
    RandomizationRange,
    RewardTerm,
    Termination,
    TrainingScaffold,
)

CONTROL_NAME = "static_scaffold_loop"


def _schema_digest(schema_path: Path) -> str:
    return "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()


_FIXED_SCAFFOLD = TrainingScaffold(
    scaffold_id="sc_static_control_v1",
    schema_id="dev-a",  # never updated to reflect whatever schema was actually requested
    schema_digest=_schema_digest(DEV_A_SCHEMA),
    task_text="lift the payload to shelf height",
    reward_terms=(
        RewardTerm(
            name="reach",
            weight=0.3,
            expression="-abs(joint.j_shoulder.qpos - joint.j_elbow.qpos)",
            symbols=("joint.j_shoulder.qpos", "joint.j_elbow.qpos"),
            rationale=(
                "Fixed template term: assumes a shoulder/elbow serial arm exists, regardless of "
                "the robot actually supplied."
            ),
        ),
        RewardTerm(
            name="lift",
            weight=0.5,
            expression="body.wrist.pos.z",
            symbols=("body.wrist.pos.z",),
            rationale="Fixed template term: assumes a body named 'wrist' exists.",
        ),
        RewardTerm(
            name="grip_engaged",
            weight=0.2,
            expression="sensor.s_touch_left",
            symbols=("sensor.s_touch_left",),
            rationale="Fixed template term: assumes dev-a's specific touch-sensor name.",
        ),
    ),
    terminations=(
        Termination(
            name="dropped",
            predicate="body.finger_left.pos.z < 0.01",
            symbols=("body.finger_left.pos.z",),
            cause_label="drop",
        ),
    ),
    curriculum=(
        CurriculumStage(0, "payload_mass", (0.3, 0.5), "success_rate > 0.6 over 32 episodes"),
    ),
    randomization=(
        RandomizationRange("friction.tangential", (0.6, 1.2), "uniform"),
    ),
    provenance=Provenance(
        prompt_version="n/a", model_id="static-control", model_tier="cheap", seed=0,
    ),
)


def run_static_scaffold_loop(
    schema_path: Path, task_text: str, *, config: Any = None
) -> TrainingScaffold:
    """Ignores `schema_path`, `task_text`, and `config`; always returns the same fixed scaffold.

    That is the entire point of the negative control (spec.md §5) -- there is no schema read, no
    task-text branch, no model call. The parameters exist only to match the loop-contract.md
    `ScaffoldLoopRunner` call shape, so the harness can invoke this exactly like the real loop
    once it exists (step 7).
    """

    return _FIXED_SCAFFOLD


__all__ = ["CONTROL_NAME", "run_static_scaffold_loop"]
