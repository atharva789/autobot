"""Robogrammar/Robomorph data types for grammar-driven robot generation.

This module is the single entry point for robot morphology specification.
The LangGraph agent loop (written separately) is responsible for:

  1. Normalizing a user prompt into ``RobotPrompt`` (functionality + terrain).
  2. Selecting / synthesizing a ``Grammar`` (structural rules + component
     templates), typically by querying a Supabase catalog of pre-existing
     grammars.
  3. Expanding the grammar's start symbol into a ``GrammarGraph`` whose
     terminal nodes are bound to concrete ``Component`` instances.
  4. Handing the ``GrammarGraph`` to the renderer / downstream consumer.

References
----------
Robogrammar (Zhao et al., 2020): https://cdfg.mit.edu/assets/files/robogrammar.pdf
Robomorph (Hatziefthymiou et al., 2024): https://arxiv.org/html/2407.08626v3

Sample structural rule (a ``StructuralRule`` value):

    {
        "Body": ["Limb", "Connector", "BodyLink", "Connector", "Limb"],
        "Limb": ["Joint", "Link", "Joint", "Link", "Foot"],
        "BodyLink": ["Link"],
        "Connector": ["Joint"],
    }

Each key is a non-terminal symbol; each value is the ordered sequence of
child symbols produced when the rule fires. Symbols that have no rule are
terminals and must have a matching entry in ``Grammar.component_rules``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal


ComponentKind = Literal[
    "link",
    "joint",
    "wheel",
    "foot",
    "body",
    "connector",
    "sensor",
    "actuator",
]


@dataclass(frozen=True)
class RobotPrompt:
    """Normalized user prompt.

    The agent loop is responsible for parsing the raw user request into
    these two free-text fields. Downstream consumers (grammar selection,
    component instantiation, rendering) read them as natural-language hints.
    """

    functionality: str
    terrain_and_conditions: str


@dataclass(frozen=True)
class Component:
    """Physical attributes attached to a terminal grammar node.

    Mirrors the Robomorph "component" abstraction: a typed building block
    with geometric and dynamic properties that the renderer / simulator
    can materialize into MJCF / URDF / mesh geometry.
    """

    component_id: str
    kind: ComponentKind
    length_m: float = 0.0
    radius_m: float = 0.0
    mass_kg: float = 0.0
    dof: int = 0
    actuator_torque_nm: float = 0.0
    material: str = ""
    extra: Mapping[str, float | int | str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class GrammarNode:
    """One node in an expanded grammar derivation tree.

    A node carries the symbol it was derived from, the ordered ids of its
    child nodes (already expanded), and — if it is a terminal — the
    bound ``Component`` describing its physical attributes.
    """

    node_id: str
    symbol: str
    component: Component | None = None
    children: tuple[str, ...] = ()


StructuralRule = Mapping[str, Sequence[str]]
"""Mapping from non-terminal symbol to ordered RHS symbols.

Terminals are symbols that do NOT appear as keys; they must instead be
present in ``Grammar.component_rules``.
"""


@dataclass(frozen=True)
class Grammar:
    """A Robogrammar-style grammar bundle.

    ``structural_rules`` defines the topology (how symbols expand).
    ``component_rules`` defines the physical instantiation for every
    terminal symbol — one ``Component`` template per terminal.
    """

    grammar_id: str
    start_symbol: str
    structural_rules: StructuralRule
    component_rules: Mapping[str, Component]
    description: str = ""


@dataclass(frozen=True)
class GrammarGraph:
    """A fully-expanded derivation tree from a ``Grammar``.

    The agent loop produces one of these per candidate robot. Terminal
    nodes have ``component`` set; non-terminal nodes describe topology
    only. ``root_id`` identifies the entry point in ``nodes``.

    Downstream renderers / simulators traverse from ``root_id`` and read
    component attributes from terminal nodes. See the agent-loop module
    for the GrammarGraph → renderer adapter — the renderer expects a
    flat parameter bundle, not a symbolic tree.
    """

    grammar_id: str
    root_id: str
    nodes: Mapping[str, GrammarNode]
    prompt: RobotPrompt


__all__ = [
    "Component",
    "ComponentKind",
    "Grammar",
    "GrammarGraph",
    "GrammarNode",
    "RobotPrompt",
    "StructuralRule",
]
