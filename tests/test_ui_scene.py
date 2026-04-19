"""
TDD tests for Phase 6: UI scene generation.

Tests for generating ui_scene.json from RobotDesignIR.
"""

import json
import pytest
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    Geometry,
    Visual,
    ActuatorSlot,
    Vector3,
)


class TestUISceneCompiler:
    """Tests for UI scene JSON generation."""

    def test_compile_empty_robot(self):
        """Can compile an empty robot to scene JSON."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(name="empty_robot", links=[], joints=[])
        scene = compile_ui_scene(ir)

        assert scene["name"] == "empty_robot"
        assert scene["links"] == []
        assert scene["joints"] == []

    def test_compile_robot_with_links(self):
        """Scene includes all links with positions."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="link_robot",
            links=[
                LinkIR(name="base"),
                LinkIR(name="arm"),
            ],
            joints=[],
        )
        scene = compile_ui_scene(ir)

        assert len(scene["links"]) == 2
        assert scene["links"][0]["name"] == "base"
        assert scene["links"][1]["name"] == "arm"

    def test_compile_robot_with_joints(self):
        """Scene includes all joints with types."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="joint_robot",
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
        scene = compile_ui_scene(ir)

        assert len(scene["joints"]) == 1
        assert scene["joints"][0]["name"] == "j1"
        assert scene["joints"][0]["type"] == "revolute"
        assert scene["joints"][0]["parent"] == "base"
        assert scene["joints"][0]["child"] == "arm"

    def test_compile_link_with_geometry(self):
        """Scene includes link geometry for rendering."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="geom_robot",
            links=[
                LinkIR(
                    name="base",
                    visual=Visual(
                        geometry=Geometry(type="box", size=(0.1, 0.1, 0.02)),
                    ),
                ),
            ],
            joints=[],
        )
        scene = compile_ui_scene(ir)

        link = scene["links"][0]
        assert "geometry" in link
        assert link["geometry"]["type"] == "box"
        assert link["geometry"]["size"] == [0.1, 0.1, 0.02]

    def test_compile_joint_with_actuator(self):
        """Scene includes actuator info for visualization."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="actuated_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                    actuator=ActuatorSlot(
                        actuator_type="servo",
                        max_torque=10.0,
                    ),
                )
            ],
        )
        scene = compile_ui_scene(ir)

        joint = scene["joints"][0]
        assert "actuator" in joint
        assert joint["actuator"]["type"] == "servo"
        assert joint["actuator"]["max_torque"] == 10.0


class TestUISceneRenderModes:
    """Tests for different render mode data."""

    def test_concept_mode(self):
        """Concept mode has minimal data."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="robot",
            links=[LinkIR(name="base")],
            joints=[],
        )
        scene = compile_ui_scene(ir, mode="concept")

        assert scene["render_mode"] == "concept"

    def test_visual_mode_includes_geometry(self):
        """Visual mode includes full geometry."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="robot",
            links=[
                LinkIR(
                    name="base",
                    visual=Visual(
                        geometry=Geometry(type="box", size=(0.1, 0.1, 0.02)),
                        rgba=(1.0, 0.0, 0.0, 1.0),
                    ),
                ),
            ],
            joints=[],
        )
        scene = compile_ui_scene(ir, mode="visual")

        assert scene["render_mode"] == "visual"
        link = scene["links"][0]
        assert "color" in link
        assert link["color"] == [1.0, 0.0, 0.0, 1.0]

    def test_components_mode_includes_custom_flag(self):
        """Components mode shows custom vs vendor parts."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="robot",
            links=[
                LinkIR(name="custom_link", is_custom_part=True),
                LinkIR(name="vendor_link", is_custom_part=False),
            ],
            joints=[],
        )
        scene = compile_ui_scene(ir, mode="components")

        assert scene["render_mode"] == "components"
        assert scene["links"][0]["is_custom"] is True
        assert scene["links"][1]["is_custom"] is False


class TestUISceneJSON:
    """Tests for JSON serialization."""

    def test_scene_is_json_serializable(self):
        """Scene can be serialized to JSON."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="json_robot",
            links=[LinkIR(name="base")],
            joints=[],
        )
        scene = compile_ui_scene(ir)

        # Should not raise
        json_str = json.dumps(scene)
        parsed = json.loads(json_str)
        assert parsed["name"] == "json_robot"

    def test_export_scene_to_file(self, tmp_path):
        """Can export scene to file."""
        from packages.pipeline.ui.scene_compiler import export_ui_scene

        ir = RobotDesignIR(
            name="file_robot",
            links=[LinkIR(name="base")],
            joints=[],
        )
        output_path = tmp_path / "ui_scene.json"
        export_ui_scene(ir, str(output_path))

        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)
        assert data["name"] == "file_robot"


class TestUISceneStats:
    """Tests for scene statistics."""

    def test_scene_includes_stats(self):
        """Scene includes summary statistics."""
        from packages.pipeline.ui.scene_compiler import compile_ui_scene

        ir = RobotDesignIR(
            name="stats_robot",
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
        scene = compile_ui_scene(ir)

        assert "stats" in scene
        assert scene["stats"]["link_count"] == 2
        assert scene["stats"]["joint_count"] == 1
