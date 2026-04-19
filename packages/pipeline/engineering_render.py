from __future__ import annotations

import base64
import json
import math
import struct
from array import array
from dataclasses import dataclass
from typing import Any

from packages.pipeline.schemas import RobotDesignCandidate, TaskSpec


@dataclass(frozen=True)
class GeometryIntent:
    profile: str
    needs_grippers: bool
    needs_payload_pack: bool
    needs_traction_spikes: bool
    needs_belly_skid: bool
    needs_stabilizer_tail: bool
    lean_factor: float
    torso_drop_m: float


_COLOR_MAP: dict[str, list[float]] = {
    "composite_shell": [0.26, 0.71, 0.64, 1.0],
    "sensor_glass": [0.85, 0.64, 0.31, 1.0],
    "anodized_metal": [0.34, 0.39, 0.96, 1.0],
    "joint_core": [0.97, 0.49, 0.18, 1.0],
    "traction_rubber": [0.16, 0.66, 0.39, 1.0],
    "payload_pack": [0.39, 0.52, 0.3, 1.0],
    "ceramic_plate": [0.77, 0.8, 0.84, 1.0],
    "optic_emitter": [0.44, 0.95, 0.84, 1.0],
    "harness_webbing": [0.18, 0.22, 0.18, 1.0],
    "brushed_alloy": [0.69, 0.72, 0.78, 1.0],
}

_MATERIAL_LABELS: dict[str, str] = {
    "composite_shell": "composite shell",
    "sensor_glass": "sensor glass",
    "anodized_metal": "anodized metal",
    "joint_core": "joint core",
    "traction_rubber": "traction rubber",
    "payload_pack": "payload textile",
    "ceramic_plate": "ceramic armor plate",
    "optic_emitter": "optic emitter",
    "harness_webbing": "woven harness webbing",
    "brushed_alloy": "brushed alloy",
}


_MESH_LIBRARY: dict[str, tuple[str, str]] = {
    "torso_shell": ("cylinder", "composite_shell"),
    "head_dome": ("sphere", "sensor_glass"),
    "sensor_pod": ("sphere", "sensor_glass"),
    "limb_tube": ("cylinder", "anodized_metal"),
    "joint_orb": ("sphere", "joint_core"),
    "shoulder_shell": ("box", "composite_shell"),
    "foot_pad": ("box", "traction_rubber"),
    "payload_pack": ("box", "payload_pack"),
    "claw_finger": ("box", "anodized_metal"),
    "traction_spike": ("cone", "traction_rubber"),
    "belly_skid": ("box", "traction_rubber"),
    "stabilizer_tail": ("cylinder", "anodized_metal"),
    "chest_plate": ("box", "ceramic_plate"),
    "back_plate": ("box", "ceramic_plate"),
    "side_fairing": ("box", "brushed_alloy"),
    "shoulder_guard": ("box", "brushed_alloy"),
    "limb_guard": ("box", "ceramic_plate"),
    "hip_skirt": ("box", "composite_shell"),
    "payload_strap": ("box", "harness_webbing"),
    "sensor_emitter": ("sphere", "optic_emitter"),
    "cable_guide": ("cylinder", "harness_webbing"),
    "joint_cowl": ("cylinder", "brushed_alloy"),
}


def build_engineering_render(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec | None = None,
) -> dict[str, Any]:
    intent = _infer_geometry_intent(candidate, task_spec)
    nodes, joints = _build_engineering_scene(candidate, intent)
    glb_bytes = _build_glb(nodes)
    accessory_count = sum(
        1
        for node in nodes
        if node["component_kind"]
        in {"payload_module", "climbing_gripper", "traction_spike", "stabilizer", "crawler_module"}
    )
    material_count = len({_MESH_LIBRARY[node["mesh_key"]][1] for node in nodes})
    primitive_keys = sorted({_MESH_LIBRARY[node["mesh_key"]][0] for node in nodes})
    panel_node_count = sum(
        1 for node in nodes if node["component_kind"] in {"shell_panel", "armor_panel", "payload_module", "cable_routing"}
    )
    pbr_extension_count = len(_material_extensions_for_nodes(nodes))
    visual_complexity_score = round(
        min(
            1.0,
            0.28
            + len(nodes) / 90.0
            + material_count / 20.0
            + panel_node_count / 40.0
            + accessory_count / 28.0,
        ),
        3,
    )
    return {
        "engineering_ready": True,
        "render_glb": "data:model/gltf-binary;base64," + base64.b64encode(glb_bytes).decode("ascii"),
        "ui_scene": {
            "candidate_id": candidate.candidate_id,
            "render_mode": "engineering",
            "units": "meters",
            "task_geometry_profile": intent.profile,
            "nodes": nodes,
            "joints": joints,
            "stats": {
                "engineering_ready": True,
                "mesh_node_count": len(nodes),
                "joint_anchor_count": len(joints),
                "material_count": material_count,
                "primitive_keys": primitive_keys,
                "accessory_node_count": accessory_count,
                "task_geometry_profile": intent.profile,
                "structure_count": len({node["structure_id"] for node in nodes}),
                "panel_node_count": panel_node_count,
                "pbr_extension_count": pbr_extension_count,
                "visual_complexity_score": visual_complexity_score,
            },
        },
    }


