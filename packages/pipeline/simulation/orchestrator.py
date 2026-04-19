"""
Simulation orchestrator for the full pipeline.

Coordinates: validate -> screen -> rank -> select
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.pipeline.simulation.candidate import DesignCandidate
from packages.pipeline.simulation.validator import validate_design
from packages.pipeline.simulation.mujoco_screening import screen_design
from packages.pipeline.simulation.ranking import rank_candidates


@dataclass
class OrchestrationResult:
    """Result of full orchestration pipeline."""

    candidates: list[DesignCandidate] = field(default_factory=list)
    top_candidate: DesignCandidate | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class SimulationOrchestrator:
    """
    Orchestrates the simulation pipeline.

    Pipeline:
    1. Wrap designs as candidates
    2. Validate each design
    3. Screen valid designs with MuJoCo
    4. Rank by screening scores
    5. Return ranked candidates with artifacts
    """

    def process(self, designs: list[RobotDesignIR]) -> OrchestrationResult:
        """
        Process multiple designs through the pipeline.

        Args:
            designs: List of robot designs to evaluate

        Returns:
            OrchestrationResult with ranked candidates
        """
        result = OrchestrationResult()

        # Step 1: Wrap as candidates
        candidates = [DesignCandidate(ir=ir) for ir in designs]

        # Step 2: Validate each
        valid_candidates = []
        for candidate in candidates:
            validation = validate_design(candidate.ir)
            if validation.is_valid:
                valid_candidates.append(candidate)
            else:
                result.errors.extend(validation.errors)

        # Step 3: Screen valid candidates
        for candidate in valid_candidates:
            screening = screen_design(candidate.ir)
            candidate.screening_result = screening
            candidate.artifacts["mjcf"] = screening.mjcf_xml

        # Step 4: Rank candidates
        ranked = rank_candidates(valid_candidates)
        result.candidates = ranked

        # Step 5: Select top candidate
        if ranked:
            result.top_candidate = ranked[0]

        # Collect artifacts
        result.artifacts = {
            "mjcf": {c.id: c.artifacts.get("mjcf") for c in ranked},
        }

        return result
