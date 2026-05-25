"""Rich RoboGrammar schema with multiple productions per nonterminal.

The legacy grammar compiler accepts ``dict[str, list[str]]`` where each
nonterminal has exactly one right-hand-side sequence. This module provides an
immutable richer schema that can represent several productions per nonterminal
while preserving the existing vocabulary-only ``CompileResult`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from packages.pipeline import grammar_graph
from packages.pipeline.grammar_graph import CompileResult, CompilerError

LegacyStructuralRules = dict[str, list[str]]


@dataclass(frozen=True)
class NodeAttributes:
    """Optional physical or geometric hints attached to one RHS symbol."""

    angle: float | None = None
    mass: float | None = None
    orientation: tuple[float, float, float] | None = None
    scale: float | None = None

    def __post_init__(self) -> None:
        if self.orientation is not None and len(self.orientation) != 3:
            raise ValueError("orientation must contain exactly three values")
        for field_name in ("angle", "mass", "scale"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, float(value))
        if self.orientation is not None:
            object.__setattr__(
                self,
                "orientation",
                tuple(float(value) for value in self.orientation),
            )


@dataclass(frozen=True)
class ProductionSymbol:
    """One RHS symbol plus optional per-node attributes."""

    symbol: str
    attributes: NodeAttributes | None = None

    def __post_init__(self) -> None:
        symbol = _clean_string(self.symbol)
        if symbol is None:
            raise ValueError("production symbol must not be blank")
        object.__setattr__(self, "symbol", symbol)


@dataclass(frozen=True)
class ProductionRule:
    """A single grammar production for one nonterminal LHS."""

    rhs: tuple[ProductionSymbol, ...]
    weight: float | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rhs", tuple(self.rhs))
        if self.weight is not None:
            weight = float(self.weight)
            if weight < 0:
                raise ValueError("weight must be non-negative")
            object.__setattr__(self, "weight", weight)
        object.__setattr__(
            self,
            "tags",
            tuple(tag for tag in (_clean_string(tag) for tag in self.tags) if tag),
        )
        object.__setattr__(self, "label", _clean_string(self.label))

    @property
    def rhs_symbols(self) -> tuple[str, ...]:
        """Return the legacy RHS symbol sequence for this production."""

        return tuple(node.symbol for node in self.rhs)


@dataclass(frozen=True)
class RichGrammar:
    """Mapping from nonterminal LHS symbols to one or more productions."""

    productions: Mapping[str, tuple[ProductionRule, ...]]
    version: str = "rich-grammar-v1"

    def __post_init__(self) -> None:
        normalized: dict[str, tuple[ProductionRule, ...]] = {}
        for lhs, rules in self.productions.items():
            lhs_symbol = _clean_string(lhs)
            if lhs_symbol is None:
                raise ValueError("production LHS must not be blank")
            rule_tuple = tuple(rules)
            if not rule_tuple:
                raise ValueError(f"{lhs_symbol} must have at least one production")
            normalized[lhs_symbol] = rule_tuple
        object.__setattr__(self, "productions", normalized)

    @classmethod
    def from_legacy(cls, rules: LegacyStructuralRules) -> "RichGrammar":
        """Build a rich grammar from the legacy ``dict[str, list[str]]`` shape."""

        return convert_legacy_rules(rules)

    def to_legacy_first_productions(self) -> LegacyStructuralRules:
        """Project to legacy shape using the first production per LHS."""

        return {
            lhs: list(rules[0].rhs_symbols)
            for lhs, rules in self.productions.items()
        }


def convert_legacy_rules(old: LegacyStructuralRules) -> RichGrammar:
    """Convert legacy single-production structural rules to ``RichGrammar``."""

    if not isinstance(old, dict):
        raise TypeError("old must be dict[str, list[str]]")

    productions: dict[str, tuple[ProductionRule, ...]] = {}
    for lhs, rhs in old.items():
        lhs_symbol = _clean_string(lhs)
        if lhs_symbol is None:
            raise ValueError("legacy rule LHS must not be blank")
        if not isinstance(rhs, list):
            raise TypeError("legacy rule RHS must be a list of strings")
        productions[lhs_symbol] = (
            ProductionRule(
                rhs=tuple(ProductionSymbol(symbol=node) for node in rhs),
                tags=("legacy",),
                label=f"legacy:{lhs_symbol}",
            ),
        )
    return RichGrammar(productions=productions)


def compile_rich_structural_rules(
    grammar: RichGrammar | LegacyStructuralRules,
    *,
    known_nodes: set[str] | None = None,
) -> CompileResult:
    """Validate rich structural rules against the GrammarNodes vocabulary.

    This mirrors ``compile_structural_rules``: it checks only LHS and RHS node
    IDs against the Supabase-backed ``GrammarNodes.short_form_name`` vocabulary
    and returns ``CompileResult`` with CompilerError wrappers.
    """

    rich_grammar = (
        convert_legacy_rules(grammar) if isinstance(grammar, dict) else grammar
    )
    if not isinstance(rich_grammar, RichGrammar):
        error = {
            "error_type": "InvalidRichGrammar",
            "error_message": "Grammar must be a RichGrammar or legacy structural-rule dict.",
        }
        return CompileResult(False, CompilerError(error=error))

    vocabulary = known_nodes
    if vocabulary is None:
        vocabulary = {
            short_name
            for short_name, _long_name in grammar_graph.fetch_grammar_from_db()
        }
    if not vocabulary:
        error = {
            "error_type": "GrammarVocabularyUnavailable",
            "error_message": "GrammarNodes vocabulary is empty.",
        }
        return CompileResult(False, CompilerError(error=error))

    invalid_nodes: list[str] = []
    for lhs, rules in rich_grammar.productions.items():
        if lhs not in vocabulary:
            invalid_nodes.append(lhs)
        for rule in rules:
            for rhs_symbol in rule.rhs:
                if rhs_symbol.symbol not in vocabulary:
                    invalid_nodes.append(rhs_symbol.symbol)

    deduped_invalid_nodes = list(dict.fromkeys(invalid_nodes))
    invalid_error = grammar_graph._compiler_error(
        "InvalidGrammarNodes",
        "Invalid nodes",
        deduped_invalid_nodes,
    )
    return CompileResult(not invalid_error.nodes, invalid_error, CompilerError())


def production_from_symbols(
    symbols: list[str] | tuple[str, ...],
    *,
    weight: float | None = None,
    tags: tuple[str, ...] = (),
    label: str | None = None,
    attributes: Mapping[str, NodeAttributes | Mapping[str, Any] | None] | None = None,
) -> ProductionRule:
    """Create a production from RHS symbols and optional per-symbol attributes."""

    attribute_map = attributes or {}
    rhs: list[ProductionSymbol] = []
    for symbol in symbols:
        raw_attributes = attribute_map.get(symbol)
        node_attributes = _coerce_attributes(raw_attributes)
        rhs.append(ProductionSymbol(symbol=symbol, attributes=node_attributes))
    return ProductionRule(
        rhs=tuple(rhs),
        weight=weight,
        tags=tags,
        label=label,
    )


def _coerce_attributes(
    value: NodeAttributes | Mapping[str, Any] | None,
) -> NodeAttributes | None:
    if value is None or isinstance(value, NodeAttributes):
        return value
    return NodeAttributes(
        angle=value.get("angle"),
        mass=value.get("mass"),
        orientation=value.get("orientation"),
        scale=value.get("scale"),
    )


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "LegacyStructuralRules",
    "NodeAttributes",
    "ProductionRule",
    "ProductionSymbol",
    "RichGrammar",
    "compile_rich_structural_rules",
    "convert_legacy_rules",
    "production_from_symbols",
]
