"""
Simulation loop for robot design evaluation.

This package orchestrates the design -> compile -> validate -> simulate -> rank pipeline.
"""

from packages.pipeline.simulation.candidate import DesignCandidate
from packages.pipeline.simulation.validator import validate_design, ValidationResult
from packages.pipeline.simulation.mujoco_screening import screen_design, ScreeningResult
from packages.pipeline.simulation.ranking import rank_candidates
from packages.pipeline.simulation.orchestrator import SimulationOrchestrator, OrchestrationResult

__all__ = [
    "DesignCandidate",
    "validate_design",
    "ValidationResult",
    "screen_design",
    "ScreeningResult",
    "rank_candidates",
    "SimulationOrchestrator",
    "OrchestrationResult",
]
