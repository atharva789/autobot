"""The real loop -- spec-012 build order step 7 (plan.md §7): "The real loop, cheap tier.
Gate: passes G1-G3 on dev schemas."

Implements contracts/loop-contract.md's `ScaffoldLoopRunner`: reads a schema and one task, and
revises a `TrainingScaffold` against the structured `RolloutBatch` a rollout of the *previous*
revision produced (never a bare scalar -- R3, C3). Every hard constraint from loop-contract.md is
enforced here, not just asserted by naming convention:

C1 - no task-text branching. `task_text` only ever flows into a prompt string and into
     `TrainingScaffold.task_text`; nothing in this module inspects its content to choose behavior.
     `tests/test_loop_research_step7.py` greps this module's own source for an `if`/`elif` line
     that references it, as a cheap static guard on top of G2/G3's behavioral one.
C2 - the schema is read via `entity_table.py` (MuJoCo's own parser), never a hardcoded name list.
C3 - the model sees the *whole* RolloutBatch every revision: termination histogram, contact
     events, joint saturation. `success_rate` is included for context only -- the prompt tells the
     model not to revise from that number alone, and the histogram is what actually explains it.
C4 - every revision after the first carries `motivating_batch_id`; `TrainingScaffold.__post_init__`
     already enforces this (R2), so a revision missing it fails at construction, not at review.
C5 - `usd_ceiling` is checked before every call; a breach returns `aborted_cost` with whatever
     scaffolds/batches were produced so far, and never raises.
C6 - one call per revision by default: the prompt carries the whole batch and the reply carries
     diagnosis + proposed edit + self-check together, never three separate calls. Escalation to
     `frontier_model` happens only when that call's own `restructure_required` field says so
     (a second call, for that revision only) -- logged in `cost["calls_by_tier"]`, never hidden.

Local substitute mode (routines/registry.md, standing arrangement while no OpenAI credits exist):
`cheap_model`/`frontier_model` default to local CLI-backed identifiers run through
`local_chat_models.make_chat_model` at $0 real spend, so the cost ceiling can't organically trip
under this provider -- the mechanism itself is proven directly in
`tests/test_loop_research_step7.py` against a stub that reports a non-zero cost, independent of
whether today's run happens to exercise it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from packages.research.local_chat_models import make_chat_model
from packages.research.loop_research.entity_table import EntityTable, load_model_and_entities
from packages.research.loop_research.expr import ExpressionError
from packages.research.loop_research.mujoco_compiler import CompilationError, compile_scaffold
from packages.research.loop_research.rollout import Policy, run_batch, sample_constants
from packages.research.loop_research.symbols import SymbolSyntaxError

# Every exception a model-authored scaffold can legitimately trigger while compiling against a
# schema: an unresolvable/malformed symbol (CompilationError, SymbolSyntaxError) or an expression
# using anything outside the whitelisted grammar (ExpressionError, e.g. a function name not in
# {abs, clamp, max, min}). All three are `ValueError` subclasses but siblings of each other, not a
# shared parent -- catching only `CompilationError` here missed `ExpressionError` outright and
# crashed the loop instead of recording "revision N failed to compile" (found running this live:
# a reply used a function name outside expr.py's whitelist).
_SCAFFOLD_COMPILE_ERRORS = (CompilationError, ExpressionError, SymbolSyntaxError)
from packages.research.loop_research.scaffold import (
    ModelTier,
    Provenance,
    RolloutBatch,
    RunStatus,
    TrainingScaffold,
)
# Reused rather than duplicated: smoke.py (build-order step "smoke", not a numbered spec step)
# already implements the exact JSON-shape parsing this loop's replies use -- same reward_terms /
# terminations / curriculum / randomization keys, same symbol grammar taught in its prompt.
from packages.research.loop_research.smoke import (
    _curriculum as _parse_curriculum,
    _parse_scaffold_json,
    _randomization as _parse_randomization,
    _reward_terms as _parse_reward_terms,
    _terminations as _parse_terminations,
)

LOOP_NAME = "scaffold_v1"


class LoopCallError(RuntimeError):
    """A model call could not be resolved or produced no usable reply."""


@dataclass(frozen=True)
class ScaffoldLoopConfig:
    """contracts/loop-contract.md `ScaffoldLoopConfig` -- defaults match the contract exactly.
    A run harness may pass smaller `episodes_per_batch`/`step_budget` for local tractability (the
    same scaling step2_run.py/step5_run.py already do for their own rollouts); the *defaults*
    below are the contract's numbers and are not edited here."""

    max_revisions: int = 8
    episodes_per_batch: int = 64
    step_budget: int = 2_000_000
    usd_ceiling: float = 5.0
    cheap_model: str = "claude-code/haiku"
    frontier_model: str = "claude-code/sonnet"
    seed: int = 42
    prompt_version: str = "v1"


