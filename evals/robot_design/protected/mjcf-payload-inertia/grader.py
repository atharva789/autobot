"""Protected direct-MuJoCo grader for the payload inertia task."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import mujoco


EXPECTED_MASS_KG = 2.0
EXPECTED_FULL_DIMS_M = (0.30, 0.20, 0.10)
EXPECTED_INERTIA_KG_M2 = (
    0.008333333333,
    0.016666666667,
    0.021666666667,
)
ABS_TOLERANCE = 1e-9


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
        ("payload-mass", "static", "Payload body mass is exactly 2.0 kg."),
        ("payload-inertia", "static", "Payload diagonal inertia matches the solid-box contract."),
        ("payload-dimensions", "static", "Payload collision box has full dimensions 0.30 x 0.20 x 0.10 m."),
        ("payload-collision", "static", "Payload collision geom is a contact-enabled box attached to payload."),
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
    """Grade ``workspace/robot.xml`` using MuJoCo's compiled model arrays."""

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

    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "payload")
    geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "payload_collision")
    load_observed = {
        "loaded": True,
        "nbody": int(model.nbody),
        "ngeom": int(model.ngeom),
        "payload_body_id": int(body_id),
        "payload_geom_id": int(geom_id),
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

    if body_id < 0 or geom_id < 0:
        missing = []
        if body_id < 0:
            missing.append("payload body")
        if geom_id < 0:
            missing.append("payload_collision geom")
        message = "Missing required named model object(s): " + ", ".join(missing)
        for grade_id, assertion in (
            ("payload-mass", "Payload body mass is exactly 2.0 kg."),
            ("payload-inertia", "Payload diagonal inertia matches the solid-box contract."),
            ("payload-dimensions", "Payload collision box has full dimensions 0.30 x 0.20 x 0.10 m."),
            ("payload-collision", "Payload collision geom is a contact-enabled box attached to payload."),
        ):
            grades.append(
                _result(
                    grade_id,
                    "static",
                    "fail",
                    assertion,
                    parameters={},
                    observed={"missing_objects": missing},
                    raw_output=message,
                )
            )
        return grades

    observed_mass = float(model.body_mass[body_id])
    mass_evidence = {"body": "payload", "mass_kg": observed_mass}
    grades.append(
        _result(
            "payload-mass",
            "static",
            "pass" if _close(observed_mass, EXPECTED_MASS_KG) else "fail",
            "Payload body mass is exactly 2.0 kg.",
            parameters={"expected_mass_kg": EXPECTED_MASS_KG, "absolute_tolerance": ABS_TOLERANCE},
            observed=mass_evidence,
            raw_output=json.dumps(mass_evidence, sort_keys=True),
        )
    )

    observed_inertia = tuple(float(value) for value in model.body_inertia[body_id])
    inertia_evidence = {
        "body": "payload",
        "diagonal_inertia_kg_m2": list(observed_inertia),
    }
    grades.append(
        _result(
            "payload-inertia",
            "static",
            "pass" if _vector_close(observed_inertia, EXPECTED_INERTIA_KG_M2) else "fail",
            "Payload diagonal inertia matches the solid-box contract.",
            parameters={
                "expected_diagonal_inertia_kg_m2": list(EXPECTED_INERTIA_KG_M2),
                "absolute_tolerance": ABS_TOLERANCE,
            },
            observed=inertia_evidence,
            raw_output=json.dumps(inertia_evidence, sort_keys=True),
        )
    )

    observed_full_dims = tuple(float(value) * 2.0 for value in model.geom_size[geom_id, :3])
    dimension_evidence = {
        "geom": "payload_collision",
        "full_dimensions_m": list(observed_full_dims),
    }
    grades.append(
        _result(
            "payload-dimensions",
            "static",
            "pass" if _vector_close(observed_full_dims, EXPECTED_FULL_DIMS_M) else "fail",
            "Payload collision box has full dimensions 0.30 x 0.20 x 0.10 m.",
            parameters={
                "expected_full_dimensions_m": list(EXPECTED_FULL_DIMS_M),
                "absolute_tolerance": ABS_TOLERANCE,
            },
            observed=dimension_evidence,
            raw_output=json.dumps(dimension_evidence, sort_keys=True),
        )
    )

    observed_type = int(model.geom_type[geom_id])
    expected_type = int(mujoco.mjtGeom.mjGEOM_BOX)
    observed_body_id = int(model.geom_bodyid[geom_id])
    contype = int(model.geom_contype[geom_id])
    conaffinity = int(model.geom_conaffinity[geom_id])
    collision_ok = (
        observed_type == expected_type
        and observed_body_id == body_id
        and contype > 0
        and conaffinity > 0
    )
    collision_evidence = {
        "geom": "payload_collision",
        "geom_type": observed_type,
        "expected_box_type": expected_type,
        "geom_body_id": observed_body_id,
        "payload_body_id": int(body_id),
        "contype": contype,
        "conaffinity": conaffinity,
    }
    grades.append(
        _result(
            "payload-collision",
            "static",
            "pass" if collision_ok else "fail",
            "Payload collision geom is a contact-enabled box attached to payload.",
            parameters={"required_geom_type": "box", "contact_masks_must_be_positive": True},
            observed=collision_evidence,
            raw_output=json.dumps(collision_evidence, sort_keys=True),
        )
    )
    return grades
