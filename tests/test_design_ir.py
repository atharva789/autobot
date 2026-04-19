"""
TDD tests for Phase 1: Canonical IR.

Tests for RobotDesignIR, LinkIR, JointIR, and IR validation.
"""

import pytest
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    Vector3,
    Inertial,
    Geometry,
    Visual,
    ActuatorSlot,
    JointLimits,
)


class TestRobotDesignIR:
    """Tests for RobotDesignIR creation and validation."""

    def test_create_empty_ir(self):
        """Can create an empty IR."""
        ir = RobotDesignIR(name="test_robot")
        assert ir.name == "test_robot"
        assert len(ir.links) == 0
        assert len(ir.joints) == 0

    def test_create_simple_robot(self):
        """Can create a simple 2-link robot."""
        ir = RobotDesignIR(
            name="simple_arm",
            links=[
                LinkIR(name="base"),
                LinkIR(name="link1"),
            ],
            joints=[
                JointIR(
                    name="joint1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link1",
                )
            ],
        )
        assert len(ir.links) == 2
        assert len(ir.joints) == 1
        assert ir.get_link("base") is not None
        assert ir.get_joint("joint1") is not None

    def test_validation_passes_for_valid_ir(self):
        """Validation returns empty list for valid IR."""
        ir = RobotDesignIR(
            name="valid_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="shoulder",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )
        errors = ir.validate()
        assert errors == []

    def test_validation_fails_for_missing_parent_link(self):
        """Validation catches missing parent link."""
        ir = RobotDesignIR(
            name="invalid_robot",
            links=[LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="joint1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="nonexistent",
                    child_link="arm",
                )
            ],
        )
        errors = ir.validate()
        assert len(errors) == 1
        assert "parent_link" in errors[0]

    def test_validation_fails_for_missing_child_link(self):
        """Validation catches missing child link."""
        ir = RobotDesignIR(
            name="invalid_robot",
            links=[LinkIR(name="base")],
            joints=[
                JointIR(
                    name="joint1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="nonexistent",
                )
            ],
        )
        errors = ir.validate()
        assert len(errors) == 1
        assert "child_link" in errors[0]

    def test_root_link_is_found(self):
        """Root link (not child of any joint) is identified."""
        ir = RobotDesignIR(
            name="chain",
            links=[
                LinkIR(name="base"),
                LinkIR(name="link1"),
                LinkIR(name="link2"),
            ],
            joints=[
                JointIR(name="j1", joint_type=JointType.REVOLUTE, parent_link="base", child_link="link1"),
                JointIR(name="j2", joint_type=JointType.REVOLUTE, parent_link="link1", child_link="link2"),
            ],
        )
        root = ir.root_link()
        assert root is not None
        assert root.name == "base"


class TestLinkIR:
    """Tests for LinkIR."""

    def test_link_with_inertial(self):
        """Link can have inertial properties."""
        link = LinkIR(
            name="heavy_link",
            inertial=Inertial(mass=5.0, origin=Vector3(0, 0, 0.1)),
        )
        assert link.inertial is not None
        assert link.inertial.mass == 5.0

    def test_link_with_geometry(self):
        """Link can have visual geometry."""
        link = LinkIR(
            name="visible_link",
            visual=Visual(
                geometry=Geometry(type="box", size=(0.1, 0.1, 0.2)),
            ),
        )
        assert link.visual is not None
        assert link.visual.geometry.type == "box"

    def test_custom_part_flag(self):
        """Link can be marked as custom part."""
        link = LinkIR(name="custom_bracket", is_custom_part=True)
        assert link.is_custom_part is True

    def test_vendor_sku(self):
        """Link can have vendor SKU."""
        link = LinkIR(name="motor_mount", vendor_sku="ABC-123")
        assert link.vendor_sku == "ABC-123"


class TestJointIR:
    """Tests for JointIR."""

    def test_joint_types(self):
        """All joint types can be created."""
        for jtype in JointType:
            joint = JointIR(
                name=f"joint_{jtype.value}",
                joint_type=jtype,
                parent_link="p",
                child_link="c",
            )
            assert joint.joint_type == jtype

    def test_joint_with_limits(self):
        """Joint can have limits."""
        joint = JointIR(
            name="limited_joint",
            joint_type=JointType.REVOLUTE,
            parent_link="p",
            child_link="c",
            limits=JointLimits(lower=-1.57, upper=1.57, effort=50.0),
        )
        assert joint.limits is not None
        assert joint.limits.lower == -1.57
        assert joint.limits.upper == 1.57

    def test_joint_with_actuator(self):
        """Joint can have actuator slot."""
        joint = JointIR(
            name="actuated_joint",
            joint_type=JointType.REVOLUTE,
            parent_link="p",
            child_link="c",
            actuator=ActuatorSlot(
                actuator_type="servo",
                max_torque=20.0,
                vendor_sku="DYNAMIXEL-XM430",
            ),
        )
        assert joint.actuator is not None
        assert joint.actuator.actuator_type == "servo"
        assert joint.actuator.vendor_sku == "DYNAMIXEL-XM430"

    def test_joint_axis(self):
        """Joint has configurable axis."""
        joint = JointIR(
            name="y_axis_joint",
            joint_type=JointType.REVOLUTE,
            parent_link="p",
            child_link="c",
            axis=Vector3(0, 1, 0),
        )
        assert joint.axis.y == 1.0
        assert joint.axis.x == 0.0
