from __future__ import annotations

import pytest

from packages.pipeline import rich_grammar_schema
from packages.pipeline.grammar_graph import CompileResult
from packages.pipeline.rich_grammar_schema import (
    NodeAttributes,
    ProductionRule,
    ProductionSymbol,
    RichGrammar,
    compile_rich_structural_rules,
    convert_legacy_rules,
    production_from_symbols,
)


def test_convert_legacy_rules_preserves_legacy_shape() -> None:
    legacy = {
        "S": ["BODY_CHAIN"],
        "BODY_CHAIN": ["BODY_SEG", "LEG_PAIR"],
    }

    grammar = convert_legacy_rules(legacy)

    assert grammar.to_legacy_first_productions() == legacy
    assert grammar.productions["S"][0].tags == ("legacy",)
    assert grammar.productions["BODY_CHAIN"][0].label == "legacy:BODY_CHAIN"


def test_rich_grammar_allows_multiple_productions_per_lhs() -> None:
    grammar = RichGrammar(
        productions={
            "BODY_CHAIN": (
                production_from_symbols(
                    ("BODY_SEG", "LEG_PAIR", "BODY_CHAIN"),
                    weight=0.7,
                    tags=("quadruped", "recursive"),
                    label="extend quadruped body chain",
                ),
                production_from_symbols(
                    ("BODY_SEG", "TAIL"),
                    weight=0.3,
                    tags=("lizard", "terminal"),
                    label="terminate with tail",
                ),
            )
        }
    )

    assert len(grammar.productions["BODY_CHAIN"]) == 2
    assert grammar.productions["BODY_CHAIN"][0].rhs_symbols == (
        "BODY_SEG",
        "LEG_PAIR",
        "BODY_CHAIN",
    )
    assert grammar.productions["BODY_CHAIN"][0].weight == 0.7
    assert grammar.productions["BODY_CHAIN"][1].tags == ("lizard", "terminal")


def test_production_symbols_support_per_node_attributes() -> None:
    rule = production_from_symbols(
        ("BODY_SEG", "LEG_PAIR"),
        attributes={
            "BODY_SEG": {"mass": 4, "scale": 1.2},
            "LEG_PAIR": NodeAttributes(
                angle=35,
                orientation=(0, 0.5, 1),
                scale=0.8,
            ),
        },
    )

    body_attrs = rule.rhs[0].attributes
    leg_attrs = rule.rhs[1].attributes
    assert body_attrs == NodeAttributes(mass=4.0, scale=1.2)
    assert leg_attrs == NodeAttributes(
        angle=35.0,
        orientation=(0.0, 0.5, 1.0),
        scale=0.8,
    )


def test_schema_objects_are_frozen() -> None:
    attrs = NodeAttributes(mass=1.0)
    symbol = ProductionSymbol("BODY_SEG", attrs)
    rule = ProductionRule(rhs=(symbol,))

    with pytest.raises(AttributeError):
        attrs.mass = 2.0  # type: ignore[misc]
    with pytest.raises(AttributeError):
        symbol.symbol = "OTHER"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        rule.weight = 0.2  # type: ignore[misc]


def test_schema_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="blank"):
        ProductionSymbol(" ")
    with pytest.raises(ValueError, match="non-negative"):
        production_from_symbols(("BODY_SEG",), weight=-0.1)
    with pytest.raises(ValueError, match="orientation"):
        NodeAttributes(orientation=(1.0, 2.0))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one production"):
        RichGrammar(productions={"S": ()})
    with pytest.raises(TypeError, match="RHS"):
        convert_legacy_rules({"S": ("BODY_SEG",)})  # type: ignore[arg-type]


def test_compile_rich_structural_rules_uses_supabase_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rich_grammar_schema.grammar_graph,
        "fetch_grammar_from_db",
        lambda: [
            ("S", "Start"),
            ("BODY_CHAIN", "Body Chain"),
            ("BODY_SEG", "Body Segment"),
            ("LEG_PAIR", "Leg Pair"),
            ("TAIL", "Tail"),
        ],
    )
    grammar = RichGrammar(
        productions={
            "S": (production_from_symbols(("BODY_CHAIN",)),),
            "BODY_CHAIN": (
                production_from_symbols(("BODY_SEG", "LEG_PAIR"), weight=0.6),
                production_from_symbols(("BODY_SEG", "TAIL"), weight=0.4),
            ),
        }
    )

    result = compile_rich_structural_rules(grammar)

    assert isinstance(result, CompileResult)
    assert result.compile_safe is True
    assert result.invalid_nodes.nodes == ()
    assert bool(result) is True


def test_compile_rich_structural_rules_reports_invalid_lhs_and_rhs() -> None:
    grammar = RichGrammar(
        productions={
            "S": (production_from_symbols(("BODY_CHAIN", "MISSING_RHS")),),
            "MISSING_LHS": (production_from_symbols(("BODY_SEG",)),),
            "BODY_CHAIN": (
                production_from_symbols(("BODY_SEG", "MISSING_RHS")),
            ),
        }
    )

    result = compile_rich_structural_rules(
        grammar,
        known_nodes={"S", "BODY_CHAIN", "BODY_SEG"},
    )

    assert result.compile_safe is False
    assert result.invalid_nodes.nodes == ("MISSING_RHS", "MISSING_LHS")


def test_compile_rich_structural_rules_loads_legacy_rules() -> None:
    result = compile_rich_structural_rules(
        {"S": ["BODY_CHAIN"], "BODY_CHAIN": ["BODY_SEG"]},
        known_nodes={"S", "BODY_CHAIN", "BODY_SEG"},
    )

    assert result == CompileResult(True)


def test_compile_rich_structural_rules_preserves_failure_for_empty_vocabulary() -> None:
    grammar = RichGrammar(
        productions={"S": (production_from_symbols(("BODY_CHAIN",)),)}
    )

    result = compile_rich_structural_rules(grammar, known_nodes=set())

    assert result.compile_safe is False
    assert result.invalid_nodes.error == {
        "error_type": "GrammarVocabularyUnavailable",
        "error_message": "GrammarNodes vocabulary is empty.",
    }


def test_to_legacy_first_productions_selects_first_rule_per_lhs() -> None:
    grammar = RichGrammar(
        productions={
            "S": (
                production_from_symbols(("BODY_CHAIN",)),
                production_from_symbols(("ALT_BODY",)),
            )
        }
    )

    assert grammar.to_legacy_first_productions() == {"S": ["BODY_CHAIN"]}