def _infer_geometry_intent(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec | None,
) -> GeometryIntent:
    text_parts = [candidate.rationale.lower(), candidate.embodiment_class.lower()]
    if task_spec is not None:
        text_parts.extend(
            [
                task_spec.task_goal.lower(),
                task_spec.success_criteria.lower(),
                " ".join(task_spec.search_queries).lower(),
            ]
        )
    task_text = " ".join(text_parts)

    climbing = any(term in task_text for term in ("climb", "wall", "vertical", "rope"))
    slippery = any(term in task_text for term in ("slippery", "slope", "descent", "downhill", "traction"))
    crawling = any(term in task_text for term in ("crawl", "crawling", "tunnel", "low-clearance"))
    payload = any(term in task_text for term in ("payload", "carry", "pack", "back", "rescue", "rope")) or candidate.payload_capacity_kg >= 2.0

    if climbing and payload:
        profile = "climbing_payload"
    elif climbing:
        profile = "climbing"
    elif slippery and payload:
        profile = "slippery_payload"
    elif slippery:
        profile = "slippery_terrain"
    elif crawling:
        profile = "crawler"
    else:
        profile = "general"

    return GeometryIntent(
        profile=profile,
        needs_grippers=climbing or (candidate.num_arms > 0 and (task_spec.manipulation_required if task_spec else False)),
        needs_payload_pack=payload,
        needs_traction_spikes=climbing or slippery,
        needs_belly_skid=crawling,
        needs_stabilizer_tail=slippery,
        lean_factor=1.18 if climbing else (0.82 if crawling else 1.0),
        torso_drop_m=0.1 if crawling else (0.05 if slippery else 0.0),
    )


