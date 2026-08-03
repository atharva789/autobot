"""Spec 012 — schema-conditioned policy synthesis.

The data model is fixed at four records (data-model.md invariant 6). Adding a
fifth requires folding one of these, argued in a spec increment.
"""

from packages.research.loop_research.records import (
    ExperimentRun,
    GateResult,
    RolloutBatch,
    TrainingScaffold,
)

__all__ = ["ExperimentRun", "GateResult", "RolloutBatch", "TrainingScaffold"]
