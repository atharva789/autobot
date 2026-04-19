"""
MJCF Compiler - Compiles RobotDesignIR to MuJoCo MJCF XML.

This compiler produces canonical, simulator-ready MJCF files from the IR.
Unlike mjcf_factory.py (which produces screening-quality MJCF from
MorphologyParams), this compiler produces full-fidelity MJCF from the IR.

Output is compatible with:
- MuJoCo native simulation
- MuJoCo MJX (JAX-accelerated)
- Isaac Sim MJCF importer
"""

from __future__ import annotations

from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    Geometry,
)


def compile_to_mjcf(ir: RobotDesignIR, indent: int = 2) -> str:
    """
    Compile a RobotDesignIR to MuJoCo MJCF XML.

    Args:
        ir: The canonical robot design IR
        indent: Number of spaces for indentation

    Returns:
        MJCF XML string ready for MuJoCo

    Raises:
        ValueError: If IR validation fails
    """
    errors = ir.validate()
    if errors:
        raise ValueError(f"IR validation failed: {errors}")

    parts = [
        _header(ir),
        _defaults(),
        _assets(ir),
        _worldbody(ir),
        _actuators(ir),
        _sensors(ir),
        _footer(),
    ]

    return "\n".join(p for p in parts if p)


def _header(ir: RobotDesignIR) -> str:
    return f'<mujoco model="{ir.name}">'


def _defaults() -> str:
    return """  <option timestep="0.002" gravity="0 0 -9.81"/>
  <default>
    <joint damping="0.5" stiffness="0"/>
    <geom friction="0.6 0.005 0.0001" condim="3"/>
  </default>"""


def _assets(ir: RobotDesignIR) -> str:
    lines = ["  <asset>"]
    lines.append('    <texture type="skybox" builtin="gradient" rgb1=".4 .6 .8" rgb2="0 0 0" width="32" height="512"/>')
    lines.append('    <texture name="grid" type="2d" builtin="checker" rgb1=".1 .2 .3" rgb2=".2 .3 .4" width="300" height="300"/>')
    lines.append('    <material name="grid" texture="grid" texrepeat="8 8" reflectance=".2"/>')

    # Add materials for links
    for i, link in enumerate(ir.links):
        r, g, b = 0.3 + (i * 0.1) % 0.5, 0.4, 0.5
        lines.append(f'    <material name="mat_{link.name}" rgba="{r:.2f} {g:.2f} {b:.2f} 1"/>')

    lines.append("  </asset>")
    return "\n".join(lines)


def _geometry_to_mjcf(geom: Geometry, prefix: str = "") -> str:
    """Convert IR geometry to MJCF geom element."""
    if geom.type == "box":
        size = " ".join(f"{s/2:.4f}" for s in geom.size[:3])  # MJCF uses half-sizes
        return f'{prefix}<geom type="box" size="{size}"/>'
    elif geom.type == "cylinder":
        radius, length = geom.size[0], geom.size[1]
        return f'{prefix}<geom type="cylinder" size="{radius:.4f} {length/2:.4f}"/>'
    elif geom.type == "sphere":
        return f'{prefix}<geom type="sphere" size="{geom.size[0]:.4f}"/>'
    elif geom.type == "capsule":
        radius, length = geom.size[0], geom.size[1]
        return f'{prefix}<geom type="capsule" size="{radius:.4f} {length/2:.4f}"/>'
    elif geom.type == "mesh" and geom.mesh_path:
        return f'{prefix}<geom type="mesh" mesh="{geom.mesh_path}"/>'
    return f'{prefix}<geom type="sphere" size="0.05"/>'


def _worldbody(ir: RobotDesignIR) -> str:
    lines = ["  <worldbody>"]
    lines.append('    <geom name="floor" type="plane" size="10 10 0.1" material="grid"/>')
    lines.append('    <light pos="0 0 3" dir="0 0 -1" diffuse=".8 .8 .8"/>')

    root = ir.root_link()
    if root:
        lines.extend(_link_tree(ir, root.name, "    "))

    lines.append("  </worldbody>")
    return "\n".join(lines)


