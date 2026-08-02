from __future__ import annotations

import json
from collections import Counter
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


def _connectivity(ir: RobotDesignIR) -> dict[str, Any]:
    link_names = {link.name for link in ir.links}
    children = [joint.child_link for joint in ir.joints if joint.child_link in link_names]
    child_counts = Counter(children)
    roots = sorted(link_names - set(children))
    adjacency: dict[str, list[str]] = {name: [] for name in link_names}
    for joint in ir.joints:
        if joint.parent_link in link_names and joint.child_link in link_names:
            adjacency[joint.parent_link].append(joint.child_link)

    visited: set[str] = set()
    active: set[str] = set()
    cycle = False

    def visit(name: str) -> None:
        nonlocal cycle
        if name in active:
            cycle = True
            return
        if name in visited:
            return
        active.add(name)
        for child in adjacency.get(name, []):
            visit(child)
        active.remove(name)
        visited.add(name)

    if len(roots) == 1:
        visit(roots[0])

    unreachable = sorted(link_names - visited)
    multiply_parented = sorted(name for name, count in child_counts.items() if count != 1)
    return {
        "roots": roots,
        "unreachable": unreachable,
        "multiply_parented": multiply_parented,
        "cycle": cycle,
    }


def _unavailable_grades(error: str) -> list[dict[str, Any]]:
    specs = [
        ("artifact.robot_json", "file-format", "robot.json exists and decodes into RobotDesignIR"),
        ("ir.references_valid", "structural", "Every joint references existing links"),
        ("ir.connected_tree", "structural", "All links form one rooted kinematic tree"),
        ("compiler.mjcf", "compile", "RobotDesignIR compiles to MJCF"),
        ("simulator.mujoco_load", "simulator-load", "Compiled MJCF loads in MuJoCo"),
        ("compiled.body_coverage", "simulator-load", "Every IR link exists as a compiled MuJoCo body"),
    ]
    return [
        _grade(grade_id, category, "fail", assertion, raw_output=error)
        for grade_id, category, assertion in specs
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
    reference_errors = list(dict.fromkeys([*validation.errors, *ir.validate()]))
    grades.append(
        _grade(
            "ir.references_valid",
            "structural",
            "pass" if not reference_errors else "fail",
            "Every joint references existing links",
            parameters={"required_invalid_reference_count": 0},
            observed={"invalid_reference_count": len(reference_errors), "errors": reference_errors},
            raw_output="\n".join(reference_errors),
        )
    )

    connectivity = _connectivity(ir)
    connected = (
        len(connectivity["roots"]) == 1
        and not connectivity["unreachable"]
        and not connectivity["multiply_parented"]
        and not connectivity["cycle"]
    )
    grades.append(
        _grade(
            "ir.connected_tree",
            "structural",
            "pass" if connected else "fail",
            "All links form one rooted kinematic tree",
            parameters={"required_root_count": 1, "required_unreachable_count": 0},
            observed=connectivity,
            raw_output=json.dumps(connectivity, sort_keys=True),
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
                _grade(
                    "compiled.body_coverage",
                    "simulator-load",
                    "fail",
                    "Every IR link exists as a compiled MuJoCo body",
                    raw_output=f"Body coverage not executed because MJCF compilation failed: {compile_error}",
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
        error = f"{type(exc).__name__}: {exc}"
        grades.extend(
            [
                _grade(
                    "simulator.mujoco_load",
                    "simulator-load",
                    "fail",
                    "Compiled MJCF loads in MuJoCo",
                    raw_output=error,
                ),
                _grade(
                    "compiled.body_coverage",
                    "simulator-load",
                    "fail",
                    "Every IR link exists as a compiled MuJoCo body",
                    raw_output=error,
                ),
            ]
        )
        return grades

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

    compiled_bodies = {
        name
        for body_id in range(1, model.nbody)
        if (name := mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)) is not None
    }
    ir_links = {link.name for link in ir.links}
    missing_bodies = sorted(ir_links - compiled_bodies)
    unexpected_bodies = sorted(compiled_bodies - ir_links)
    grades.append(
        _grade(
            "compiled.body_coverage",
            "simulator-load",
            "pass" if not missing_bodies else "fail",
            "Every IR link exists as a compiled MuJoCo body",
            parameters={"required_missing_body_count": 0},
            observed={
                "ir_links": sorted(ir_links),
                "compiled_bodies": sorted(compiled_bodies),
                "missing_bodies": missing_bodies,
                "unexpected_bodies": unexpected_bodies,
            },
            raw_output=json.dumps(
                {
                    "compiled_bodies": sorted(compiled_bodies),
                    "ir_links": sorted(ir_links),
                    "missing_bodies": missing_bodies,
                    "unexpected_bodies": unexpected_bodies,
                },
                sort_keys=True,
            ),
        )
    )

    return grades
