"""
Design candidate wrapper for simulation pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from packages.pipeline.ir.design_ir import RobotDesignIR
    from packages.pipeline.simulation.mujoco_screening import ScreeningResult


@dataclass
class DesignCandidate:
    """
    A design candidate in the simulation pipeline.

    Wraps a RobotDesignIR with additional metadata for
    tracking through validation, screening, and ranking.
    """

    ir: "RobotDesignIR"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    screening_result: "ScreeningResult | None" = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    rank: int | None = None

    @property
    def name(self) -> str:
        """Get the design name."""
        return self.ir.name

    @property
    def score(self) -> float:
        """Get the screening score, or 0 if not screened."""
        if self.screening_result:
            return self.screening_result.overall_score
        return 0.0
