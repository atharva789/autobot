"""
TDD tests for Phase 3: Real component semantics.

Tests for component resolution, catalog models, and slot resolver.
Acceptance criteria:
- No joint exists without a component stack
- No custom part is silently represented as a vendor part
"""

import pytest
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    ActuatorSlot,
)
from packages.pipeline.components.catalog_models import (
    ComponentCategory,
    VendorPart,
    CustomPart,
    ComponentStack,
    ActuatorSpec,
    TransmissionSpec,
)
from packages.pipeline.components.slot_resolver import (
    resolve_joint_components,
    resolve_link_components,
    resolve_robot_components,
    ComponentResolution,
)


class TestCatalogModels:
    """Tests for component catalog models."""

    def test_component_categories_exist(self):
        """All required component categories are defined."""
        required = [
            "STRUCTURAL", "ACTUATION", "TRANSMISSION", "JOINT_SUPPORT",
            "ELECTRONICS", "SENSORS", "WIRING", "PRINTED_CUSTOM", "MACHINED_CUSTOM"
        ]
        for cat in required:
            assert hasattr(ComponentCategory, cat), f"Missing category: {cat}"

    def test_vendor_part_has_sku(self):
        """Vendor parts must have SKU."""
        part = VendorPart(
            name="Dynamixel XM430-W350",
            sku="902-0135-000",
            vendor="Robotis",
            category=ComponentCategory.ACTUATION,
            unit_price_usd=269.90,
        )
        assert part.sku is not None
        assert part.vendor is not None

    def test_custom_part_marked_as_custom(self):
        """Custom parts are explicitly marked."""
        part = CustomPart(
            name="Motor Mount Bracket",
            category=ComponentCategory.STRUCTURAL,
            manufacturing_method="3d_print",
            material="PLA",
        )
        assert part.is_custom is True
        assert part.manufacturing_method is not None

    def test_component_stack_for_joint(self):
        """Joint component stack has all required layers."""
        stack = ComponentStack(
            actuator=ActuatorSpec(
                part=VendorPart(
                    name="Servo",
                    sku="SRV-001",
                    vendor="Acme",
                    category=ComponentCategory.ACTUATION,
                ),
                max_torque_nm=10.0,
            ),
            transmission=TransmissionSpec(
                type="direct",
                gear_ratio=1.0,
            ),
        )
        assert stack.actuator is not None
        assert stack.transmission is not None


class TestSlotResolver:
    """Tests for component slot resolution."""

    def test_resolve_joint_returns_component_stack(self):
        """Joint resolution returns a component stack."""
        joint = JointIR(
            name="shoulder",
            joint_type=JointType.REVOLUTE,
            parent_link="torso",
            child_link="upper_arm",
            actuator=ActuatorSlot(
                actuator_type="servo",
                max_torque=20.0,
            ),
        )
        resolution = resolve_joint_components(joint)
        assert isinstance(resolution, ComponentResolution)
        assert resolution.component_stack is not None

    def test_resolve_joint_without_actuator_slot(self):
        """Unactuated joint still gets resolution (passive joint)."""
        joint = JointIR(
            name="passive_joint",
            joint_type=JointType.REVOLUTE,
            parent_link="a",
            child_link="b",
            # No actuator
        )
        resolution = resolve_joint_components(joint)
        assert resolution is not None
        assert resolution.is_passive is True

    def test_resolve_link_identifies_custom_parts(self):
        """Link resolution identifies custom vs vendor parts."""
        link = LinkIR(
            name="custom_bracket",
            is_custom_part=True,
        )
        resolution = resolve_link_components(link)
        assert resolution.has_custom_parts is True
        assert len(resolution.custom_parts) > 0

    def test_resolve_link_with_vendor_sku(self):
        """Link with vendor SKU resolves to vendor part."""
        link = LinkIR(
            name="motor_mount",
            vendor_sku="ABC-123",
        )
        resolution = resolve_link_components(link)
        assert resolution.has_vendor_parts is True

    def test_resolve_robot_all_joints_have_stacks(self):
        """Full robot resolution ensures all joints have component stacks."""
        ir = RobotDesignIR(
            name="test_robot",
            links=[
                LinkIR(name="base"),
                LinkIR(name="link1"),
                LinkIR(name="link2"),
            ],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link1",
                    actuator=ActuatorSlot(actuator_type="motor"),
                ),
                JointIR(
                    name="j2",
                    joint_type=JointType.REVOLUTE,
                    parent_link="link1",
                    child_link="link2",
                ),
            ],
        )
        resolution = resolve_robot_components(ir)
        assert len(resolution.joint_resolutions) == 2
        for joint_name, joint_res in resolution.joint_resolutions.items():
            assert joint_res is not None, f"Joint {joint_name} has no resolution"


class TestComponentResolutionValidation:
    """Tests for validation of component resolution."""

    def test_unresolved_parts_are_flagged(self):
        """Parts that couldn't be resolved are flagged."""
        joint = JointIR(
            name="exotic_joint",
            joint_type=JointType.REVOLUTE,
            parent_link="a",
            child_link="b",
            actuator=ActuatorSlot(
                actuator_type="hydraulic",  # Less common, may not resolve
                max_torque=500.0,
            ),
        )
        resolution = resolve_joint_components(joint)
        # Either resolves or flags as unresolved
        assert resolution.is_resolved or len(resolution.unresolved_items) > 0

    def test_custom_parts_never_have_vendor_sku(self):
        """Custom parts don't accidentally get vendor SKUs."""
        link = LinkIR(
            name="custom_link",
            is_custom_part=True,
        )
        resolution = resolve_link_components(link)
        for part in resolution.custom_parts:
            assert not hasattr(part, 'sku') or part.sku is None


class TestComponentStackCompleteness:
    """Tests ensuring component stacks are complete."""

    def test_actuated_joint_has_actuator_and_transmission(self):
        """Actuated joints must have both actuator and transmission."""
        joint = JointIR(
            name="actuated",
            joint_type=JointType.REVOLUTE,
            parent_link="a",
            child_link="b",
            actuator=ActuatorSlot(
                actuator_type="servo",
                max_torque=10.0,
            ),
        )
        resolution = resolve_joint_components(joint)
        stack = resolution.component_stack
        assert stack is not None
        assert stack.actuator is not None
        assert stack.transmission is not None

    def test_resolution_includes_fasteners(self):
        """Joint resolution includes mounting hardware."""
        joint = JointIR(
            name="j1",
            joint_type=JointType.REVOLUTE,
            parent_link="a",
            child_link="b",
            actuator=ActuatorSlot(actuator_type="servo"),
        )
        resolution = resolve_joint_components(joint)
        # Should include fasteners/mounting hardware
        assert resolution.includes_fasteners or resolution.fastener_estimate > 0
