"""
CadQuery-based part geometry generation.

In production with CadQuery installed, this generates real CAD solids.
Without CadQuery, uses a mock implementation for testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from packages.pipeline.ir.design_ir import Geometry, LinkIR

# Try to import CadQuery, fall back to mock
try:
    import cadquery as cq

    CADQUERY_AVAILABLE = True
except ImportError:
    CADQUERY_AVAILABLE = False


@dataclass
class MockSolid:
    """Mock solid for testing when CadQuery is not available."""

    geometry_type: str
    dimensions: dict[str, float]
    _vertices: list[tuple[float, float, float]] | None = None

    def val(self) -> "MockSolid":
        """Mimic CadQuery's val() method."""
        return self

    def vertices(self) -> list[tuple[float, float, float]]:
        """Return mock vertices."""
        if self._vertices is None:
            self._vertices = [(0, 0, 0), (1, 1, 1)]
        return self._vertices


def generate_from_geometry(geometry: Geometry) -> Any:
    """
    Generate solid from Geometry specification.

    Args:
        geometry: The geometry specification

    Returns:
        CadQuery Workplane or MockSolid
    """
    if CADQUERY_AVAILABLE:
        return _generate_cadquery_solid(geometry)
    else:
        return _generate_mock_solid(geometry)


def generate_link_geometry(link: LinkIR) -> Any:
    """
    Generate geometry for a link.

    Uses the link's visual geometry if available,
    otherwise creates a default box.

    Args:
        link: The LinkIR to generate geometry for

    Returns:
        CadQuery Workplane or MockSolid
    """
    if link.visual and link.visual.geometry:
        return generate_from_geometry(link.visual.geometry)

    # Default geometry if no visual specified
    default_geometry = Geometry(type="box", size=(0.1, 0.04, 0.02))
    return generate_from_geometry(default_geometry)


# Backwards compatibility aliases
generate_part_geometry = generate_from_geometry
generate_link_bracket = generate_link_geometry


def _generate_cadquery_solid(geometry: Geometry) -> Any:
    """Generate real CadQuery solid."""
    geom_type = geometry.type
    size = geometry.size

    if geom_type == "box":
        dims = size if len(size) >= 3 else (0.1, 0.05, 0.02)
        return cq.Workplane("XY").box(
            dims[0] * 1000,  # Convert m to mm
            dims[1] * 1000,
            dims[2] * 1000,
        )

    elif geom_type == "cylinder":
        # size = (radius, length)
        radius = (size[0] if len(size) >= 1 else 0.01) * 1000
        length = (size[1] if len(size) >= 2 else 0.1) * 1000
        return cq.Workplane("XY").cylinder(length, radius)

    elif geom_type == "sphere":
        # size = (radius,)
        radius = (size[0] if len(size) >= 1 else 0.02) * 1000
        return cq.Workplane("XY").sphere(radius)

    else:
        # Default to box
        return cq.Workplane("XY").box(100, 50, 20)


def _generate_mock_solid(geometry: Geometry) -> MockSolid:
    """Generate mock solid for testing."""
    geom_type = geometry.type
    size = geometry.size

    if geom_type == "box":
        dims = size if len(size) >= 3 else (0.1, 0.05, 0.02)
        return MockSolid(
            geometry_type="box",
            dimensions={"x": dims[0], "y": dims[1], "z": dims[2]},
        )

    elif geom_type == "cylinder":
        radius = size[0] if len(size) >= 1 else 0.01
        length = size[1] if len(size) >= 2 else 0.1
        return MockSolid(
            geometry_type="cylinder",
            dimensions={"radius": radius, "length": length},
        )

    elif geom_type == "sphere":
        radius = size[0] if len(size) >= 1 else 0.02
        return MockSolid(
            geometry_type="sphere",
            dimensions={"radius": radius},
        )

    else:
        return MockSolid(
            geometry_type="box",
            dimensions={"x": 0.1, "y": 0.05, "z": 0.02},
        )
