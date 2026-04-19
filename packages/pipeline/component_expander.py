"""Deterministic component expansion from high-level design to recursive graph.

This module implements the staged expansion pipeline:
1. RobotDesignCandidate -> Subsystem graph
2. Subsystem -> Assembly graph
3. Assembly -> Component graph
4. Component -> Parts

All expansions are deterministic based on templates. Gemini only proposes
the high-level embodiment; the compiler handles the recursive expansion.
"""
from __future__ import annotations

from packages.pipeline.component_ir import (
    RobotComponentGraph,
    SubsystemSpec,
    AssemblySpec,
    ComponentSpec,
    PartSpec,
    JointSpec,
    PartGeometry,
    InterfaceSpec,
    make_id,
)
from packages.pipeline.schemas import RobotDesignCandidate


SUBSYSTEM_TEMPLATES: dict[str, list[str]] = {
    "biped": ["locomotion:biped", "structure:torso", "sensing:head"],
    "quadruped": ["locomotion:quadruped", "structure:torso", "sensing:head"],
    "hexapod": ["locomotion:hexapod", "structure:torso", "sensing:head"],
    "wheeled": ["locomotion:wheeled", "structure:chassis", "sensing:front"],
    "tracked": ["locomotion:tracked", "structure:chassis", "sensing:front"],
    "wheeled_manipulator": ["locomotion:wheeled", "manipulation:arm", "structure:chassis"],
    "mobile_arm": ["locomotion:wheeled", "manipulation:arm", "structure:platform"],
    "fixed_arm": ["manipulation:arm", "structure:base"],
    "dual_arm": ["manipulation:dual_arm", "structure:torso"],
    "snake": ["locomotion:snake", "sensing:head"],
    "climbing_hybrid": ["locomotion:quadruped", "manipulation:climbing_gripper", "traction:microspine"],
    "tensegrity": ["locomotion:tensegrity", "sensing:distributed"],
    "spherical": ["locomotion:spherical", "sensing:internal"],
    "inchworm": ["locomotion:inchworm", "manipulation:gripper"],
    "tripod": ["locomotion:tripod", "structure:torso"],
    "omnidirectional": ["locomotion:omnidirectional", "structure:platform"],
    "legged_wheeled": ["locomotion:legged_wheeled", "structure:chassis"],
    "soft_continuum": ["locomotion:soft", "manipulation:soft"],
    "modular": ["locomotion:modular", "structure:modular"],
    "arm": ["manipulation:arm", "structure:base"],
    "hybrid": ["locomotion:quadruped", "manipulation:arm", "structure:torso"],
}


LEG_POSITIONS_BY_COUNT: dict[int, list[tuple[str, tuple[float, float, float]]]] = {
    2: [
        ("leg_l", (-0.1, 0.0, 0.0)),
        ("leg_r", (0.1, 0.0, 0.0)),
    ],
    4: [
        ("leg_fl", (-0.12, 0.0, 0.15)),
        ("leg_fr", (0.12, 0.0, 0.15)),
        ("leg_rl", (-0.12, 0.0, -0.15)),
        ("leg_rr", (0.12, 0.0, -0.15)),
    ],
    6: [
        ("leg_fl", (-0.12, 0.0, 0.2)),
        ("leg_fr", (0.12, 0.0, 0.2)),
        ("leg_ml", (-0.14, 0.0, 0.0)),
        ("leg_mr", (0.14, 0.0, 0.0)),
        ("leg_rl", (-0.12, 0.0, -0.2)),
        ("leg_rr", (0.12, 0.0, -0.2)),
    ],
}

ARM_POSITIONS_BY_COUNT: dict[int, list[tuple[str, tuple[float, float, float]]]] = {
    1: [("arm_0", (0.0, 0.3, 0.1))],
    2: [
        ("arm_l", (-0.18, 0.3, 0.0)),
        ("arm_r", (0.18, 0.3, 0.0)),
    ],
}


