"""The four records of spec 012. See specs/012-.../data-model.md.

Frozen dataclasses, plain-dict serialization, no ORM. The core stays at four
records (data-model invariant 6): proposing a fifth requires folding one of
these, argued in a spec increment.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class TrainingScaffold:
    """The loop's only output. Never a policy, never Python.

    ``reward_terms`` / ``terminations`` entries carry a ``symbols`` list of
    dotted paths (``joint.<name>``, ``body.<name>``, ``site.<name>``,
    ``actuator.<name>``, ``sensor.<name>``); ``const.<name>`` never resolves
    against a schema — that is what G1 exploits.
    """

    scaffold_id: str
    schema_id: str
    schema_digest: str
    task_text: str
    reward_terms: tuple[dict[str, Any], ...]
    terminations: tuple[dict[str, Any], ...]
    curriculum: tuple[dict[str, Any], ...]
    randomization: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]
    parent_scaffold_id: str | None = None
    motivating_batch_id: str | None = None

    def __post_init__(self) -> None:
        if self.parent_scaffold_id is not None and self.motivating_batch_id is None:
            raise ValueError(
                "R2 violation: a revision must cite the rollout batch that "
                "motivated it (parent set, motivating_batch_id missing)."
            )


@dataclass(frozen=True)
class RolloutBatch:
    """What the simulator returns. R3 forbids collapsing this to a scalar."""

    batch_id: str
    scaffold_id: str
    episodes: int
    step_budget: int
    success_rate: float
    termination_histogram: dict[str, int]
    contact_events: dict[str, int]
    joint_saturation: dict[str, float]
    trace_uri: str
    seed: int
    wall_clock_s: float


@dataclass(frozen=True)
class GateResult:
    """One gate outcome. Recorded on pass and on fail (R4)."""

    gate: Literal["G1", "G2", "G3", "G4"]
    scaffold_id: str
    passed: bool
    score: float
    threshold: float
    detail: dict[str, Any]
    rubric_version: str = "v1"


@dataclass(frozen=True)
class ExperimentRun:
    """The committed record: one directory under .runs/loop_research/<run_id>."""

    run_id: str
    git_sha: str
    trigger: Literal["routine", "manual"]
    status: Literal["completed", "aborted_cost", "aborted_error"]
    scaffolds: tuple[str, ...]
    batches: tuple[str, ...]
    gates: tuple[GateResult, ...]
    cost: dict[str, Any]
    replay: dict[str, Any]
    manifest_path: str | None = None
    control: dict[str, Any] = field(default_factory=dict)

    def write(self, root: Path, scaffold_records: list[TrainingScaffold]) -> Path:
        """Persist the run in the committed layout data-model.md defines."""

        run_dir = root / self.run_id
        if run_dir.exists():
            raise FileExistsError(
                f"Run history is append-only; {run_dir} already exists."
            )
        scaffold_dir = run_dir / "scaffolds"
        scaffold_dir.mkdir(parents=True)
        for record in scaffold_records:
            path = scaffold_dir / f"{record.scaffold_id}.json"
            path.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
        (run_dir / "gates.json").write_text(
            json.dumps([asdict(g) for g in self.gates], indent=2), encoding="utf-8"
        )
        run_path = run_dir / "run.json"
        run_path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return run_path
