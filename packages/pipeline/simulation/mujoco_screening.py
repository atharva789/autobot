"""
MuJoCo screening service for design evaluation.

Performs lightweight physics checks:
- MJCF compilation
- Static stability
- Reachability
- Short-horizon task sanity
"""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf


@dataclass
class ScreeningResult:
    """Result of MuJoCo screening."""

    mjcf_compiled: bool = True
    mjcf_xml: str | None = None
    stability_score: float = 0.5
    reachability_score: float = 0.5
    task_sanity_score: float = 0.5
    overall_score: float = 0.5
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate overall score if not set."""
        if self.overall_score == 0.5 and self.mjcf_compiled:
            # Weighted average
            self.overall_score = (
                self.stability_score * 0.4 +
                self.reachability_score * 0.3 +
                self.task_sanity_score * 0.3
            )


def screen_design(ir: RobotDesignIR) -> ScreeningResult:
    """
    Screen a robot design using MuJoCo.

    Performs:
    1. MJCF compilation
    2. Static stability check
    3. Reachability analysis
    4. Short-horizon task sanity

    Args:
        ir: The robot design to screen

    Returns:
        ScreeningResult with scores and compiled MJCF
    """
    result = ScreeningResult()

    # Step 1: Compile to MJCF
    try:
        mjcf_xml = compile_to_mjcf(ir)
        result.mjcf_compiled = True
        result.mjcf_xml = mjcf_xml
    except Exception as e:
        result.mjcf_compiled = False
        result.errors.append(f"MJCF compilation failed: {e}")
        result.overall_score = 0.0
        return result

    # Step 2: Static stability check (mock for now)
    # In production, would load into MuJoCo and check
    result.stability_score = _estimate_stability(ir)

    # Step 3: Reachability analysis (mock)
    result.reachability_score = _estimate_reachability(ir)

    # Step 4: Task sanity (mock)
    result.task_sanity_score = _estimate_task_sanity(ir)

    # Calculate overall score
    result.overall_score = (
        result.stability_score * 0.4 +
        result.reachability_score * 0.3 +
        result.task_sanity_score * 0.3
    )

    return result


def _estimate_stability(ir: RobotDesignIR) -> float:
    """
    Estimate static stability (mock implementation).

    In production, would simulate the robot in MuJoCo
    and check if it remains stable.
    """
    # Heuristic: more links = potentially less stable
    num_links = len(ir.links)
    if num_links == 0:
        return 0.5
    if num_links <= 3:
        return 0.8
    if num_links <= 6:
        return 0.6
    return 0.4


def _estimate_reachability(ir: RobotDesignIR) -> float:
    """
    Estimate reachability (mock implementation).

    In production, would sample workspace and check
    what percentage of points are reachable.
    """
    # Heuristic: more joints = better reachability
    num_joints = len(ir.joints)
    if num_joints == 0:
        return 0.3
    if num_joints <= 2:
        return 0.5
    if num_joints <= 4:
        return 0.7
    return 0.8


def _estimate_task_sanity(ir: RobotDesignIR) -> float:
    """
    Estimate task sanity (mock implementation).

    In production, would run a short trajectory
    and check for self-collision, singularities, etc.
    """
    # Heuristic: having actuators is good
    num_actuated = sum(1 for j in ir.joints if j.actuator is not None)
    if len(ir.joints) == 0:
        return 0.5
    ratio = num_actuated / len(ir.joints)
    return 0.5 + ratio * 0.4