def _expand_leg_assembly(
    subsystem_id: str,
    leg_name: str,
    position: tuple[float, float, float],
    leg_length_m: float,
    leg_dof: int,
    actuator_torque_nm: float,
) -> AssemblySpec:
    """Expand a leg into hip/thigh/knee/shin/ankle/foot components."""
    assembly_id = make_id("assembly", subsystem_id.split(":")[1], leg_name)

    components: list[ComponentSpec] = []
    joints: list[JointSpec] = []

    segment_length = leg_length_m / max(leg_dof, 1) * 0.5
    y_offset = 0.0

    joint_components = ["hip", "knee", "ankle"][:leg_dof]
    link_components = ["thigh", "shin", "foot"][:leg_dof]

    for i, (joint_name, link_name) in enumerate(zip(joint_components, link_components)):
        joint_comp_id = make_id("component", subsystem_id.split(":")[1], leg_name, joint_name)
        link_comp_id = make_id("component", subsystem_id.split(":")[1], leg_name, link_name)

        joint_comp = ComponentSpec(
            id=joint_comp_id,
            parent_id=assembly_id,
            kind="joint_module",
            display_name=f"{leg_name} {joint_name}",
            is_actuated=True,
            dof=1,
            position=(position[0], y_offset, position[2]),
            parts=[
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], leg_name, joint_name, "motor"),
                    parent_id=joint_comp_id,
                    kind="actuator",
                    role="motor",
                    display_name=f"{joint_name} motor",
                    mass_kg=0.15,
                    geometry=PartGeometry(
                        primitive="cylinder",
                        dimensions=(0.04, 0.03, 0.04),
                        material_key="anodized_metal",
                    ),
                ),
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], leg_name, joint_name, "gearbox"),
                    parent_id=joint_comp_id,
                    kind="transmission",
                    role="gearbox",
                    display_name=f"{joint_name} gearbox",
                    mass_kg=0.08,
                    geometry=PartGeometry(
                        primitive="cylinder",
                        dimensions=(0.035, 0.02, 0.035),
                        material_key="brushed_alloy",
                    ),
                ),
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], leg_name, joint_name, "encoder"),
                    parent_id=joint_comp_id,
                    kind="encoder",
                    role="encoder",
                    display_name=f"{joint_name} encoder",
                    mass_kg=0.02,
                    geometry=PartGeometry(
                        primitive="cylinder",
                        dimensions=(0.015, 0.01, 0.015),
                        material_key="sensor_glass",
                    ),
                ),
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], leg_name, joint_name, "housing"),
                    parent_id=joint_comp_id,
                    kind="structural",
                    role="housing",
                    display_name=f"{joint_name} housing",
                    mass_kg=0.05,
                    geometry=PartGeometry(
                        primitive="sphere",
                        dimensions=(0.045, 0.045, 0.045),
                        material_key="joint_core",
                    ),
                ),
            ],
        )
        components.append(joint_comp)
        y_offset -= 0.05

        link_comp = ComponentSpec(
            id=link_comp_id,
            parent_id=assembly_id,
            kind="link",
            display_name=f"{leg_name} {link_name}",
            position=(position[0], y_offset - segment_length / 2, position[2]),
            parts=[
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], leg_name, link_name, "tube"),
                    parent_id=link_comp_id,
                    kind="structural",
                    role="link_tube",
                    display_name=f"{link_name} tube",
                    mass_kg=0.1,
                    geometry=PartGeometry(
                        primitive="capsule",
                        dimensions=(0.025, segment_length, 0.025),
                        material_key="anodized_metal",
                    ),
                ),
            ],
        )
        components.append(link_comp)

        if i > 0:
            joints.append(JointSpec(
                id=make_id("part", subsystem_id.split(":")[1], leg_name, f"joint_{i}"),
                name=f"{leg_name}_{joint_name}_joint",
                kind="revolute",
                parent_component_id=components[-3].id if len(components) > 2 else joint_comp_id,
                child_component_id=joint_comp_id,
                position=(position[0], y_offset + 0.05, position[2]),
            ))

        y_offset -= segment_length

    foot_comp_id = make_id("component", subsystem_id.split(":")[1], leg_name, "foot")
    foot_comp = ComponentSpec(
        id=foot_comp_id,
        parent_id=assembly_id,
        kind="end_effector",
        display_name=f"{leg_name} foot",
        position=(position[0], y_offset, position[2]),
        parts=[
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], leg_name, "foot", "pad"),
                parent_id=foot_comp_id,
                kind="contact_pad",
                role="contact_pad",
                display_name=f"{leg_name} foot pad",
                mass_kg=0.03,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.05, 0.015, 0.06),
                    material_key="traction_rubber",
                ),
            ),
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], leg_name, "foot", "force_sensor"),
                parent_id=foot_comp_id,
                kind="sensor",
                role="force_sensor",
                display_name=f"{leg_name} force sensor",
                mass_kg=0.01,
                geometry=PartGeometry(
                    primitive="cylinder",
                    dimensions=(0.02, 0.005, 0.02),
                    material_key="sensor_glass",
                ),
            ),
        ],
    )
    components.append(foot_comp)

    return AssemblySpec(
        id=assembly_id,
        parent_id=subsystem_id,
        kind="leg",
        display_name=leg_name.replace("_", " ").title(),
        template_key=f"leg_{leg_dof}dof",
        components=components,
        joints=joints,
        position=position,
    )