def _build_engineering_scene(
    candidate: RobotDesignCandidate,
    intent: GeometryIntent,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    joints: list[dict[str, Any]] = []

    torso_height = max(0.34, candidate.torso_length_m * (0.92 if intent.profile.startswith("climbing") else 1.0))
    torso_radius_x = max(0.11, min(0.22, torso_height * 0.26 / intent.lean_factor))
    torso_radius_z = max(0.1, torso_radius_x * (0.86 if intent.profile.startswith("climbing") else 1.0))
    torso_center = [0.0, 0.82 - intent.torso_drop_m, 0.0]

    nodes.append(
        _node(
            "torso_main",
            "structural",
            "torso_shell",
            torso_center,
            [torso_radius_x, torso_height, torso_radius_z],
        )
    )
    nodes.append(
        _node(
            "torso_collar",
            "structural",
            "shoulder_shell",
            [0.0, torso_center[1] + torso_height * 0.44, 0.0],
            [torso_radius_x * 2.1, torso_height * 0.12, torso_radius_z * 1.55],
        )
    )
    nodes.append(
        _node(
            "torso_head",
            "sensor_mount",
            "head_dome",
            [0.0, torso_center[1] + torso_height * 0.72, torso_radius_z * 0.05],
            [torso_radius_x * 0.86, torso_radius_x * 0.86, torso_radius_x * 0.86],
        )
    )
    nodes.extend(
        [
            _node(
                "torso_chest_plate",
                "shell_panel",
                "chest_plate",
                [0.0, torso_center[1] + torso_height * 0.08, torso_radius_z * 0.88],
                [torso_radius_x * 1.75, torso_height * 0.42, 0.028],
            ),
            _node(
                "torso_back_plate",
                "shell_panel",
                "back_plate",
                [0.0, torso_center[1] + torso_height * 0.05, -torso_radius_z * 0.92],
                [torso_radius_x * 1.82, torso_height * 0.46, 0.03],
            ),
            _node(
                "torso_side_plate_left",
                "shell_panel",
                "side_fairing",
                [-torso_radius_x * 1.02, torso_center[1] + torso_height * 0.05, 0.02],
                [0.028, torso_height * 0.44, torso_radius_z * 1.38],
            ),
            _node(
                "torso_side_plate_right",
                "shell_panel",
                "side_fairing",
                [torso_radius_x * 1.02, torso_center[1] + torso_height * 0.05, 0.02],
                [0.028, torso_height * 0.44, torso_radius_z * 1.38],
            ),
        ]
    )
    if "camera" in candidate.sensor_package:
        nodes.append(
            _node(
                "sensor_pod_front",
                "sensor_mount",
                "sensor_pod",
                [0.0, torso_center[1] + torso_height * 0.62, torso_radius_z * 0.62],
                [0.06, 0.06, 0.06],
            )
        )
        nodes.append(
            _node(
                "sensor_emitter_front",
                "sensor_mount",
                "sensor_emitter",
                [0.0, torso_center[1] + torso_height * 0.62, torso_radius_z * 0.72],
                [0.03, 0.03, 0.03],
            )
        )

    shoulder_span = max(0.32, torso_radius_x * 3.6)
    shoulder_y = torso_center[1] + torso_height * 0.32
    arm_length = max(0.24, candidate.arm_length_m * 0.56) if candidate.num_arms else 0.0
    for index in range(candidate.num_arms):
        sign = -1.0 if index == 0 else 1.0
        shoulder = [sign * shoulder_span * 0.5, shoulder_y, 0.03]
        elbow = [sign * shoulder_span * 0.92, shoulder_y - arm_length * 0.48, 0.06]
        hand = [sign * shoulder_span * 1.12, shoulder_y - arm_length * 0.98, 0.09]
        nodes.extend(
            [
                _segment_node(f"arm_{index+1}_upper", shoulder, elbow, 0.055, "structural", "limb_tube"),
                _node(
                    f"arm_{index+1}_shoulder_guard",
                    "armor_panel",
                    "shoulder_guard",
                    [shoulder[0] + sign * 0.025, shoulder[1] - 0.02, shoulder[2] + 0.01],
                    [0.08, 0.12, 0.08],
                    rotation=_quat_from_axis_angle([0.0, 0.0, 1.0], sign * 0.22),
                ),
                _node(f"arm_{index+1}_shoulder_cowl", "armor_panel", "joint_cowl", shoulder, [0.07, 0.09, 0.07]),
                _node(f"arm_{index+1}_elbow", "joint_anchor", "joint_orb", elbow, [0.065, 0.065, 0.065]),
                _segment_node(f"arm_{index+1}_lower", elbow, hand, 0.047, "structural", "limb_tube"),
                _segment_node(
                    f"arm_{index+1}_cable_guide",
                    [shoulder[0], shoulder[1] + 0.02, shoulder[2] - 0.02],
                    [elbow[0], elbow[1] + 0.04, elbow[2] - 0.01],
                    0.014,
                    "cable_routing",
                    "cable_guide",
                ),
                _node(
                    f"arm_{index+1}_forearm_guard",
                    "armor_panel",
                    "limb_guard",
                    [(elbow[0] + hand[0]) * 0.5, (elbow[1] + hand[1]) * 0.5, (elbow[2] + hand[2]) * 0.5 + 0.018],
                    [0.058, arm_length * 0.32, 0.04],
                    rotation=_quat_from_y_axis([hand[0] - elbow[0], hand[1] - elbow[1], hand[2] - elbow[2]]),
                ),
                _node(f"arm_{index+1}_wrist", "joint_anchor", "joint_orb", hand, [0.058, 0.058, 0.058]),
            ]
        )
        joints.extend(
            [
                _joint_anchor(f"shoulder_{index+1}", shoulder, "revolute"),
                _joint_anchor(f"elbow_{index+1}", elbow, "revolute"),
                _joint_anchor(f"wrist_{index+1}", hand, "ball"),
            ]
        )
        if intent.needs_grippers:
            nodes.extend(_gripper_nodes(index + 1, hand, sign))

    hip_y = torso_center[1] - torso_height * 0.52
    leg_width = max(0.18, 0.12 * max(1, candidate.num_legs - 1))
    leg_length = max(0.22, candidate.leg_length_m * 0.52) if candidate.num_legs else 0.0
    if candidate.num_legs >= 2:
        nodes.extend(
            [
                _node(
                    "hip_skirt_left",
                    "shell_panel",
                    "hip_skirt",
                    [-torso_radius_x * 0.78, hip_y + 0.06, -0.01],
                    [0.12, 0.08, 0.14],
                ),
                _node(
                    "hip_skirt_right",
                    "shell_panel",
                    "hip_skirt",
                    [torso_radius_x * 0.78, hip_y + 0.06, -0.01],
                    [0.12, 0.08, 0.14],
                ),
            ]
        )
    for index in range(candidate.num_legs):
        x_offset = 0.0 if candidate.num_legs == 1 else -leg_width * 0.5 + (leg_width / max(1, candidate.num_legs - 1)) * index
        hip = [x_offset, hip_y, 0.0]
        knee = [x_offset, hip_y - leg_length * 0.52, 0.04]
        ankle = [x_offset, hip_y - leg_length * 1.02, 0.08]
        foot = [x_offset, ankle[1] - 0.03, 0.14]
        nodes.extend(
            [
                _segment_node(f"leg_{index+1}_upper", hip, knee, 0.062, "structural", "limb_tube"),
                _node(f"leg_{index+1}_hip_cowl", "armor_panel", "joint_cowl", hip, [0.075, 0.095, 0.075]),
                _node(f"leg_{index+1}_knee", "joint_anchor", "joint_orb", knee, [0.067, 0.067, 0.067]),
                _segment_node(f"leg_{index+1}_lower", knee, ankle, 0.053, "structural", "limb_tube"),
                _node(
                    f"leg_{index+1}_shin_guard",
                    "armor_panel",
                    "limb_guard",
                    [(knee[0] + ankle[0]) * 0.5, (knee[1] + ankle[1]) * 0.5, (knee[2] + ankle[2]) * 0.5 + 0.028],
                    [0.062, leg_length * 0.28, 0.05],
                    rotation=_quat_from_y_axis([ankle[0] - knee[0], ankle[1] - knee[1], ankle[2] - knee[2]]),
                ),
                _node(f"leg_{index+1}_ankle", "joint_anchor", "joint_orb", ankle, [0.058, 0.058, 0.058]),
                _node(f"leg_{index+1}_foot", "traction_module", "foot_pad", foot, [0.12, 0.032, 0.2]),
            ]
        )
        joints.extend(
            [
                _joint_anchor(f"hip_{index+1}", hip, "revolute"),
                _joint_anchor(f"knee_{index+1}", knee, "revolute"),
                _joint_anchor(f"ankle_{index+1}", ankle, "revolute"),
            ]
        )
        if intent.needs_traction_spikes:
            nodes.extend(_spike_nodes(index + 1, foot))

    if candidate.spine_dof > 0:
        for spine_index in range(candidate.spine_dof):
            joints.append(
                _joint_anchor(
                    f"spine_{spine_index+1}",
                    [0.0, torso_center[1] - torso_height * 0.18 + spine_index * 0.08, 0.0],
                    "revolute",
                )
            )
            nodes.append(
                _node(
                    f"spine_fairing_{spine_index+1}",
                    "shell_panel",
                    "side_fairing",
                    [0.0, torso_center[1] - torso_height * 0.18 + spine_index * 0.08, -torso_radius_z * 0.42],
                    [torso_radius_x * 1.15, 0.055, 0.028],
                )
            )

    if intent.needs_payload_pack:
        pack_scale = [torso_radius_x * 1.55, torso_height * 0.45, torso_radius_z * 1.08]
        pack_pos = [0.0, torso_center[1] + torso_height * 0.06, -torso_radius_z * 1.45]
        nodes.append(_node("payload_pack", "payload_module", "payload_pack", pack_pos, pack_scale))
        nodes.extend(
            [
                _node(
                    "payload_strap_left",
                    "payload_module",
                    "payload_strap",
                    [-torso_radius_x * 0.92, torso_center[1] + torso_height * 0.18, -torso_radius_z * 0.76],
                    [0.026, torso_height * 0.62, 0.02],
                    rotation=_quat_from_axis_angle([0.0, 0.0, 1.0], 0.22),
                ),
                _node(
                    "payload_strap_right",
                    "payload_module",
                    "payload_strap",
                    [torso_radius_x * 0.92, torso_center[1] + torso_height * 0.18, -torso_radius_z * 0.76],
                    [0.026, torso_height * 0.62, 0.02],
                    rotation=_quat_from_axis_angle([0.0, 0.0, 1.0], -0.22),
                ),
            ]
        )
        nodes.append(
            _segment_node(
                "payload_mount_left",
                [-torso_radius_x * 0.95, torso_center[1] + torso_height * 0.18, -torso_radius_z * 0.4],
                [-torso_radius_x * 1.05, torso_center[1] + torso_height * 0.1, -torso_radius_z * 1.15],
                0.028,
                "payload_module",
                "limb_tube",
            )
        )
        nodes.append(
            _segment_node(
                "payload_mount_right",
                [torso_radius_x * 0.95, torso_center[1] + torso_height * 0.18, -torso_radius_z * 0.4],
                [torso_radius_x * 1.05, torso_center[1] + torso_height * 0.1, -torso_radius_z * 1.15],
                0.028,
                "payload_module",
                "limb_tube",
            )
        )

    if intent.needs_belly_skid:
        nodes.append(
            _node(
                "belly_skid",
                "crawler_module",
                "belly_skid",
                [0.0, torso_center[1] - torso_height * 0.56, 0.03],
                [torso_radius_x * 1.75, 0.03, torso_radius_z * 1.35],
            )
        )

    if intent.needs_stabilizer_tail:
        tail_start = [0.0, torso_center[1] - torso_height * 0.18, -torso_radius_z * 1.25]
        tail_end = [0.0, torso_center[1] - torso_height * 0.34, -torso_radius_z * 2.2]
        nodes.append(_segment_node("stabilizer_tail", tail_start, tail_end, 0.038, "stabilizer", "stabilizer_tail"))

    return nodes, joints


def _gripper_nodes(arm_index: int, hand: list[float], sign: float) -> list[dict[str, Any]]:
    palm = [hand[0] + sign * 0.035, hand[1] - 0.015, hand[2] + 0.02]
    palm_rotation = _quat_from_axis_angle([0.0, 0.0, 1.0], sign * 0.32)
    nodes = [
        _node(
            f"arm_{arm_index}_gripper_palm",
            "climbing_gripper",
            "claw_finger",
            palm,
            [0.038, 0.09, 0.05],
            rotation=palm_rotation,
        )
    ]
    finger_offsets = [-0.035, 0.0, 0.035]
    finger_angles = [0.38, 0.0, -0.38]
    for finger_index, (offset, angle) in enumerate(zip(finger_offsets, finger_angles, strict=True), start=1):
        start = [palm[0] + sign * 0.028, palm[1] + offset, palm[2] + 0.018]
        rotation = _quat_from_axis_angle([0.0, 0.0, 1.0], sign * (0.28 + angle))
        nodes.append(
            _node(
                f"arm_{arm_index}_gripper_finger_{finger_index}",
                "climbing_gripper",
                "claw_finger",
                start,
                [0.018, 0.085, 0.022],
                rotation=rotation,
            )
        )
    return nodes


def _spike_nodes(leg_index: int, foot: list[float]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    x, y, z = foot
    for spike_index, offset in enumerate((-0.045, 0.0, 0.045), start=1):
        nodes.append(
            _node(
                f"leg_{leg_index}_spike_{spike_index}",
                "traction_spike",
                "traction_spike",
                [x + offset, y - 0.01, z + 0.07],
                [0.02, 0.08, 0.02],
                rotation=_quat_from_axis_angle([1.0, 0.0, 0.0], math.pi * 0.5),
            )
        )
    return nodes


def _node(
    name: str,
    component_kind: str,
    mesh_key: str,
    position: list[float],
    scale: list[float],
    rotation: list[float] | None = None,
) -> dict[str, Any]:
    material_key = _MESH_LIBRARY[mesh_key][1]
    structure_id = _structure_id_for_name(name)
    display_name = _display_name_for_name(name)
    return {
        "name": name,
        "component_id": name,
        "structure_id": structure_id,
        "display_name": display_name,
        "component_kind": component_kind,
        "role_label": component_kind.replace("_", " "),
        "mesh_key": mesh_key,
        "primitive_key": _MESH_LIBRARY[mesh_key][0],
        "material_key": material_key,
        "material_label": _MATERIAL_LABELS[material_key],
        "position": [round(v, 4) for v in position],
        "scale": [round(max(v, 0.001), 4) for v in scale],
        "bounds_m": [round(max(v, 0.001), 4) for v in scale],
        "rotation": [round(v, 6) for v in (rotation or [0.0, 0.0, 0.0, 1.0])],
        "color": _COLOR_MAP[material_key],
        "focus_summary": _focus_summary(component_kind, display_name, material_key),
        "highlight_color": [0.49, 0.87, 0.45, 1.0],
    }


def _segment_node(
    name: str,
    start: list[float],
    end: list[float],
    thickness: float,
    component_kind: str,
    mesh_key: str,
) -> dict[str, Any]:
    center = [
        (start[0] + end[0]) * 0.5,
        (start[1] + end[1]) * 0.5,
        (start[2] + end[2]) * 0.5,
    ]
    direction = [end[0] - start[0], end[1] - start[1], end[2] - start[2]]
    length = max(math.dist(start, end), thickness * 2.0)
    return _node(
        name,
        component_kind,
        mesh_key,
        center,
        [thickness, length, thickness],
        rotation=_quat_from_y_axis(direction),
    )


def _joint_anchor(name: str, position: list[float], joint_kind: str) -> dict[str, Any]:
    return {
        "name": name,
        "joint_kind": joint_kind,
        "position": [round(v, 4) for v in position],
    }


def _structure_id_for_name(name: str) -> str:
    parts = name.split("_")
    if len(parts) >= 2 and parts[1].isdigit():
        return "_".join(parts[:2])
    return parts[0]


def _display_name_for_name(name: str) -> str:
    return name.replace("_", " ")


def _focus_summary(component_kind: str, display_name: str, material_key: str) -> str:
    role = component_kind.replace("_", " ")
    material = _MATERIAL_LABELS[material_key]
    if component_kind == "climbing_gripper":
        return f"{display_name} is a grasping structure used to secure the robot to vertical surfaces with {material} contact faces."
    if component_kind == "traction_spike":
        return f"{display_name} is a traction element that increases purchase on steep or slippery terrain."
    if component_kind == "payload_module":
        return f"{display_name} is part of the carried payload assembly and affects center-of-mass and clearance."
    if component_kind == "joint_anchor":
        return f"{display_name} is a joint anchor that concentrates articulation loads through a {material} housing."
    return f"{display_name} is a {role} component built around {material} geometry."


def _material_extensions_for_nodes(nodes: list[dict[str, Any]]) -> set[str]:
    materials = {_MESH_LIBRARY[node["mesh_key"]][1] for node in nodes}
    used_extensions: set[str] = set()
    for material in _materials():
        if material["name"] in materials:
            used_extensions.update((material.get("extensions") or {}).keys())
    return used_extensions


def _normalize(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-8:
        return [0.0, 1.0, 0.0]
    return [component / length for component in vector]


def _quat_from_axis_angle(axis: list[float], angle: float) -> list[float]:
    axis_n = _normalize(axis)
    sin_half = math.sin(angle * 0.5)
    return [axis_n[0] * sin_half, axis_n[1] * sin_half, axis_n[2] * sin_half, math.cos(angle * 0.5)]


def _quat_from_y_axis(direction: list[float]) -> list[float]:
    up = [0.0, 1.0, 0.0]
    target = _normalize(direction)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(up, target, strict=True))))
    if dot > 0.999999:
        return [0.0, 0.0, 0.0, 1.0]
    if dot < -0.999999:
        return [1.0, 0.0, 0.0, 0.0]
    cross = [
        up[1] * target[2] - up[2] * target[1],
        up[2] * target[0] - up[0] * target[2],
        up[0] * target[1] - up[1] * target[0],
    ]
    s = math.sqrt((1.0 + dot) * 2.0)
    inv = 1.0 / s
    return [cross[0] * inv, cross[1] * inv, cross[2] * inv, s * 0.5]


