"""G1 — schema-reference gate. Static, zero model cost, runs on every scaffold.

Implements contracts/eval-contract.md exactly: >= 0.80 of reward-term symbols
must resolve against the schema's entity table, and 100% of termination
symbols must resolve. ``const.*`` never resolves, by design.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from packages.research.loop_research.records import GateResult, TrainingScaffold

_TERM_RESOLVE_THRESHOLD = 0.80  # eval-contract.md G1; do not change without human review

_URDF_KIND_MAP = {"link": "body", "joint": "joint"}
_MJCF_KINDS = {"body", "joint", "site", "actuator", "sensor"}


def build_entity_table(schema_path: Path) -> dict[str, set[str]]:
    """Parse a URDF or MJCF file into {kind: {names}}.

    MJCF actuators/sensors live under <actuator>/<sensor> parents whose child
    tags vary (motor, position, force, ...), so any named child of those
    parents counts as that kind.
    """

    root = ET.parse(schema_path).getroot()  # noqa: S314 - local, repo-controlled files
    table: dict[str, set[str]] = {k: set() for k in _MJCF_KINDS}

    if root.tag == "robot":  # URDF
        for tag, kind in _URDF_KIND_MAP.items():
            table[kind].update(
                name for el in root.iter(tag) if (name := el.get("name"))
            )
        return table

    for parent_tag in ("actuator", "sensor"):
        for parent in root.iter(parent_tag):
            table[parent_tag].update(
                name for el in parent if (name := el.get("name"))
            )
    for kind in ("body", "joint", "site"):
        table[kind].update(name for el in root.iter(kind) if (name := el.get("name")))
    return table


def _resolve(symbol: str, table: dict[str, set[str]]) -> bool:
    kind, _, name = symbol.partition(".")
    return bool(name) and name in table.get(kind, set())


def run_g1(scaffold: TrainingScaffold, schema_path: Path) -> GateResult:
    table = build_entity_table(schema_path)

    term_symbols = [s for t in scaffold.reward_terms for s in t.get("symbols", [])]
    term_resolved = [s for s in term_symbols if _resolve(s, table)]
    term_ratio = len(term_resolved) / len(term_symbols) if term_symbols else 0.0

    stop_symbols = [s for t in scaffold.terminations for s in t.get("symbols", [])]
    stop_unresolved = [s for s in stop_symbols if not _resolve(s, table)]

    passed = (
        bool(term_symbols)
        and bool(stop_symbols)
        and term_ratio >= _TERM_RESOLVE_THRESHOLD
        and not stop_unresolved
    )
    return GateResult(
        gate="G1",
        scaffold_id=scaffold.scaffold_id,
        passed=passed,
        score=round(term_ratio, 4),
        threshold=_TERM_RESOLVE_THRESHOLD,
        detail={
            "resolved": len(term_resolved),
            "total": len(term_symbols),
            "unresolved": sorted(set(term_symbols) - set(term_resolved)),
            "termination_unresolved": sorted(set(stop_unresolved)),
            "entity_counts": {k: len(v) for k, v in table.items()},
        },
    )