def _expand_arm_assembly(
    subsystem_id: str,
    arm_name: str,
    position: tuple[float, float, float],
    arm_length_m: float,
    arm_dof: int,
) -> AssemblySpec:
    """Expand an arm into shoulder/upper/elbow/forearm/wrist/hand components."""
    assembly_id = make_id("assembly", subsystem_id.split(":")[1], arm_name)

    components: list[ComponentSpec] = []
    joints: list[JointSpec] = []

    joint_names = ["shoulder", "elbow", "wrist"][:min(arm_dof, 3)]
    segment_length = arm_length_m / len(joint_names) * 0.9

    x_offset = position[0]
    y_offset = position[1]
    z_offset = position[2]

    for i, joint_name in enumerate(joint_names):
        joint_comp_id = make_id("component", subsystem_id.split(":")[1], arm_name, joint_name)

        joint_comp = ComponentSpec(
            id=joint_comp_id,
            parent_id=assembly_id,
            kind="joint_module",
            display_name=f"{arm_name} {joint_name}",
            is_actuated=True,
            dof=1,
            position=(x_offset, y_offset, z_offset),
            parts=[
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], arm_name, joint_name, "motor"),
                    parent_id=joint_comp_id,
                    kind="actuator",
                    role="motor",
                    display_name=f"{joint_name} motor",
                    mass_kg=0.12,
                    geometry=PartGeometry(
                        primitive="cylinder",
                        dimensions=(0.035, 0.025, 0.035),
                        material_key="anodized_metal",
                    ),
                ),
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], arm_name, joint_name, "housing"),
                    parent_id=joint_comp_id,
                    kind="structural",
                    role="housing",
                    display_name=f"{joint_name} housing",
                    mass_kg=0.04,
                    geometry=PartGeometry(
                        primitive="sphere",
                        dimensions=(0.04, 0.04, 0.04),
                        material_key="joint_core",
                    ),
                ),
            ],
        )
        components.append(joint_comp)

        link_name = ["upper_arm", "forearm", "hand"][i] if i < 3 else f"link_{i}"
        link_comp_id = make_id("component", subsystem_id.split(":")[1], arm_name, link_name)

        x_direction = 1 if "r" in arm_name or "0" in arm_name else -1
        link_x = x_offset + x_direction * segment_length / 2

        link_comp = ComponentSpec(
            id=link_comp_id,
            parent_id=assembly_id,
            kind="link",
            display_name=f"{arm_name} {link_name}",
            position=(link_x, y_offset - 0.02, z_offset),
            parts=[
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], arm_name, link_name, "tube"),
                    parent_id=link_comp_id,
                    kind="structural",
                    role="link_tube",
                    display_name=f"{link_name} tube",
                    mass_kg=0.08,
                    geometry=PartGeometry(
                        primitive="capsule",
                        dimensions=(0.02, segment_length * 0.9, 0.02),
                        rotation=(0.0, 0.0, 1.57),
                        material_key="anodized_metal",
                    ),
                ),
            ],
        )
        components.append(link_comp)

        x_offset = link_x + x_direction * segment_length / 2
        y_offset -= 0.03

    gripper_comp_id = make_id("component", subsystem_id.split(":")[1], arm_name, "gripper")
    gripper_comp = ComponentSpec(
        id=gripper_comp_id,
        parent_id=assembly_id,
        kind="end_effector",
        display_name=f"{arm_name} gripper",
        position=(x_offset, y_offset, z_offset),
        parts=[
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], arm_name, "gripper", "palm"),
                parent_id=gripper_comp_id,
                kind="structural",
                role="palm",
                display_name="gripper palm",
                mass_kg=0.05,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.04, 0.03, 0.05),
                    material_key="composite_shell",
                ),
            ),
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], arm_name, "gripper", "finger_0"),
                parent_id=gripper_comp_id,
                kind="structural",
                role="finger",
                display_name="finger 0",
                mass_kg=0.02,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.01, 0.04, 0.015),
                    position=(0.015, -0.035, 0.0),
                    material_key="anodized_metal",
                ),
            ),
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], arm_name, "gripper", "finger_1"),
                parent_id=gripper_comp_id,
                kind="structural",
                role="finger",
                display_name="finger 1",
                mass_kg=0.02,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.01, 0.04, 0.015),
                    position=(-0.015, -0.035, 0.0),
                    material_key="anodized_metal",
                ),
            ),
        ],
    )
    components.append(gripper_comp)

    return AssemblySpec(
        id=assembly_id,
        parent_id=subsystem_id,
        kind="arm",
        display_name=arm_name.replace("_", " ").title(),
        template_key=f"arm_{arm_dof}dof",
        components=components,
        joints=joints,
        position=position,
    )


