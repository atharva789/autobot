from __future__ import annotations

import random

from packages.pipeline.types import MorphologyParams
from packages.pipeline.urdf_factory import build_urdf, validate_urdf


def _random_params(rng: random.Random) -> MorphologyParams:
    return MorphologyParams(
        num_arms=rng.choice([0, 1, 2]),
        num_legs=rng.choice([2, 4]),
        has_torso=rng.choice([True, False]),
        torso_length=rng.uniform(0.2, 0.6),
        arm_length=rng.uniform(0.3, 0.8),
        leg_length=rng.uniform(0.4, 1.0),
        arm_dof=rng.randint(3, 7),
        leg_dof=rng.randint(3, 6),
        spine_dof=rng.randint(0, 3),
        joint_damping=rng.uniform(0.01, 1.0),
        joint_stiffness=rng.uniform(1.0, 100.0),
        friction=rng.uniform(0.3, 1.2),
    )


def _passes_gravity_test(xml: str, duration_s: float = 0.5) -> bool:
    """
    Run a short MuJoCo simulation and check the robot hasn't fallen through the floor.
    Returns True when mujoco is not installed (skip the filter).
    """
    try:
        import mujoco  # type: ignore[import]

        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        mujoco.mj_resetData(model, data)
        n_steps = int(duration_s / model.opt.timestep)
        for _ in range(n_steps):
            mujoco.mj_step(model, data)
        root_z = data.qpos[2] if model.nq >= 3 else 1.0
        return float(root_z) > 0.05
    except ImportError:
        return True  # mujoco not installed — skip gravity filter
    except Exception as exc:
        import logging
        logging.warning("gravity test failed for xml: %s", exc)
        return False


def generate_filtered_dataset(
    n_total: int = 10_000,
    seed: int = 0,
) -> list[MorphologyParams]:
    """
    Generate up to *n_total* random MorphologyParams, keep those that pass
    both the structural validator and a brief gravity simulation.
    """
    rng = random.Random(seed)
    valid: list[MorphologyParams] = []
    for _ in range(n_total):
        p = _random_params(rng)
        if not validate_urdf(p):
            continue
        xml = build_urdf(p)
        if _passes_gravity_test(xml):
            valid.append(p)
    return valid