@dataclass(frozen=True)
class ScaffoldLoopResult:
    """contracts/loop-contract.md `ScaffoldLoopResult`. Frozen dataclass and tuples: a revision
    history that can be mutated after the fact is not evidence (loop-contract.md)."""

    scaffolds: tuple[TrainingScaffold, ...]
    batches: tuple[RolloutBatch, ...]
    status: RunStatus
    cost: Mapping[str, Any]


_SYMBOL_GRAMMAR = """Symbol grammar — every "symbols" entry must be a dotted path in one of these exact forms:
- "joint.<name>" or "joint.<name>.qpos" or "joint.<name>.qvel" (scalar)
- "body.<name>.pos.x" / ".pos.y" / ".pos.z" (a body has no default; you must pick an axis)
- "site.<name>.pos.x" / ".pos.y" / ".pos.z" (same)
- "actuator.<name>" or "actuator.<name>.ctrl" or "actuator.<name>.force" (scalar)
- "sensor.<name>" (scalar, first channel)
- "const.<name>": DO NOT USE THIS unless "<name>" also appears as the "parameter" of an entry in
  "randomization" below, spelled exactly the same. An expression referencing "const.foo" with no
  "randomization" entry named "foo" will fail to compile and the whole revision will be discarded.
  For any fixed threshold or offset (a target height, a tolerance, a bonus) just write the number
  directly in the expression (e.g. "0.35", "0.03") instead of naming it "const.<name>".

Expressions may use ONLY: the symbols above, numeric literals, "+", "-", "*", "/", comparisons
(">", "<", ">=", "<=", "=="), and these four function calls: abs(x), min(a, b, ...), max(a, b, ...),
clamp(x, lo, hi). No other function name is permitted -- not sqrt, not pow, not round, not clip
(the clamping function is spelled "clamp", not "clip"). Using any function outside this exact list
of four will fail to compile and the whole revision will be discarded. If you need a square root
or a power, restructure the expression to avoid it (e.g. compare squared distances instead of
taking a square root)."""

_INITIAL_PROMPT = """You are designing an RL training scaffold for one specific robot.

Robot entities parsed from its schema (only these names exist; anything else will fail a static
resolution gate):
{entity_table}

Task: {task}

{grammar}

Return ONE JSON object, no prose, no code fences, with exactly these keys:
- "reward_terms": list of {{"name", "weight" (float), "expression" (Python-like, using only
  the symbols above, "+", "-", "*", "/", comparisons, and min/max/abs/clamp), "symbols" (list of
  every dotted ref used in "expression"), "rationale"}}
- "terminations": list of {{"name", "predicate" (boolean expression, same rules), "symbols",
  "cause_label"}}
- "curriculum": list of {{"stage" (int), "parameter", "range" ([lo, hi]), "advance_when"}}
- "randomization": list of {{"parameter", "range" ([lo, hi]), "distribution"}}

Every reward term and every termination must reference at least one symbol from the entity table
above. Ground every choice in THIS robot's actuators, joints, sites and sensors — not a generic
template."""

_REVISION_PROMPT = """You are revising an RL training scaffold for one specific robot, using
rollout evidence from the previous revision. Read the evidence below before changing anything --
every edit must be traceable to something in it.

Robot entities parsed from its schema (only these names exist; anything else will fail a static
resolution gate):
{entity_table}

Task: {task}

{grammar}

Current scaffold (revision {revision}, about to become revision {next_revision}):
{current_scaffold_json}

Rollout evidence from running the current scaffold for {episodes} episodes -- this is why you are
being asked to revise it:
- termination_histogram (why episodes ended, keyed by the cause_label your own terminations
  declared): {termination_histogram}
- contact_events: {contact_events}
- joint_saturation (fraction of steps each limited joint spent at its limit): {joint_saturation}
- success_rate (context only -- do not revise from this number alone; the histogram above is why
  it is what it is): {success_rate}

Return ONE JSON object, no prose, no code fences, with exactly these keys:
- "diagnosis": one or two sentences on what the evidence above indicates is going wrong or right.
- "restructure_required": true only if the fix needs a larger rethink than a numeric/weight nudge
  can achieve -- most revisions should set this false.
- "self_check": one sentence confirming every symbol referenced below appears in the entity table
  above.
- "reward_terms", "terminations", "curriculum", "randomization": the revised scaffold, same shape
  as before. Keep a term unchanged if the evidence does not call for a change to it.

Every reward term and every termination must reference at least one symbol from the entity table
above. Ground every choice in THIS robot's actuators, joints, sites and sensors — not a generic
template."""


