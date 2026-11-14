"""Compiles a TrainingScaffold against a schema into a steppable MuJoCo environment.

spec.md §3: "A scaffold compiles to a MuJoCo environment or it is rejected. Compilation is a gate,
not a score." Every non-const symbol declared on a reward term or termination must resolve against
the schema's entity table at compile time — this is a hard requirement for producing a working
environment, not the scored G1 gate (that gate, with its 80%/100% thresholds, belongs to build-order
step 3 and is not implemented here).

Randomization scope for step 1: only `const.*` parameters are sampled and injected into the
constants namespace. Randomizing physical model fields (geom friction, body mass, ...) needs to
edit `MjModel` arrays per episode and is deferred — declared entries of that form parse and are
recorded but are not applied. Noted here rather than silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import mujoco
import numpy as np

from packages.research.loop_research.entity_table import EntityTable
from packages.research.loop_research.expr import CompiledExpression, compile_expression
from packages.research.loop_research.scaffold import TrainingScaffold
from packages.research.loop_research.symbols import is_schema_resolvable, parse_symbol

_AXES = {"x": 0, "y": 1, "z": 2}


class CompilationError(ValueError):
    """Raised when a TrainingScaffold cannot be compiled against a schema."""


@dataclass(frozen=True)
class _CompiledTerm:
    name: str
    weight: float
    cause_label: str | None
    expr: CompiledExpression


@dataclass(frozen=True)
class StepOutcome:
    reward: float
    reward_breakdown: Mapping[str, float]
    done: bool
    cause: str | None
    contacts: Mapping[str, int]


def _check_symbols_resolve(symbols: tuple[str, ...], entities: EntityTable, *, where: str) -> None:
    for text in symbols:
        symbol = parse_symbol(text)
        if is_schema_resolvable(symbol) and not entities.has(symbol.kind, symbol.entity):
            raise CompilationError(
                f"{where}: {text!r} does not resolve against this schema "
                f"(no {symbol.kind} named {symbol.entity!r})"
            )


def _compile_terms(scaffold: TrainingScaffold, entities: EntityTable) -> tuple[_CompiledTerm, ...]:
    compiled = []
    for term in scaffold.reward_terms:
        _check_symbols_resolve(term.symbols, entities, where=f"reward term {term.name!r}")
        expr = compile_expression(term.expression, declared_symbols=term.symbols)
        compiled.append(_CompiledTerm(term.name, term.weight, None, expr))
    return tuple(compiled)


def _compile_terminations(scaffold: TrainingScaffold, entities: EntityTable) -> tuple[_CompiledTerm, ...]:
    compiled = []
    for term in scaffold.terminations:
        _check_symbols_resolve(term.symbols, entities, where=f"termination {term.name!r}")
        expr = compile_expression(term.predicate, declared_symbols=term.symbols)
        compiled.append(_CompiledTerm(term.name, 0.0, term.cause_label, expr))
    return tuple(compiled)


class _SimContext:
    __slots__ = ("data", "entities", "constants")

    def __init__(self, data: mujoco.MjData, entities: EntityTable, constants: Mapping[str, float]):
        self.data = data
        self.entities = entities
        self.constants = constants

    def resolve(self, symbol_text: str) -> float:
        symbol = parse_symbol(symbol_text)
        if symbol.kind == "const":
            if symbol.entity not in self.constants:
                raise CompilationError(f"const.{symbol.entity} has no runtime value bound")
            return float(self.constants[symbol.entity])
        if not self.entities.has(symbol.kind, symbol.entity):
            raise CompilationError(f"{symbol_text} does not resolve against this schema")
        resolver = _RESOLVERS[symbol.kind]
        return resolver(self.data, symbol.entity, symbol.attr_path)


def _resolve_joint(data: mujoco.MjData, name: str, attr_path: tuple[str, ...]) -> float:
    view = data.joint(name)
    if not attr_path or attr_path == ("qpos",):
        return float(view.qpos[0])
    if attr_path == ("qvel",):
        return float(view.qvel[0])
    raise CompilationError(f"joint.{name} does not support attribute path {'.'.join(attr_path)}")


def _resolve_vector_pos(view, name: str, kind: str, attr_path: tuple[str, ...]) -> float:
    if len(attr_path) == 2 and attr_path[0] == "pos" and attr_path[1] in _AXES:
        return float(view.xpos[_AXES[attr_path[1]]])
    raise CompilationError(
        f"{kind}.{name} requires a .pos.x / .pos.y / .pos.z suffix, "
        f"got {'.'.join(attr_path) or '<none>'}"
    )


def _resolve_body(data: mujoco.MjData, name: str, attr_path: tuple[str, ...]) -> float:
    return _resolve_vector_pos(data.body(name), name, "body", attr_path)


def _resolve_site(data: mujoco.MjData, name: str, attr_path: tuple[str, ...]) -> float:
    return _resolve_vector_pos(data.site(name), name, "site", attr_path)


def _resolve_actuator(data: mujoco.MjData, name: str, attr_path: tuple[str, ...]) -> float:
    view = data.actuator(name)
    if not attr_path or attr_path == ("ctrl",):
        return float(view.ctrl[0])
    if attr_path == ("force",):
        return float(view.force[0])
    raise CompilationError(f"actuator.{name} does not support attribute path {'.'.join(attr_path)}")


def _resolve_sensor(data: mujoco.MjData, name: str, attr_path: tuple[str, ...]) -> float:
    if attr_path:
        raise CompilationError(f"sensor.{name} does not support an attribute suffix")
    return float(data.sensor(name).data[0])


_RESOLVERS = {
    "joint": _resolve_joint,
    "body": _resolve_body,
    "site": _resolve_site,
    "actuator": _resolve_actuator,
    "sensor": _resolve_sensor,
}


def _contact_counts(model: mujoco.MjModel, data: mujoco.MjData) -> dict[str, int]:
    counts: dict[str, int] = {}
    for i in range(data.ncon):
        contact = data.contact[i]
        name1 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom1) or str(contact.geom1)
        name2 = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom2) or str(contact.geom2)
        key = "_".join(sorted((name1, name2)))
        counts[key] = counts.get(key, 0) + 1
    return counts


class CompiledScaffold:
    """A TrainingScaffold bound to a concrete MjModel, ready to step."""

    def __init__(self, scaffold: TrainingScaffold, model: mujoco.MjModel, entities: EntityTable):
        self.scaffold = scaffold
        self.model = model
        self.entities = entities
        self.data = mujoco.MjData(model)
        self._reward_terms = _compile_terms(scaffold, entities)
        self._terminations = _compile_terminations(scaffold, entities)

    def reset(self) -> None:
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)

    def step(self, ctrl: np.ndarray, constants: Mapping[str, float]) -> StepOutcome:
        n = min(len(ctrl), self.model.nu)
        self.data.ctrl[:n] = ctrl[:n]
        mujoco.mj_step(self.model, self.data)

        ctx = _SimContext(self.data, self.entities, constants)
        breakdown = {t.name: t.expr(ctx) * t.weight for t in self._reward_terms}
        reward = sum(breakdown.values())

        cause = None
        for term in self._terminations:
            if bool(term.expr(ctx)):
                cause = term.cause_label
                break

        return StepOutcome(
            reward=reward,
            reward_breakdown=breakdown,
            done=cause is not None,
            cause=cause,
            contacts=_contact_counts(self.model, self.data),
        )


def compile_scaffold(scaffold: TrainingScaffold, model: mujoco.MjModel, entities: EntityTable) -> CompiledScaffold:
    return CompiledScaffold(scaffold, model, entities)


__all__ = ["CompilationError", "CompiledScaffold", "StepOutcome", "compile_scaffold"]
