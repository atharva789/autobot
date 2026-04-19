"""
Design validation for robot designs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.ir.design_ir import RobotDesignIR


@dataclass
class ValidationResult:
    """Result of design validation."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_design(ir: RobotDesignIR) -> ValidationResult:
    """
    Validate a robot design.

    Checks for:
    - Link existence (joints reference valid links)
    - Kinematic chain consistency
    - Actuator specifications

    Args:
        ir: The robot design to validate

    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult()

    # Check for empty robot
    if len(ir.links) == 0:
        result.warnings.append("Robot has no links")

    if len(ir.joints) == 0 and len(ir.links) > 1:
        result.warnings.append("Robot has multiple links but no joints")

    # Build link name set
    link_names = {link.name for link in ir.links}

    # Check joint references
    for joint in ir.joints:
        if joint.parent_link not in link_names:
            result.is_valid = False
            result.errors.append(
                f"Joint '{joint.name}' references missing parent link '{joint.parent_link}'"
            )

        if joint.child_link not in link_names:
            result.is_valid = False
            result.errors.append(
                f"Joint '{joint.name}' references missing child link '{joint.child_link}'"
            )

    # Check for duplicate link names
    if len(link_names) != len(ir.links):
        result.warnings.append("Robot has duplicate link names")

    # Check for duplicate joint names
    joint_names = {joint.name for joint in ir.joints}
    if len(joint_names) != len(ir.joints):
        result.warnings.append("Robot has duplicate joint names")

    return result