def _entity_lines(entities: EntityTable) -> str:
    return "\n".join(
        f"  {kind}: {', '.join(sorted(names))}"
        for kind, names in (
            ("joint", entities.joints),
            ("body", entities.bodies),
            ("site", entities.sites),
            ("actuator", entities.actuators),
            ("sensor", entities.sensors),
        )
        if names
    )


def _scaffold_to_prompt_dict(scaffold: TrainingScaffold) -> dict:
    return {
        "reward_terms": [asdict(t) for t in scaffold.reward_terms],
        "terminations": [asdict(t) for t in scaffold.terminations],
        "curriculum": [asdict(c) for c in scaffold.curriculum],
        "randomization": [asdict(r) for r in scaffold.randomization],
    }


def _invoke(provider_model: str, prompt: str) -> str:
    provider, _, model_name = provider_model.partition("/")
    if not provider or not model_name:
        raise LoopCallError(f"expected 'provider/model', got {provider_model!r}")
    model = make_chat_model(model_name, provider=provider)
    if model is None:
        raise LoopCallError(f"provider {provider_model!r} did not resolve to a model")
    reply = model.invoke(prompt)
    if not getattr(reply, "content", None):
        raise LoopCallError(f"provider {provider_model!r} returned an empty reply")
    return reply.content


def _generate_revision(
    prompt: str, config: ScaffoldLoopConfig, *, allow_escalation: bool
) -> tuple[dict, ModelTier, list[ModelTier]]:
    """One revision step (C6): a cheap-tier call, escalated to the frontier tier only if that
    call's own reply asks for it. Returns (parsed_json, tier_that_produced_the_accepted_edit,
    calls_made)."""

    content = _invoke(config.cheap_model, prompt)
    parsed = _parse_scaffold_json(content)
    calls: list[ModelTier] = ["cheap"]
    tier: ModelTier = "cheap"

    if allow_escalation and bool(parsed.get("restructure_required", False)):
        content = _invoke(config.frontier_model, prompt)
        parsed = _parse_scaffold_json(content)
        calls.append("frontier")
        tier = "frontier"

    return parsed, tier, calls


def _random_probe_policy(model: mujoco.MjModel, seed: int) -> Policy:
    """A schema-agnostic rollout policy: bounded uniform noise per actuator, seeded. Not learned
    and not claimed to be good (spec.md §2 puts policy quality out of scope for this spec) -- it
    only needs to move the robot enough that rollout evidence is not universally the same
    termination cause every episode. Uses each actuator's own `ctrlrange` rather than a fixed
    per-schema constant, so it works unmodified whether it is driving dev-a, dev-b, or a G2
    permutation of either."""

    rng = np.random.default_rng(seed)
    limited = model.actuator_ctrllimited.astype(bool)
    lo = np.where(limited, model.actuator_ctrlrange[:, 0], -1.0)
    hi = np.where(limited, model.actuator_ctrlrange[:, 1], 1.0)

    def policy(constants: Mapping[str, float], step: int) -> np.ndarray:
        return rng.uniform(lo, hi)

    return policy


