"""Derived telemetry for human-in-the-loop approval and UI surfaces."""

from __future__ import annotations

from math import ceil

from packages.pipeline.design_quality import assess_design_quality
from packages.pipeline.schemas import (
    BOMOutput,
    CandidateTelemetry,
    RobotDesignCandidate,
    TaskSpec,
)


def _estimate_reach(candidate: RobotDesignCandidate) -> float:
    limb_reach = max(candidate.arm_length_m, candidate.leg_length_m)
    if limb_reach <= 0:
        limb_reach = candidate.torso_length_m * 0.75
    return round(max(limb_reach * 1.6, 0.1), 3)


def _estimate_backlash_deg(candidate: RobotDesignCandidate) -> float:
    base = {
        "servo": 0.85,
        "bldc": 0.28,
        "stepper": 1.15,
        "hydraulic": 0.08,
    }.get(candidate.actuator_class, 0.75)
    if candidate.joint_stiffness >= 250:
        base *= 0.8
    if candidate.num_legs > 4:
        base *= 1.08
    return round(max(base, 0.05), 3)


def _estimate_bandwidth_hz(candidate: RobotDesignCandidate) -> float:
    total_dof = (
        candidate.num_legs * candidate.leg_dof
        + candidate.num_arms * candidate.arm_dof
        + candidate.spine_dof
    )
    base = {
        "servo": 120.0,
        "bldc": 138.0,
        "stepper": 86.0,
        "hydraulic": 64.0,
    }.get(candidate.actuator_class, 100.0)
    estimated = base - candidate.total_mass_kg * 1.2 - total_dof * 1.7
    return round(max(20.0, estimated), 1)


def build_candidate_telemetry(
    candidate: RobotDesignCandidate,
    bom: BOMOutput | None = None,
    task_spec: TaskSpec | None = None,
) -> CandidateTelemetry:
    quality = assess_design_quality(candidate, task_spec)
    payload_margin = candidate.payload_capacity_kg
    if task_spec is not None:
        payload_margin = candidate.payload_capacity_kg - max(task_spec.payload_kg, 0.0)

    risk_flags = list(quality.risk_flags)
    if bom is not None and bom.procurement_confidence < 0.7:
        risk_flags.append("procurement_uncertain")
    if bom is not None and bom.total_cost_usd is None:
        risk_flags.append("cost_unknown")

    total_cost = bom.total_cost_usd if bom is not None else None
    summary_parts = [
        f"{candidate.embodiment_class} with {candidate.total_mass_kg:.1f} kg mass",
        f"{candidate.payload_capacity_kg:.1f} kg payload",
        f"reach {_estimate_reach(candidate):.2f} m",
    ]
    if total_cost is not None:
        summary_parts.append(f"est. cost ${total_cost:.0f}")
    if risk_flags:
        summary_parts.append(f"risks: {', '.join(sorted(set(risk_flags)))}")

    return CandidateTelemetry(
        candidate_id=candidate.candidate_id,
        estimated_total_cost_usd=total_cost,
        estimated_mass_kg=candidate.total_mass_kg,
        payload_capacity_kg=candidate.payload_capacity_kg,
        payload_margin_kg=round(payload_margin, 3),
        estimated_reach_m=_estimate_reach(candidate),
        actuator_torque_nm=candidate.actuator_torque_nm,
        estimated_backlash_deg=_estimate_backlash_deg(candidate),
        estimated_bandwidth_hz=_estimate_bandwidth_hz(candidate),
        procurement_confidence=bom.procurement_confidence if bom is not None else 0.0,
        design_quality_score=quality.score,
        risk_flags=sorted(set(risk_flags)),
        summary="; ".join(summary_parts),
    )
