"""Spec 012 — schema-conditioned policy synthesis.

Build-order position (specs/012-schema-conditioned-policy-synthesis/plan.md §7): step 1
(TrainingScaffold schema + compiler-to-MuJoCo) and step 3 (G1 static resolver) are implemented.
The data model is fixed at four records (data-model.md invariant 6): proposing a fifth requires
folding one of these, argued in a spec increment.
"""

from packages.research.loop_research.entity_table import (
    EntityTable,
    load_model_and_entities,
    load_model_and_entities_from_xml,
)
from packages.research.loop_research.expr import CompiledExpression, ExpressionError, compile_expression
from packages.research.loop_research.g1 import run_g1
from packages.research.loop_research.mujoco_compiler import (
    CompilationError,
    CompiledScaffold,
    StepOutcome,
    compile_scaffold,
)
from packages.research.loop_research.rollout import Policy, run_batch, run_episode, sample_constants
from packages.research.loop_research.scaffold import (
    CurriculumStage,
    ExperimentRun,
    GateName,
    GateResult,
    ModelTier,
    Provenance,
    RandomizationRange,
    RewardTerm,
    RolloutBatch,
    RunStatus,
    RunTrigger,
    Termination,
    TrainingScaffold,
)
from packages.research.loop_research.symbols import Symbol, SymbolSyntaxError, is_schema_resolvable, parse_symbol

__all__ = [
    "EntityTable",
    "load_model_and_entities",
    "load_model_and_entities_from_xml",
    "CompiledExpression",
    "ExpressionError",
    "compile_expression",
    "run_g1",
    "CompilationError",
    "CompiledScaffold",
    "StepOutcome",
    "compile_scaffold",
    "Policy",
    "run_batch",
    "run_episode",
    "sample_constants",
    "CurriculumStage",
    "ExperimentRun",
    "GateName",
    "GateResult",
    "ModelTier",
    "Provenance",
    "RandomizationRange",
    "RewardTerm",
    "RolloutBatch",
    "RunStatus",
    "RunTrigger",
    "Termination",
    "TrainingScaffold",
    "Symbol",
    "SymbolSyntaxError",
    "is_schema_resolvable",
    "parse_symbol",
]