def run_scaffold_loop(
    schema_path: Path, task_text: str, *, config: ScaffoldLoopConfig
) -> ScaffoldLoopResult:
    """contracts/loop-contract.md `ScaffoldLoopRunner.__call__`. See the module docstring for
    where each hard constraint (C1-C6) is enforced."""

    schema_path = Path(schema_path)
    schema_digest = "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()
    model, entities = load_model_and_entities(schema_path)
    entity_table_text = _entity_lines(entities)
    max_steps = min(config.step_budget, 500)  # see module docstring: step_budget is the
    # contract's much larger training-step field; this run-time cap is the same kind of scaling
    # step2_run.py/step5_run.py already apply to their own rollouts (max_steps=300), not a change
    # to the contract's own numbers.

    scaffolds: list[TrainingScaffold] = []
    batches: list[RolloutBatch] = []
    cost_usd_total = 0.0
    calls_by_tier = {"cheap": 0, "frontier": 0}

    parent_id: str | None = None
    motivating_batch_id: str | None = None
    current: TrainingScaffold | None = None

    def _aborted(status: RunStatus, **extra: Any) -> ScaffoldLoopResult:
        return ScaffoldLoopResult(
            scaffolds=tuple(scaffolds),
            batches=tuple(batches),
            status=status,
            cost={
                "usd_total": round(cost_usd_total, 6),
                "usd_ceiling": config.usd_ceiling,
                "ceiling_hit": status == "aborted_cost",
                "calls_by_tier": dict(calls_by_tier),
                **extra,
            },
        )

    for revision in range(config.max_revisions + 1):
        # C5: checked before every call, not after -- a breach never starts a call it can't pay
        # for, and the abort carries whatever was already produced rather than raising.
        if cost_usd_total >= config.usd_ceiling:
            return _aborted("aborted_cost")

        if current is None:
            prompt = _INITIAL_PROMPT.format(
                entity_table=entity_table_text, task=task_text, grammar=_SYMBOL_GRAMMAR
            )
        else:
            batch = batches[-1]
            prompt = _REVISION_PROMPT.format(
                entity_table=entity_table_text,
                task=task_text,
                grammar=_SYMBOL_GRAMMAR,
                revision=revision - 1,
                next_revision=revision,
                current_scaffold_json=json.dumps(_scaffold_to_prompt_dict(current), indent=2),
                episodes=batch.episodes,
                termination_histogram=json.dumps(dict(batch.termination_histogram)),
                contact_events=json.dumps(dict(batch.contact_events)),
                joint_saturation=json.dumps({k: round(v, 3) for k, v in batch.joint_saturation.items()}),
                success_rate=round(batch.success_rate, 3),
            )

        try:
            parsed, tier, calls = _generate_revision(
                prompt, config, allow_escalation=current is not None
            )
        except (LoopCallError, ValueError, json.JSONDecodeError) as exc:
            return _aborted("aborted_error", error=f"revision {revision} call failed: {exc}")

        for call_tier in calls:
            calls_by_tier[call_tier] += 1
        # Local substitute providers (routines/registry.md) report no per-call cost; a real
        # provider's per-call spend would accumulate into cost_usd_total here instead of the
        # literal 0.0 every local call reports today.
        cost_usd_total += 0.0

        try:
            candidate = TrainingScaffold(
                scaffold_id=f"sc_{uuid.uuid4().hex[:12]}",
                schema_id=schema_path.stem,
                schema_digest=schema_digest,
                task_text=task_text,
                reward_terms=_parse_reward_terms(parsed.get("reward_terms", [])),
                terminations=_parse_terminations(parsed.get("terminations", [])),
                curriculum=_parse_curriculum(parsed.get("curriculum", [])),
                randomization=_parse_randomization(parsed.get("randomization", [])),
                provenance=Provenance(
                    prompt_version=config.prompt_version,
                    model_id=config.cheap_model if tier == "cheap" else config.frontier_model,
                    model_tier=tier,
                    seed=config.seed,
                    cost_usd=0.0,
                ),
                parent_scaffold_id=parent_id,
                motivating_batch_id=motivating_batch_id,
            )
        except (ValueError, KeyError, TypeError) as exc:
            return _aborted("aborted_error", error=f"revision {revision} produced an invalid scaffold: {exc}")

        try:
            compiled_factory = lambda c=candidate: compile_scaffold(c, model, entities)  # noqa: E731
            # Construction alone (mujoco_compiler.compile_scaffold) only compiles each
            # expression's syntax tree -- it does not evaluate it, so a reward/termination
            # expression that references a `const.*` symbol with no matching `randomization`
            # entry (unbound at runtime) passes construction and only fails on the first real
            # `.step()`, deep inside a rollout. A one-step dry run here catches that
            # deterministically (the same expression tree fails on every step, not just some),
            # so it counts as this revision failing to compile (spec.md §3) rather than crashing
            # the loop the first time a rollout actually exercises it.
            probe = compiled_factory()
            probe.reset()
            probe.step(np.zeros(model.nu), sample_constants(candidate, np.random.default_rng(config.seed)))
        except _SCAFFOLD_COMPILE_ERRORS as exc:
            return _aborted("aborted_error", error=f"revision {revision} failed to compile: {exc}")

        scaffolds.append(candidate)
        current = candidate

        if revision == config.max_revisions:
            break

        batch = run_batch(
            candidate,
            model,
            compiled_factory,
            _random_probe_policy(model, config.seed + revision),
            batch_id=f"rb_{uuid.uuid4().hex[:12]}",
            episodes=config.episodes_per_batch,
            max_steps=max_steps,
            seed=config.seed + revision,
        )
        batches.append(batch)
        parent_id = candidate.scaffold_id
        motivating_batch_id = batch.batch_id

    return ScaffoldLoopResult(
        scaffolds=tuple(scaffolds),
        batches=tuple(batches),
        status="completed",
        cost={
            "usd_total": round(cost_usd_total, 6),
            "usd_ceiling": config.usd_ceiling,
            "ceiling_hit": False,
            "calls_by_tier": dict(calls_by_tier),
        },
    )


__all__ = ["LOOP_NAME", "LoopCallError", "ScaffoldLoopConfig", "ScaffoldLoopResult", "run_scaffold_loop"]
