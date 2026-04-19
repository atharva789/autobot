"""
Standards compilers for robot descriptions.

These compilers transform the canonical RobotDesignIR into
format-specific robot description files.

Modules:
- mjcf_compiler: Compile IR to MuJoCo MJCF XML
- urdf_compiler: Compile IR to URDF XML (future)
- xacro_compiler: Compile IR to Xacro templates (future)
- ros2_control_compiler: Generate ros2_control config (future)
- ui_scene_compiler: Generate UI scene graph JSON (future)
"""

from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf

__all__ = ["compile_to_mjcf"]
