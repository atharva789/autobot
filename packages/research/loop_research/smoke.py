"""Local smoke of the spec-012 loop: one evidence-dense model call, G1, run log.

No OpenAI credits exist yet, so this runs on local CLI-backed providers via the repo's existing
adapter (claude-code subscription auth or codex). It exercises the loop's first honest slice:
schema in -> scaffold out -> static gate -> committed run record. No MuJoCo, no revision loop yet.

Usage:
    python -m packages.research.loop_research.smoke \
        --schema evals/policy_synthesis/dev/dev-a.xml \
        --task "lift the payload to shelf height" \
        --provider claude-code --model haiku
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

from packages.research.local_chat_models import make_chat_model
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.scaffold import (
    CurriculumStage,
    ExperimentRun,
    Provenance,
    RandomizationRange,
    RewardTerm,
    Termination,
    TrainingScaffold,
)

_RUNS_ROOT = Path(".runs/loop_research")

_PROMPT = """You are designing an RL training scaffold for one specific robot.

Robot entities parsed from its schema (only these names exist; anything else will fail a static
resolution gate):
{entity_table}

Task: {task}

Symbol grammar — every "symbols" entry must be a dotted path in one of these exact forms:
- "joint.<name>" or "joint.<name>.qpos" or "joint.<name>.qvel" (scalar)
- "body.<name>.pos.x" / ".pos.y" / ".pos.z" (a body has no default; you must pick an axis)
- "site.<name>.pos.x" / ".pos.y" / ".pos.z" (same)
- "actuator.<name>" or "actuator.<name>.ctrl" or "actuator.<name>.force" (scalar)
- "sensor.<name>" (scalar, first channel)
- "const.<name>" (a runtime constant you name; never resolves against the schema, use sparingly)

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


def _parse_scaffold_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object in model output: {raw[:200]!r}")
    return json.loads(text[start : end + 1])


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _reward_terms(raw: list[dict]) -> tuple[RewardTerm, ...]:
    return tuple(
        RewardTerm(
            name=r["name"],
            weight=float(r["weight"]),
            expression=r["expression"],
            symbols=tuple(r.get("symbols", [])),
            rationale=r.get("rationale", ""),
        )
        for r in raw
    )


def _terminations(raw: list[dict]) -> tuple[Termination, ...]:
    return tuple(
        Termination(
            name=t["name"],
            predicate=t["predicate"],
            symbols=tuple(t.get("symbols", [])),
            cause_label=t.get("cause_label", t["name"]),
        )
        for t in raw
    )


def _curriculum(raw: list[dict]) -> tuple[CurriculumStage, ...]:
    return tuple(
        CurriculumStage(
            stage=int(c["stage"]),
            parameter=c["parameter"],
            range=(float(c["range"][0]), float(c["range"][1])),
            advance_when=c["advance_when"],
        )
        for c in raw
    )


def _randomization(raw: list[dict]) -> tuple[RandomizationRange, ...]:
    return tuple(
        RandomizationRange(
            parameter=r["parameter"],
            range=(float(r["range"][0]), float(r["range"][1])),
            distribution=r.get("distribution", "uniform"),
        )
        for r in raw
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--task", required=True)
    parser.add_argument("--provider", default="claude-code")
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    schema_bytes = args.schema.read_bytes()
    schema_digest = "sha256:" + hashlib.sha256(schema_bytes).hexdigest()
    _, entities = load_model_and_entities(args.schema)
    entity_lines = "\n".join(
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

    model = make_chat_model(args.model, provider=args.provider)
    if model is None:
        raise SystemExit(f"Provider {args.provider!r} did not resolve to a model.")

    started = time.time()
    reply = model.invoke(_PROMPT.format(entity_table=entity_lines, task=args.task))
    elapsed = time.time() - started
    parsed = _parse_scaffold_json(reply.content)

    scaffold = TrainingScaffold(
        scaffold_id=f"sc_{uuid.uuid4().hex[:12]}",
        schema_id=args.schema.stem,
        schema_digest=schema_digest,
        task_text=args.task,
        reward_terms=_reward_terms(parsed.get("reward_terms", [])),
        terminations=_terminations(parsed.get("terminations", [])),
        curriculum=_curriculum(parsed.get("curriculum", [])),
        randomization=_randomization(parsed.get("randomization", [])),
        provenance=Provenance(
            prompt_version="smoke-v1",
            model_id=f"{args.provider}/{args.model}",
            model_tier="cheap",
            seed=args.seed,
            cost_usd=0.0,
        ),
    )
    gate = run_g1(scaffold, entities)

    run = ExperimentRun(
        run_id=time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
        + f"_smoke_{uuid.uuid4().hex[:6]}",
        git_sha=_git_sha(),
        trigger="manual",
        status="completed",
        scaffolds=(scaffold.scaffold_id,),
        batches=(),
        gates=(gate,),
        cost={
            "usd_total": 0.0,
            "usd_ceiling": 0.0,
            "ceiling_hit": False,
            "note": "local substitute provider (subscription auth); no API spend",
        },
        replay={
            "schema_digest": schema_digest,
            "prompt_version": "smoke-v1",
            "model_id": f"{args.provider}/{args.model}",
            "seed": args.seed,
            "wall_clock_s": round(elapsed, 2),
        },
        control={"note": "negative control not yet implemented (build order step 4)"},
    )
    run_path = run.write(_RUNS_ROOT, [scaffold])

    print(f"run:      {run_path}")
    print(
        f"scaffold: {len(scaffold.reward_terms)} reward terms, "
        f"{len(scaffold.terminations)} terminations"
    )
    print(f"G1:       {'PASS' if gate.passed else 'FAIL'} (score {gate.score}, threshold {gate.threshold})")
    if gate.detail["unresolved"] or gate.detail["termination_unresolved"]:
        print(
            f"unresolved: {gate.detail['unresolved']} "
            f"terminations: {gate.detail['termination_unresolved']}"
        )
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
