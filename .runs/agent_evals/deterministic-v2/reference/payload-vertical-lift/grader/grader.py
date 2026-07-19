from __future__ import annotations

import json
import traceback
from pathlib import Path

import mujoco


ROBOT_FILE = "robot.xml"
ROLLOUT_STEPS = 1500
CONTROL_TARGET_M = 0.30
MINIMUM_LIFT_M = 0.20
MAX_FINAL_SPEED_M_S = 0.02
MAX_ACTUATOR_FORCE_N = 50.0
MINIMUM_PAYLOAD_MASS_KG = 2.0


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
        "control_target_m": CONTROL_TARGET_M,
        "rollout_steps": ROLLOUT_STEPS,
        "minimum_payload_mass_kg": MINIMUM_PAYLOAD_MASS_KG,
        "minimum_lift_m": MINIMUM_LIFT_M,
        "max_final_speed_m_s": MAX_FINAL_SPEED_M_S,
        "max_actuator_force_n": MAX_ACTUATOR_FORCE_N,
    }


def grade(workspace: Path) -> list[dict]:
    """Load and execute the frozen payload artifact under gravity."""

    robot_path = Path(workspace) / ROBOT_FILE
    load_assertion = "robot.xml loads as a MuJoCo model"
    behavior_assertion = (
        "a payload of at least 2 kg lifts 0.20 m and settles within velocity and force limits"
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
                "payload-lifts-and-settles",
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
                "payload-lifts-and-settles",
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
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "payload")
        site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "payload_site")
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "payload_slide")
        actuator_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, "lift_servo")
        missing = [
            name
            for name, object_id in (
                ("payload", body_id),
                ("payload_site", site_id),
                ("payload_slide", joint_id),
                ("lift_servo", actuator_id),
            )
            if object_id < 0
        ]
        if missing:
            return [
                load_grade,
                _row(
                    "payload-lifts-and-settles",
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
        connected = (
            site_body_id == body_id
            and joint_body_id == body_id
            and actuator_joint_id == joint_id
        )
        if not connected:
            observed = {
                "payload_body_id": body_id,
                "site_body_id": site_body_id,
                "joint_body_id": joint_body_id,
                "actuator_joint_id": actuator_joint_id,
            }
            return [
                load_grade,
                _row(
                    "payload-lifts-and-settles",
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
        initial_height = float(data.site_xpos[site_id, 2])
        data.ctrl[actuator_id] = CONTROL_TARGET_M
        peak_force = 0.0
        for _ in range(ROLLOUT_STEPS):
            mujoco.mj_step(model, data)
            peak_force = max(peak_force, abs(float(data.actuator_force[actuator_id])))

        final_height = float(data.site_xpos[site_id, 2])
        lift = final_height - initial_height
        final_speed = abs(float(data.qvel[model.jnt_dofadr[joint_id]]))
        payload_mass = float(model.body_mass[body_id])
        observed = {
            "payload_mass_kg": payload_mass,
            "initial_payload_height_m": initial_height,
            "final_payload_height_m": final_height,
            "vertical_lift_m": lift,
            "absolute_final_slide_velocity_m_s": final_speed,
            "peak_absolute_actuator_force_n": peak_force,
            "simulated_time_s": float(data.time),
        }
        passed = (
            payload_mass >= MINIMUM_PAYLOAD_MASS_KG
            and lift >= MINIMUM_LIFT_M
            and final_speed <= MAX_FINAL_SPEED_M_S
            and peak_force <= MAX_ACTUATOR_FORCE_N + 1e-9
        )
        return [
            load_grade,
            _row(
                "payload-lifts-and-settles",
                "behavior",
                "pass" if passed else "fail",
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
                "payload-lifts-and-settles",
                "behavior",
                "error",
                behavior_assertion,
                parameters=_behavior_parameters(),
                observed={},
                raw_output=diagnostic,
            ),
        ]
