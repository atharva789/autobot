"""Recursive Component IR (Intermediate Representation) for robot design.

This module defines the hierarchical component model that replaces flat part lists.
The hierarchy is: Robot -> Subsystem -> Assembly -> Component -> Part -> Feature

Key design decisions:
1. Stable, hierarchical IDs enable deterministic expansion
2. Model (Gemini) proposes high-level; compiler expands deterministically
3. Every node knows its parent, enabling roll-up operations (cost, mass, etc.)
"""
from __future__ import annotations

from typing import Literal, Any
from pydantic import BaseModel, Field


ComponentLevel = Literal["robot", "subsystem", "assembly", "component", "part", "feature"]

SubsystemKind = Literal[
    "locomotion",
    "manipulation",
    "sensing",
    "power",
    "compute",
    "payload",
    "structure",
]

AssemblyKind = Literal[
    "leg",
    "arm",
    "gripper",
    "hand",
    "torso",
    "head",
    "tail",
    "wheel",
    "track",
    "wing",
    "payload_bay",
    "battery_bay",
    "controller_bay",
]

ComponentKind = Literal[
    "joint_module",
    "link",
    "end_effector",
    "chassis",
    "finger_assembly",
    "palm",
    "wrist_interface",
    "sensor_module",
    "motor_assembly",
    "gearbox_assembly",
    "shell_panel",
    "mounting_bracket",
    "cable_harness",
    "connector_block",
]

PartKind = Literal[
    "actuator",
    "transmission",
    "encoder",
    "structural",
    "fastener",
    "sensor",
    "cable",
    "connector",
    "bearing",
    "shaft",
    "bushing",
    "spring",
    "damper",
    "contact_pad",
    "shell",
    "bracket",
    "pcb",
    "power_rail",
]


def make_id(level: ComponentLevel, *segments: str) -> str:
    """Generate stable hierarchical ID.

    Examples:
        make_id("subsystem", "locomotion") -> "subsystem:locomotion"
        make_id("assembly", "locomotion", "leg_fl") -> "assembly:locomotion.leg_fl"
        make_id("component", "locomotion", "leg_fl", "hip") -> "component:locomotion.leg_fl.hip"
    """
    if not segments:
        raise ValueError("At least one segment required")
    path = ".".join(segments)
    return f"{level}:{path}"


def parent_id_from(node_id: str) -> str | None:
    """Extract parent ID from hierarchical ID.

    Examples:
        "component:locomotion.leg_fl.hip" -> "assembly:locomotion.leg_fl"
        "assembly:locomotion.leg_fl" -> "subsystem:locomotion"
        "subsystem:locomotion" -> None (robot level)
    """
    level, path = node_id.split(":", 1)
    parts = path.split(".")

    if len(parts) <= 1:
        return None

    parent_path = ".".join(parts[:-1])

    level_hierarchy = ["robot", "subsystem", "assembly", "component", "part", "feature"]
    try:
        idx = level_hierarchy.index(level)
        if idx == 0:
            return None
        parent_level = level_hierarchy[idx - 1]
        return f"{parent_level}:{parent_path}"
    except ValueError:
        return None


class InterfaceSpec(BaseModel):
    """Connection point between components."""

    id: str
    kind: Literal["mechanical", "electrical", "data", "fluid"]
    connector_type: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mate_id: str | None = None


class PartGeometry(BaseModel):
    """Geometry specification for a renderable part."""

    primitive: Literal["box", "cylinder", "sphere", "capsule", "cone", "mesh"]
    dimensions: tuple[float, float, float]
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    material_key: str = "anodized_metal"
    mesh_path: str | None = None


class PartSpec(BaseModel):
    """Terminal component - maps to BOM item."""

    id: str
    parent_id: str
    level: Literal["part"] = "part"

    kind: PartKind
    role: str
    display_name: str

    vendor: str | None = None
    sku: str | None = None
    unit_price_usd: float | None = None

    geometry: PartGeometry | None = None
    mass_kg: float | None = None

    interfaces: list[InterfaceSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComponentSpec(BaseModel):
    """Intermediate assembly - contains parts."""

    id: str
    parent_id: str
    level: Literal["component"] = "component"

    kind: ComponentKind
    display_name: str

    parts: list[PartSpec] = Field(default_factory=list)
    interfaces: list[InterfaceSpec] = Field(default_factory=list)

    is_actuated: bool = False
    dof: int = 0

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float] = (0.0, 0.0, 0.0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def part_ids(self) -> list[str]:
        return [p.id for p in self.parts]

    def total_mass_kg(self) -> float:
        return sum(p.mass_kg or 0.0 for p in self.parts)

    def total_cost_usd(self) -> float:
        return sum(p.unit_price_usd or 0.0 for p in self.parts)


class JointSpec(BaseModel):
    """Joint between components in an assembly."""

    id: str
    name: str
    kind: Literal["revolute", "prismatic", "fixed", "spherical", "continuous"]

    parent_component_id: str
    child_component_id: str

    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)

    lower_limit: float | None = None
    upper_limit: float | None = None
    velocity_limit: float | None = None
    effort_limit: float | None = None


