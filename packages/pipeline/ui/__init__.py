"""
UI scene generation for robot visualization.

This package compiles RobotDesignIR to JSON scene graphs
for frontend rendering.
"""

from packages.pipeline.ui.scene_compiler import (
    compile_ui_scene,
    export_ui_scene,
)

__all__ = [
    "compile_ui_scene",
    "export_ui_scene",
]
