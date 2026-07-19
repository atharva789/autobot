from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf
from packages.pipeline.ir.design_ir import (
    ActuatorSlot,
    Collision,
    Geometry,
    Inertial,
    JointIR,
    JointLimits,
    JointType,
    LinkIR,
    RobotDesignIR,
    SensorSlot,
    Vector3,
    Visual,
)
from packages.pipeline.simulation.validator import validate_design


def _grade(
    grade_id: str,
    category: str,
    status: str,
    assertion: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "grade_id": grade_id,
        "category": category,
        "status": status,
        "assertion": assertion,
        **extra,
    }


def _vector(raw: Any) -> Vector3:
    data = raw if isinstance(raw, dict) else {}
    return Vector3(
        x=float(data.get("x", 0.0)),
        y=float(data.get("y", 0.0)),
        z=float(data.get("z", 0.0)),
    )


def _geometry(raw: dict[str, Any]) -> Geometry:
    return Geometry(
        type=str(raw["type"]),
        size=tuple(float(value) for value in raw.get("size", [])),
        mesh_path=raw.get("mesh_path"),
        mesh_scale=_vector(raw.get("mesh_scale")),
    )


def _link(raw: dict[str, Any]) -> LinkIR:
    inertial_raw = raw.get("inertial")
    inertial = None
    if isinstance(inertial_raw, dict):
        inertial = Inertial(
            mass=float(inertial_raw["mass"]),
            origin=_vector(inertial_raw.get("origin")),
            ixx=float(inertial_raw.get("ixx", 0.0)),
            ixy=float(inertial_raw.get("ixy", 0.0)),
            ixz=float(inertial_raw.get("ixz", 0.0)),
            iyy=float(inertial_raw.get("iyy", 0.0)),
            iyz=float(inertial_raw.get("iyz", 0.0)),
            izz=float(inertial_raw.get("izz", 0.0)),
        )

    visual_raw = raw.get("visual")
    visual = None
    if isinstance(visual_raw, dict):
        visual = Visual(
            geometry=_geometry(visual_raw["geometry"]),
            origin=_vector(visual_raw.get("origin")),
            material_name=visual_raw.get("material_name"),
            rgba=tuple(float(value) for value in visual_raw.get("rgba", [0.8, 0.8, 0.8, 1.0])),
        )

    collision_raw = raw.get("collision")
    collision = None
    if isinstance(collision_raw, dict):
        collision = Collision(
            geometry=_geometry(collision_raw["geometry"]),
            origin=_vector(collision_raw.get("origin")),
        )

    return LinkIR(
        name=str(raw["name"]),
        inertial=inertial,
        visual=visual,
        collision=collision,
        is_custom_part=bool(raw.get("is_custom_part", False)),
        vendor_sku=raw.get("vendor_sku"),
    )


def _joint(raw: dict[str, Any]) -> JointIR:
    limits_raw = raw.get("limits")
    limits = None
    if isinstance(limits_raw, dict):
        limits = JointLimits(
            lower=float(limits_raw.get("lower", -1.047)),
            upper=float(limits_raw.get("upper", 1.047)),
            effort=float(limits_raw.get("effort", 1.0)),
            velocity=float(limits_raw.get("velocity", 10.0)),
        )

    actuator_raw = raw.get("actuator")
    actuator = None
    if isinstance(actuator_raw, dict):
        actuator = ActuatorSlot(
            actuator_type=str(actuator_raw["actuator_type"]),
            max_torque=float(actuator_raw.get("max_torque", 1.0)),
            max_velocity=float(actuator_raw.get("max_velocity", 10.0)),
            gear_ratio=float(actuator_raw.get("gear_ratio", 1.0)),
            vendor_sku=actuator_raw.get("vendor_sku"),
        )

    return JointIR(
        name=str(raw["name"]),
        joint_type=JointType(str(raw["joint_type"])),
        parent_link=str(raw["parent_link"]),
        child_link=str(raw["child_link"]),
        origin=_vector(raw.get("origin")),
        axis=_vector(raw.get("axis", {"z": 1.0})),
        limits=limits,
        actuator=actuator,
        damping=float(raw.get("damping", 0.1)),
        friction=float(raw.get("friction", 0.0)),
    )


def _load_ir(path: Path) -> RobotDesignIR:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("robot.json must contain one JSON object")
    return RobotDesignIR(
        name=str(raw["name"]),
        links=[_link(link) for link in raw.get("links", [])],
        joints=[_joint(joint) for joint in raw.get("joints", [])],
        sensors=[
            SensorSlot(
                sensor_type=str(sensor["sensor_type"]),
                mount_link=str(sensor["mount_link"]),
                origin=_vector(sensor.get("origin")),
                vendor_sku=sensor.get("vendor_sku"),
            )
            for sensor in raw.get("sensors", [])
        ],
        version=str(raw.get("version", "1.0.0")),
        source_candidate_id=raw.get("source_candidate_id"),
    )


