"""Geometry-aware anti-collapse ranking for robot design candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from packages.pipeline.schemas import (
    CandidateSimilarity,
    CollapseDetectionReport,
    DesignCandidatesResponse,
    DesignNoveltySignature,
    RobotDesignCandidate,
    TaskSpec,
)
from packages.pipeline.task_conditioning import build_task_capability_graph

_STRUCTURAL_COMPONENT_KINDS = {
    "torso_shell",
    "leg_segment",
    "arm_segment",
    "joint_anchor",
    "sensor_head",
}


@dataclass(frozen=True)
class PromptConditioningFingerprint:
    task_family: str
    tags: tuple[str, ...]
    summary: str


def build_prompt_conditioning_fingerprint(task_spec: TaskSpec) -> PromptConditioningFingerprint:
    graph = build_task_capability_graph(task_spec)
    tags = {
        graph.task_family,
        task_spec.environment,
        task_spec.locomotion_type,
        *graph.terrain_tags,
    }
    if task_spec.manipulation_required:
        tags.add("manipulation")
    if task_spec.payload_kg > 0:
        tags.add("payload")
    if graph.payload_strategy:
        tags.add(graph.payload_strategy)
    ordered = tuple(sorted(tags))
    return PromptConditioningFingerprint(
        task_family=graph.task_family,
        tags=ordered,
        summary="|".join(ordered),
    )


def build_design_novelty_signature(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec,
    render_payload: dict[str, Any] | None,
) -> DesignNoveltySignature:
    stats = (render_payload or {}).get("ui_scene", {}).get("stats", {})
    nodes = (render_payload or {}).get("ui_scene", {}).get("nodes", [])
    accessory_tokens: set[str] = set()
    for node in nodes:
        component_kind = str(node.get("component_kind") or "")
        name = str(node.get("name") or "")
        if component_kind and component_kind not in _STRUCTURAL_COMPONENT_KINDS:
            accessory_tokens.add(component_kind)
            if name:
                if any(token in name for token in ("payload_pack", "gripper", "spike", "tail", "skid")):
                    accessory_tokens.add(name)
    accessory_profile = sorted(accessory_tokens)
    primitive_keys = sorted(str(item) for item in stats.get("primitive_keys", []))
    geometry_profile = str(stats.get("task_geometry_profile") or build_prompt_conditioning_fingerprint(task_spec).task_family)
    topology_key = (
        f"{candidate.embodiment_class}:{candidate.num_legs}:{candidate.num_arms}:"
        f"{candidate.leg_dof}:{candidate.arm_dof}:{candidate.spine_dof}"
    )
    actuation_key = f"{candidate.actuator_class}:{round(candidate.actuator_torque_nm / 5):02d}"
    return DesignNoveltySignature(
        topology_key=topology_key,
        actuation_key=actuation_key,
        geometry_profile=geometry_profile,
        primitive_keys=primitive_keys,
        accessory_profile=accessory_profile,
        material_count=int(stats.get("material_count") or 0),
    )


def _jaccard(items_a: set[str], items_b: set[str]) -> float:
    if not items_a and not items_b:
        return 1.0
    union = items_a | items_b
    if not union:
        return 0.0
    return len(items_a & items_b) / len(union)


def _prompt_similarity(
    current: PromptConditioningFingerprint,
    other_tags: set[str],
) -> float:
    return _jaccard(set(current.tags), other_tags)


def _similarity_report(
    candidate_id: str,
    other_candidate_id: str,
    source: str,
    signature: DesignNoveltySignature,
    other_signature: DesignNoveltySignature,
    *,
    prompt_distance: float | None = None,
) -> CandidateSimilarity:
    score = 0.0
    reasons: list[str] = []

    if signature.topology_key == other_signature.topology_key:
        score += 0.45
        reasons.append("matching_topology")
    else:
        own = signature.topology_key.split(":")
        other = other_signature.topology_key.split(":")
        if own[:3] == other[:3]:
            score += 0.22
            reasons.append("same_embodiment_and_limb_inventory")

    if signature.geometry_profile == other_signature.geometry_profile:
        score += 0.2
        reasons.append("matching_geometry_profile")

    primitive_overlap = _jaccard(set(signature.primitive_keys), set(other_signature.primitive_keys))
    if primitive_overlap:
        score += primitive_overlap * 0.1
        if primitive_overlap >= 0.75:
            reasons.append("shared_primitive_composition")

    accessory_overlap = _jaccard(set(signature.accessory_profile), set(other_signature.accessory_profile))
    if accessory_overlap:
        score += accessory_overlap * 0.15
        if accessory_overlap >= 0.75:
            reasons.append("shared_accessory_pattern")

    if signature.actuation_key == other_signature.actuation_key:
        score += 0.05
        reasons.append("matching_actuation_band")

    material_delta = abs(signature.material_count - other_signature.material_count)
    score += max(0.0, 1 - min(material_delta / 6, 1.0)) * 0.05
    return CandidateSimilarity(
        candidate_id=candidate_id,
        other_candidate_id=other_candidate_id,
        source="batch" if source == "batch" else "history",
        similarity=round(min(score, 1.0), 3),
        reasons=reasons,
        prompt_distance=None if prompt_distance is None else round(prompt_distance, 3),
    )


def _history_signature(context: dict[str, Any]) -> tuple[DesignNoveltySignature | None, set[str]]:
    design_json = context.get("design_json")
    render_json = context.get("render_json")
    er16_plan_json = context.get("er16_plan_json")
    if not isinstance(design_json, dict) or not isinstance(render_json, dict):
        return None, set()
    try:
        candidate = RobotDesignCandidate.model_validate(design_json)
    except Exception:
        return None, set()
    task_tags: set[str] = set()
    if er16_plan_json:
        try:
            raw = json.loads(er16_plan_json) if isinstance(er16_plan_json, str) else er16_plan_json
            if isinstance(raw, dict):
                spec = TaskSpec.model_validate(raw)
                task_tags = set(build_prompt_conditioning_fingerprint(spec).tags)
            else:
                spec = None
        except Exception:
            spec = None
    else:
        spec = None
    if spec is None:
        spec = TaskSpec(
            task_goal="generic task",
            environment="indoor",
            locomotion_type="walking",
            manipulation_required=False,
            payload_kg=0.0,
            success_criteria="generic task",
            search_queries=["generic task"],
        )
    return build_design_novelty_signature(candidate, spec, render_json), task_tags


def apply_diversity_controls(
    response: DesignCandidatesResponse,
    task_spec: TaskSpec,
    render_payloads: dict[str, dict[str, Any]],
    prior_design_contexts: list[dict[str, Any]] | None = None,
) -> DesignCandidatesResponse:
    prior_design_contexts = prior_design_contexts or []
    prompt_fingerprint = build_prompt_conditioning_fingerprint(task_spec)
    signatures = {
        candidate.candidate_id: build_design_novelty_signature(
            candidate,
            task_spec,
            render_payloads.get(candidate.candidate_id),
        )
        for candidate in response.candidates
    }

    batch_reports: list[CandidateSimilarity] = []
    batch_max_similarity: dict[str, float] = {candidate.candidate_id: 0.0 for candidate in response.candidates}
    for left, right in combinations(response.candidates, 2):
        report = _similarity_report(
            left.candidate_id,
            right.candidate_id,
            "batch",
            signatures[left.candidate_id],
            signatures[right.candidate_id],
        )
        if report.similarity >= 0.75:
            batch_reports.append(report)
        batch_max_similarity[left.candidate_id] = max(batch_max_similarity[left.candidate_id], report.similarity)
        batch_max_similarity[right.candidate_id] = max(batch_max_similarity[right.candidate_id], report.similarity)

    history_reports: list[CandidateSimilarity] = []
    history_penalties: dict[str, float] = {candidate.candidate_id: 0.0 for candidate in response.candidates}
    for context in prior_design_contexts:
        signature, history_tags = _history_signature(context)
        if signature is None:
            continue
        for candidate in response.candidates:
            report = _similarity_report(
                candidate.candidate_id,
                str(context.get("candidate_id") or context.get("id") or "history"),
                "history",
                signatures[candidate.candidate_id],
                signature,
                prompt_distance=1 - _prompt_similarity(prompt_fingerprint, history_tags),
            )
            prompt_gap = report.prompt_distance or 0.0
            adjusted_similarity = report.similarity * max(0.0, prompt_gap)
            if adjusted_similarity >= 0.48:
                history_reports.append(
                    report.model_copy(update={"similarity": round(adjusted_similarity, 3)})
                )
            history_penalties[candidate.candidate_id] = max(
                history_penalties[candidate.candidate_id],
                adjusted_similarity,
            )

    annotated_candidates: list[RobotDesignCandidate] = []
    final_scores: dict[str, float] = {}
    for candidate in response.candidates:
        batch_penalty = max(0.0, batch_max_similarity[candidate.candidate_id] - 0.78) * 0.42
        history_penalty = max(0.0, history_penalties[candidate.candidate_id] - 0.42) * 0.6
        diversity_penalty = round(min(batch_penalty + history_penalty, 0.55), 3)
        novelty_score = round(max(0.0, 1.0 - batch_max_similarity[candidate.candidate_id] * 0.55 - history_penalties[candidate.candidate_id] * 0.45), 3)
        base_score = candidate.task_fit_score if candidate.task_fit_score is not None else candidate.confidence
        final_scores[candidate.candidate_id] = round(base_score - diversity_penalty, 3)
        annotated_candidates.append(
            candidate.model_copy(
                update={
                    "novelty_score": novelty_score,
                    "diversity_penalty": diversity_penalty,
                    "novelty_signature": signatures[candidate.candidate_id],
                }
            )
        )

    candidate_map = {candidate.candidate_id: candidate for candidate in annotated_candidates}
    current_candidate = candidate_map[response.model_preferred_id]
    current_final = final_scores[current_candidate.candidate_id]
    best_candidate = max(
        annotated_candidates,
        key=lambda candidate: (
            final_scores[candidate.candidate_id],
            candidate.task_fit_score if candidate.task_fit_score is not None else candidate.confidence,
            candidate.confidence,
        ),
    )
    best_final = final_scores[best_candidate.candidate_id]
    current_base = current_candidate.task_fit_score if current_candidate.task_fit_score is not None else current_candidate.confidence
    best_base = best_candidate.task_fit_score if best_candidate.task_fit_score is not None else best_candidate.confidence
    should_override = (
        best_candidate.candidate_id != current_candidate.candidate_id
        and best_final >= current_final + 0.02
        and best_base >= current_base - 0.08
    )

    collapse_report = CollapseDetectionReport(
        prompt_fingerprint=prompt_fingerprint.summary,
        duplicate_pairs=batch_reports,
        history_matches=history_reports,
        summary=(
            f"batch duplicates={len(batch_reports)}; history matches={len(history_reports)}; "
            f"selected={best_candidate.candidate_id if should_override else current_candidate.candidate_id}"
        ),
    )

    if should_override:
        history_phrase = "History-aware diversity reranking" if history_reports else "Diversity reranking"
        rationale = (
            f"{response.selection_rationale} {history_phrase} overrode "
            f"{current_candidate.candidate_id} -> {best_candidate.candidate_id}. "
            f"Final diversity-adjusted scores: "
            f"{current_candidate.candidate_id}={current_final}, {best_candidate.candidate_id}={best_final}."
        )
    else:
        rationale = response.selection_rationale
        if batch_reports or history_reports:
            rationale = (
                f"{response.selection_rationale} Diversity screen kept "
                f"{current_candidate.candidate_id}; no alternative improved the diversity-adjusted score enough."
            )

    return response.model_copy(
        update={
            "candidates": annotated_candidates,
            "model_preferred_id": best_candidate.candidate_id if should_override else current_candidate.candidate_id,
            "selection_rationale": rationale,
            "collapse_report": collapse_report,
        }
    )
