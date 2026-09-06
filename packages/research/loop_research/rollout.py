"""Runs episodes against a CompiledScaffold and reduces them to a RolloutBatch.

R3 forbids collapsing a batch to a bare scalar: this module always returns the structured
termination histogram, contact events, and joint saturation the loop needs to diagnose *why*
episodes ended, not just how well they scored.
"""

from __future__ import annotations

import random
import time
from typing import Callable, Mapping

import mujoco
import numpy as np

from packages.research.loop_research.mujoco_compiler import CompiledScaffold
from packages.research.loop_research.scaffold import RolloutBatch, TrainingScaffold
from packages.research.loop_research.symbols import parse_symbol

Policy = Callable[[Mapping[str, float], int], np.ndarray]

_SATURATION_TOL = 1e-3


def sample_constants(scaffold: TrainingScaffold, rng: random.Random) -> dict[str, float]:
    """Samples `const.*` randomization entries. Physical-field ranges are parsed but not applied —
    see the module docstring in mujoco_compiler.py."""

    sampled: dict[str, float] = {}
    for entry in scaffold.randomization:
        try:
            symbol = parse_symbol(entry.parameter)
        except ValueError:
            continue
        if symbol.kind != "const":
            continue
        low, high = entry.range
        sampled[symbol.entity] = rng.uniform(low, high)
    return sampled


def _limited_joint_names(model: mujoco.MjModel) -> list[str]:
    names = []
    for i in range(model.njnt):
        if model.jnt_limited[i]:
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i)
            if name:
                names.append(name)
    return names


def run_episode(
    compiled: CompiledScaffold,
    policy: Policy,
    *,
    max_steps: int,
    constants: Mapping[str, float],
) -> tuple[str, dict[str, int], dict[str, float]]:
    """Returns (termination_cause, contact_events, per-joint fraction-of-steps-at-limit)."""

    compiled.reset()
    limited = _limited_joint_names(compiled.model)
    at_limit = {name: 0 for name in limited}
    contacts: dict[str, int] = {}
    cause = "timeout"

    for step in range(max_steps):
        ctrl = policy(constants, step)
        outcome = compiled.step(np.asarray(ctrl, dtype=float), constants)
        for key, count in outcome.contacts.items():
            contacts[key] = contacts.get(key, 0) + count
        for name in limited:
            qpos = compiled.data.joint(name).qpos[0]
            lo, hi = compiled.model.jnt_range[mujoco.mj_name2id(compiled.model, mujoco.mjtObj.mjOBJ_JOINT, name)]
            if abs(qpos - lo) < _SATURATION_TOL or abs(qpos - hi) < _SATURATION_TOL:
                at_limit[name] += 1
        if outcome.done:
            cause = outcome.cause or "unlabeled"
            steps_taken = step + 1
            break
    else:
        steps_taken = max_steps

    saturation = {name: at_limit[name] / steps_taken for name in limited}
    return cause, contacts, saturation


def run_batch(
    scaffold: TrainingScaffold,
    model: mujoco.MjModel,
    compiled_factory: Callable[[], CompiledScaffold],
    policy: Policy,
    *,
    batch_id: str,
    episodes: int,
    max_steps: int,
    seed: int,
) -> RolloutBatch:
    rng = random.Random(seed)
    histogram: dict[str, int] = {}
    contact_totals: dict[str, int] = {}
    saturation_totals: dict[str, list[float]] = {}
    started = time.perf_counter()

    for _ in range(episodes):
        compiled = compiled_factory()
        constants = sample_constants(scaffold, rng)
        cause, contacts, saturation = run_episode(
            compiled, policy, max_steps=max_steps, constants=constants
        )
        histogram[cause] = histogram.get(cause, 0) + 1
        for key, count in contacts.items():
            contact_totals[key] = contact_totals.get(key, 0) + count
        for name, frac in saturation.items():
            saturation_totals.setdefault(name, []).append(frac)

    wall_clock_s = time.perf_counter() - started
    success_rate = histogram.get("success", 0) / episodes
    joint_saturation = {
        name: sum(fracs) / len(fracs) for name, fracs in saturation_totals.items()
    }

    return RolloutBatch(
        batch_id=batch_id,
        scaffold_id=scaffold.scaffold_id,
        episodes=episodes,
        step_budget=max_steps,
        success_rate=success_rate,
        termination_histogram=histogram,
        contact_events=contact_totals,
        joint_saturation=joint_saturation,
        seed=seed,
        wall_clock_s=wall_clock_s,
    )


__all__ = ["Policy", "run_batch", "run_episode", "sample_constants"]
