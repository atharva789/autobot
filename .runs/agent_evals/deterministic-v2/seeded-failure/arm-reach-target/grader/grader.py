from __future__ import annotations

import json
import traceback
from pathlib import Path

import mujoco
import numpy as np


ROBOT_FILE = "robot.xml"
ROLLOUT_STEPS = 1000
CONTROL_TARGET_RADIANS = 0.8
TARGET_POSITION_M = np.array([0.557365, 0.573885, 0.5], dtype=float)
MAX_TARGET_ERROR_M = 0.02
MIN_INITIAL_TARGET_ERROR_M = 0.50


def _row(
    grade_id: str,
    category: str,
    status: str,
    assertion: str,
    *,
    parameters: dict[str, object],
    observed: dict[str, object],
    raw_output: str,
) -> dict[str, object]:
    return {
        "grade_id": grade_id,
        "category": category,
        "status": status,
        "assertion": assertion,
        "parameters": parameters,
        "observed": observed,
        "raw_output": raw_output,
    }


def _behavior_parameters() -> dict[str, object]:
    return {
        "control_target_radians": CONTROL_TARGET_RADIANS,
        "rollout_steps": ROLLOUT_STEPS,
        "target_position_m": TARGET_POSITION_M.tolist(),
        "minimum_initial_target_error_m": MIN_INITIAL_TARGET_ERROR_M,
        "max_target_error_m": MAX_TARGET_ERROR_M,
    }


def grade(workspace: Path) -> list[dict]:
    """Load and execute the frozen arm artifact in a deterministic MuJoCo rollout."""

    robot_path = Path(workspace) / ROBOT_FILE
    load_assertion = "robot.xml loads as a MuJoCo model"
    behavior_assertion = (
        "a connected shoulder moves end_effector from at least 0.50 m away to within 0.02 m "
        "of the target after 1,000 steps"
    )
    if not robot_path.is_file():
        message = f"missing required artifact: {ROBOT_FILE}"
        return [
            _row(
                "mujoco-load",
                "simulator-load",
                "fail",
                load_assertion,
                parameters={"required_artifact": ROBOT_FILE},
                observed={"artifact_present": False},
                raw_output=message,
            ),
            _row(
                "arm-reaches-target",
                "behavior",
                "unrun",
                behavior_assertion,
                parameters=_behavior_parameters(),
                observed={},
                raw_output=message,
            ),
        ]

    try:
        model = mujoco.MjModel.from_xml_path(str(robot_path))
    except Exception:
        diagnostic = traceback.format_exc()
        return [
            _row(
                "mujoco-load",
                "simulator-load",
                "fail",
                load_assertion,
                parameters={"required_artifact": ROBOT_FILE},
                observed={"artifact_present": True, "model_loaded": False},
                raw_output=diagnostic,
            ),
            _row(
                "arm-reaches-target",
                "behavior",
                "unrun",
                behavior_assertion,
                parameters=_behavior_parameters(),
                observed={},
                raw_output=diagnostic,
            ),
        ]

    load_grade = _row(
        "mujoco-load",
        "simulator-load",
        "pass",
        load_assertion,
        parameters={"required_artifact": ROBOT_FILE},
        observed={"artifact_present": True, "model_loaded": True},
        raw_output=f"MuJoCo {mujoco.__version__} loaded nq={model.nq} nv={model.nv} nu={model.nu}",
    )

    try:
        site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "end_effector")
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "shoulder")
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, "shoulder_position"
        )
        missing = [
            name
            for name, object_id in (
                ("end_effector", site_id),
                ("shoulder", joint_id),
                ("shoulder_position", actuator_id),
            )
            if object_id < 0
        ]
        if missing:
            return [
                load_grade,
                _row(
                    "arm-reaches-target",
                    "behavior",
                    "fail",
                    behavior_assertion,
                    parameters=_behavior_parameters(),
                    observed={"missing_named_objects": missing},
                    raw_output=f"missing named MuJoCo objects: {', '.join(missing)}",
                ),
            ]

        site_body_id = int(model.site_bodyid[site_id])
        joint_body_id = int(model.jnt_bodyid[joint_id])
        actuator_joint_id = int(model.actuator_trnid[actuator_id, 0])
        connected = site_body_id == joint_body_id and actuator_joint_id == joint_id
        if not connected:
            observed = {
                "site_body_id": site_body_id,
                "joint_body_id": joint_body_id,
                "actuator_joint_id": actuator_joint_id,
            }
            return [
                load_grade,
                _row(
                    "arm-reaches-target",
                    "behavior",
                    "fail",
                    behavior_assertion,
                    parameters=_behavior_parameters(),
                    observed=observed,
                    raw_output=json.dumps(observed, sort_keys=True),
                ),
            ]

        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        initial_position = np.asarray(data.site_xpos[site_id], dtype=float).copy()
        initial_target_error = float(np.linalg.norm(initial_position - TARGET_POSITION_M))
        data.ctrl[actuator_id] = CONTROL_TARGET_RADIANS
        for _ in range(ROLLOUT_STEPS):
            mujoco.mj_step(model, data)

        final_position = np.asarray(data.site_xpos[site_id], dtype=float).copy()
        target_error = float(np.linalg.norm(final_position - TARGET_POSITION_M))
        final_joint_position = float(data.qpos[model.jnt_qposadr[joint_id]])
        observed = {
            "initial_end_effector_position_m": initial_position.tolist(),
            "initial_target_error_m": initial_target_error,
            "final_end_effector_position_m": final_position.tolist(),
            "final_shoulder_position_radians": final_joint_position,
            "target_error_m": target_error,
            "simulated_time_s": float(data.time),
        }
        return [
            load_grade,
            _row(
                "arm-reaches-target",
                "behavior",
                "pass"
                if initial_target_error >= MIN_INITIAL_TARGET_ERROR_M
                and target_error <= MAX_TARGET_ERROR_M
                else "fail",
                behavior_assertion,
                parameters=_behavior_parameters(),
                observed=observed,
                raw_output=json.dumps(observed, sort_keys=True),
            ),
        ]
    except Exception:
        diagnostic = traceback.format_exc()
        return [
            load_grade,
            _row(
                "arm-reaches-target",
                "behavior",
                "error",
                behavior_assertion,
                parameters=_behavior_parameters(),
                observed={},
                raw_output=diagnostic,
            ),
        ]
