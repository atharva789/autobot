"""
Canonical Robot Design Intermediate Representation (IR).

This is the single source of truth for robot structure. All compilers
(URDF, MJCF, USD, CAD, BOM) derive from this representation.

The IR contains:
- Links: Rigid bodies with mass, inertia, visual/collision geometry
- Joints: Connections between links with type, axis, limits
- Actuator slots: Where motors/actuators attach
- Sensor slots: Where sensors mount
- Component references: Links to vendor parts or custom geometry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class JointType(str, Enum):
    """Joint types following URDF/MJCF conventions."""
    REVOLUTE = "revolute"
    CONTINUOUS = "continuous"
    PRISMATIC = "prismatic"
    FIXED = "fixed"
    FLOATING = "floating"
    PLANAR = "planar"
    BALL = "ball"  # MJCF only


@dataclass(frozen=True)
class Vector3:
    """Immutable 3D vector."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class Inertial:
    """Inertial properties of a link."""
    mass: float
    origin: Vector3 = field(default_factory=Vector3)
    ixx: float = 0.0
    ixy: float = 0.0
    ixz: float = 0.0
    iyy: float = 0.0
    iyz: float = 0.0
    izz: float = 0.0


@dataclass(frozen=True)
class Geometry:
    """Visual or collision geometry specification."""
    type: Literal["box", "cylinder", "sphere", "mesh", "capsule"]
    size: tuple[float, ...] = ()  # Dimensions depend on type
    mesh_path: str | None = None  # For mesh type
    mesh_scale: Vector3 = field(default_factory=lambda: Vector3(1.0, 1.0, 1.0))


@dataclass(frozen=True)
class Visual:
    """Visual representation of a link."""
    geometry: Geometry
    origin: Vector3 = field(default_factory=Vector3)
    material_name: str | None = None
    rgba: tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)


@dataclass(frozen=True)
class Collision:
    """Collision geometry of a link."""
    geometry: Geometry
    origin: Vector3 = field(default_factory=Vector3)


@dataclass(frozen=True)
class ActuatorSlot:
    """Slot for an actuator on a joint."""
    actuator_type: Literal["motor", "servo", "hydraulic", "pneumatic"]
    max_torque: float = 100.0
    max_velocity: float = 10.0
    gear_ratio: float = 1.0
    vendor_sku: str | None = None  # If resolved to real part


@dataclass(frozen=True)
class SensorSlot:
    """Slot for a sensor on a link or joint."""
    sensor_type: Literal["imu", "force_torque", "encoder", "camera", "lidar", "touch"]
    mount_link: str
    origin: Vector3 = field(default_factory=Vector3)
    vendor_sku: str | None = None


@dataclass(frozen=True)
class JointLimits:
    """Joint motion limits."""
    lower: float = -3.14159
    upper: float = 3.14159
    effort: float = 100.0
    velocity: float = 10.0


@dataclass
class LinkIR:
    """Canonical representation of a robot link (rigid body)."""
    name: str
    inertial: Inertial | None = None
    visual: Visual | None = None
    collision: Collision | None = None
    is_custom_part: bool = False  # True if requires manufacturing
    vendor_sku: str | None = None  # If off-the-shelf


@dataclass
class JointIR:
    """Canonical representation of a robot joint."""
    name: str
    joint_type: JointType
    parent_link: str
    child_link: str
    origin: Vector3 = field(default_factory=Vector3)
    axis: Vector3 = field(default_factory=lambda: Vector3(0.0, 0.0, 1.0))
    limits: JointLimits | None = None
    actuator: ActuatorSlot | None = None
    damping: float = 0.1
    friction: float = 0.0


@dataclass
class RobotDesignIR:
    """
    Canonical Intermediate Representation for a robot design.

    This is THE source of truth. All exports derive from this:
    - URDF: compilers/urdf_compiler.py
    - MJCF: compilers/mjcf_compiler.py
    - USD: compilers/usd_compiler.py (future)
    - CAD: cad/assembly_builder.py (future)
    - BOM: components/slot_resolver.py
    - UI: compilers/ui_scene_compiler.py
    """
    name: str
    links: list[LinkIR] = field(default_factory=list)
    joints: list[JointIR] = field(default_factory=list)
    sensors: list[SensorSlot] = field(default_factory=list)

    # Metadata
    version: str = "1.0.0"
    source_candidate_id: str | None = None  # Link to GenerateDesignsResponse

    def get_link(self, name: str) -> LinkIR | None:
        """Find link by name."""
        return next((l for l in self.links if l.name == name), None)

    def get_joint(self, name: str) -> JointIR | None:
        """Find joint by name."""
        return next((j for j in self.joints if j.name == name), None)

    def root_link(self) -> LinkIR | None:
        """Find the root link (not a child of any joint)."""
        child_links = {j.child_link for j in self.joints}
        for link in self.links:
            if link.name not in child_links:
                return link
        return self.links[0] if self.links else None

    def validate(self) -> list[str]:
        """Validate IR consistency. Returns list of errors."""
        errors = []
        link_names = {l.name for l in self.links}

        for joint in self.joints:
            if joint.parent_link not in link_names:
                errors.append(f"Joint {joint.name}: parent_link '{joint.parent_link}' not found")
            if joint.child_link not in link_names:
                errors.append(f"Joint {joint.name}: child_link '{joint.child_link}' not found")

        for sensor in self.sensors:
            if sensor.mount_link not in link_names:
                errors.append(f"Sensor on '{sensor.mount_link}': link not found")

        return errors
