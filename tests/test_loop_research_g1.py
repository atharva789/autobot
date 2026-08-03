"""G1 gate tests — spec 012, contracts/eval-contract.md.

The gate is only trustworthy if it demonstrably fails scaffolds that fabricate entities, which is
the negative-control property everything else builds on. Runs against the real locked dev-a schema
(evals/policy_synthesis/dev/dev-a.xml), not a throwaway fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.scaffold import (
    Provenance,
    RewardTerm,
    Termination,
    TrainingScaffold,
)

SCHEMA = Path("evals/policy_synthesis/dev/dev-a.xml")


def _scaffold(reward_terms, terminations) -> TrainingScaffold:
    return TrainingScaffold(
        scaffold_id="sc_test",
        schema_id="dev-a",
        schema_digest="sha256:test",
        task_text="lift the payload",
        reward_terms=tuple(
            RewardTerm(name=r["name"], weight=1.0, expression="1", symbols=tuple(r["symbols"]), rationale="")
            for r in reward_terms
        ),
        terminations=tuple(
            Termination(name=t["name"], predicate="1", symbols=tuple(t["symbols"]), cause_label=t["name"])
            for t in terminations
        ),
        curriculum=(),
        randomization=(),
        provenance=Provenance(prompt_version="test", model_id="test", model_tier="cheap", seed=1),
    )


def test_entity_table_reads_real_schema() -> None:
    _, entities = load_model_and_entities(SCHEMA)
    assert "j_elbow" in entities.joints
    assert "grip_center" in entities.sites
    assert "m_shoulder" in entities.actuators
    assert "s_touch_left" in entities.sensors
    assert "payload" in entities.bodies


def test_g1_passes_grounded_scaffold() -> None:
    _, entities = load_model_and_entities(SCHEMA)
    gate = run_g1(
        _scaffold(
            reward_terms=[
                {"name": "lift", "symbols": ["body.payload", "site.shelf_target"]},
                {"name": "grip", "symbols": ["sensor.s_touch_left"]},
            ],
            terminations=[{"name": "drop", "symbols": ["body.payload"]}],
        ),
        entities,
    )
    assert gate.passed
    assert gate.score == 1.0


def test_g1_fails_fabricated_entities() -> None:
    """The static_scaffold_loop cheat: plausible names that do not exist here."""
    _, entities = load_model_and_entities(SCHEMA)
    gate = run_g1(
        _scaffold(
            reward_terms=[
                {"name": "lift", "symbols": ["body.torso", "joint.j_hip"]},
                {"name": "alive", "symbols": ["const.alive_bonus"]},
            ],
            terminations=[{"name": "fall", "symbols": ["body.torso"]}],
        ),
        entities,
    )
    assert not gate.passed
    assert gate.score == 0.0
    assert "body.torso" in gate.detail["termination_unresolved"]


def test_g1_holds_terminations_to_100_percent() -> None:
    """80% reward-term resolution is fine; one bad termination is not."""
    _, entities = load_model_and_entities(SCHEMA)
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
        entities,
    )
    assert gate.score >= 0.8
    assert not gate.passed  # the termination sinks it regardless


def test_empty_scaffold_rejected_at_construction() -> None:
    """TrainingScaffold itself requires >=1 reward term and termination (scaffold.py), a
    stronger, earlier guarantee than G1 needing to catch an empty scaffold at gate time."""

    with pytest.raises(ValueError):
        _scaffold([], [])


def test_g1_resolves_multi_level_symbols_by_entity_not_full_string() -> None:
    """A dotted attribute suffix (body.payload.pos.z) still resolves — G1 checks the entity
    exists, not the full string; attribute-path validity is the compiler's concern
    (mujoco_compiler rejects an unresolvable attribute suffix at compile time, not G1's job)."""

    _, entities = load_model_and_entities(SCHEMA)
    gate = run_g1(
        _scaffold(
            reward_terms=[{"name": "lift", "symbols": ["body.payload.pos.z"]}],
            terminations=[{"name": "drop", "symbols": ["body.payload.pos.z"]}],
        ),
        entities,
    )
    assert gate.passed


def test_r2_revision_requires_motivating_batch() -> None:
    with pytest.raises(ValueError, match="R2"):
        TrainingScaffold(
            scaffold_id="sc_child",
            schema_id="dev-a",
            schema_digest="sha256:x",
            task_text="t",
            reward_terms=(RewardTerm("r", 1.0, "1", ("const.c",), ""),),
            terminations=(Termination("t", "1", ("const.c",), "t"),),
            curriculum=(),
            randomization=(),
            provenance=Provenance(prompt_version="test", model_id="test", model_tier="cheap", seed=1),
            parent_scaffold_id="sc_parent",
            motivating_batch_id=None,
        )
