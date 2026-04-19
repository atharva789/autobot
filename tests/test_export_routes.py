"""
TDD tests for Phase 8: Export routes and functionality.

Tests for API endpoints and export functions.
"""

import os
import pytest

# Enable test mode before importing app
os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
)


@pytest.fixture
def client():
    """Create test client with app."""
    from demo.app import app
    return TestClient(app)


class TestExportEndpoints:
    """Tests for export API endpoints."""

    def test_compile_endpoint_exists(self, client):
        """Compile endpoint exists and returns 404 for missing design."""
        response = client.post("/designs/nonexistent/compile")
        assert response.status_code == 404

    def test_artifacts_endpoint_exists(self, client):
        """Artifacts endpoint exists."""
        response = client.get("/designs/nonexistent/artifacts")
        assert response.status_code == 404

    def test_mujoco_export_endpoint_exists(self, client):
        """MuJoCo export endpoint exists."""
        response = client.post("/designs/nonexistent/export/mujoco")
        assert response.status_code == 404

    def test_print_export_endpoint_exists(self, client):
        """Print export endpoint exists."""
        response = client.post("/designs/nonexistent/export/print")
        assert response.status_code == 404

    def test_procurement_endpoint_exists(self, client):
        """Procurement endpoint exists."""
        response = client.get("/designs/nonexistent/procurement")
        assert response.status_code == 404


class TestDesignToIR:
    """Tests for converting design dict to IR."""

    def test_design_to_ir_basic(self):
        """Can convert basic design to IR."""
        from demo.routes.exports import _design_to_ir

        design = {
            "name": "test_robot",
            "morphology": {
                "links": [{"name": "base"}, {"name": "arm"}],
                "joints": [
                    {
                        "name": "j1",
                        "type": "revolute",
                        "parent": "base",
                        "child": "arm",
                    }
                ],
            },
        }

        ir = _design_to_ir(design)

        assert ir.name == "test_robot"
        assert len(ir.links) == 2
        assert len(ir.joints) == 1
        assert ir.joints[0].joint_type == JointType.REVOLUTE

    def test_design_to_ir_empty(self):
        """Can convert empty design."""
        from demo.routes.exports import _design_to_ir

        design = {"name": "empty_robot"}
        ir = _design_to_ir(design)

        assert ir.name == "empty_robot"
        assert len(ir.links) == 1  # Default base link


class TestCompileDesignLogic:
    """Tests for compile logic."""

    def test_compile_to_mjcf(self):
        """Can compile IR to MJCF."""
        from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf

        ir = RobotDesignIR(
            name="compile_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )

        mjcf = compile_to_mjcf(ir)
        assert "<mujoco" in mjcf
        assert "compile_robot" in mjcf

    def test_compile_to_ui_scene(self):
        """Can compile IR to UI scene."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="scene_robot",
            links=[LinkIR(name="base")],
            joints=[],
        )

        scene = compile_ui_scene(ir)
        assert scene["name"] == "scene_robot"
        assert "links" in scene


class TestExportPrintLogic:
    """Tests for print export logic."""

    def test_export_robot_parts(self, tmp_path):
        """Can export robot parts to files."""
        from packages.pipeline.cad.print_export import export_robot_parts

        ir = RobotDesignIR(
            name="print_robot",
            links=[
                LinkIR(name="base", is_custom_part=True),
                LinkIR(name="arm", is_custom_part=True),
            ],
            joints=[],
        )

        result = export_robot_parts(ir, str(tmp_path))

        assert result.parts_exported >= 1
        assert len(result.step_files) >= 1
        assert len(result.stl_files) >= 1


class TestProcurementLogic:
    """Tests for procurement logic."""

    def test_generate_procurement_report(self):
        """Can generate procurement report."""
        from packages.pipeline.components.slot_resolver import resolve_robot_components
        from packages.pipeline.procurement import generate_procurement_report

        ir = RobotDesignIR(
            name="procure_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )

        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        assert report.total_items >= 0
        assert 0.0 <= report.confidence <= 1.0


class TestExportIntegration:
    """Integration tests for export pipeline."""

    def test_full_export_pipeline(self, tmp_path):
        """Test full export pipeline from design to artifacts."""
        from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf
        from packages.pipeline.ui.scene_compiler import compile_ui_scene
        from packages.pipeline.cad.print_export import export_robot_parts
        from packages.pipeline.components.slot_resolver import resolve_robot_components
        from packages.pipeline.procurement import generate_procurement_report

        # Create a design
        ir = RobotDesignIR(
            name="full_pipeline_robot",
            links=[
                LinkIR(name="base", is_custom_part=True),
                LinkIR(name="arm", is_custom_part=True),
            ],
            joints=[
                JointIR(
                    name="shoulder",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )

        # Compile to MJCF
        mjcf = compile_to_mjcf(ir)
        assert "<mujoco" in mjcf

        # Compile to UI scene
        scene = compile_ui_scene(ir)
        assert scene["stats"]["joint_count"] == 1

        # Export print files
        print_result = export_robot_parts(ir, str(tmp_path))
        assert print_result.parts_exported == 2

        # Generate procurement
        resolution = resolve_robot_components(ir)
        procurement = generate_procurement_report(resolution)
        assert procurement is not None