def _unavailable_grades(error: str) -> list[dict[str, Any]]:
    return [
        _grade(
            "artifact.robot_json",
            "file-format",
            "fail",
            "robot.json exists and decodes into RobotDesignIR",
            raw_output=error,
        ),
        _grade(
            "ir.references_valid",
            "structural",
            "fail",
            "Every joint references existing parent and child links",
            raw_output="RobotDesignIR was unavailable",
        ),
        _grade(
            "ir.single_root",
            "structural",
            "fail",
            "The valid kinematic graph has exactly one root",
            raw_output="RobotDesignIR was unavailable",
        ),
        _grade(
            "compiler.mjcf",
            "compile",
            "fail",
            "RobotDesignIR compiles to MJCF",
            raw_output="RobotDesignIR was unavailable",
        ),
        _grade(
            "simulator.mujoco_load",
            "simulator-load",
            "fail",
            "Compiled MJCF loads in MuJoCo",
            raw_output="Compiled MJCF was unavailable",
        ),
    ]


def grade(workspace: Path) -> list[dict[str, Any]]:
    robot_path = workspace / "robot.json"
    try:
        ir = _load_ir(robot_path)
    except Exception as exc:
        return _unavailable_grades(f"{type(exc).__name__}: {exc}")

    grades = [
        _grade(
            "artifact.robot_json",
            "file-format",
            "pass",
            "robot.json exists and decodes into RobotDesignIR",
            observed={"path": "robot.json", "link_count": len(ir.links), "joint_count": len(ir.joints)},
        )
    ]

    validation = validate_design(ir)
    ir_errors = ir.validate()
    reference_errors = list(dict.fromkeys([*validation.errors, *ir_errors]))
    grades.append(
        _grade(
            "ir.references_valid",
            "structural",
            "pass" if not reference_errors else "fail",
            "Every joint references existing parent and child links",
            parameters={"required_invalid_reference_count": 0},
            observed={"invalid_reference_count": len(reference_errors), "errors": reference_errors},
            raw_output="\n".join(reference_errors),
        )
    )

    link_names = {link.name for link in ir.links}
    valid_children = {
        joint.child_link
        for joint in ir.joints
        if joint.parent_link in link_names and joint.child_link in link_names
    }
    roots = sorted(link_names - valid_children)
    grades.append(
        _grade(
            "ir.single_root",
            "structural",
            "pass" if len(roots) == 1 else "fail",
            "The valid kinematic graph has exactly one root",
            parameters={"required_root_count": 1},
            observed={"root_count": len(roots), "roots": roots},
            raw_output=json.dumps({"roots": roots}, sort_keys=True),
        )
    )

    try:
        mjcf_xml = compile_to_mjcf(ir)
    except Exception as exc:
        compile_error = f"{type(exc).__name__}: {exc}"
        grades.extend(
            [
                _grade(
                    "compiler.mjcf",
                    "compile",
                    "fail",
                    "RobotDesignIR compiles to MJCF",
                    raw_output=compile_error,
                ),
                _grade(
                    "simulator.mujoco_load",
                    "simulator-load",
                    "fail",
                    "Compiled MJCF loads in MuJoCo",
                    raw_output=f"MuJoCo load not executed because MJCF compilation failed: {compile_error}",
                ),
            ]
        )
        return grades

    grades.append(
        _grade(
            "compiler.mjcf",
            "compile",
            "pass",
            "RobotDesignIR compiles to MJCF",
            observed={"xml_bytes": len(mjcf_xml.encode("utf-8"))},
            raw_output=mjcf_xml,
        )
    )

    try:
        import mujoco

        model = mujoco.MjModel.from_xml_string(mjcf_xml)
    except Exception as exc:
        grades.append(
            _grade(
                "simulator.mujoco_load",
                "simulator-load",
                "fail",
                "Compiled MJCF loads in MuJoCo",
                raw_output=f"{type(exc).__name__}: {exc}",
            )
        )
    else:
        load_evidence = {
            "mujoco_version": mujoco.__version__,
            "nbody": int(model.nbody),
            "njnt": int(model.njnt),
            "nu": int(model.nu),
        }
        grades.append(
            _grade(
                "simulator.mujoco_load",
                "simulator-load",
                "pass",
                "Compiled MJCF loads in MuJoCo",
                parameters={"simulator": "mujoco", "simulator_version": mujoco.__version__},
                observed={"nbody": int(model.nbody), "njnt": int(model.njnt), "nu": int(model.nu)},
                raw_output=json.dumps(load_evidence, sort_keys=True),
            )
        )

    return grades