def _expand_torso_assembly(
    subsystem_id: str,
    torso_length_m: float,
    has_payload: bool,
) -> AssemblySpec:
    """Expand torso into shell panels, bays, and mounting brackets."""
    assembly_id = make_id("assembly", subsystem_id.split(":")[1], "torso")

    components: list[ComponentSpec] = []

    chassis_comp_id = make_id("component", subsystem_id.split(":")[1], "torso", "chassis")
    chassis_comp = ComponentSpec(
        id=chassis_comp_id,
        parent_id=assembly_id,
        kind="chassis",
        display_name="Torso Chassis",
        position=(0.0, torso_length_m / 2, 0.0),
        parts=[
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], "torso", "chassis", "frame"),
                parent_id=chassis_comp_id,
                kind="structural",
                role="frame",
                display_name="main frame",
                mass_kg=0.5,
                geometry=PartGeometry(
                    primitive="capsule",
                    dimensions=(0.12, torso_length_m, 0.08),
                    material_key="composite_shell",
                ),
            ),
        ],
    )
    components.append(chassis_comp)

    shell_comp_id = make_id("component", subsystem_id.split(":")[1], "torso", "shell")
    shell_comp = ComponentSpec(
        id=shell_comp_id,
        parent_id=assembly_id,
        kind="shell_panel",
        display_name="Shell Panels",
        position=(0.0, torso_length_m / 2, 0.0),
        parts=[
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], "torso", "shell", "top_panel"),
                parent_id=shell_comp_id,
                kind="shell",
                role="top_panel",
                display_name="top shell panel",
                mass_kg=0.1,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.14, 0.01, 0.1),
                    position=(0.0, torso_length_m / 2 + 0.06, 0.0),
                    material_key="ceramic_plate",
                ),
            ),
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], "torso", "shell", "side_panel_l"),
                parent_id=shell_comp_id,
                kind="shell",
                role="side_panel",
                display_name="left side panel",
                mass_kg=0.08,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.01, torso_length_m * 0.8, 0.08),
                    position=(-0.07, torso_length_m / 2, 0.0),
                    material_key="brushed_alloy",
                ),
            ),
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], "torso", "shell", "side_panel_r"),
                parent_id=shell_comp_id,
                kind="shell",
                role="side_panel",
                display_name="right side panel",
                mass_kg=0.08,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.01, torso_length_m * 0.8, 0.08),
                    position=(0.07, torso_length_m / 2, 0.0),
                    material_key="brushed_alloy",
                ),
            ),
        ],
    )
    components.append(shell_comp)

    controller_comp_id = make_id("component", subsystem_id.split(":")[1], "torso", "controller_bay")
    controller_comp = ComponentSpec(
        id=controller_comp_id,
        parent_id=assembly_id,
        kind="chassis",
        display_name="Controller Bay",
        position=(0.0, torso_length_m * 0.7, 0.0),
        parts=[
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], "torso", "controller_bay", "mcu"),
                parent_id=controller_comp_id,
                kind="pcb",
                role="mcu",
                display_name="main controller",
                vendor="Raspberry Pi Foundation",
                sku="RPI5-8GB",
                unit_price_usd=80.0,
                mass_kg=0.05,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.085, 0.017, 0.056),
                    material_key="sensor_glass",
                ),
            ),
        ],
    )
    components.append(controller_comp)

    battery_comp_id = make_id("component", subsystem_id.split(":")[1], "torso", "battery_bay")
    battery_comp = ComponentSpec(
        id=battery_comp_id,
        parent_id=assembly_id,
        kind="chassis",
        display_name="Battery Bay",
        position=(0.0, torso_length_m * 0.3, 0.0),
        parts=[
            PartSpec(
                id=make_id("part", subsystem_id.split(":")[1], "torso", "battery_bay", "battery"),
                parent_id=battery_comp_id,
                kind="power_rail",
                role="battery",
                display_name="main battery",
                mass_kg=0.3,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.08, 0.04, 0.06),
                    material_key="anodized_metal",
                ),
            ),
        ],
    )
    components.append(battery_comp)

    if has_payload:
        payload_comp_id = make_id("component", subsystem_id.split(":")[1], "torso", "payload_mount")
        payload_comp = ComponentSpec(
            id=payload_comp_id,
            parent_id=assembly_id,
            kind="mounting_bracket",
            display_name="Payload Mount",
            position=(0.0, torso_length_m + 0.05, -0.02),
            parts=[
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], "torso", "payload_mount", "bracket"),
                    parent_id=payload_comp_id,
                    kind="bracket",
                    role="mount_bracket",
                    display_name="payload bracket",
                    mass_kg=0.1,
                    geometry=PartGeometry(
                        primitive="box",
                        dimensions=(0.1, 0.02, 0.08),
                        material_key="composite_shell",
                    ),
                ),
                PartSpec(
                    id=make_id("part", subsystem_id.split(":")[1], "torso", "payload_mount", "strap_0"),
                    parent_id=payload_comp_id,
                    kind="structural",
                    role="strap",
                    display_name="payload strap",
                    mass_kg=0.02,
                    geometry=PartGeometry(
                        primitive="box",
                        dimensions=(0.12, 0.08, 0.01),
                        material_key="harness_webbing",
                    ),
                ),
            ],
        )
        components.append(payload_comp)

    return AssemblySpec(
        id=assembly_id,
        parent_id=subsystem_id,
        kind="torso",
        display_name="Torso",
        template_key="torso_standard",
        components=components,
        joints=[],
        position=(0.0, 0.0, 0.0),
    )


