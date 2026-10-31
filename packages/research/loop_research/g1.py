"""G1 — schema-reference gate. Static, zero model cost, runs on every scaffold.

Implements contracts/eval-contract.md's G1 procedure exactly: parse the schema into an entity
table, attempt resolution for every symbol on every reward term and termination, and pass when
>= 80% of reward-term symbols resolve AND 100% of termination symbols resolve. `const.*` never
resolves, by construction (symbols.py). The thresholds below are the contract's numbers, not a
local choice — do not change them without a human-reviewed contract version bump.
"""

from __future__ import annotations

from packages.research.loop_research.entity_table import EntityTable
from packages.research.loop_research.scaffold import GateResult, TrainingScaffold
from packages.research.loop_research.symbols import SymbolSyntaxError, is_schema_resolvable, parse_symbol

_TERM_RESOLVE_THRESHOLD = 0.80  # eval-contract.md G1; do not change without human review


def _resolves(symbol_text: str, entities: EntityTable) -> bool:
    try:
        symbol = parse_symbol(symbol_text)
    except SymbolSyntaxError:
        return False
    if not is_schema_resolvable(symbol):
        return False
    return entities.has(symbol.kind, symbol.entity)


def run_g1(scaffold: TrainingScaffold, entities: EntityTable) -> GateResult:
    term_symbols = [s for term in scaffold.reward_terms for s in term.symbols]
    term_resolved = [s for s in term_symbols if _resolves(s, entities)]
    term_ratio = len(term_resolved) / len(term_symbols) if term_symbols else 0.0

    stop_symbols = [s for term in scaffold.terminations for s in term.symbols]
    stop_unresolved = [s for s in stop_symbols if not _resolves(s, entities)]

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
            "entity_counts": {
                "joint": len(entities.joints),
                "body": len(entities.bodies),
                "site": len(entities.sites),
                "actuator": len(entities.actuators),
                "sensor": len(entities.sensors),
            },
        },
    )


__all__ = ["run_g1"]
