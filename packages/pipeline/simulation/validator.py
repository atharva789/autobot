"""
Design validation for robot designs.

Validates both IR consistency and MuJoCo physics viability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.ir.design_ir import RobotDesignIR


@dataclass
class ValidationResult:
    """Result of design validation."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_design(ir: RobotDesignIR) -> ValidationResult:
    """
    Validate a robot design for IR consistency.

    Checks link existence, joint references, and naming.
    """
    result = ValidationResult()

    if len(ir.links) == 0:
        result.warnings.append("Robot has no links")

    if len(ir.joints) == 0 and len(ir.links) > 1:
        result.warnings.append("Robot has multiple links but no joints")

    link_names = {link.name for link in ir.links}

    for joint in ir.joints:
        if joint.parent_link not in link_names:
            result.is_valid = False
            result.errors.append(
                f"Joint '{joint.name}' references missing parent link '{joint.parent_link}'"
            )

        if joint.child_link not in link_names:
            result.is_valid = False
            result.errors.append(
                f"Joint '{joint.name}' references missing child link '{joint.child_link}'"
            )

    if len(link_names) != len(ir.links):
        result.warnings.append("Robot has duplicate link names")

    joint_names = {joint.name for joint in ir.joints}
    if len(joint_names) != len(ir.joints):
        result.warnings.append("Robot has duplicate joint names")

    return result


def validate_compiles(mjcf_xml: str) -> tuple[bool, str]:
    """Check whether MJCF XML compiles to a valid MuJoCo model."""
    import mujoco

    try:
        mujoco.MjModel.from_xml_string(mjcf_xml)
        return True, ""
    except Exception as e:
        return False, str(e)


def validate_zero_control_stability(
    mjcf_xml: str, steps: int = 1000
) -> tuple[bool, str]:
    """Run zero-control simulation and check for NaN, explosion, or collapse."""
    import mujoco
    import numpy as np

    try:
        model = mujoco.MjModel.from_xml_string(mjcf_xml)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)

        for _ in range(steps):
            data.ctrl[:] = 0.0
            mujoco.mj_step(model, data)
            if np.any(np.isnan(data.qpos)) or np.any(np.abs(data.qpos) > 100):
                return False, "Simulation diverged (NaN or explosion)"

        if model.nq >= 3:
            root_z = data.qpos[2]
            if root_z < 0.01:
                return False, f"Robot collapsed (root z={root_z:.4f})"
    except Exception as e:
        return False, str(e)

    return True, ""


def validate_actuator_coverage(mjcf_xml: str) -> tuple[bool, str]:
    """Check that all non-free joints have actuators."""
    import mujoco

    try:
        model = mujoco.MjModel.from_xml_string(mjcf_xml)
    except Exception as e:
        return False, str(e)

    if model.nu == 0:
        return False, "No actuators defined"

    actuated_joints: set[int] = set()
    for i in range(model.nu):
        actuated_joints.add(int(model.actuator_trnid[i, 0]))

    unactuated = []
    for j in range(model.njnt):
        if model.jnt_type[j] != 0 and j not in actuated_joints:
            unactuated.append(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j))

    if unactuated:
        return False, f"Unactuated joints: {unactuated}"
    return True, ""


def validate_no_self_collision(mjcf_xml: str) -> tuple[bool, str]:
    """Check for self-collision in the rest pose."""
    import mujoco

    try:
        model = mujoco.MjModel.from_xml_string(mjcf_xml)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
    except Exception as e:
        return False, str(e)

    if data.ncon > 0:
        return False, f"Self-collision in rest pose: {data.ncon} contacts"
    return True, ""


def validate_full(mjcf_xml: str) -> ValidationResult:
    """Run all MuJoCo-based validation checks on compiled MJCF."""
    result = ValidationResult()

    ok, err = validate_compiles(mjcf_xml)
    if not ok:
        result.is_valid = False
        result.errors.append(f"MJCF compile failed: {err}")
        return result

    ok, err = validate_actuator_coverage(mjcf_xml)
    if not ok:
        result.is_valid = False
        result.errors.append(err)

    ok, err = validate_no_self_collision(mjcf_xml)
    if not ok:
        result.warnings.append(err)

    ok, err = validate_zero_control_stability(mjcf_xml)
    if not ok:
        result.is_valid = False
        result.errors.append(err)

    return result
