"""
Slot resolver - maps IR joints/links to concrete components.

This module resolves abstract actuator slots and link definitions
to concrete purchasable or manufacturable parts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.pipeline.components.catalog_models import (
    ComponentCategory,
    VendorPart,
    CustomPart,
    ComponentStack,
    ActuatorSpec,
    TransmissionSpec,
    LinkComponents,
)

if TYPE_CHECKING:
    from packages.pipeline.ir.design_ir import RobotDesignIR, JointIR, LinkIR


# Sample actuator catalog (would be loaded from database/API in production)
ACTUATOR_CATALOG: dict[str, VendorPart] = {
    "servo_small": VendorPart(
        name="Dynamixel XL430-W250",
        sku="902-0135-000",
        vendor="Robotis",
        category=ComponentCategory.ACTUATION,
        unit_price_usd=49.90,
    ),
    "servo_medium": VendorPart(
        name="Dynamixel XM430-W350",
        sku="902-0188-000",
        vendor="Robotis",
        category=ComponentCategory.ACTUATION,
        unit_price_usd=269.90,
    ),
    "servo_large": VendorPart(
        name="Dynamixel XM540-W270",
        sku="902-0189-000",
        vendor="Robotis",
        category=ComponentCategory.ACTUATION,
        unit_price_usd=299.00,
    ),
    "motor_bldc": VendorPart(
        name="T-Motor U8 KV85",
        sku="U8-KV85",
        vendor="T-Motor",
        category=ComponentCategory.ACTUATION,
        unit_price_usd=189.00,
    ),
}


@dataclass
class ComponentResolution:
    """Result of resolving a joint or link to components."""
    component_stack: ComponentStack | None = None
    link_components: LinkComponents | None = None
    is_passive: bool = False
    is_resolved: bool = True
    unresolved_items: list[str] = field(default_factory=list)
    includes_fasteners: bool = False
    fastener_estimate: int = 0
    custom_parts: list[CustomPart] = field(default_factory=list)
    vendor_parts: list[VendorPart] = field(default_factory=list)

    @property
    def has_custom_parts(self) -> bool:
        return len(self.custom_parts) > 0

    @property
    def has_vendor_parts(self) -> bool:
        return len(self.vendor_parts) > 0


@dataclass
class RobotComponentResolution:
    """Full component resolution for a robot."""
    joint_resolutions: dict[str, ComponentResolution] = field(default_factory=dict)
    link_resolutions: dict[str, ComponentResolution] = field(default_factory=dict)

    @property
    def total_unresolved(self) -> int:
        count = 0
        for res in self.joint_resolutions.values():
            count += len(res.unresolved_items)
        for res in self.link_resolutions.values():
            count += len(res.unresolved_items)
        return count

    @property
    def all_custom_parts(self) -> list[CustomPart]:
        parts = []
        for res in self.joint_resolutions.values():
            parts.extend(res.custom_parts)
        for res in self.link_resolutions.values():
            parts.extend(res.custom_parts)
        return parts


def resolve_joint_components(joint: "JointIR") -> ComponentResolution:
    """
    Resolve a joint to its component stack.

    Args:
        joint: The joint IR to resolve

    Returns:
        ComponentResolution with component stack or unresolved items
    """
    resolution = ComponentResolution()

    # Passive joint (no actuator)
    if joint.actuator is None:
        resolution.is_passive = True
        resolution.fastener_estimate = 4  # Basic mounting hardware
        resolution.includes_fasteners = True
        return resolution

    # Find appropriate actuator
    actuator_part = _select_actuator(joint)
    if actuator_part is None:
        resolution.is_resolved = False
        resolution.unresolved_items.append(
            f"No matching actuator for {joint.actuator.actuator_type} "
            f"with {joint.actuator.max_torque}Nm"
        )
        return resolution

    resolution.vendor_parts.append(actuator_part)

    # Build component stack
    actuator_spec = ActuatorSpec(
        part=actuator_part,
        max_torque_nm=joint.actuator.max_torque,
        gear_ratio=joint.actuator.gear_ratio,
    )

    transmission_spec = TransmissionSpec(
        type="direct" if joint.actuator.gear_ratio == 1.0 else "gear",
        gear_ratio=joint.actuator.gear_ratio,
    )

    # Add custom mount bracket
    mount_bracket = CustomPart(
        name=f"{joint.name}_mount",
        category=ComponentCategory.STRUCTURAL,
        manufacturing_method="3d_print",
        material="PLA",
        estimated_cost_usd=5.0,
    )
    resolution.custom_parts.append(mount_bracket)

    resolution.component_stack = ComponentStack(
        actuator=actuator_spec,
        transmission=transmission_spec,
        custom_mounts=[mount_bracket],
    )

    resolution.fastener_estimate = 8  # Screws for mounting
    resolution.includes_fasteners = True
    resolution.is_resolved = True

    return resolution


def _select_actuator(joint: "JointIR") -> VendorPart | None:
    """Select an appropriate actuator from catalog."""
    if joint.actuator is None:
        return None

    torque = joint.actuator.max_torque
    atype = joint.actuator.actuator_type

    # Match by type and torque
    if atype in ("servo", "motor"):
        if torque <= 5.0:
            return ACTUATOR_CATALOG.get("servo_small")
        elif torque <= 15.0:
            return ACTUATOR_CATALOG.get("servo_medium")
        elif torque <= 30.0:
            return ACTUATOR_CATALOG.get("servo_large")
        else:
            return ACTUATOR_CATALOG.get("motor_bldc")
    elif atype == "hydraulic":
        # Hydraulic not in catalog yet
        return None

    return ACTUATOR_CATALOG.get("servo_medium")


def resolve_link_components(link: "LinkIR") -> ComponentResolution:
    """
    Resolve a link to its component list.

    Args:
        link: The link IR to resolve

    Returns:
        ComponentResolution with link components
    """
    resolution = ComponentResolution()
    link_comps = LinkComponents()

    if link.is_custom_part:
        # Create a custom structural part
        custom = CustomPart(
            name=link.name,
            category=ComponentCategory.STRUCTURAL,
            manufacturing_method="3d_print",
            material="PLA",
            estimated_cost_usd=10.0,
        )
        link_comps.structural_parts.append(custom)
        resolution.custom_parts.append(custom)
    elif link.vendor_sku:
        # Resolve vendor SKU (would lookup in real catalog)
        vendor = VendorPart(
            name=link.name,
            sku=link.vendor_sku,
            vendor="Unknown",
            category=ComponentCategory.STRUCTURAL,
        )
        link_comps.structural_parts.append(vendor)
        resolution.vendor_parts.append(vendor)
    else:
        # Default: assume custom 3D printed part
        custom = CustomPart(
            name=f"{link.name}_body",
            category=ComponentCategory.PRINTED_CUSTOM,
            manufacturing_method="3d_print",
            material="PLA",
            estimated_cost_usd=8.0,
        )
        link_comps.structural_parts.append(custom)
        resolution.custom_parts.append(custom)

    resolution.link_components = link_comps
    return resolution


def resolve_robot_components(ir: "RobotDesignIR") -> RobotComponentResolution:
    """
    Resolve all components for a complete robot.

    Args:
        ir: The robot design IR

    Returns:
        RobotComponentResolution with all joint and link resolutions
    """
    result = RobotComponentResolution()

    for joint in ir.joints:
        result.joint_resolutions[joint.name] = resolve_joint_components(joint)

    for link in ir.links:
        result.link_resolutions[link.name] = resolve_link_components(link)

    return result