def _build_glb(nodes: list[dict[str, Any]]) -> bytes:
    primitive_cache = {
        "box": _build_box_geometry(),
        "sphere": _build_uv_sphere_geometry(18, 14),
        "cylinder": _build_cylinder_geometry(20),
        "cone": _build_cone_geometry(20),
    }
    materials = _materials()
    material_lookup = {material["name"]: index for index, material in enumerate(materials)}
    mesh_defs = sorted({_MESH_LIBRARY[node["mesh_key"]] for node in nodes})
    mesh_lookup: dict[tuple[str, str], int] = {}

    bin_blob = bytearray()
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []

    def add_buffer_view(data: bytes, target: int) -> int:
        while len(bin_blob) % 4:
            bin_blob.append(0)
        offset = len(bin_blob)
        bin_blob.extend(data)
        buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        return len(buffer_views) - 1

    def add_accessor(buffer_view: int, component_type: int, count: int, accessor_type: str, min_values: list[float] | None = None, max_values: list[float] | None = None) -> int:
        accessor: dict[str, Any] = {
            "bufferView": buffer_view,
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
        }
        if min_values is not None:
            accessor["min"] = min_values
        if max_values is not None:
            accessor["max"] = max_values
        accessors.append(accessor)
        return len(accessors) - 1

    for primitive_key, material_key in mesh_defs:
        positions, normals, indices = primitive_cache[primitive_key]
        position_values = array("f", [component for vertex in positions for component in vertex])
        normal_values = array("f", [component for normal in normals for component in normal])
        index_values = array("H", indices)

        pos_view = add_buffer_view(position_values.tobytes(), 34962)
        normal_view = add_buffer_view(normal_values.tobytes(), 34962)
        index_view = add_buffer_view(index_values.tobytes(), 34963)

        min_values = [min(vertex[i] for vertex in positions) for i in range(3)]
        max_values = [max(vertex[i] for vertex in positions) for i in range(3)]
        pos_accessor = add_accessor(pos_view, 5126, len(positions), "VEC3", min_values, max_values)
        normal_accessor = add_accessor(normal_view, 5126, len(normals), "VEC3")
        index_accessor = add_accessor(index_view, 5123, len(indices), "SCALAR", [0], [max(indices)])
        mesh_lookup[(primitive_key, material_key)] = len(meshes)
        meshes.append(
            {
                "name": f"{primitive_key}_{material_key}",
                "primitives": [
                    {
                        "attributes": {"POSITION": pos_accessor, "NORMAL": normal_accessor},
                        "indices": index_accessor,
                        "material": material_lookup[material_key],
                    }
                ],
            }
        )

    gltf_nodes = [
        {
            "name": node["name"],
            "mesh": mesh_lookup[_MESH_LIBRARY[node["mesh_key"]]],
            "translation": node["position"],
            "scale": node["scale"],
            "rotation": node["rotation"],
        }
        for node in nodes
    ]

    gltf = {
        "asset": {"version": "2.0", "generator": "ILIdeationEngineeringRenderV2"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(gltf_nodes)))}],
        "nodes": gltf_nodes,
        "meshes": meshes,
        "materials": materials,
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "extensionsUsed": [
            "KHR_materials_clearcoat",
            "KHR_materials_emissive_strength",
            "KHR_materials_specular",
            "KHR_materials_transmission",
        ],
    }
    return _pack_glb(gltf, bytes(bin_blob))


