"""
UI scene compiler.

Compiles RobotDesignIR to JSON scene graphs for frontend rendering.
Supports multiple render modes for different visualization needs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from packages.pipeline.ir.design_ir import RobotDesignIR, LinkIR, JointIR


RenderMode = Literal["concept", "visual", "collision", "joints", "components", "sensors", "actuators", "procurement"]


def compile_ui_scene(
    ir: RobotDesignIR,
    mode: RenderMode = "visual",
) -> dict[str, Any]:
    """
    Compile RobotDesignIR to UI scene JSON.

    Args:
        ir: The robot design intermediate representation
        mode: Render mode for the scene

    Returns:
        JSON-serializable scene dictionary
    """
    scene: dict[str, Any] = {
        "name": ir.name,
        "render_mode": mode,
        "links": [],
        "joints": [],
        "stats": {
            "link_count": len(ir.links),
            "joint_count": len(ir.joints),
        },
    }

    # Compile links
    for link in ir.links:
        link_data = _compile_link(link, mode)
        scene["links"].append(link_data)

    # Compile joints
    for joint in ir.joints:
        joint_data = _compile_joint(joint, mode)
        scene["joints"].append(joint_data)

    return scene


def _compile_link(link: LinkIR, mode: RenderMode) -> dict[str, Any]:
    """Compile a single link to scene data."""
    data: dict[str, Any] = {
        "name": link.name,
    }

    # Add geometry if visual exists
    if link.visual and link.visual.geometry:
        geom = link.visual.geometry
        data["geometry"] = {
            "type": geom.type,
            "size": list(geom.size),
        }
        if geom.mesh_path:
            data["geometry"]["mesh"] = geom.mesh_path

    # Mode-specific data
    if mode == "visual" and link.visual:
        data["color"] = list(link.visual.rgba)

    if mode == "components":
        data["is_custom"] = link.is_custom_part
        if link.vendor_sku:
            data["vendor_sku"] = link.vendor_sku

    return data


def _compile_joint(joint: JointIR, mode: RenderMode) -> dict[str, Any]:
    """Compile a single joint to scene data."""
    data: dict[str, Any] = {
        "name": joint.name,
        "type": joint.joint_type.value,
        "parent": joint.parent_link,
        "child": joint.child_link,
        "axis": [joint.axis.x, joint.axis.y, joint.axis.z],
        "origin": [joint.origin.x, joint.origin.y, joint.origin.z],
    }

    # Add limits if available
    if joint.limits:
        data["limits"] = {
            "lower": joint.limits.lower,
            "upper": joint.limits.upper,
            "effort": joint.limits.effort,
            "velocity": joint.limits.velocity,
        }

    # Add actuator if available
    if joint.actuator:
        data["actuator"] = {
            "type": joint.actuator.actuator_type,
            "max_torque": joint.actuator.max_torque,
            "max_velocity": joint.actuator.max_velocity,
        }
        if joint.actuator.vendor_sku:
            data["actuator"]["vendor_sku"] = joint.actuator.vendor_sku

    return data


def export_ui_scene(
    ir: RobotDesignIR,
    output_path: str,
    mode: RenderMode = "visual",
) -> str:
    """
    Export UI scene to JSON file.

    Args:
        ir: The robot design intermediate representation
        output_path: Path for the output JSON file
        mode: Render mode for the scene

    Returns:
        The output path
    """
    scene = compile_ui_scene(ir, mode)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(scene, f, indent=2)

    return str(path)
