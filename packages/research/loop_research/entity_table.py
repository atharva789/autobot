"""Parses a robot schema (MJCF) into the entity table G1 and the compiler both resolve against.

loop-contract.md C2: "The schema is read, not assumed." This module reads it via MuJoCo's own
parser rather than a hand-maintained name list, so an unusual naming convention in a schema is
handled the same way a familiar one is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mujoco

from packages.research.loop_research.symbols import SymbolKind

_KIND_TO_MJOBJ = {
    "joint": mujoco.mjtObj.mjOBJ_JOINT,
    "body": mujoco.mjtObj.mjOBJ_BODY,
    "site": mujoco.mjtObj.mjOBJ_SITE,
    "actuator": mujoco.mjtObj.mjOBJ_ACTUATOR,
    "sensor": mujoco.mjtObj.mjOBJ_SENSOR,
}
_KIND_TO_COUNT_ATTR = {
    "joint": "njnt",
    "body": "nbody",
    "site": "nsite",
    "actuator": "nu",
    "sensor": "nsensor",
}


@dataclass(frozen=True)
class EntityTable:
    joints: frozenset[str]
    bodies: frozenset[str]
    sites: frozenset[str]
    actuators: frozenset[str]
    sensors: frozenset[str]

    def names(self, kind: SymbolKind) -> frozenset[str]:
        if kind == "const":
            return frozenset()
        return {
            "joint": self.joints,
            "body": self.bodies,
            "site": self.sites,
            "actuator": self.actuators,
            "sensor": self.sensors,
        }[kind]

    def has(self, kind: SymbolKind, name: str) -> bool:
        return name in self.names(kind)


def _names(model: mujoco.MjModel, kind: SymbolKind) -> frozenset[str]:
    mjobj = _KIND_TO_MJOBJ[kind]
    count = getattr(model, _KIND_TO_COUNT_ATTR[kind])
    names = set()
    for i in range(count):
        name = mujoco.mj_id2name(model, mjobj, i)
        if name:
            names.add(name)
    return frozenset(names)


def entity_table_from_model(model: mujoco.MjModel) -> EntityTable:
    return EntityTable(
        joints=_names(model, "joint"),
        bodies=_names(model, "body"),
        sites=_names(model, "site"),
        actuators=_names(model, "actuator"),
        sensors=_names(model, "sensor"),
    )


def load_model_and_entities(schema_path: str | Path) -> tuple[mujoco.MjModel, EntityTable]:
    model = mujoco.MjModel.from_xml_path(str(schema_path))
    return model, entity_table_from_model(model)


def load_model_and_entities_from_xml(xml: str) -> tuple[mujoco.MjModel, EntityTable]:
    model = mujoco.MjModel.from_xml_string(xml)
    return model, entity_table_from_model(model)


__all__ = [
    "EntityTable",
    "entity_table_from_model",
    "load_model_and_entities",
    "load_model_and_entities_from_xml",
]
