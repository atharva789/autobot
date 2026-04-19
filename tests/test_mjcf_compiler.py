"""
TDD tests for Phase 2: MJCF Compiler.

Tests that the compiler produces valid, parseable MJCF from IR.
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
from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf


class TestMJCFCompilerOutput:
    """Tests for MJCF compiler output format."""

    def test_output_starts_with_mujoco_tag(self):
        """Output must start with <mujoco> tag."""
        ir = RobotDesignIR(name="test", links=[LinkIR(name="base")])
        mjcf = compile_to_mjcf(ir)
        assert mjcf.startswith('<mujoco model="test">')

    def test_output_ends_with_mujoco_close(self):
        """Output must end with </mujoco>."""
        ir = RobotDesignIR(name="test", links=[LinkIR(name="base")])
        mjcf = compile_to_mjcf(ir)
        assert mjcf.strip().endswith("</mujoco>")

    def test_includes_worldbody(self):
        """Output includes worldbody section."""
        ir = RobotDesignIR(name="test", links=[LinkIR(name="base")])
        mjcf = compile_to_mjcf(ir)
        assert "<worldbody>" in mjcf
        assert "</worldbody>" in mjcf

    def test_includes_floor_geom(self):
        """Output includes floor geometry for simulation."""
        ir = RobotDesignIR(name="test", links=[LinkIR(name="base")])
        mjcf = compile_to_mjcf(ir)
        assert 'name="floor"' in mjcf
        assert 'type="plane"' in mjcf


class TestMJCFCompilerLinks:
    """Tests for link compilation."""

    def test_link_becomes_body(self):
        """Each link becomes a <body> element."""
        ir = RobotDesignIR(
            name="test",
            links=[LinkIR(name="torso"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="shoulder",
                    joint_type=JointType.REVOLUTE,
                    parent_link="torso",
                    child_link="arm",
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert '<body name="torso">' in mjcf
        assert '<body name="arm">' in mjcf

    def test_link_with_inertial(self):
        """Link inertial is compiled to inertial element."""
        ir = RobotDesignIR(
            name="test",
            links=[
                LinkIR(
                    name="heavy",
                    inertial=Inertial(mass=5.0, origin=Vector3(0, 0, 0.1)),
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert "inertial" in mjcf
        assert 'mass="5.0' in mjcf


class TestMJCFCompilerJoints:
    """Tests for joint compilation."""

    def test_revolute_joint_becomes_hinge(self):
        """Revolute joint compiles to hinge."""
        ir = RobotDesignIR(
            name="test",
            links=[LinkIR(name="base"), LinkIR(name="link1")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link1",
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert '<joint name="j1" type="hinge"' in mjcf

    def test_prismatic_joint_becomes_slide(self):
        """Prismatic joint compiles to slide."""
        ir = RobotDesignIR(
            name="test",
            links=[LinkIR(name="base"), LinkIR(name="link1")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.PRISMATIC,
                    parent_link="base",
                    child_link="link1",
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert '<joint name="j1" type="slide"' in mjcf

    def test_joint_limits_compiled(self):
        """Joint limits are included in output."""
        ir = RobotDesignIR(
            name="test",
            links=[LinkIR(name="base"), LinkIR(name="link1")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link1",
                    limits=JointLimits(lower=-1.5, upper=1.5),
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert 'range="-1.5' in mjcf or "range='-1.5" in mjcf


class TestMJCFCompilerActuators:
    """Tests for actuator compilation."""

    def test_actuated_joint_has_motor(self):
        """Joints with actuators get motor elements."""
        ir = RobotDesignIR(
            name="test",
            links=[LinkIR(name="base"), LinkIR(name="link1")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link1",
                    actuator=ActuatorSlot(actuator_type="motor", gear_ratio=100.0),
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert "<actuator>" in mjcf
        assert 'motor' in mjcf
        assert 'joint="j1"' in mjcf

    def test_no_actuator_section_if_no_actuators(self):
        """No actuator section if no joints have actuators."""
        ir = RobotDesignIR(
            name="test",
            links=[LinkIR(name="base"), LinkIR(name="link1")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link1",
                    # No actuator
                )
            ],
        )
        mjcf = compile_to_mjcf(ir)
        assert "<actuator>" not in mjcf


class TestMJCFCompilerValidation:
    """Tests for compiler validation."""

    def test_invalid_ir_raises_error(self):
        """Compiler raises error for invalid IR."""
        ir = RobotDesignIR(
            name="invalid",
            links=[LinkIR(name="orphan")],
            joints=[
                JointIR(
                    name="bad",
                    joint_type=JointType.REVOLUTE,
                    parent_link="missing",
                    child_link="orphan",
                )
            ],
        )
        with pytest.raises(ValueError, match="validation failed"):
            compile_to_mjcf(ir)
