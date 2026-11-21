"""Tests for build-order step 1: TrainingScaffold schema + compiler-to-MuJoCo.

specs/012-schema-conditioned-policy-synthesis/plan.md §7 step 1 gate: "a hand-written scaffold
trains". Interpreted here as: the compiled environment's reward and termination logic are causally
coupled to real MuJoCo physics (generous budget -> succeeds, starved budget -> does not), not that
literal policy-gradient training converges — training a policy is out of scope for the compiler
(spec.md §2 "Out of scope").
"""

from __future__ import annotations

import dataclasses

import pytest

from packages.research.loop_research.entity_table import load_model_and_entities_from_xml
from packages.research.loop_research.examples.hand_written_lift import (
    FIXTURE_MJCF,
    build_hand_written_lift_scaffold,
    target_height_policy,
)
from packages.research.loop_research.expr import ExpressionError, compile_expression
from packages.research.loop_research.mujoco_compiler import CompilationError, compile_scaffold
from packages.research.loop_research.rollout import run_batch
from packages.research.loop_research.scaffold import Provenance, RewardTerm, Termination, TrainingScaffold
from packages.research.loop_research.symbols import SymbolSyntaxError, parse_symbol


# --- symbol grammar ---------------------------------------------------------------------------


def test_parse_symbol_accepts_dotted_paths():
    symbol = parse_symbol("body.payload.pos.z")
    assert symbol.kind == "body"
    assert symbol.entity == "payload"
    assert symbol.attr_path == ("pos", "z")


def test_parse_symbol_rejects_unknown_kind():
    with pytest.raises(SymbolSyntaxError):
        parse_symbol("robot.payload")


def test_parse_symbol_rejects_bare_entity():
    with pytest.raises(SymbolSyntaxError):
        parse_symbol("body.")


# --- expression compiler -----------------------------------------------------------------------


class _StaticContext:
    def __init__(self, values):
        self._values = values

    def resolve(self, symbol):
        return self._values[symbol]


def test_expr_compiler_evaluates_whitelisted_forms():
    expr = compile_expression(
        "clamp(body.payload.pos.z / const.target_height, 0.0, 1.0)",
        declared_symbols=("body.payload.pos.z", "const.target_height"),
    )
    ctx = _StaticContext({"body.payload.pos.z": 0.3, "const.target_height": 0.6})
    assert expr(ctx) == pytest.approx(0.5)


def test_expr_compiler_rejects_undeclared_symbols():
    with pytest.raises(ExpressionError):
        compile_expression("const.sneaky", declared_symbols=("const.target_height",))


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('echo hi')",
        "body.payload.__class__",
        "eval('1')",
        "[x for x in range(3)]",
        "body.payload.pos.z if True else 0",
        "lambda: 1",
    ],
)
def test_expr_compiler_rejects_unsafe_constructs(source):
    with pytest.raises(ExpressionError):
        compile_expression(source)


# --- TrainingScaffold invariants -----------------------------------------------------------------


def _minimal_scaffold(**overrides) -> TrainingScaffold:
    fields = dict(
        scaffold_id="sc_test",
        schema_id="fixture-lift-v1",
        schema_digest="sha256:deadbeef",
        task_text="test",
        reward_terms=(RewardTerm("r", 1.0, "const.c", ("const.c",), "test"),),
        terminations=(Termination("t", "const.c > 0", ("const.c",), "success"),),
        curriculum=(),
        randomization=(),
        provenance=Provenance(prompt_version="v1", model_id="m", model_tier="cheap", seed=1),
    )
    fields.update(overrides)
    return TrainingScaffold(**fields)


def test_scaffold_rejects_revision_with_no_motivating_batch():
    with pytest.raises(ValueError):
        _minimal_scaffold(parent_scaffold_id="sc_parent", motivating_batch_id=None)


def test_scaffold_accepts_revision_with_motivating_batch():
    scaffold = _minimal_scaffold(parent_scaffold_id="sc_parent", motivating_batch_id="rb_1")
    assert scaffold.parent_scaffold_id == "sc_parent"


def test_scaffold_requires_at_least_one_reward_term():
    with pytest.raises(ValueError):
        _minimal_scaffold(reward_terms=())


# --- compiler ------------------------------------------------------------------------------------


def test_hand_written_scaffold_compiles_against_its_fixture():
    scaffold = build_hand_written_lift_scaffold()
    model, entities = load_model_and_entities_from_xml(FIXTURE_MJCF)
    assert entities.has("body", "payload")
    compile_scaffold(scaffold, model, entities)  # must not raise


def test_compiler_rejects_symbol_absent_from_schema():
    scaffold = build_hand_written_lift_scaffold()
    bad_reward = dataclasses.replace(
        scaffold.reward_terms[0],
        expression="clamp(body.nonexistent_body.pos.z / const.target_height, 0.0, 1.0)",
        symbols=("body.nonexistent_body.pos.z", "const.target_height"),
    )
    scaffold = dataclasses.replace(scaffold, reward_terms=(bad_reward,))
    model, entities = load_model_and_entities_from_xml(FIXTURE_MJCF)
    with pytest.raises(CompilationError):
        compile_scaffold(scaffold, model, entities)


# --- end-to-end rollout: physics causally drives the compiled reward/termination logic -----------


def _make_batch(*, episodes: int, max_steps: int, seed: int):
    scaffold = build_hand_written_lift_scaffold()
    model, entities = load_model_and_entities_from_xml(FIXTURE_MJCF)

    def factory():
        return compile_scaffold(scaffold, model, entities)

    return run_batch(
        scaffold,
        model,
        factory,
        target_height_policy,
        batch_id=f"rb_test_{seed}",
        episodes=episodes,
        max_steps=max_steps,
        seed=seed,
    )


def test_generous_step_budget_reaches_success_every_episode():
    batch = _make_batch(episodes=6, max_steps=2000, seed=42)
    assert batch.episodes == 6
    assert sum(batch.termination_histogram.values()) == 6
    assert batch.termination_histogram.get("success", 0) == 6
    assert batch.success_rate == pytest.approx(1.0)


def test_starved_step_budget_times_out_every_episode():
    batch = _make_batch(episodes=6, max_steps=3, seed=42)
    assert sum(batch.termination_histogram.values()) == 6
    assert batch.termination_histogram.get("timeout", 0) == 6
    assert batch.success_rate == pytest.approx(0.0)


def test_rollout_batch_reports_joint_saturation_key():
    batch = _make_batch(episodes=2, max_steps=50, seed=7)
    assert "j_lift" in batch.joint_saturation
    assert 0.0 <= batch.joint_saturation["j_lift"] <= 1.0
