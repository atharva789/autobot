from __future__ import annotations

from packages.pipeline.types import MorphologyParams


def validate_mjcf(p: MorphologyParams) -> bool:
    """Return True only if params fall within safe simulation ranges for MJCF generation."""
    if p.torso_length < 0.15 or p.torso_length > 0.65:
        return False
    if p.arm_length < 0.25 or p.arm_length > 0.85:
        return False
    if p.leg_length < 0.35 or p.leg_length > 1.05:
        return False
    if p.num_legs not in (2, 4):
        return False
    if p.num_arms not in (0, 1, 2):
        return False
    return True


def build_mjcf(p: MorphologyParams) -> str:
    """Build a MuJoCo MJCF XML string from MorphologyParams.

    Note: This produces MJCF format (MuJoCo's native XML), not URDF.
    For URDF output, use compilers/urdf_compiler.py (Phase 2).
    """
    parts = [_header(p), _worldbody(p), _actuators(p), _footer()]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _header(p: MorphologyParams) -> str:
    return (
        f'<mujoco model="automorph">\n'
        f'  <option timestep="0.002" gravity="0 0 -9.81"/>\n'
        f'  <default>\n'
        f'    <joint damping="{p.joint_damping}" stiffness="{p.joint_stiffness}"/>\n'
        f'    <geom friction="{p.friction} 0.005 0.0001"/>\n'
        f'  </default>\n'
        f'  <asset>\n'
        f'    <texture type="skybox" builtin="gradient" rgb1=".3 .5 .7"'
        f' rgb2="0 0 0" width="32" height="512"/>\n'
        f'    <texture name="texplane" type="2d" builtin="checker"'
        f' rgb1=".2 .3 .4" rgb2=".1 .2 .3" width="512" height="512" mark="cross"/>\n'
        f'    <material name="matplane" reflectance="0.3" texture="texplane"'
        f' texrepeat="1 1" texuniform="true"/>\n'
        f'  </asset>'
    )


def _worldbody(p: MorphologyParams) -> str:
    lines: list[str] = [
        "  <worldbody>",
        '    <geom name="floor" size="0 0 .05" type="plane" material="matplane"/>',
        '    <light pos="0 0 3" dir="0 0 -1" diffuse=".8 .8 .8"/>',
        f'    <body name="torso" pos="0 0 {p.leg_length + 0.1:.4f}">',
        "      <freejoint/>",
        f'      <geom type="capsule" size="0.06" fromto="0 0 0 0 0 {p.torso_length:.4f}"/>',
    ]

    if p.spine_dof > 0:
        lines.append('      <joint name="spine" type="ball" range="-30 30"/>')

    for side, sign in [("left", -1), ("right", 1)][:p.num_arms]:
        lines.extend(_arm_links(p, side, sign))

    for side, sign in [("left", -1), ("right", 1)]:
        lines.extend(_leg_links(p, side, sign))

    lines.append("    </body>")
    lines.append("  </worldbody>")
    return "\n".join(lines)


def _arm_links(p: MorphologyParams, side: str, sign: int) -> list[str]:
    if p.num_arms == 0:
        return []

    half = p.arm_length / max(p.arm_dof - 1, 1)
    y_off = sign * 0.12
    lines: list[str] = [
        f'      <body name="{side}_shoulder" pos="0 {y_off:.4f} {p.torso_length * 0.9:.4f}">',
        f'        <geom type="capsule" size="0.04" fromto="0 0 0 0 {sign * half:.4f} 0"/>',
        f'        <joint name="{side}_shoulder_x" type="hinge" axis="1 0 0" range="-90 90"/>',
        f'        <joint name="{side}_shoulder_y" type="hinge" axis="0 1 0" range="-90 90"/>',
        f'        <joint name="{side}_shoulder_z" type="hinge" axis="0 0 1" range="-90 90"/>',
    ]

    if p.arm_dof >= 5:
        lines += [
            f'        <body name="{side}_elbow" pos="0 {sign * half:.4f} 0">',
            f'          <geom type="capsule" size="0.035" fromto="0 0 0 0 {sign * half:.4f} 0"/>',
            f'          <joint name="{side}_elbow" type="hinge" axis="1 0 0" range="-140 0"/>',
            "        </body>",
        ]

    lines.append("      </body>")
    return lines


def _leg_links(p: MorphologyParams, side: str, sign: int) -> list[str]:
    half = p.leg_length / 2.0
    y_off = sign * 0.1
    return [
        f'      <body name="{side}_hip" pos="0 {y_off:.4f} 0">',
        f'        <geom type="capsule" size="0.05" fromto="0 0 0 0 0 -{half:.4f}"/>',
        f'        <joint name="{side}_hip_x" type="hinge" axis="1 0 0" range="-60 60"/>',
        f'        <joint name="{side}_hip_y" type="hinge" axis="0 1 0" range="-120 20"/>',
        f'        <joint name="{side}_hip_z" type="hinge" axis="0 0 1" range="-40 40"/>',
        f'        <body name="{side}_knee" pos="0 0 -{half:.4f}">',
        f'          <geom type="capsule" size="0.04" fromto="0 0 0 0 0 -{half:.4f}"/>',
        f'          <joint name="{side}_knee" type="hinge" axis="1 0 0" range="-150 0"/>',
        f'          <body name="{side}_foot" pos="0 0 -{half:.4f}">',
        f'            <geom type="sphere" size="0.06"/>',
        "          </body>",
        "        </body>",
        "      </body>",
    ]


def _actuators(p: MorphologyParams) -> str:
    lines: list[str] = ["  <actuator>"]

    for side in ("left", "right"):
        if p.num_arms > 0:
            for ax in ("x", "y", "z"):
                lines.append(
                    f'    <motor name="{side}_shoulder_{ax}" joint="{side}_shoulder_{ax}"'
                    f' gear="100" ctrllimited="true" ctrlrange="-1 1"/>'
                )
            if p.arm_dof >= 5:
                lines.append(
                    f'    <motor name="{side}_elbow" joint="{side}_elbow"'
                    f' gear="80" ctrllimited="true" ctrlrange="-1 1"/>'
                )
        for jt in ("hip_x", "hip_y", "hip_z", "knee"):
            lines.append(
                f'    <motor name="{side}_{jt}" joint="{side}_{jt}"'
                f' gear="120" ctrllimited="true" ctrlrange="-1 1"/>'
            )

    lines.append("  </actuator>")
    return "\n".join(lines)


def _footer() -> str:
    return "</mujoco>"


# Backwards-compatible aliases (deprecated - use build_mjcf/validate_mjcf)
build_urdf = build_mjcf
validate_urdf = validate_mjcf