def _materials() -> list[dict[str, Any]]:
    return [
        {
            "name": "composite_shell",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["composite_shell"],
                "metallicFactor": 0.22,
                "roughnessFactor": 0.24,
            },
            "extensions": {
                "KHR_materials_clearcoat": {
                    "clearcoatFactor": 0.88,
                    "clearcoatRoughnessFactor": 0.12,
                },
                "KHR_materials_specular": {
                    "specularFactor": 0.54,
                },
            },
        },
        {
            "name": "sensor_glass",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["sensor_glass"],
                "metallicFactor": 0.08,
                "roughnessFactor": 0.12,
            },
            "emissiveFactor": [0.18, 0.12, 0.06],
            "extensions": {
                "KHR_materials_clearcoat": {
                    "clearcoatFactor": 0.95,
                    "clearcoatRoughnessFactor": 0.04,
                },
                "KHR_materials_specular": {
                    "specularFactor": 0.86,
                },
                "KHR_materials_transmission": {
                    "transmissionFactor": 0.42,
                },
            },
        },
        {
            "name": "anodized_metal",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["anodized_metal"],
                "metallicFactor": 0.82,
                "roughnessFactor": 0.28,
            },
            "extensions": {
                "KHR_materials_specular": {
                    "specularFactor": 0.68,
                }
            },
        },
        {
            "name": "joint_core",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["joint_core"],
                "metallicFactor": 0.74,
                "roughnessFactor": 0.24,
            },
            "emissiveFactor": [0.18, 0.08, 0.04],
            "extensions": {"KHR_materials_emissive_strength": {"emissiveStrength": 1.9}},
        },
        {
            "name": "traction_rubber",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["traction_rubber"],
                "metallicFactor": 0.04,
                "roughnessFactor": 0.82,
            },
        },
        {
            "name": "payload_pack",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["payload_pack"],
                "metallicFactor": 0.1,
                "roughnessFactor": 0.52,
            },
        },
        {
            "name": "ceramic_plate",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["ceramic_plate"],
                "metallicFactor": 0.08,
                "roughnessFactor": 0.31,
            },
            "extensions": {
                "KHR_materials_clearcoat": {
                    "clearcoatFactor": 0.36,
                    "clearcoatRoughnessFactor": 0.22,
                }
            },
        },
        {
            "name": "optic_emitter",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["optic_emitter"],
                "metallicFactor": 0.04,
                "roughnessFactor": 0.18,
            },
            "emissiveFactor": [0.24, 0.5, 0.42],
            "extensions": {"KHR_materials_emissive_strength": {"emissiveStrength": 2.4}},
        },
        {
            "name": "harness_webbing",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["harness_webbing"],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.88,
            },
        },
        {
            "name": "brushed_alloy",
            "pbrMetallicRoughness": {
                "baseColorFactor": _COLOR_MAP["brushed_alloy"],
                "metallicFactor": 0.66,
                "roughnessFactor": 0.34,
            },
            "extensions": {
                "KHR_materials_specular": {
                    "specularFactor": 0.74,
                }
            },
        },
    ]


