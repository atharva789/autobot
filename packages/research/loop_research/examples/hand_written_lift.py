"""A hand-written scaffold + fixture schema, used only to demonstrate build-order step 1's gate:
"a hand-written scaffold trains" (plan.md §7 step 1).

This is deliberately NOT one of spec.md §2's four locked schemas (dev-a, dev-b, holdout-a,
holdout-b) — those, and the negative control that must fail against them, are step 2 and step 4.
This fixture exists only to prove the TrainingScaffold compiler produces a MuJoCo environment whose
reward and termination logic are causally coupled to real physics: given a generous step budget the
scaffold succeeds, given too little budget it does not. Compiling and stepping correctly is what
step 1 requires; it is not a claim about schema-conditioning, which is what G2/G3 (step 5) exist to
measure.
"""

from __future__ import annotations

import hashlib

from packages.research.loop_research.scaffold import (
    CurriculumStage,
    Provenance,
    RandomizationRange,
    RewardTerm,
    Termination,
    TrainingScaffold,
)

FIXTURE_MJCF = """<mujoco model="lift_fixture">
  <compiler angle="radian"/>
  <option timestep="0.004167" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="1 1 0.1" rgba="0.6 0.6 0.6 1"/>
    <body name="lifter" pos="0 0 0.05">
      <joint name="j_lift" type="slide" axis="0 0 1" range="0 1" limited="true" damping="2"/>
      <geom name="lifter_geom" type="box" size="0.05 0.05 0.02" mass="0.2"/>
      <body name="payload" pos="0 0 0.05">
        <geom name="payload_geom" type="box" size="0.04 0.04 0.04" mass="0.3"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <position name="act_lift" joint="j_lift" kp="40" ctrlrange="0 1"/>
  </actuator>
</mujoco>
"""


def _schema_digest(xml: str) -> str:
    return "sha256:" + hashlib.sha256(xml.encode("utf-8")).hexdigest()


def build_hand_written_lift_scaffold() -> TrainingScaffold:
    return TrainingScaffold(
        scaffold_id="sc_handwritten_lift_v1",
        schema_id="fixture-lift-v1",
        schema_digest=_schema_digest(FIXTURE_MJCF),
        task_text="lift the payload to the sampled target height",
        reward_terms=(
            RewardTerm(
                name="lift_progress",
                weight=1.0,
                expression="clamp(body.payload.pos.z / const.target_height, 0.0, 1.0)",
                symbols=("body.payload.pos.z", "const.target_height"),
                rationale="Dense shaping toward the sampled target height.",
            ),
        ),
        terminations=(
            Termination(
                name="reached_target",
                predicate="body.payload.pos.z - const.target_height >= -0.02",
                symbols=("body.payload.pos.z", "const.target_height"),
                cause_label="success",
            ),
        ),
        curriculum=(
            CurriculumStage(
                stage=0,
                parameter="const.target_height",
                range=(0.3, 0.4),
                advance_when="success_rate > 0.6 over 8 episodes",
            ),
        ),
        randomization=(
            RandomizationRange(parameter="const.target_height", range=(0.3, 0.8), distribution="uniform"),
        ),
        provenance=Provenance(
            prompt_version="v0-handwritten",
            model_id="hand-written-baseline",
            model_tier="cheap",
            seed=42,
        ),
    )


def target_height_policy(constants, step: int):
    """Position-actuator policy: drive straight to the sampled target height every step."""

    return [constants["target_height"]]


__all__ = ["FIXTURE_MJCF", "build_hand_written_lift_scaffold", "target_height_policy"]
