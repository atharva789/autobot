"""The four records of spec 012, matching data-model.md exactly:
TrainingScaffold, RolloutBatch, GateResult, ExperimentRun. Invariant 6: the core stays at four
records — proposing a fifth requires folding one of these, argued in a spec increment.

All records are immutable: a revision never edits its predecessor, it references it (data-model.md
preamble). Frozen dataclasses and tuples throughout, mirroring
packages/pipeline/ir/design_ir.py and loop-contract.md's ScaffoldLoopResult.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

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


GateName = Literal["G1", "G2", "G3", "G4"]


@dataclass(frozen=True)
class GateResult:
    """One gate outcome. Recorded on pass and on fail (R4) — see contracts/eval-contract.md."""

    gate: GateName
    scaffold_id: str
    passed: bool
    score: float
    threshold: float
    detail: Mapping[str, Any]
    rubric_version: str = "v1"


RunStatus = Literal["completed", "aborted_cost", "aborted_error"]
RunTrigger = Literal["routine", "manual"]


@dataclass(frozen=True)
class ExperimentRun:
    """The committed record: one directory under .runs/loop_research/<run_id>/ (data-model.md
    "Files on disk"). `write()` persists it in that layout; `run.json` is the only file the daily
    routine is required to parse."""

    run_id: str
    git_sha: str
    trigger: RunTrigger
    status: RunStatus
    scaffolds: tuple[str, ...]
    batches: tuple[str, ...]
    gates: tuple[GateResult, ...]
    cost: Mapping[str, Any]
    replay: Mapping[str, Any]
    manifest_path: str | None = None
    control: Mapping[str, Any] = field(default_factory=dict)

    def write(self, root: Path, scaffolds: list[TrainingScaffold]) -> Path:
        run_dir = root / self.run_id
        if run_dir.exists():
            raise FileExistsError(f"Run history is append-only; {run_dir} already exists.")
        scaffold_dir = run_dir / "scaffolds"
        scaffold_dir.mkdir(parents=True)
        for record in scaffolds:
            path = scaffold_dir / f"{record.scaffold_id}.json"
            path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        (run_dir / "gates.json").write_text(
            json.dumps([asdict(g) for g in self.gates], indent=2), encoding="utf-8"
        )
        run_path = run_dir / "run.json"
        run_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return run_path


__all__ = [
    "ModelTier",
    "GateName",
    "RunStatus",
    "RunTrigger",
    "RewardTerm",
    "Termination",
    "CurriculumStage",
    "RandomizationRange",
    "Provenance",
    "TrainingScaffold",
    "RolloutBatch",
    "GateResult",
    "ExperimentRun",
]
