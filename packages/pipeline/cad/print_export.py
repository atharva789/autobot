"""
Export functions for 3D printing and CAD interchange.

Supports STEP, STL, and 3MF export formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.pipeline.cad.cadquery_parts import (
    generate_link_geometry,
    CADQUERY_AVAILABLE,
    MockSolid,
)


@dataclass
class ExportResult:
    """Result of robot parts export."""

    parts_exported: int = 0
    step_files: list[str] = field(default_factory=list)
    stl_files: list[str] = field(default_factory=list)
    threemf_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def export_step(solid: Any, output_path: str) -> str:
    """
    Export solid to STEP format.

    Args:
        solid: CadQuery Workplane or MockSolid
        output_path: Output file path

    Returns:
        The output path
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if CADQUERY_AVAILABLE and not isinstance(solid, MockSolid):
        # Real CadQuery export
        solid.val().exportStep(str(path))
    else:
        # Mock export - create placeholder file
        with open(path, "w") as f:
            f.write("ISO-10303-21;\n")
            f.write("HEADER;\n")
            f.write(f"/* Mock STEP file for {path.stem} */\n")
            if isinstance(solid, MockSolid):
                f.write(f"/* Geometry: {solid.geometry_type} */\n")
                f.write(f"/* Dimensions: {solid.dimensions} */\n")
            f.write("ENDSEC;\n")
            f.write("DATA;\n")
            f.write("ENDSEC;\n")
            f.write("END-ISO-10303-21;\n")

    return str(path)


def export_stl(solid: Any, output_path: str) -> str:
    """
    Export solid to STL format.

    Args:
        solid: CadQuery Workplane or MockSolid
        output_path: Output file path

    Returns:
        The output path
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if CADQUERY_AVAILABLE and not isinstance(solid, MockSolid):
        # Real CadQuery export
        solid.val().exportStl(str(path))
    else:
        # Mock export - create minimal ASCII STL
        with open(path, "w") as f:
            name = path.stem
            f.write(f"solid {name}\n")
            # Minimal triangle for valid STL
            f.write("  facet normal 0 0 1\n")
            f.write("    outer loop\n")
            f.write("      vertex 0 0 0\n")
            f.write("      vertex 1 0 0\n")
            f.write("      vertex 0 1 0\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
            f.write(f"endsolid {name}\n")

    return str(path)


def export_3mf(solid: Any, output_path: str) -> str | None:
    """
    Export solid to 3MF format.

    Falls back to STL if 3MF export is not supported.

    Args:
        solid: CadQuery Workplane or MockSolid
        output_path: Output file path

    Returns:
        The actual output path (may be .stl if fallback)
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 3MF requires additional dependencies (OCP)
    # For now, always fall back to STL
    stl_path = path.with_suffix(".stl")
    return export_stl(solid, str(stl_path))


def export_robot_parts(ir: RobotDesignIR, output_dir: str) -> ExportResult:
    """
    Export all custom parts from a robot design.

    Args:
        ir: The robot design intermediate representation
        output_dir: Directory for output files

    Returns:
        ExportResult with list of exported files
    """
    result = ExportResult()
    output_path = Path(output_dir)

    # Create subdirectories
    parts_dir = output_path / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)

    # Export each custom link
    for link in ir.links:
        if not link.is_custom_part:
            continue

        try:
            solid = generate_link_geometry(link)
            name = link.name.replace(" ", "_")

            # Export STEP
            step_path = parts_dir / f"{name}.step"
            export_step(solid, str(step_path))
            result.step_files.append(str(step_path))

            # Export STL
            stl_path = parts_dir / f"{name}.stl"
            export_stl(solid, str(stl_path))
            result.stl_files.append(str(stl_path))

            result.parts_exported += 1

        except Exception as e:
            result.errors.append(f"Failed to export {link.name}: {e}")

    return result