def _link_tree(ir: RobotDesignIR, link_name: str, indent: str) -> list[str]:
    """Recursively build link tree."""
    lines = []
    link = ir.get_link(link_name)
    if not link:
        return lines

    lines.append(f'{indent}<body name="{link.name}">')

    # Inertial
    if link.inertial:
        i = link.inertial
        lines.append(f'{indent}  <inertial pos="{i.origin.x:.4f} {i.origin.y:.4f} {i.origin.z:.4f}" mass="{i.mass:.4f}"/>')

    # Visual/collision geometry
    if link.visual:
        geom_str = _geometry_to_mjcf(link.visual.geometry, f"{indent}  ")
        lines.append(geom_str.rstrip("/>") + f' material="mat_{link.name}"/>')
    elif link.collision:
        lines.append(_geometry_to_mjcf(link.collision.geometry, f"{indent}  "))

    # Child joints and links
    for joint in ir.joints:
        if joint.parent_link == link_name:
            lines.extend(_joint_and_child(ir, joint, indent + "  "))

    lines.append(f"{indent}</body>")
    return lines


def _joint_and_child(ir: RobotDesignIR, joint: JointIR, indent: str) -> list[str]:
    """Generate joint element and recurse to child."""
    lines = []

    # Joint type mapping
    jtype = {
        JointType.REVOLUTE: "hinge",
        JointType.CONTINUOUS: "hinge",
        JointType.PRISMATIC: "slide",
        JointType.FIXED: None,  # No joint element for fixed
        JointType.BALL: "ball",
    }.get(joint.joint_type, "hinge")

    if jtype:
        axis = f"{joint.axis.x:.2f} {joint.axis.y:.2f} {joint.axis.z:.2f}"
        pos = f"{joint.origin.x:.4f} {joint.origin.y:.4f} {joint.origin.z:.4f}"

        limit_str = ""
        if joint.limits and joint.joint_type == JointType.REVOLUTE:
            limit_str = f' range="{joint.limits.lower:.3f} {joint.limits.upper:.3f}"'

        lines.append(f'{indent}<joint name="{joint.name}" type="{jtype}" pos="{pos}" axis="{axis}"{limit_str}/>')

    # Recurse to child
    lines.extend(_link_tree(ir, joint.child_link, indent))

    return lines


def _actuators(ir: RobotDesignIR) -> str:
    actuated_joints = [j for j in ir.joints if j.actuator]
    if not actuated_joints:
        return ""

    lines = ["  <actuator>"]
    for joint in actuated_joints:
        if joint.actuator:
            gear = joint.actuator.gear_ratio
            lines.append(f'    <motor name="motor_{joint.name}" joint="{joint.name}" gear="{gear:.1f}" ctrllimited="true" ctrlrange="-1 1"/>')
    lines.append("  </actuator>")
    return "\n".join(lines)


def _sensors(ir: RobotDesignIR) -> str:
    if not ir.sensors:
        return ""

    lines = ["  <sensor>"]
    for sensor in ir.sensors:
        if sensor.sensor_type == "imu":
            lines.append(f'    <accelerometer name="accel_{sensor.mount_link}" site="site_{sensor.mount_link}"/>')
            lines.append(f'    <gyro name="gyro_{sensor.mount_link}" site="site_{sensor.mount_link}"/>')
        elif sensor.sensor_type == "force_torque":
            lines.append(f'    <force name="force_{sensor.mount_link}" site="site_{sensor.mount_link}"/>')
            lines.append(f'    <torque name="torque_{sensor.mount_link}" site="site_{sensor.mount_link}"/>')
    lines.append("  </sensor>")
    return "\n".join(lines)


def _footer() -> str:
    return "</mujoco>"
