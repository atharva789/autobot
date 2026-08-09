"""Step 7 -- the real loop (`scaffold_v1`), build order plan.md §7. Gate: "passes G1-G3 on dev
schemas." These tests exercise the loop deterministically against a stubbed model (no live CLI
call, no network, no wall-clock dependency on a real provider's latency) so they run in ordinary
CI. `step7_run.py` is what actually points this loop at the real local `claude-code` provider and
produces the committed run log the G1-G3 gate claim rests on.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from packages.research.loop_research import scaffold_loop
from packages.research.loop_research.baselines import DEV_A_SCHEMA
from packages.research.loop_research.scaffold_loop import (
    LoopCallError,
    ScaffoldLoopConfig,
    _generate_revision,
    run_scaffold_loop,
)

_TASK = "lift the payload to shelf height"


class _FakeReply:
    def __init__(self, content: str) -> None:
        self.content = content


def _initial_reply_json() -> dict:
    return {
        "reward_terms": [
            {
                "name": "lift",
                "weight": 0.5,
                "expression": "-abs(site.payload_center.pos.z - site.shelf_target.pos.z)",
                "symbols": ["site.payload_center.pos.z", "site.shelf_target.pos.z"],
                "rationale": "close the height gap to the shelf",
            },
            {
                "name": "grip",
                "weight": 0.2,
                "expression": "sensor.s_touch_left",
                "symbols": ["sensor.s_touch_left"],
                "rationale": "reward sustained contact",
            },
        ],
        "terminations": [
            {
                "name": "success",
                "predicate": "abs(site.payload_center.pos.z - site.shelf_target.pos.z) < 0.03",
                "symbols": ["site.payload_center.pos.z", "site.shelf_target.pos.z"],
                "cause_label": "success",
            }
        ],
        "curriculum": [
            {"stage": 0, "parameter": "payload_mass", "range": [0.3, 0.5], "advance_when": "success_rate > 0.6 over 32 episodes"}
        ],
        "randomization": [
            {"parameter": "friction.tangential", "range": [0.6, 1.2], "distribution": "uniform"}
        ],
    }


def _revision_reply_json(*, restructure_required: bool = False) -> dict:
    return {
        "diagnosis": "most episodes timed out without contact; reach term is too weak",
        "restructure_required": restructure_required,
        "self_check": "every symbol below exists in the entity table",
        **_initial_reply_json(),
    }


def _stub_model(reply_json: dict):
    model = object.__new__(object)
    model.invoke = lambda prompt: _FakeReply(json.dumps(reply_json))
    return model


def test_c1_no_task_text_branching_in_loop_source() -> None:
    """Static guard on top of G2/G3's behavioral one: `task_text` must never appear on an
    `if`/`elif` line -- loop-contract.md C1, "a `if \"lift\" in task_text:` is a spec violation."""

    source = inspect.getsource(scaffold_loop)
    offending = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("if ", "elif ")) and "task_text" in line
    ]
    assert offending == []


def test_run_completes_one_revision_against_a_stubbed_model() -> None:
    """Happy path: initial generation, one rollout, one revision call, all compiling against
    dev-a. Proves R2 (the revision carries motivating_batch_id), C4, and that the loop's own
    plumbing (parse -> construct -> compile -> rollout -> revise) works end to end."""

    config = ScaffoldLoopConfig(max_revisions=1, episodes_per_batch=2, step_budget=40, seed=0)

    calls = [_initial_reply_json(), _revision_reply_json()]

    def fake_invoke(provider_model: str, prompt: str) -> str:
        return json.dumps(calls.pop(0))

    with patch.object(scaffold_loop, "_invoke", side_effect=fake_invoke):
        result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=config)

    assert result.status == "completed"
    assert len(result.scaffolds) == 2
    assert len(result.batches) == 1

    initial, revised = result.scaffolds
    assert initial.parent_scaffold_id is None
    assert initial.motivating_batch_id is None
    assert revised.parent_scaffold_id == initial.scaffold_id
    assert revised.motivating_batch_id == result.batches[0].batch_id
    assert result.cost["calls_by_tier"]["cheap"] == 2
    assert result.cost["calls_by_tier"]["frontier"] == 0


def test_restructure_required_escalates_to_frontier_tier() -> None:
    """C6: escalation happens only when the cheap-tier reply itself asks for it, and costs one
    extra call for that revision -- logged, not silent."""

    replies = iter(
        [
            ("claude-code/haiku", json.dumps(_revision_reply_json(restructure_required=True))),
            ("claude-code/sonnet", json.dumps(_revision_reply_json(restructure_required=False))),
        ]
    )

    def fake_invoke(provider_model: str, prompt: str) -> str:
        expected_provider, content = next(replies)
        assert provider_model == expected_provider
        return content

    config = ScaffoldLoopConfig()
    with patch.object(scaffold_loop, "_invoke", side_effect=fake_invoke):
        parsed, tier, calls = _generate_revision("prompt", config, allow_escalation=True)

    assert tier == "frontier"
    assert calls == ["cheap", "frontier"]
    assert parsed["restructure_required"] is False


