"""
Assembly builder for robot parts.

Builds a complete assembly from RobotDesignIR,
including only custom parts (vendor parts are references).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.pipeline.cad.cadquery_parts import (
    generate_link_geometry,
    CADQUERY_AVAILABLE,
)

if CADQUERY_AVAILABLE:
    import cadquery as cq


@dataclass
class AssemblyPart:
    """A part in the assembly."""

    name: str
    solid: Any
    is_custom: bool = True
    position: tuple[float, float, float] = (0, 0, 0)
    rotation: tuple[float, float, float] = (0, 0, 0)


@dataclass
class RobotAssembly:
    """Complete robot assembly."""

    name: str
    parts: list[AssemblyPart] = field(default_factory=list)
    _assembly: Any = None

    def add_part(self, part: AssemblyPart) -> None:
        """Add a part to the assembly."""
        self.parts.append(part)

    def get_custom_parts(self) -> list[AssemblyPart]:
        """Get only custom (printable) parts."""
        return [p for p in self.parts if p.is_custom]


def build_assembly(ir: RobotDesignIR) -> RobotAssembly:
    """
    Build assembly from RobotDesignIR.

    Only custom parts are included with geometry.
    Vendor parts are tracked but have no printable geometry.

    Args:
        ir: The robot design intermediate representation

    Returns:
        RobotAssembly containing all custom parts
    """
    assembly = RobotAssembly(name=ir.name)

    # Process links
    z_offset = 0.0
    for link in ir.links:
        if link.is_custom_part:
            solid = generate_link_geometry(link)
            part = AssemblyPart(
                name=link.name,
                solid=solid,
                is_custom=True,
                position=(0, 0, z_offset),
            )
            assembly.add_part(part)

            # Stack parts vertically for visualization
            if link.visual and link.visual.geometry and link.visual.geometry.size:
                size = link.visual.geometry.size
                if len(size) >= 3:
                    z_offset += size[2]
                else:
                    z_offset += 0.05
            else:
                z_offset += 0.05

    return assembly


def build_cadquery_assembly(ir: RobotDesignIR) -> Any:
    """
    Build a CadQuery Assembly object (when CadQuery is available).

    Args:
        ir: The robot design intermediate representation

    Returns:
        cq.Assembly or None if CadQuery not available
    """
    if not CADQUERY_AVAILABLE:
        return None

    assy = cq.Assembly()

    for link in ir.links:
        if link.is_custom_part:
            solid = generate_link_geometry(link)
            assy.add(solid, name=link.name)

    return assy
