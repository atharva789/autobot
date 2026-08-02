"""Build-order step 1 (specs/012-schema-conditioned-policy-synthesis/plan.md §7):
the TrainingScaffold schema and its compiler-to-MuJoCo.

Later build-order steps (schemas, G1-G4 gates, the negative control, the orchestrator) add
sibling modules to this package as they are built; this file only exports what step 1 delivers.
"""

from packages.research.loop_research.entity_table import (
    EntityTable,
    load_model_and_entities,
    load_model_and_entities_from_xml,
)
from packages.research.loop_research.expr import CompiledExpression, ExpressionError, compile_expression
from packages.research.loop_research.mujoco_compiler import (
    CompilationError,
    CompiledScaffold,
    StepOutcome,
    compile_scaffold,
)
from packages.research.loop_research.rollout import Policy, run_batch, run_episode, sample_constants
from packages.research.loop_research.scaffold import (
    CurriculumStage,
    ModelTier,
    Provenance,
    RandomizationRange,
    RewardTerm,
    RolloutBatch,
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
    "CompilationError",
    "CompiledScaffold",
    "StepOutcome",
    "compile_scaffold",
    "Policy",
    "run_batch",
    "run_episode",
    "sample_constants",
    "CurriculumStage",
    "ModelTier",
    "Provenance",
    "RandomizationRange",
    "RewardTerm",
    "RolloutBatch",
    "Termination",
    "TrainingScaffold",
    "Symbol",
    "SymbolSyntaxError",
    "is_schema_resolvable",
    "parse_symbol",
]
