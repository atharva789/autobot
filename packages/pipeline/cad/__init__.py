"""
CAD generation and export for robot parts.

This package handles CadQuery-based part generation and
export to various manufacturing formats (STEP, STL, 3MF).
"""

from packages.pipeline.cad.cadquery_parts import (
    generate_from_geometry,
    generate_link_geometry,
    MockSolid,
    CADQUERY_AVAILABLE,
)
from packages.pipeline.cad.assembly_builder import (
    build_assembly,
    RobotAssembly,
    AssemblyPart,
)
from packages.pipeline.cad.print_export import (
    export_step,
    export_stl,
    export_3mf,
    export_robot_parts,
    ExportResult,
)

__all__ = [
    "generate_from_geometry",
    "generate_link_geometry",
    "MockSolid",
    "CADQUERY_AVAILABLE",
    "build_assembly",
    "RobotAssembly",
    "AssemblyPart",
    "export_step",
    "export_stl",
    "export_3mf",
    "export_robot_parts",
    "ExportResult",
]