def _build_box_geometry() -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[int]]:
    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    indices: list[int] = []
    faces = [
        ((0.0, 0.0, 1.0), [(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]),
        ((0.0, 0.0, -1.0), [(0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5)]),
        ((1.0, 0.0, 0.0), [(0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5)]),
        ((-1.0, 0.0, 0.0), [(-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5)]),
        ((0.0, 1.0, 0.0), [(-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5)]),
        ((0.0, -1.0, 0.0), [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5)]),
    ]
    for normal, corners in faces:
        base = len(vertices)
        vertices.extend(corners)
        normals.extend([normal] * 4)
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return vertices, normals, indices


def _build_uv_sphere_geometry(width_segments: int, height_segments: int) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[int]]:
    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    indices: list[int] = []
    grid: list[list[int]] = []
    for y_index in range(height_segments + 1):
        v = y_index / height_segments
        theta = v * math.pi
        row: list[int] = []
        for x_index in range(width_segments + 1):
            u = x_index / width_segments
            phi = u * math.pi * 2.0
            x = math.sin(theta) * math.cos(phi) * 0.5
            y = math.cos(theta) * 0.5
            z = math.sin(theta) * math.sin(phi) * 0.5
            row.append(len(vertices))
            vertices.append((x, y, z))
            normals.append(tuple(_normalize([x, y, z])))
        grid.append(row)
    for y_index in range(height_segments):
        for x_index in range(width_segments):
            a = grid[y_index][x_index + 1]
            b = grid[y_index][x_index]
            c = grid[y_index + 1][x_index]
            d = grid[y_index + 1][x_index + 1]
            if y_index != 0:
                indices.extend([a, b, d])
            if y_index != height_segments - 1:
                indices.extend([b, c, d])
    return vertices, normals, indices