class AssemblySpec(BaseModel):
    """Functional unit - contains components and joints."""

    id: str
    parent_id: str
    level: Literal["assembly"] = "assembly"

    kind: AssemblyKind
    display_name: str
    template_key: str

    components: list[ComponentSpec] = Field(default_factory=list)
    joints: list[JointSpec] = Field(default_factory=list)

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float] = (0.0, 0.0, 0.0)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def component_ids(self) -> list[str]:
        return [c.id for c in self.components]

    def all_parts(self) -> list[PartSpec]:
        parts: list[PartSpec] = []
        for comp in self.components:
            parts.extend(comp.parts)
        return parts

    def total_mass_kg(self) -> float:
        return sum(c.total_mass_kg() for c in self.components)

    def total_cost_usd(self) -> float:
        return sum(c.total_cost_usd() for c in self.components)

    def total_dof(self) -> int:
        return sum(1 for j in self.joints if j.kind != "fixed")


class SubsystemSpec(BaseModel):
    """Top-level functional grouping - contains assemblies."""

    id: str
    parent_id: str
    level: Literal["subsystem"] = "subsystem"

    kind: SubsystemKind
    display_name: str

    assemblies: list[AssemblySpec] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def assembly_ids(self) -> list[str]:
        return [a.id for a in self.assemblies]

    def all_components(self) -> list[ComponentSpec]:
        comps: list[ComponentSpec] = []
        for asm in self.assemblies:
            comps.extend(asm.components)
        return comps

    def all_parts(self) -> list[PartSpec]:
        parts: list[PartSpec] = []
        for asm in self.assemblies:
            parts.extend(asm.all_parts())
        return parts

    def total_mass_kg(self) -> float:
        return sum(a.total_mass_kg() for a in self.assemblies)

    def total_cost_usd(self) -> float:
        return sum(a.total_cost_usd() for a in self.assemblies)

    def total_dof(self) -> int:
        return sum(a.total_dof() for a in self.assemblies)


class RobotComponentGraph(BaseModel):
    """Complete hierarchical representation of a robot design."""

    id: str
    level: Literal["robot"] = "robot"

    candidate_id: Literal["A", "B", "C"]
    embodiment_class: str
    display_name: str

    subsystems: list[SubsystemSpec] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def subsystem_ids(self) -> list[str]:
        return [s.id for s in self.subsystems]

    def all_assemblies(self) -> list[AssemblySpec]:
        asms: list[AssemblySpec] = []
        for sub in self.subsystems:
            asms.extend(sub.assemblies)
        return asms

    def all_components(self) -> list[ComponentSpec]:
        comps: list[ComponentSpec] = []
        for sub in self.subsystems:
            comps.extend(sub.all_components())
        return comps

    def all_parts(self) -> list[PartSpec]:
        parts: list[PartSpec] = []
        for sub in self.subsystems:
            parts.extend(sub.all_parts())
        return parts

    def total_mass_kg(self) -> float:
        return sum(s.total_mass_kg() for s in self.subsystems)

    def total_cost_usd(self) -> float:
        return sum(s.total_cost_usd() for s in self.subsystems)

    def total_dof(self) -> int:
        return sum(s.total_dof() for s in self.subsystems)

    def find_by_id(self, node_id: str) -> SubsystemSpec | AssemblySpec | ComponentSpec | PartSpec | None:
        """Find any node by its hierarchical ID."""
        level = node_id.split(":")[0]

        if level == "subsystem":
            for sub in self.subsystems:
                if sub.id == node_id:
                    return sub
        elif level == "assembly":
            for sub in self.subsystems:
                for asm in sub.assemblies:
                    if asm.id == node_id:
                        return asm
        elif level == "component":
            for sub in self.subsystems:
                for asm in sub.assemblies:
                    for comp in asm.components:
                        if comp.id == node_id:
                            return comp
        elif level == "part":
            for part in self.all_parts():
                if part.id == node_id:
                    return part

        return None

    def to_flat_node_list(self) -> list[dict[str, Any]]:
        """Convert to flat list for UI scene consumption."""
        nodes: list[dict[str, Any]] = []

        for sub in self.subsystems:
            nodes.append({
                "id": sub.id,
                "parent_id": self.id,
                "level": "subsystem",
                "kind": sub.kind,
                "display_name": sub.display_name,
                "has_children": len(sub.assemblies) > 0,
            })

            for asm in sub.assemblies:
                nodes.append({
                    "id": asm.id,
                    "parent_id": sub.id,
                    "level": "assembly",
                    "kind": asm.kind,
                    "display_name": asm.display_name,
                    "position": asm.position,
                    "has_children": len(asm.components) > 0,
                })

                for comp in asm.components:
                    nodes.append({
                        "id": comp.id,
                        "parent_id": asm.id,
                        "level": "component",
                        "kind": comp.kind,
                        "display_name": comp.display_name,
                        "position": comp.position,
                        "is_actuated": comp.is_actuated,
                        "dof": comp.dof,
                        "has_children": len(comp.parts) > 0,
                    })

                    for part in comp.parts:
                        node: dict[str, Any] = {
                            "id": part.id,
                            "parent_id": comp.id,
                            "level": "part",
                            "kind": part.kind,
                            "role": part.role,
                            "display_name": part.display_name,
                            "has_children": False,
                        }
                        if part.geometry:
                            node["geometry"] = part.geometry.model_dump()
                        if part.vendor:
                            node["vendor"] = part.vendor
                        if part.sku:
                            node["sku"] = part.sku
                        nodes.append(node)

        return nodes
