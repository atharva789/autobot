"""Build-order step 2 tests (plan.md §7): "Four structurally different schemas. Gate: all
compile, baselines run."

Only two of the four locked schemas exist yet (dev-a, dev-b); holdout-a/holdout-b are step 8's job
and must not be created early (spec.md §2, evals/policy_synthesis/holdout/README.md). These tests
cover what step 2 actually requires now: dev-a and dev-b are structurally different per spec.md
§2's three axes (DOF count, kinematic topology, actuator type), both compile, and both frozen
baselines run to completion and produce a structurally valid RolloutBatch. "Baselines run" is not
a claim that they succeed at the task -- see baselines.py's module docstring.
"""

from __future__ import annotations

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


def test_dev_a_and_dev_b_differ_structurally():
    """spec.md §2: the four schemas must differ in DOF count, kinematic topology, and actuator
    type -- otherwise the G3 divergence gate (build-order step 5) would be unfalsifiable."""

    model_a, entities_a = load_model_and_entities(DEV_A_SCHEMA)
    model_b, entities_b = load_model_and_entities(DEV_B_SCHEMA)

    assert model_a.nu != model_b.nu, "actuator (DOF) count must differ"

    joint_types_a = {int(t) for t in model_a.jnt_type}
    joint_types_b = {int(t) for t in model_b.jnt_type}
    assert joint_types_a != joint_types_b, "kinematic topology (joint type mix) must differ"

    # MuJoCo lowers both <motor> and <position> to gaintype=FIXED; `biastype` is what actually
    # distinguishes them -- NONE (raw torque) for motor vs AFFINE (kp-servo) for position.
    biastype_a = {int(t) for t in model_a.actuator_biastype}
    biastype_b = {int(t) for t in model_b.actuator_biastype}
    assert biastype_a != biastype_b, "actuator type (bias model: torque vs. position-servo) must differ"

    assert entities_a.bodies != entities_b.bodies
    assert entities_a.joints != entities_b.joints


def test_both_baselines_compile_and_g1_passes():
    for schema_path, build in ((DEV_A_SCHEMA, build_dev_a_baseline), (DEV_B_SCHEMA, build_dev_b_baseline)):
        scaffold = build()
        model, entities = load_model_and_entities(schema_path)
        compiled = compile_scaffold(scaffold, model, entities)
        compiled.reset()
        outcome = compiled.step(np.zeros(model.nu), constants={})
        assert np.isfinite(outcome.reward)

        gate = run_g1(scaffold, entities)
        assert gate.passed
        assert gate.score == 1.0


def test_both_baselines_run_a_rollout_batch():
    for schema_path, build, policy in (
        (DEV_A_SCHEMA, build_dev_a_baseline, lambda c, s: np.zeros(6)),
        (DEV_B_SCHEMA, build_dev_b_baseline, lambda c, s: np.array([0.15, 0.10, 0.06 if s < 50 else 0.43, 0.05])),
    ):
        scaffold = build()
        model, entities = load_model_and_entities(schema_path)
        batch = run_batch(
            scaffold,
            model,
            lambda: compile_scaffold(scaffold, model, entities),
            policy,
            batch_id="rb_test",
            episodes=3,
            max_steps=100,
            seed=1,
        )
        assert batch.episodes == 3
        assert sum(batch.termination_histogram.values()) == 3
        assert 0.0 <= batch.success_rate <= 1.0
