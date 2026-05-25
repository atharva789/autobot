"""
MuJoCo screening service for design evaluation.

Performs physics-based checks using actual MuJoCo simulation:
- MJCF compilation
- Zero-control stability (real simulation)
- Actuator coverage
- Self-collision detection
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf


@dataclass
class ScreeningResult:
    """Result of MuJoCo screening."""

    mjcf_compiled: bool = True
    mjcf_xml: str | None = None
    stability_score: float = 0.0
    reachability_score: float = 0.0
    task_sanity_score: float = 0.0
    overall_score: float = 0.0
    errors: list[str] = field(default_factory=list)


def screen_design(ir: RobotDesignIR) -> ScreeningResult:
    """
    Screen a robot design using actual MuJoCo simulation.

    1. MJCF compilation
    2. Zero-control stability (simulated)
    3. Actuator coverage check
    4. Self-collision check in rest pose
    """
    from packages.pipeline.simulation.validator import (
        validate_compiles,
        validate_actuator_coverage,
        validate_no_self_collision,
    )

    result = ScreeningResult()

    try:
        mjcf_xml = compile_to_mjcf(ir)
        result.mjcf_xml = mjcf_xml
    except Exception as e:
        result.mjcf_compiled = False
        result.errors.append(f"MJCF compilation failed: {e}")
        return result

    ok, err = validate_compiles(mjcf_xml)
    if not ok:
        result.mjcf_compiled = False
        result.errors.append(f"MuJoCo load failed: {err}")
        return result

    result.stability_score = _simulate_stability(mjcf_xml)

    ok, err = validate_actuator_coverage(mjcf_xml)
    result.task_sanity_score = 1.0 if ok else 0.0
    if not ok:
        result.errors.append(err)

    ok, err = validate_no_self_collision(mjcf_xml)
    result.reachability_score = 1.0 if ok else 0.2
    if not ok:
        result.errors.append(err)

    result.overall_score = (
        result.stability_score * 0.4
        + result.reachability_score * 0.3
        + result.task_sanity_score * 0.3
    )

    return result


def _simulate_stability(mjcf_xml: str, steps: int = 1000) -> float:
    """
    Run zero-control simulation and score based on final state.

    Returns 0.0-1.0 where 1.0 means the robot remained upright and stable.
    """
    import mujoco
    import numpy as np

    model = mujoco.MjModel.from_xml_string(mjcf_xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    initial_z = data.qpos[2] if model.nq >= 3 else 0.5

    for _ in range(steps):
        data.ctrl[:] = 0.0
        mujoco.mj_step(model, data)
        if np.any(np.isnan(data.qpos)):
            return 0.0

    if model.nq < 3:
        return 0.5

    final_z = data.qpos[2]

    if final_z < 0.01:
        return 0.1

    height_ratio = min(final_z / max(initial_z, 0.01), 1.0)
    max_vel = float(np.max(np.abs(data.qvel)))
    velocity_penalty = min(max_vel / 10.0, 0.5)

    return max(0.0, min(1.0, height_ratio - velocity_penalty))