def _build_cylinder_geometry(radial_segments: int) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[int]]:
    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    indices: list[int] = []

    top_ring: list[int] = []
    bottom_ring: list[int] = []
    for segment in range(radial_segments + 1):
        angle = (segment / radial_segments) * math.pi * 2.0
        x = math.cos(angle) * 0.5
        z = math.sin(angle) * 0.5
        top_ring.append(len(vertices))
        vertices.append((x, 0.5, z))
        normals.append(tuple(_normalize([x, 0.0, z])))
        bottom_ring.append(len(vertices))
        vertices.append((x, -0.5, z))
        normals.append(tuple(_normalize([x, 0.0, z])))
    for segment in range(radial_segments):
        a = top_ring[segment]
        b = bottom_ring[segment]
        c = bottom_ring[segment + 1]
        d = top_ring[segment + 1]
        indices.extend([a, b, d, b, c, d])

    top_center = len(vertices)
    vertices.append((0.0, 0.5, 0.0))
    normals.append((0.0, 1.0, 0.0))
    bottom_center = len(vertices)
    vertices.append((0.0, -0.5, 0.0))
    normals.append((0.0, -1.0, 0.0))
    top_cap: list[int] = []
    bottom_cap: list[int] = []
    for segment in range(radial_segments):
        angle = (segment / radial_segments) * math.pi * 2.0
        x = math.cos(angle) * 0.5
        z = math.sin(angle) * 0.5
        top_cap.append(len(vertices))
        vertices.append((x, 0.5, z))
        normals.append((0.0, 1.0, 0.0))
        bottom_cap.append(len(vertices))
        vertices.append((x, -0.5, z))
        normals.append((0.0, -1.0, 0.0))
    for segment in range(radial_segments):
        next_index = (segment + 1) % radial_segments
        indices.extend([top_center, top_cap[segment], top_cap[next_index]])
        indices.extend([bottom_center, bottom_cap[next_index], bottom_cap[segment]])
    return vertices, normals, indices


