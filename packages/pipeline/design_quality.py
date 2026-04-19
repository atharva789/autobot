"""Heuristics for judging whether a candidate robot design is sane."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.schemas import RobotDesignCandidate, TaskSpec


@dataclass(frozen=True)
class DesignQualityReport:
    score: float
    risk_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _task_text(task_spec: TaskSpec | None) -> str:
    if task_spec is None:
        return ""
    return " ".join(
        [
            task_spec.task_goal,
            task_spec.success_criteria,
            task_spec.environment,
            task_spec.locomotion_type,
            " ".join(task_spec.search_queries),
        ]
    ).lower()


def assess_design_quality(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec | None = None,
) -> DesignQualityReport:
    """Score a candidate on plausibility, simplicity, and task fit."""
    score = 1.0
    risk_flags: list[str] = []
    notes: list[str] = []
    task_text = _task_text(task_spec)
    total_dof = (
        candidate.num_legs * candidate.leg_dof
        + candidate.num_arms * candidate.arm_dof
        + candidate.spine_dof
    )

    if candidate.num_legs > 4:
        penalty = 0.1 * (candidate.num_legs - 4)
        score -= penalty
        risk_flags.append("excessive_leg_count")
        notes.append("More than four legs usually indicates unnecessary complexity.")

    if candidate.num_arms > 2 and candidate.embodiment_class not in {"arm", "hybrid"}:
        score -= 0.15
        risk_flags.append("overbuilt_manipulation")

    if total_dof > 16:
        score -= 0.1
        risk_flags.append("high_dof_complexity")

    if candidate.total_mass_kg > 30.0:
        score -= 0.08
        risk_flags.append("heavy_platform")

    if candidate.actuator_torque_nm < max(candidate.total_mass_kg / max(total_dof, 1), 1.0):
        score -= 0.12
        risk_flags.append("under_torqued")

    if task_text:
        if any(term in task_text for term in ("slippery", "slope", "stairs", "stair")):
            if candidate.num_legs > 4:
                score -= 0.12
                risk_flags.append("unrealistic_locomotion_for_terrain")
        if any(term in task_text for term in ("carry", "lift", "payload", "box", "crate")):
            if candidate.payload_capacity_kg <= 0:
                score -= 0.2
                risk_flags.append("insufficient_payload")
        if candidate.embodiment_class == "hexapod" and "slippery" in task_text:
            score -= 0.08
            risk_flags.append("overfit_hexapod")

    score = max(0.0, min(1.0, score))
    return DesignQualityReport(score=round(score, 3), risk_flags=risk_flags, notes=notes)

