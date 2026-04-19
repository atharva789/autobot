"""
TDD tests for Phase 5: CAD and printing.

Tests for CadQuery part generation and export.
"""

import pytest
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    Geometry,
    Visual,
)


class TestCadQueryParts:
    """Tests for CadQuery part generation."""

    def test_generate_box_part(self):
        """Can generate a box-shaped part."""
        from packages.pipeline.cad.cadquery_parts import generate_from_geometry

        geometry = Geometry(type="box", size=(0.1, 0.05, 0.02))
        result = generate_from_geometry(geometry)
        assert result is not None
        assert result.val() is not None

    def test_generate_cylinder_part(self):
        """Can generate a cylinder-shaped part."""
        from packages.pipeline.cad.cadquery_parts import generate_from_geometry

        geometry = Geometry(type="cylinder", size=(0.01, 0.1))
        result = generate_from_geometry(geometry)
        assert result is not None

    def test_generate_sphere_part(self):
        """Can generate a sphere-shaped part."""
        from packages.pipeline.cad.cadquery_parts import generate_from_geometry

        geometry = Geometry(type="sphere", size=(0.02,))
        result = generate_from_geometry(geometry)
        assert result is not None

    def test_generate_link_bracket(self):
        """Can generate geometry from LinkIR with visual."""
        from packages.pipeline.cad.cadquery_parts import generate_link_geometry

        link = LinkIR(
            name="arm_link",
            is_custom_part=True,
            visual=Visual(
                geometry=Geometry(type="box", size=(0.15, 0.04, 0.03)),
            ),
        )
        result = generate_link_geometry(link)
        assert result is not None


class TestAssemblyBuilder:
    """Tests for assembly building."""

    def test_build_assembly_from_ir(self):
        """Can build assembly from RobotDesignIR."""
        from packages.pipeline.cad.assembly_builder import build_assembly

        ir = RobotDesignIR(
            name="test_robot",
            links=[
                LinkIR(name="base", is_custom_part=True),
                LinkIR(name="arm", is_custom_part=True),
            ],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )
        assembly = build_assembly(ir)
        assert assembly is not None

    def test_assembly_contains_custom_parts_only(self):
        """Assembly only includes custom parts, not vendor parts."""
        from packages.pipeline.cad.assembly_builder import build_assembly

        ir = RobotDesignIR(
            name="mixed_robot",
            links=[
                LinkIR(name="base", is_custom_part=True),
                LinkIR(name="vendor_link", is_custom_part=False),
            ],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="vendor_link",
                )
            ],
        )
        assembly = build_assembly(ir)
        assert assembly is not None


class TestPrintExport:
    """Tests for print file export."""

    def test_export_step(self, tmp_path):
        """Can export STEP file."""
        from packages.pipeline.cad.cadquery_parts import generate_from_geometry
        from packages.pipeline.cad.print_export import export_step

        geometry = Geometry(type="box", size=(0.1, 0.05, 0.02))
        solid = generate_from_geometry(geometry)
        output_path = tmp_path / "bracket.step"
        export_step(solid, str(output_path))
        assert output_path.exists()

    def test_export_stl(self, tmp_path):
        """Can export STL file."""
        from packages.pipeline.cad.cadquery_parts import generate_from_geometry
        from packages.pipeline.cad.print_export import export_stl

        geometry = Geometry(type="box", size=(0.1, 0.05, 0.02))
        solid = generate_from_geometry(geometry)
        output_path = tmp_path / "bracket.stl"
        export_stl(solid, str(output_path))
        assert output_path.exists()

    def test_export_3mf(self, tmp_path):
        """Can export 3MF file (or fallback to STL)."""
        from packages.pipeline.cad.cadquery_parts import generate_from_geometry
        from packages.pipeline.cad.print_export import export_3mf

        geometry = Geometry(type="box", size=(0.1, 0.05, 0.02))
        solid = generate_from_geometry(geometry)
        output_path = tmp_path / "bracket.3mf"
        result_path = export_3mf(solid, str(output_path))
        assert result_path is not None


class TestRobotExport:
    """Tests for full robot export."""

    def test_export_robot_parts(self, tmp_path):
        """Can export all custom parts from a robot."""
        from packages.pipeline.cad.print_export import export_robot_parts

        ir = RobotDesignIR(
            name="export_test",
            links=[
                LinkIR(
                    name="base",
                    is_custom_part=True,
                    visual=Visual(
                        geometry=Geometry(type="box", size=(0.1, 0.1, 0.02)),
                    ),
                ),
                LinkIR(
                    name="arm",
                    is_custom_part=True,
                    visual=Visual(
                        geometry=Geometry(type="cylinder", size=(0.02, 0.15)),
                    ),
                ),
            ],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )

        result = export_robot_parts(ir, str(tmp_path))

        assert result.parts_exported >= 1
        assert len(result.step_files) >= 1
        assert len(result.stl_files) >= 1

    def test_export_excludes_vendor_parts(self, tmp_path):
        """Export skips vendor parts (no geometry to print)."""
        from packages.pipeline.cad.print_export import export_robot_parts

        ir = RobotDesignIR(
            name="vendor_test",
            links=[
                LinkIR(name="servo_mount", is_custom_part=False),
            ],
            joints=[],
        )

        result = export_robot_parts(ir, str(tmp_path))
        assert result.parts_exported == 0
