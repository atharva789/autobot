"""Build-order step 4 tests (plan.md §7): "`static_scaffold_loop` negative control. Gate: fails
G1-G3; its margin sets tau."

eval-contract.md's required outcome table for the control:

  G1  Fail on every schema except dev-a
  G2  Fail on all four permutation classes (D = 0 by construction)
  G3  Fail (D = 0 across bodies)
  G4  Not run

G2/G3 need the structural diff D(a, b) (build-order step 5, not implemented yet), so this file
proves what is provable today: G1's pass/fail split exactly as the contract requires, and the
schema/task-blindness that makes D = 0 inevitable once D exists -- without asserting a numeric
G2/G3 score that hasn't been computed by anything.
"""

from __future__ import annotations

from packages.research.loop_research.baselines import DEV_A_SCHEMA, DEV_B_SCHEMA
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.mujoco_compiler import CompilationError, compile_scaffold
from packages.research.loop_research.static_scaffold_loop import run_static_scaffold_loop


def test_control_ignores_schema_and_task_text():
    """The control's entire purpose: its output must not depend on its inputs."""

    a = run_static_scaffold_loop(DEV_A_SCHEMA, "lift the payload to shelf height")
    b = run_static_scaffold_loop(DEV_B_SCHEMA, "an entirely different task description")
    assert a is b
    assert a.scaffold_id == b.scaffold_id
    assert a.reward_terms == b.reward_terms
    assert a.terminations == b.terminations


def test_control_output_is_schema_blind_so_d_is_zero_by_construction():
    """G2/G3's structural diff D(a, b) is 0.40*jaccard(term_names) + 0.25*jaccard(symbol_set) +
    0.20*jaccard(termination_causes) + 0.15*weight_distance (eval-contract.md). Every one of those
    inputs is identical between any two calls to the control (proved above), so every term of D
    evaluates to 0 regardless of how D is implemented -- this does not require step 5 to exist to
    be true, only to be *measured* as a run.json number, which this test does not claim."""

    a = run_static_scaffold_loop(DEV_A_SCHEMA, "lift the payload to shelf height")
    b = run_static_scaffold_loop(DEV_B_SCHEMA, "lift the payload to shelf height")

    assert {t.name for t in a.reward_terms} == {t.name for t in b.reward_terms}
    assert {s for t in a.reward_terms for s in t.symbols} == {s for t in b.reward_terms for s in t.symbols}
    assert {t.cause_label for t in a.terminations} == {t.cause_label for t in b.terminations}
    assert {t.name: t.weight for t in a.reward_terms} == {t.name: t.weight for t in b.reward_terms}


def test_control_g1_passes_on_dev_a():
    """Required outcome: the control's fixed symbols were hand-tuned for dev-a, so G1 must pass
    there -- otherwise the control isn't "hand-tuned for dev-a", it's just broken."""

    scaffold = run_static_scaffold_loop(DEV_A_SCHEMA, "lift the payload to shelf height")
    _, entities = load_model_and_entities(DEV_A_SCHEMA)
    gate = run_g1(scaffold, entities)
    assert gate.passed
    assert gate.score == 1.0


def test_control_g1_fails_on_dev_b():
    """Required outcome (eval-contract.md): "G1 Fail on every schema except dev-a -- its symbols
    only exist in dev-a." dev-b shares some site names with dev-a by baselines.py's own design
    (grip_center, payload_center, shelf_target), but the control deliberately avoids those and
    uses dev-a's serial-arm-specific joint/body/actuator names instead, none of which exist on
    dev-b's gantry -- so this must fail completely, not just dip below threshold."""

    scaffold = run_static_scaffold_loop(DEV_B_SCHEMA, "lift the payload to shelf height")
    _, entities = load_model_and_entities(DEV_B_SCHEMA)
    gate = run_g1(scaffold, entities)
    assert not gate.passed
    assert gate.score == 0.0
    assert gate.detail["resolved"] == 0


def test_control_compiles_against_dev_a_but_not_dev_b():
    """Corroborates the G1 result at the compiler level (spec.md §3: "a scaffold compiles to a
    MuJoCo environment or it is rejected"): the same fixed scaffold that produces a real,
    steppable environment for dev-a raises CompilationError against dev-b, because none of its
    declared symbols resolve."""

    scaffold = run_static_scaffold_loop(DEV_A_SCHEMA, "lift the payload to shelf height")

    model_a, entities_a = load_model_and_entities(DEV_A_SCHEMA)
    compile_scaffold(scaffold, model_a, entities_a)  # must not raise

    model_b, entities_b = load_model_and_entities(DEV_B_SCHEMA)
    try:
        compile_scaffold(scaffold, model_b, entities_b)
        raised = False
    except CompilationError:
        raised = True
    assert raised