def _build_cone_geometry(radial_segments: int) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[int]]:
    vertices: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    indices: list[int] = []
    apex_index = len(vertices)
    vertices.append((0.0, 0.5, 0.0))
    normals.append((0.0, 1.0, 0.0))
    ring: list[int] = []
    slope = _normalize([0.5, 0.5, 0.0])
    for segment in range(radial_segments + 1):
        angle = (segment / radial_segments) * math.pi * 2.0
        x = math.cos(angle) * 0.5
        z = math.sin(angle) * 0.5
        ring.append(len(vertices))
        vertices.append((x, -0.5, z))
        normals.append((slope[0] * math.cos(angle), slope[1], slope[0] * math.sin(angle)))
    for segment in range(radial_segments):
        indices.extend([apex_index, ring[segment], ring[segment + 1]])
    base_center = len(vertices)
    vertices.append((0.0, -0.5, 0.0))
    normals.append((0.0, -1.0, 0.0))
    base_ring: list[int] = []
    for segment in range(radial_segments):
        angle = (segment / radial_segments) * math.pi * 2.0
        x = math.cos(angle) * 0.5
        z = math.sin(angle) * 0.5
        base_ring.append(len(vertices))
        vertices.append((x, -0.5, z))
        normals.append((0.0, -1.0, 0.0))
    for segment in range(radial_segments):
        next_index = (segment + 1) % radial_segments
        indices.extend([base_center, base_ring[next_index], base_ring[segment]])
    return vertices, normals, indices


def _pack_glb(gltf: dict[str, Any], bin_blob: bytes) -> bytes:
    json_chunk = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_padding = b" " * ((4 - (len(json_chunk) % 4)) % 4)
    json_chunk += json_padding
    bin_padding = b"\x00" * ((4 - (len(bin_blob) % 4)) % 4)
    bin_blob += bin_padding
    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_blob)
    return b"".join(
        [
            struct.pack("<III", 0x46546C67, 2, total_length),
            struct.pack("<I4s", len(json_chunk), b"JSON"),
            json_chunk,
            struct.pack("<I4s", len(bin_blob), b"BIN\x00"),
            bin_blob,
        ]
    )
