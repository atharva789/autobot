"""Explicit hardrails for non-traditional tasks and terrain."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.schemas import RobotDesignCandidate, TaskCapabilityGraph, TaskSpec


@dataclass(frozen=True)
class HardrailEvaluation:
    rejected: bool
    rejection_reasons: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _task_text(task_spec: TaskSpec) -> str:
    return " ".join(
        [
            task_spec.task_goal,
            task_spec.success_criteria,
            task_spec.environment,
            task_spec.locomotion_type,
            " ".join(task_spec.search_queries),
        ]
    ).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _has_attachment_strategy(candidate: RobotDesignCandidate) -> bool:
    text = candidate.rationale.lower()
    return _contains_any(
        text,
        (
            "adhesion",
            "microspine",
            "claw",
            "hook",
            "grasp",
            "suction",
            "magnetic",
            "attachment",
            "anchor",
        ),
    )


def _has_traction_or_descent_strategy(candidate: RobotDesignCandidate) -> bool:
    text = candidate.rationale.lower()
    if _contains_any(
        text,
        (
            "no traction",
            "no explicit traction",
            "without traction",
            "no controlled descent",
            "without controlled descent",
            "no explicit descent",
        ),
    ):
        return False
    return candidate.friction >= 0.95 or _contains_any(
        text,
        (
            "traction",
            "wide stance",
            "controlled descent",
            "descent",
            "brake",
            "rubberized",
            "grip",
            "cleat",
            "support polygon",
        ),
    )


def evaluate_candidate_hardrails(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec,
    graph: TaskCapabilityGraph,
) -> HardrailEvaluation:
    """Reject candidates that violate task-family-specific hardrails."""
    task_text = _task_text(task_spec)
    rejection_reasons: list[str] = []
    risk_flags: list[str] = []
    notes: list[str] = []

    if graph.task_family == "climbing":
        if not _has_attachment_strategy(candidate):
            rejection_reasons.append("missing_attachment_or_grasp_strategy_for_climbing")
        if candidate.embodiment_class == "quadruped":
            risk_flags.append("generic_quadruped_without_climbing_mechanism")
        if candidate.num_arms < 2 and not _contains_any(candidate.rationale.lower(), ("hooked feet", "microspine", "adhesion")):
            notes.append("climbing candidate lacks dual-arm or specialized foothold strategy")

    if graph.task_family == "crawling":
        if candidate.embodiment_class == "biped" and candidate.torso_length_m > 0.4:
            rejection_reasons.append("upright_profile_exceeds_crawl_clearance")
        if candidate.leg_length_m > 0.45 and candidate.num_legs <= 2:
            risk_flags.append("tall_leg_geometry_for_crawling")

    if graph.task_family == "slippery_terrain":
        if not _has_traction_or_descent_strategy(candidate):
            rejection_reasons.append("no_traction_or_controlled_descent_strategy")
        if candidate.num_legs <= 2 and candidate.leg_length_m >= 0.65:
            rejection_reasons.append("tall_narrow_platform_for_slippery_terrain")
        if candidate.num_legs <= 2:
            risk_flags.append("limited_support_contacts")

    if "payload_stability" in graph.required_capabilities and candidate.payload_capacity_kg < max(task_spec.payload_kg, 0.5):
        rejection_reasons.append("payload_capacity_below_required_margin")

    return HardrailEvaluation(
        rejected=bool(rejection_reasons),
        rejection_reasons=sorted(set(rejection_reasons)),
        risk_flags=sorted(set(risk_flags)),
        notes=notes,
    )