def expand_candidate_to_component_graph(
    candidate: RobotDesignCandidate,
) -> RobotComponentGraph:
    """Expand a design candidate into full recursive component graph."""
    robot_id = f"robot:{candidate.candidate_id.lower()}_{candidate.embodiment_class}"

    subsystems: list[SubsystemSpec] = []

    subsystem_hints = SUBSYSTEM_TEMPLATES.get(candidate.embodiment_class, ["structure:chassis"])

    if candidate.num_legs > 0:
        loco_subsystem_id = make_id("subsystem", "locomotion")
        leg_positions = LEG_POSITIONS_BY_COUNT.get(candidate.num_legs, [])

        if not leg_positions:
            leg_positions = [
                (f"leg_{i}", (0.1 * (i % 2 * 2 - 1), 0.0, 0.1 * (i // 2 - candidate.num_legs / 4)))
                for i in range(candidate.num_legs)
            ]

        leg_assemblies = [
            _expand_leg_assembly(
                loco_subsystem_id,
                leg_name,
                position,
                candidate.leg_length_m,
                candidate.leg_dof,
                candidate.actuator_torque_nm,
            )
            for leg_name, position in leg_positions
        ]

        subsystems.append(SubsystemSpec(
            id=loco_subsystem_id,
            parent_id=robot_id,
            kind="locomotion",
            display_name="Locomotion",
            assemblies=leg_assemblies,
        ))

    if candidate.num_arms > 0:
        manip_subsystem_id = make_id("subsystem", "manipulation")
        arm_positions = ARM_POSITIONS_BY_COUNT.get(candidate.num_arms, [])

        if not arm_positions:
            arm_positions = [
                (f"arm_{i}", (0.15 * (i % 2 * 2 - 1), 0.3, 0.0))
                for i in range(candidate.num_arms)
            ]

        arm_assemblies = [
            _expand_arm_assembly(
                manip_subsystem_id,
                arm_name,
                position,
                candidate.arm_length_m,
                candidate.arm_dof,
            )
            for arm_name, position in arm_positions
        ]

        subsystems.append(SubsystemSpec(
            id=manip_subsystem_id,
            parent_id=robot_id,
            kind="manipulation",
            display_name="Manipulation",
            assemblies=arm_assemblies,
        ))

    if candidate.has_torso:
        struct_subsystem_id = make_id("subsystem", "structure")
        has_payload = candidate.payload_capacity_kg > 0

        torso_assembly = _expand_torso_assembly(
            struct_subsystem_id,
            candidate.torso_length_m,
            has_payload,
        )

        subsystems.append(SubsystemSpec(
            id=struct_subsystem_id,
            parent_id=robot_id,
            kind="structure",
            display_name="Structure",
            assemblies=[torso_assembly],
        ))

    sensing_subsystem_id = make_id("subsystem", "sensing")
    sensor_assemblies: list[AssemblySpec] = []

    if "camera" in candidate.sensor_package or "lidar" in candidate.sensor_package:
        head_assembly_id = make_id("assembly", "sensing", "head")
        head_comp_id = make_id("component", "sensing", "head", "sensor_pod")
        head_parts: list[PartSpec] = []

        if "camera" in candidate.sensor_package:
            head_parts.append(PartSpec(
                id=make_id("part", "sensing", "head", "sensor_pod", "camera"),
                parent_id=head_comp_id,
                kind="sensor",
                role="camera",
                display_name="RGB camera",
                mass_kg=0.02,
                geometry=PartGeometry(
                    primitive="box",
                    dimensions=(0.03, 0.02, 0.03),
                    material_key="sensor_glass",
                ),
            ))

        if "lidar" in candidate.sensor_package:
            head_parts.append(PartSpec(
                id=make_id("part", "sensing", "head", "sensor_pod", "lidar"),
                parent_id=head_comp_id,
                kind="sensor",
                role="lidar",
                display_name="LiDAR scanner",
                mass_kg=0.05,
                geometry=PartGeometry(
                    primitive="cylinder",
                    dimensions=(0.04, 0.03, 0.04),
                    material_key="sensor_glass",
                ),
            ))

        head_comp = ComponentSpec(
            id=head_comp_id,
            parent_id=head_assembly_id,
            kind="sensor_module",
            display_name="Head Sensor Pod",
            position=(0.0, candidate.torso_length_m + 0.1, 0.05),
            parts=head_parts,
        )

        head_dome_comp_id = make_id("component", "sensing", "head", "dome")
        head_dome_comp = ComponentSpec(
            id=head_dome_comp_id,
            parent_id=head_assembly_id,
            kind="shell_panel",
            display_name="Head Dome",
            position=(0.0, candidate.torso_length_m + 0.12, 0.0),
            parts=[
                PartSpec(
                    id=make_id("part", "sensing", "head", "dome", "shell"),
                    parent_id=head_dome_comp_id,
                    kind="shell",
                    role="dome_shell",
                    display_name="head dome shell",
                    mass_kg=0.05,
                    geometry=PartGeometry(
                        primitive="sphere",
                        dimensions=(0.08, 0.08, 0.08),
                        material_key="sensor_glass",
                    ),
                ),
            ],
        )

        sensor_assemblies.append(AssemblySpec(
            id=head_assembly_id,
            parent_id=sensing_subsystem_id,
            kind="head",
            display_name="Head",
            template_key="head_sensor",
            components=[head_comp, head_dome_comp],
            joints=[],
            position=(0.0, candidate.torso_length_m + 0.1, 0.0),
        ))

    if sensor_assemblies:
        subsystems.append(SubsystemSpec(
            id=sensing_subsystem_id,
            parent_id=robot_id,
            kind="sensing",
            display_name="Sensing",
            assemblies=sensor_assemblies,
        ))

    return RobotComponentGraph(
        id=robot_id,
        candidate_id=candidate.candidate_id,
        embodiment_class=candidate.embodiment_class,
        display_name=f"{candidate.embodiment_class.replace('_', ' ').title()} Robot",
        subsystems=subsystems,
    )
