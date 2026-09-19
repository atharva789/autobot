"""Frozen hand-written baseline scaffolds, one per locked dev schema (spec.md §2: "Baseline: One
hand-written scaffold per schema, authored once, frozen").

Distinct from `examples/hand_written_lift.py`, which is a throwaway fixture used only to
demonstrate build-order step 1's gate against a schema that is deliberately *not* one of the four
locked schemas. These two functions build the real per-schema baselines that step 2's gate ("all
compile, baselines run") and later G2/G3/G4 comparisons are measured against.

Do not edit either scaffold after a run has scored against it -- a moving baseline invalidates
every prior comparison (data-model.md invariant 3, by extension). Add a `_v2` function and retire
this one via a spec increment instead.

Both baselines deliberately have no height-based "drop" termination: both dev-a and dev-b rest
their payload directly on a single ground plane with nothing lower to fall to, so a termination
shaped like `body.payload.pos.z < <resting height>` fires on a nearly-motionless policy — a bug
caught while drafting an earlier, discarded prototype of this file. `success` and the rollout
runner's own step-budget `timeout` are the only two termination causes here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from packages.research.loop_research.scaffold import (
    CurriculumStage,
    Provenance,
    RandomizationRange,
    RewardTerm,
    Termination,
    TrainingScaffold,
)

DEV_A_SCHEMA = Path("evals/policy_synthesis/dev/dev-a.xml")
DEV_B_SCHEMA = Path("evals/policy_synthesis/dev/dev-b.xml")


def _schema_digest(schema_path: Path) -> str:
    return "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()


def _reach_lift_grip_terms(grip_site: str, payload_site: str, target_site: str, touch_sensor: str) -> tuple[RewardTerm, ...]:
    return (
        RewardTerm(
            name="reach",
            weight=0.3,
            expression=(
                f"-(abs(site.{grip_site}.pos.x - site.{payload_site}.pos.x) "
                f"+ abs(site.{grip_site}.pos.y - site.{payload_site}.pos.y) "
                f"+ abs(site.{grip_site}.pos.z - site.{payload_site}.pos.z))"
            ),
            symbols=(
                f"site.{grip_site}.pos.x", f"site.{payload_site}.pos.x",
                f"site.{grip_site}.pos.y", f"site.{payload_site}.pos.y",
                f"site.{grip_site}.pos.z", f"site.{payload_site}.pos.z",
            ),
            rationale="The gripper must close the gap to the payload before any lift is possible.",
        ),
        RewardTerm(
            name="lift",
            weight=0.5,
            expression=f"-abs(site.{payload_site}.pos.z - site.{target_site}.pos.z)",
            symbols=(f"site.{payload_site}.pos.z", f"site.{target_site}.pos.z"),
            rationale="Primary task objective (spec.md §2): payload height must match the target height.",
        ),
        RewardTerm(
            name="grip_engaged",
            weight=0.2,
            expression=f"sensor.{touch_sensor}",
            symbols=(f"sensor.{touch_sensor}",),
            rationale="Rewards sustained gripper-payload contact once the reach term has closed the gap.",
        ),
    )


def _success_termination(payload_site: str, target_site: str) -> tuple[Termination, ...]:
    # "timeout" is not declared here: rollout.run_episode already assigns that cause by default
    # to any episode that exhausts max_steps without another termination firing (mujoco_compiler
    # compiles every declared termination's predicate, so an empty/unconditional one isn't a
    # valid way to model it -- the step budget is the rollout runner's job, not the scaffold's).
    return (
        Termination(
            name="success",
            predicate=f"abs(site.{payload_site}.pos.z - site.{target_site}.pos.z) < 0.03",
            symbols=(f"site.{payload_site}.pos.z", f"site.{target_site}.pos.z"),
            cause_label="success",
        ),
    )


def build_dev_a_baseline() -> TrainingScaffold:
    return TrainingScaffold(
        scaffold_id="sc_dev_a_baseline",
        schema_id="dev-a",
        schema_digest=_schema_digest(DEV_A_SCHEMA),
        task_text="lift the payload to shelf height",
        reward_terms=_reach_lift_grip_terms("grip_center", "payload_center", "shelf_target", "s_touch_left"),
        terminations=_success_termination("payload_center", "shelf_target"),
        curriculum=(
            CurriculumStage(0, "payload_mass", (0.3, 0.5), "success_rate > 0.6 over 32 episodes"),
            CurriculumStage(1, "payload_mass", (0.5, 1.0), "success_rate > 0.6 over 32 episodes"),
        ),
        randomization=(
            RandomizationRange("friction.tangential", (0.6, 1.2), "uniform"),
        ),
        provenance=Provenance(
            prompt_version="n/a", model_id="human", model_tier="cheap", seed=42,
        ),
    )


def build_dev_b_baseline() -> TrainingScaffold:
    return TrainingScaffold(
        scaffold_id="sc_dev_b_baseline",
        schema_id="dev-b",
        schema_digest=_schema_digest(DEV_B_SCHEMA),
        task_text="lift the payload to shelf height",
        reward_terms=_reach_lift_grip_terms("grip_center", "payload_center", "shelf_target", "s_touch_jaw"),
        terminations=_success_termination("payload_center", "shelf_target"),
        curriculum=(
            CurriculumStage(0, "payload_mass", (0.2, 0.4), "success_rate > 0.6 over 32 episodes"),
            CurriculumStage(1, "payload_mass", (0.4, 0.8), "success_rate > 0.6 over 32 episodes"),
        ),
        randomization=(
            RandomizationRange("friction.tangential", (0.6, 1.2), "uniform"),
        ),
        provenance=Provenance(
            prompt_version="n/a", model_id="human", model_tier="cheap", seed=42,
        ),
    )


__all__ = ["DEV_A_SCHEMA", "DEV_B_SCHEMA", "build_dev_a_baseline", "build_dev_b_baseline"]
