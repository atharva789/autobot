from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_physical_link(
    name: str,
    *,
    length: float = 0.15,
    radius: float = 0.02,
    mass: float = 0.3,
) -> "LinkIR":
    """Create a LinkIR with valid geometry and inertial properties."""
    from packages.pipeline.ir.design_ir import (
        LinkIR, Inertial, Geometry, Visual, Collision,
    )

    geom = Geometry(type="capsule", size=(radius, length))
    ixx = mass * (3 * radius**2 + length**2) / 12.0
    return LinkIR(
        name=name,
        inertial=Inertial(mass=mass, ixx=ixx, iyy=ixx, izz=mass * radius**2 / 2.0),
        visual=Visual(geometry=geom),
        collision=Collision(geometry=geom),
    )
