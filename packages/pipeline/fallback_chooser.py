"""Deterministic fallback chooser for ranking design candidates.

Used when MuJoCo MJX screening or training is unavailable/fails.
Ranks candidates by kinematic feasibility, stability, BOM confidence, and retargetability.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from packages.pipeline.bom_generator import generate_bom_for_candidate
from packages.pipeline.design_generator import candidate_to_morphology_params
from packages.pipeline.schemas import (
    BOMOutput,
    FallbackRanking,
    RobotDesignCandidate,
)


@dataclass
class _CandidateScores:
    candidate_id: str
    kinematic_feasibility: float
    static_stability: float
    bom_confidence: float
    retargetability: float
    total: float


def kinematic_feasibility_score(
    candidate: RobotDesignCandidate,
    q_target: np.ndarray | None = None,
) -> float:
    """Score kinematic feasibility based on design parameters.

    Checks:
    - DOF sufficiency for motion type
    - Limb length plausibility
    - Actuator torque adequacy

    Returns 0.0-1.0 score.
    """
    score = 1.0

    if candidate.embodiment_class == "biped":
        if candidate.num_legs != 2:
            score *= 0.3
        if candidate.leg_dof < 3:
            score *= 0.5
    elif candidate.embodiment_class == "quadruped":
        if candidate.num_legs != 4:
            score *= 0.3
        if candidate.leg_dof < 2:
            score *= 0.6
    elif candidate.embodiment_class == "arm":
        if candidate.num_arms < 1:
            score *= 0.2
        if candidate.arm_dof < 4:
            score *= 0.7

    if candidate.num_legs > 0 and candidate.leg_length_m < 0.1:
        score *= 0.5
    if candidate.num_arms > 0 and candidate.arm_length_m < 0.05:
        score *= 0.6

    mass_per_actuator = candidate.total_mass_kg / max(
        candidate.num_legs * candidate.leg_dof
        + candidate.num_arms * candidate.arm_dof
        + candidate.spine_dof,
        1,
    )
    if mass_per_actuator > 2.0 and candidate.actuator_torque_nm < 5.0:
        score *= 0.6

    if q_target is not None and len(q_target) > 0:
        total_dof = (
            candidate.num_legs * candidate.leg_dof
            + candidate.num_arms * candidate.arm_dof
            + candidate.spine_dof
        )
        target_dof = q_target.shape[1] if len(q_target.shape) > 1 else 1
        dof_ratio = min(total_dof, target_dof) / max(total_dof, target_dof)
        score *= 0.7 + 0.3 * dof_ratio

    return max(0.0, min(1.0, score))


def static_stability_score(candidate: RobotDesignCandidate) -> float:
    """Score static stability based on geometry.

    Checks:
    - Support polygon (more legs = more stable)
    - Center of mass height vs base width
    - Mass distribution

    Returns 0.0-1.0 score.
    """
    score = 0.5

    if candidate.num_legs >= 4:
        score += 0.3
    elif candidate.num_legs == 3:
        score += 0.2
    elif candidate.num_legs == 2:
        score += 0.0
    elif candidate.num_legs == 0:
        if candidate.embodiment_class == "arm":
            score += 0.4
        else:
            score -= 0.2

    if candidate.has_torso:
        com_height = candidate.torso_length_m / 2 + candidate.leg_length_m
        base_width = candidate.leg_length_m * 0.3 * max(candidate.num_legs, 1)
        if base_width > 0:
            height_ratio = com_height / base_width
            if height_ratio < 2.0:
                score += 0.2
            elif height_ratio > 4.0:
                score -= 0.2

    if candidate.total_mass_kg < 5.0:
        score += 0.1
    elif candidate.total_mass_kg > 50.0:
        score -= 0.1

    return max(0.0, min(1.0, score))


def bom_confidence_score(candidate: RobotDesignCandidate) -> float:
    """Score based on BOM procurement confidence.

    Higher score = more parts have known SKUs/vendors.
    """
    bom = generate_bom_for_candidate(candidate)
    return bom.procurement_confidence


def retargetability_score(
    candidate: RobotDesignCandidate,
    q_target: np.ndarray | None = None,
) -> float:
    """Score how well the design can retarget reference motion.

    Checks:
    - End-effector count matches reference
    - Limb lengths allow reaching reference positions
    - DOF allows required motion range

    Returns 0.0-1.0 score.
    """
    score = 0.7

    if candidate.embodiment_class == "biped":
        expected_ee = 6
    elif candidate.embodiment_class == "quadruped":
        expected_ee = 4
    elif candidate.embodiment_class == "arm":
        expected_ee = 1
    else:
        expected_ee = candidate.num_legs + candidate.num_arms

    actual_ee = candidate.num_legs + candidate.num_arms
    if actual_ee >= expected_ee:
        score += 0.15

    if candidate.num_legs > 0:
        leg_reach = candidate.leg_length_m * 1.5
        if leg_reach > 0.3:
            score += 0.1
    if candidate.num_arms > 0:
        arm_reach = candidate.arm_length_m * 1.8
        if arm_reach > 0.4:
            score += 0.05

    if q_target is not None and len(q_target) > 0:
        motion_range = float(np.ptp(q_target))
        if motion_range < math.pi:
            score += 0.1
        elif motion_range > 2 * math.pi:
            score -= 0.1

    return max(0.0, min(1.0, score))


def rank_candidates_fallback(
    candidates: list[RobotDesignCandidate],
    q_target: np.ndarray | None = None,
    *,
    weights: dict[str, float] | None = None,
) -> list[FallbackRanking]:
    """Rank candidates using deterministic heuristics.

    Args:
        candidates: List of design candidates to rank.
        q_target: Optional reference trajectory for motion-aware scoring.
        weights: Optional custom weights for scoring components.
            Defaults: kinematic=0.35, stability=0.25, bom=0.20, retarget=0.20

    Returns:
        List of FallbackRanking sorted by total_score descending.
    """
    if weights is None:
        weights = {
            "kinematic": 0.35,
            "stability": 0.25,
            "bom": 0.20,
            "retarget": 0.20,
        }

    scores: list[_CandidateScores] = []
    for candidate in candidates:
        kin = kinematic_feasibility_score(candidate, q_target)
        stab = static_stability_score(candidate)
        bom = bom_confidence_score(candidate)
        ret = retargetability_score(candidate, q_target)

        total = (
            weights["kinematic"] * kin
            + weights["stability"] * stab
            + weights["bom"] * bom
            + weights["retarget"] * ret
        )
        scores.append(
            _CandidateScores(
                candidate_id=candidate.candidate_id,
                kinematic_feasibility=round(kin, 3),
                static_stability=round(stab, 3),
                bom_confidence=round(bom, 3),
                retargetability=round(ret, 3),
                total=round(total, 3),
            )
        )

    scores.sort(key=lambda s: -s.total)

    return [
        FallbackRanking(
            candidate_id=s.candidate_id,
            kinematic_feasibility=s.kinematic_feasibility,
            static_stability=s.static_stability,
            bom_confidence=s.bom_confidence,
            retargetability=s.retargetability,
            total_score=s.total,
        )
        for s in scores
    ]


def select_best_candidate_fallback(
    candidates: list[RobotDesignCandidate],
    q_target: np.ndarray | None = None,
) -> tuple[RobotDesignCandidate, FallbackRanking]:
    """Select the best candidate using fallback heuristics.

    Returns tuple of (best_candidate, ranking_info).
    """
    rankings = rank_candidates_fallback(candidates, q_target)
    best_ranking = rankings[0]
    best_candidate = next(
        c for c in candidates if c.candidate_id == best_ranking.candidate_id
    )
    return best_candidate, best_ranking
