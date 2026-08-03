"""G1 gate tests — spec 012, contracts/eval-contract.md.

The gate is only trustworthy if it demonstrably fails scaffolds that fabricate
entities, which is the negative-control property everything else builds on.
"""

from pathlib import Path

import pytest

from packages.research.loop_research.g1 import build_entity_table, run_g1
from packages.research.loop_research.records import TrainingScaffold

SCHEMA = Path("evals/policy_synthesis/dev/dev-a.xml")


def _scaffold(reward_terms, terminations) -> TrainingScaffold:
    return TrainingScaffold(
        scaffold_id="sc_test",
        schema_id="dev-a",
        schema_digest="sha256:test",
        task_text="lift the payload",
        reward_terms=tuple(reward_terms),
        terminations=tuple(terminations),
        curriculum=(),
        randomization=(),
        provenance={"prompt_version": "test"},
    )


def test_entity_table_reads_real_schema() -> None:
    table = build_entity_table(SCHEMA)
    assert "j_elbow" in table["joint"]
    assert "grip_center" in table["site"]
    assert "m_shoulder" in table["actuator"]
    assert "s_touch_left" in table["sensor"]
    assert "payload" in table["body"]


def test_g1_passes_grounded_scaffold() -> None:
    gate = run_g1(
        _scaffold(
            reward_terms=[
                {"name": "lift", "symbols": ["body.payload", "site.shelf_target"]},
                {"name": "grip", "symbols": ["sensor.s_touch_left"]},
            ],
            terminations=[{"name": "drop", "symbols": ["body.payload"]}],
        ),
        SCHEMA,
    )
    assert gate.passed
    assert gate.score == 1.0


def test_g1_fails_fabricated_entities() -> None:
    """The static_scaffold_loop cheat: plausible names that do not exist here."""
    gate = run_g1(
        _scaffold(
            reward_terms=[
                {"name": "lift", "symbols": ["body.torso", "joint.j_hip"]},
                {"name": "alive", "symbols": ["const.alive_bonus"]},
            ],
            terminations=[{"name": "fall", "symbols": ["body.torso"]}],
        ),
        SCHEMA,
    )
    assert not gate.passed
    assert gate.score == 0.0
    assert "body.torso" in gate.detail["termination_unresolved"]


def test_g1_holds_terminations_to_100_percent() -> None:
    """80% reward-term resolution is fine; one bad termination is not."""
    gate = run_g1(
        _scaffold(
            reward_terms=[
                {"name": "a", "symbols": ["body.payload"]},
                {"name": "b", "symbols": ["site.grip_center"]},
                {"name": "c", "symbols": ["joint.j_elbow"]},
                {"name": "d", "symbols": ["sensor.s_touch_left"]},
                {"name": "e", "symbols": ["const.magic"]},  # 4/5 = 0.8, at threshold
            ],
            terminations=[{"name": "bad", "symbols": ["body.imaginary"]}],
        ),
        SCHEMA,
    )
    assert gate.score >= 0.8
    assert not gate.passed  # the termination sinks it regardless


def test_g1_rejects_empty_scaffold() -> None:
    gate = run_g1(_scaffold([], []), SCHEMA)
    assert not gate.passed


def test_r2_revision_requires_motivating_batch() -> None:
    with pytest.raises(ValueError, match="R2"):
        TrainingScaffold(
            scaffold_id="sc_child",
            schema_id="dev-a",
            schema_digest="sha256:x",
            task_text="t",
            reward_terms=(),
            terminations=(),
            curriculum=(),
            randomization=(),
            provenance={},
            parent_scaffold_id="sc_parent",
            motivating_batch_id=None,
        )