def test_restructure_required_ignored_when_escalation_disallowed() -> None:
    """Revision 0 (the initial generation) has no diagnosis to escalate from -- `allow_escalation`
    is False there regardless of what the reply claims."""

    def fake_invoke(provider_model: str, prompt: str) -> str:
        assert provider_model == "claude-code/haiku"
        return json.dumps(_revision_reply_json(restructure_required=True))

    config = ScaffoldLoopConfig()
    with patch.object(scaffold_loop, "_invoke", side_effect=fake_invoke):
        parsed, tier, calls = _generate_revision("prompt", config, allow_escalation=False)

    assert tier == "cheap"
    assert calls == ["cheap"]


def test_cost_ceiling_aborts_before_any_call() -> None:
    """C5: usd_ceiling is checked before every call. A pre-exhausted ceiling (0.0, the honest
    starting balance) aborts immediately with zero scaffolds and no call made -- never raises."""

    config = ScaffoldLoopConfig(usd_ceiling=0.0)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("must not call the model once the ceiling is already exhausted")

    with patch.object(scaffold_loop, "_invoke", side_effect=fail_if_called):
        result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=config)

    assert result.status == "aborted_cost"
    assert result.scaffolds == ()
    assert result.batches == ()
    assert result.cost["ceiling_hit"] is True


def test_malformed_reply_aborts_with_error_status_not_an_exception() -> None:
    """A model call that returns unparseable content is a `LoopCallError`/parse failure the loop
    must record, not propagate -- C5's "never raises" spirit applies to any expected failure mode,
    not only the cost ceiling."""

    config = ScaffoldLoopConfig()

    with patch.object(scaffold_loop, "_invoke", return_value="not json at all"):
        result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=config)

    assert result.status == "aborted_error"
    assert result.scaffolds == ()
    assert "error" in result.cost


def test_fabricated_symbol_reply_aborts_at_compile_not_recorded() -> None:
    """spec.md §3: "compiles to a MuJoCo environment or it is rejected." A reply citing an entity
    that doesn't exist on this schema must not be recorded as a scaffold at all."""

    bad = _initial_reply_json()
    bad["reward_terms"][0]["expression"] = "body.torso.pos.z"
    bad["reward_terms"][0]["symbols"] = ["body.torso.pos.z"]

    config = ScaffoldLoopConfig()
    with patch.object(scaffold_loop, "_invoke", return_value=json.dumps(bad)):
        result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=config)

    assert result.status == "aborted_error"
    assert result.scaffolds == ()
    assert "compile" in result.cost["error"]


def test_whitelist_violating_expression_aborts_gracefully_not_a_crash() -> None:
    """Regression: `expr.py` raises `ExpressionError` (a `ValueError` sibling of
    `CompilationError`, not a subclass of it) for a function name outside its whitelist
    (abs/clamp/max/min). Found running this loop for real against dev-b -- a live reply used a
    function outside that set and crashed the whole script uncaught, because only
    `CompilationError` was caught at the compile-check site."""

    bad = _initial_reply_json()
    bad["reward_terms"][0]["expression"] = "sqrt(site.payload_center.pos.z)"
    bad["reward_terms"][0]["symbols"] = ["site.payload_center.pos.z"]

    config = ScaffoldLoopConfig()
    with patch.object(scaffold_loop, "_invoke", return_value=json.dumps(bad)):
        result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=config)

    assert result.status == "aborted_error"
    assert result.scaffolds == ()
    assert "compile" in result.cost["error"]


def test_provider_resolution_failure_raises_loop_call_error() -> None:
    with pytest.raises(LoopCallError):
        scaffold_loop._invoke("not-a-valid-spec", "prompt")


def test_unbound_const_reference_aborts_gracefully_not_a_crash() -> None:
    """Regression: `mujoco_compiler.compile_scaffold`'s construction only compiles an
    expression's syntax tree, it does not evaluate it -- a reward term citing `const.*` with no
    matching `randomization` entry passes construction and only raises on the first real
    `.step()`, deep inside a rollout with no enclosing try/except. Found while running this loop
    for real against dev-a (a live reply referenced `const.table_height` with no randomization
    entry for it) -- without this check the loop crashes instead of recording an honest
    `aborted_error` for that revision."""

    bad = _initial_reply_json()
    bad["reward_terms"][0]["expression"] = "const.table_height - site.payload_center.pos.z"
    bad["reward_terms"][0]["symbols"] = ["const.table_height", "site.payload_center.pos.z"]

    config = ScaffoldLoopConfig()
    with patch.object(scaffold_loop, "_invoke", return_value=json.dumps(bad)):
        result = run_scaffold_loop(DEV_A_SCHEMA, _TASK, config=config)

    assert result.status == "aborted_error"
    assert result.scaffolds == ()
    assert "compile" in result.cost["error"]
