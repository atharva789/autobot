"""TrainingScaffold and RolloutBatch records.

Shape follows specs/012-schema-conditioned-policy-synthesis/data-model.md exactly. Only the two
records step 1 of the build order needs (plan.md §7) are defined here; GateResult and
ExperimentRun belong to later steps (G1 static resolver, the orchestrator run log) and are added
when those steps are built, not speculatively.

All records are immutable: a revision never edits its predecessor, it references it (data-model.md
preamble). Frozen dataclasses and tuples throughout, mirroring
packages/pipeline/ir/design_ir.py and loop-contract.md's ScaffoldLoopResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

ModelTier = Literal["cheap", "frontier"]


@dataclass(frozen=True)
class RewardTerm:
    name: str
    weight: float
    expression: str
    symbols: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class Termination:
    name: str
    predicate: str
    symbols: tuple[str, ...]
    cause_label: str


@dataclass(frozen=True)
class CurriculumStage:
    stage: int
    parameter: str
    range: tuple[float, float]
    advance_when: str


@dataclass(frozen=True)
class RandomizationRange:
    parameter: str
    range: tuple[float, float]
    distribution: str


@dataclass(frozen=True)
class Provenance:
    prompt_version: str
    model_id: str
    model_tier: ModelTier
    seed: int
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class TrainingScaffold:
    """The loop's only output. Never a policy, never Python (spec.md §3)."""

    scaffold_id: str
    schema_id: str
    schema_digest: str
    task_text: str
    reward_terms: tuple[RewardTerm, ...]
    terminations: tuple[Termination, ...]
    curriculum: tuple[CurriculumStage, ...]
    randomization: tuple[RandomizationRange, ...]
    provenance: Provenance
    parent_scaffold_id: str | None = None
    motivating_batch_id: str | None = None

    def __post_init__(self) -> None:
        # data-model.md invariant 1 / spec.md R2: a revision with no antecedent evidence is
        # rejected at write time.
        if self.parent_scaffold_id is not None and self.motivating_batch_id is None:
            raise ValueError(
                "TrainingScaffold with a parent_scaffold_id must carry the motivating_batch_id "
                "that produced the revision (R2)."
            )
        if not self.reward_terms:
            raise ValueError("TrainingScaffold must declare at least one reward term.")
        if not self.terminations:
            raise ValueError("TrainingScaffold must declare at least one termination predicate.")


@dataclass(frozen=True)
class RolloutBatch:
    """What the simulator returns. R3 forbids collapsing this to a scalar."""

    batch_id: str
    scaffold_id: str
    episodes: int
    step_budget: int
    success_rate: float
    termination_histogram: Mapping[str, int]
    contact_events: Mapping[str, int]
    joint_saturation: Mapping[str, float]
    seed: int
    wall_clock_s: float
    trace_uri: str | None = None


__all__ = [
    "ModelTier",
    "RewardTerm",
    "Termination",
    "CurriculumStage",
    "RandomizationRange",
    "Provenance",
    "TrainingScaffold",
    "RolloutBatch",
]
