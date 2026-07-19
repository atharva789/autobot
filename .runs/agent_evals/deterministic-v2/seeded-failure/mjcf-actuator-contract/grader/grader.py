"""Protected direct-MuJoCo grader for the actuator contract task."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import mujoco


EXPECTED_AXIS = (0.0, 1.0, 0.0)
EXPECTED_RANGE_RAD = (math.radians(-30.0), math.radians(45.0))
EXPECTED_CTRL_RANGE = (-1.0, 1.0)
EXPECTED_FORCE_RANGE_NM = (-12.0, 12.0)
ABS_TOLERANCE = 1e-9
ROLLOUT_COMMAND = 1.0
ROLLOUT_STEPS = 250
MIN_POSITIVE_DELTA_RAD = 0.05


def _result(
    grade_id: str,
    category: str,
    status: str,
    assertion: str,
    *,
    parameters: dict[str, Any],
    observed: dict[str, Any],
    raw_output: str,
) -> dict[str, Any]:
    return {
        "grade_id": grade_id,
        "category": category,
        "status": status,
        "assertion": assertion,
        "parameters": parameters,
        "observed": observed,
        "raw_output": raw_output,
    }


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=ABS_TOLERANCE)


def _vector_close(observed: tuple[float, ...], expected: tuple[float, ...]) -> bool:
    return len(observed) == len(expected) and all(
        _close(left, right) for left, right in zip(observed, expected, strict=True)
    )


def _unrun_after_load_error(message: str) -> list[dict[str, Any]]:
    raw = json.dumps({"load_error": message}, sort_keys=True)
    definitions = (
        ("joint-axis", "static", "shoulder is a hinge with axis 0 1 0."),
        ("joint-range", "static", "shoulder range is -30 to 45 degrees."),
        ("actuator-binding", "static", "shoulder_motor is bound to shoulder."),
        ("actuator-control-range", "static", "shoulder_motor control range is -1 to 1."),
        ("actuator-force-range", "static", "shoulder_motor force range is -12 to 12 N*m."),
        ("actuator-positive-direction", "behavior", "A positive command increases shoulder position by at least 0.05 radians."),
    )
    return [
        _result(
            grade_id,
            category,
            "unrun",
            assertion,
            parameters={},
            observed={"reason": "MuJoCo model did not load"},
            raw_output=raw,
        )
        for grade_id, category, assertion in definitions
    ]


def grade(workspace: Path) -> list[dict[str, Any]]:
    """Grade direct model contracts and an executed positive-control rollout."""

    robot_path = workspace / "robot.xml"
    try:
        model = mujoco.MjModel.from_xml_path(str(robot_path))
    except Exception as exc:  # MuJoCo exposes multiple parse/load exception types.
        message = f"{type(exc).__name__}: {exc}"
        load_grade = _result(
            "mjcf-load",
            "simulator-load",
            "fail",
            "robot.xml loads as a MuJoCo model.",
            parameters={"artifact": "robot.xml"},
            observed={"loaded": False, "error": message},
            raw_output=message,
        )
        return [load_grade, *_unrun_after_load_error(message)]

    joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "shoulder")
    actuator_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "shoulder_motor")
    load_observed = {
        "loaded": True,
        "njnt": int(model.njnt),
        "nu": int(model.nu),
        "shoulder_joint_id": int(joint_id),
        "shoulder_motor_id": int(actuator_id),
    }
    grades = [
        _result(
            "mjcf-load",
            "simulator-load",
            "pass",
            "robot.xml loads as a MuJoCo model.",
            parameters={"artifact": "robot.xml"},
            observed=load_observed,
            raw_output=json.dumps(load_observed, sort_keys=True),
        )
    ]

    if joint_id < 0 or actuator_id < 0:
        missing = []
        if joint_id < 0:
            missing.append("shoulder joint")
        if actuator_id < 0:
            missing.append("shoulder_motor actuator")
        message = "Missing required named model object(s): " + ", ".join(missing)
        for grade_id, category, assertion in (
            ("joint-axis", "static", "shoulder is a hinge with axis 0 1 0."),
            ("joint-range", "static", "shoulder range is -30 to 45 degrees."),
            ("actuator-binding", "static", "shoulder_motor is bound to shoulder."),
            ("actuator-control-range", "static", "shoulder_motor control range is -1 to 1."),
            ("actuator-force-range", "static", "shoulder_motor force range is -12 to 12 N*m."),
            ("actuator-positive-direction", "behavior", "A positive command increases shoulder position by at least 0.05 radians."),
        ):
            grades.append(
                _result(
                    grade_id,
                    category,
                    "fail" if grade_id != "actuator-positive-direction" else "unrun",
                    assertion,
                    parameters={},
                    observed={"missing_objects": missing},
                    raw_output=message,
                )
            )
        return grades

    observed_joint_type = int(model.jnt_type[joint_id])
    expected_hinge_type = int(mujoco.mjtJoint.mjJNT_HINGE)
    observed_axis = tuple(float(value) for value in model.jnt_axis[joint_id])
    axis_ok = observed_joint_type == expected_hinge_type and _vector_close(observed_axis, EXPECTED_AXIS)
    axis_evidence = {
        "joint": "shoulder",
        "joint_type": observed_joint_type,
        "expected_hinge_type": expected_hinge_type,
        "axis": list(observed_axis),
    }
    grades.append(
        _result(
            "joint-axis",
            "static",
            "pass" if axis_ok else "fail",
            "shoulder is a hinge with axis 0 1 0.",
            parameters={"expected_axis": list(EXPECTED_AXIS), "absolute_tolerance": ABS_TOLERANCE},
            observed=axis_evidence,
            raw_output=json.dumps(axis_evidence, sort_keys=True),
        )
    )

    observed_range = tuple(float(value) for value in model.jnt_range[joint_id])
    range_evidence = {
        "joint": "shoulder",
        "range_rad": list(observed_range),
        "range_degree": [math.degrees(value) for value in observed_range],
    }
    grades.append(
        _result(
            "joint-range",
            "static",
            "pass" if _vector_close(observed_range, EXPECTED_RANGE_RAD) else "fail",
            "shoulder range is -30 to 45 degrees.",
            parameters={"expected_range_rad": list(EXPECTED_RANGE_RAD), "absolute_tolerance": ABS_TOLERANCE},
            observed=range_evidence,
            raw_output=json.dumps(range_evidence, sort_keys=True),
        )
    )

    transmission_joint_id = int(model.actuator_trnid[actuator_id, 0])
    binding_evidence = {
        "actuator": "shoulder_motor",
        "transmission_joint_id": transmission_joint_id,
        "shoulder_joint_id": int(joint_id),
    }
    grades.append(
        _result(
            "actuator-binding",
            "static",
            "pass" if transmission_joint_id == joint_id else "fail",
            "shoulder_motor is bound to shoulder.",
            parameters={"required_joint": "shoulder"},
            observed=binding_evidence,
            raw_output=json.dumps(binding_evidence, sort_keys=True),
        )
    )

    observed_ctrl_range = tuple(float(value) for value in model.actuator_ctrlrange[actuator_id])
    ctrl_limited = bool(model.actuator_ctrllimited[actuator_id])
    control_evidence = {
        "actuator": "shoulder_motor",
        "ctrl_limited": ctrl_limited,
        "ctrl_range": list(observed_ctrl_range),
    }
    grades.append(
        _result(
            "actuator-control-range",
            "static",
            "pass" if ctrl_limited and _vector_close(observed_ctrl_range, EXPECTED_CTRL_RANGE) else "fail",
            "shoulder_motor control range is -1 to 1.",
            parameters={"expected_control_range": list(EXPECTED_CTRL_RANGE), "absolute_tolerance": ABS_TOLERANCE},
            observed=control_evidence,
            raw_output=json.dumps(control_evidence, sort_keys=True),
        )
    )

    observed_force_range = tuple(float(value) for value in model.actuator_forcerange[actuator_id])
    force_limited = bool(model.actuator_forcelimited[actuator_id])
    force_evidence = {
        "actuator": "shoulder_motor",
        "force_limited": force_limited,
        "force_range_Nm": list(observed_force_range),
    }
    grades.append(
        _result(
            "actuator-force-range",
            "static",
            "pass" if force_limited and _vector_close(observed_force_range, EXPECTED_FORCE_RANGE_NM) else "fail",
            "shoulder_motor force range is -12 to 12 N*m.",
            parameters={"expected_force_range_Nm": list(EXPECTED_FORCE_RANGE_NM), "absolute_tolerance": ABS_TOLERANCE},
            observed=force_evidence,
            raw_output=json.dumps(force_evidence, sort_keys=True),
        )
    )

    data = mujoco.MjData(model)
    mujoco.mj_resetData(model, data)
    qpos_address = int(model.jnt_qposadr[joint_id])
    initial_position = float(data.qpos[qpos_address])
    samples = [{"step": 0, "qpos_rad": initial_position}]
    data.ctrl[actuator_id] = ROLLOUT_COMMAND
    for step in range(1, ROLLOUT_STEPS + 1):
        mujoco.mj_step(model, data)
        if step % 50 == 0 or step == ROLLOUT_STEPS:
            samples.append({"step": step, "qpos_rad": float(data.qpos[qpos_address])})
    final_position = float(data.qpos[qpos_address])
    delta = final_position - initial_position
    direction_evidence = {
        "joint": "shoulder",
        "actuator": "shoulder_motor",
        "initial_qpos_rad": initial_position,
        "final_qpos_rad": final_position,
        "delta_qpos_rad": delta,
        "final_qvel_rad_s": float(data.qvel[int(model.jnt_dofadr[joint_id])]),
        "samples": samples,
    }
    grades.append(
        _result(
            "actuator-positive-direction",
            "behavior",
            "pass" if delta >= MIN_POSITIVE_DELTA_RAD else "fail",
            "A positive command increases shoulder position by at least 0.05 radians.",
            parameters={
                "control_command": ROLLOUT_COMMAND,
                "steps": ROLLOUT_STEPS,
                "timestep_seconds": float(model.opt.timestep),
                "minimum_positive_delta_rad": MIN_POSITIVE_DELTA_RAD,
            },
            observed=direction_evidence,
            raw_output=json.dumps(direction_evidence, sort_keys=True),
        )
    )
    return grades
