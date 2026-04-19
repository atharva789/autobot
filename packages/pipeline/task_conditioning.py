"""Task-conditioned capability extraction and deterministic design ranking."""

from __future__ import annotations

from dataclasses import dataclass, field

from packages.pipeline.design_quality import assess_design_quality
from packages.pipeline.schemas import (
    DesignCandidatesResponse,
    RobotDesignCandidate,
    TaskCapabilityGraph,
    TaskSpec,
)
from packages.pipeline.task_hardrails import evaluate_candidate_hardrails


@dataclass(frozen=True)
class CandidateTaskFitReport:
    score: float
    evidence: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    hardrail_passed: bool = True
    hardrail_rejection_reasons: list[str] = field(default_factory=list)
    summary: str = ""


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


def build_task_capability_graph(task_spec: TaskSpec) -> TaskCapabilityGraph:
    """Normalize task requirements into explicit capability requirements."""
    text = _task_text(task_spec)
    required: list[str] = []
    preferred_embodiments: list[str] = []
    disallowed: list[str] = []
    terrain_tags: list[str] = []
    payload_strategy: str | None = None
    task_family = "general_mobility"

    if any(term in text for term in ("climb", "wall", "vertical", "ladder", "rock")):
        task_family = "climbing"
        required.extend(
            [
                "vertical_support_strategy",
                "surface_attachment_strategy",
                "payload_stability",
            ]
        )
        if task_spec.manipulation_required or task_spec.payload_kg > 0:
            required.append("dual_arm_grasping")
        preferred_embodiments.extend(["hybrid", "biped"])
        disallowed.append("quadruped_without_attachment")
        terrain_tags.extend(["vertical", "rough_surface"])
        payload_strategy = "back_mount_or_centered_load"
    elif any(term in text for term in ("crawl", "crawlspace", "under", "pipe", "tunnel")):
        task_family = "crawling"
        required.extend(["low_profile_clearance", "stable_low_com_profile"])
        preferred_embodiments.extend(["quadruped", "hexapod", "hybrid"])
        disallowed.append("upright_high_profile_humanoid")
        terrain_tags.extend(["constrained_clearance"])
        payload_strategy = "top_mount_low_profile"
    elif any(
        term in text
        for term in ("slippery", "slope", "incline", "downhill", "ice", "wet", "stairs", "stair")
    ):
        task_family = "slippery_terrain"
        required.extend(["traction_contact_strategy", "controlled_descent", "payload_stability"])
        preferred_embodiments.extend(["quadruped", "hybrid", "hexapod"])
        disallowed.append("tall_narrow_platform_without_traction")
        terrain_tags.extend(["slippery", "unstable_support"])
        payload_strategy = "low_center_payload"
    elif task_spec.manipulation_required:
        task_family = "manipulation"
        required.extend(["payload_stability", "end_effector_control"])
        preferred_embodiments.extend(["arm", "hybrid", "biped"])
        payload_strategy = "front_mount_manipulation"
    elif task_spec.locomotion_type == "walking":
        task_family = "walking"
        required.append("stable_locomotion")
        preferred_embodiments.extend(["biped", "quadruped"])
    else:
        required.append("task_fit")

    if task_spec.payload_kg > 0 and "payload_stability" not in required:
        required.append("payload_stability")

    summary = (
        f"{task_family.replace('_', ' ')} task requiring "
        + ", ".join(required[:4])
        + ("" if len(required) <= 4 else ", ...")
    )
    return TaskCapabilityGraph(
        task_family=task_family,
        required_capabilities=required,
        preferred_embodiments=preferred_embodiments,
        disallowed_patterns=disallowed,
        terrain_tags=terrain_tags,
        payload_strategy=payload_strategy,
        summary=summary,
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _supports_capability(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec,
    capability: str,
) -> bool:
    rationale = candidate.rationale.lower()
    task_text = _task_text(task_spec)

    if capability == "vertical_support_strategy":
        return _contains_any(
            rationale,
            ("climb", "anchor", "support strategy", "vertical", "grasp", "hook"),
        ) or (candidate.num_arms >= 2 and candidate.num_legs >= 2 and candidate.leg_dof >= 4)

    if capability == "surface_attachment_strategy":
        return _contains_any(
            rationale,
            (
                "adhesion",
                "microspine",
                "claw",
                "hook",
                "grasp",
                "suction",
                "magnetic",
                "attachment",
                "support strategy",
            ),
        )

    if capability == "payload_stability":
        required_payload = max(task_spec.payload_kg, 0.5 if "carry" in task_text else 0.0)
        return candidate.payload_capacity_kg >= required_payload

    if capability == "dual_arm_grasping":
        return candidate.num_arms >= 2 and candidate.arm_dof >= 3

    if capability == "low_profile_clearance":
        return (
            candidate.torso_length_m <= 0.35
            or (candidate.num_legs >= 4 and candidate.leg_length_m <= 0.32)
        )

    if capability == "stable_low_com_profile":
        return candidate.num_legs >= 4 or (
            candidate.embodiment_class == "hybrid" and candidate.leg_length_m <= 0.4
        )

    if capability == "traction_contact_strategy":
        return candidate.friction >= 0.95 or _contains_any(
            rationale,
            ("traction", "wide stance", "slip", "cleat", "grip", "rubberized"),
        )

    if capability == "controlled_descent":
        return _contains_any(
            rationale,
            ("descent", "brake", "controlled", "support polygon", "wide stance"),
        ) or (candidate.num_legs >= 4 and candidate.friction >= 0.95)

    if capability == "end_effector_control":
        return candidate.num_arms >= 1 and candidate.arm_dof >= 4

    if capability == "stable_locomotion":
        return candidate.num_legs in {2, 4}

    return False


def score_candidate_task_fit(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec,
    graph: TaskCapabilityGraph | None = None,
) -> CandidateTaskFitReport:
    """Score how well a candidate covers task-specific affordances."""
    graph = graph or build_task_capability_graph(task_spec)
    evidence: list[str] = []
    missing: list[str] = []
    risk_flags: list[str] = []

    for capability in graph.required_capabilities:
        if _supports_capability(candidate, task_spec, capability):
            evidence.append(capability)
        else:
            missing.append(f"missing_{capability}")

    if (
        graph.task_family == "climbing"
        and candidate.embodiment_class == "quadruped"
        and not _supports_capability(candidate, task_spec, "surface_attachment_strategy")
    ):
        risk_flags.append("generic_quadruped_without_climbing_mechanism")

    if (
        graph.task_family == "crawling"
        and candidate.embodiment_class == "biped"
        and candidate.torso_length_m > 0.4
    ):
        risk_flags.append("upright_profile_for_crawling")

    if (
        graph.task_family == "slippery_terrain"
        and candidate.num_legs <= 2
        and candidate.friction < 0.95
    ):
        risk_flags.append("limited_traction_strategy")

    quality = assess_design_quality(candidate, task_spec)
    hardrail = evaluate_candidate_hardrails(candidate, task_spec, graph)
    capability_score = (
        len(evidence) / len(graph.required_capabilities)
        if graph.required_capabilities
        else 1.0
    )
    score = capability_score * 0.7 + quality.score * 0.25 + candidate.confidence * 0.05

    if graph.preferred_embodiments and candidate.embodiment_class in graph.preferred_embodiments:
        score += 0.05

    if risk_flags:
        score -= 0.15 * len(risk_flags)
    if hardrail.rejected:
        score = min(score, 0.24)

    summary = (
        f"Matched {len(evidence)}/{len(graph.required_capabilities)} required capabilities"
    )
    return CandidateTaskFitReport(
        score=max(0.0, min(1.0, round(score, 3))),
        evidence=evidence,
        missing_capabilities=missing,
        risk_flags=risk_flags + hardrail.risk_flags + quality.risk_flags,
        hardrail_passed=not hardrail.rejected,
        hardrail_rejection_reasons=hardrail.rejection_reasons,
        summary=summary,
    )


def apply_task_conditioning(
    response: DesignCandidatesResponse,
    task_spec: TaskSpec,
) -> DesignCandidatesResponse:
    """Annotate candidates with task-fit evidence and deterministically rerank them."""
    graph = build_task_capability_graph(task_spec)
    scored: list[tuple[RobotDesignCandidate, CandidateTaskFitReport]] = []
    for candidate in response.candidates:
        fit = score_candidate_task_fit(candidate, task_spec, graph)
        annotated = candidate.model_copy(
            update={
                "task_fit_score": fit.score,
                "task_fit_evidence": fit.evidence,
                "risk_flags": sorted(set(candidate.risk_flags + fit.risk_flags)),
                "hardrail_passed": fit.hardrail_passed,
                "hardrail_rejection_reasons": fit.hardrail_rejection_reasons,
            }
        )
        scored.append((annotated, fit))

    scored_map = {candidate.candidate_id: (candidate, fit) for candidate, fit in scored}
    eligible_scored = [item for item in scored if item[1].hardrail_passed]
    candidate_pool = eligible_scored or scored
    best_candidate, best_fit = max(
        candidate_pool,
        key=lambda item: (
            item[1].score,
            item[0].payload_capacity_kg,
            item[0].confidence,
        ),
    )
    current_candidate, current_fit = scored_map[response.model_preferred_id]
    should_override = (
        best_candidate.candidate_id != response.model_preferred_id
        and (
            best_fit.score >= current_fit.score + 0.08
            or len(current_fit.missing_capabilities) > len(best_fit.missing_capabilities)
        )
    )

    selected_candidate = best_candidate if should_override else current_candidate
    selected_fit = best_fit if should_override else current_fit
    rationale = response.selection_rationale
    if should_override:
        rationale = (
            f"{response.selection_rationale} "
            f"Task-conditioned reranking overrode model_preferred_id "
            f"{response.model_preferred_id} -> {best_candidate.candidate_id}. "
            f"{best_fit.summary}. "
            f"Required capabilities: {', '.join(best_candidate.task_fit_evidence) or 'none'}."
        )
    else:
        rationale = (
            f"{response.selection_rationale} "
            f"Task-conditioned rank confirmed {selected_candidate.candidate_id}: {selected_fit.summary}."
        ).strip()
    if not selected_fit.hardrail_passed:
        rationale = (
            f"{rationale} No candidate passed hardrails; selected the least-bad option with reasons: "
            f"{', '.join(selected_fit.hardrail_rejection_reasons) or 'unknown'}."
        )
    elif any(not fit.hardrail_passed for _, fit in scored):
        rejected = [
            f"{candidate.candidate_id}:{','.join(fit.hardrail_rejection_reasons)}"
            for candidate, fit in scored
            if not fit.hardrail_passed
        ]
        rationale = f"{rationale} Hardrail rejections: {'; '.join(rejected)}."

    return response.model_copy(
        update={
            "task_capability_graph": graph,
            "candidates": [candidate for candidate, _ in scored],
            "model_preferred_id": selected_candidate.candidate_id,
            "selection_rationale": rationale,
        }
    )
