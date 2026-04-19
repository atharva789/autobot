"""Revision-level validation loop for compiled design artifacts."""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from packages.pipeline.schemas import (
    BOMOutput,
    CandidateTelemetry,
    DesignValidationReport,
    RobotDesignCandidate,
    TaskSpec,
    ValidationCheckResult,
)


def _default_output_dir() -> Path:
    return Path(
        os.environ.get(
            "VALIDATION_RUNS_DIR",
            str(Path.cwd() / "research" / "runs" / "validation_loop"),
        )
    )


def _render_stats(render_payload: dict[str, Any] | None) -> dict[str, Any]:
    return ((render_payload or {}).get("ui_scene") or {}).get("stats") or {}


def build_design_validation_report(
    *,
    design_id: str,
    revision_id: str,
    task_spec: TaskSpec,
    candidate: RobotDesignCandidate,
    render_payload: dict[str, Any] | None,
    bom: BOMOutput,
    telemetry: CandidateTelemetry,
    artifact_paths: dict[str, str],
    output_dir: Path | None = None,
) -> DesignValidationReport:
    checks: list[ValidationCheckResult] = []
    failure_categories: list[str] = []
    render_stats = _render_stats(render_payload)

    structural_details: list[str] = []
    structural_status = "pass"
    if candidate.num_legs == 0 and candidate.num_arms == 0:
        structural_status = "fail"
        structural_details.append("candidate has neither locomotion nor manipulation links")
    if candidate.has_torso and candidate.torso_length_m <= 0.0:
        structural_status = "fail"
        structural_details.append("torso length is non-positive")
    if candidate.num_arms > 0 and candidate.arm_length_m <= 0.0:
        structural_status = "fail"
        structural_details.append("arm count is non-zero but arm_length_m is invalid")
    if candidate.num_legs > 0 and candidate.leg_length_m <= 0.0:
        structural_status = "fail"
        structural_details.append("leg count is non-zero but leg_length_m is invalid")
    if structural_status == "fail":
        failure_categories.append("structural")
    checks.append(
        ValidationCheckResult(
            name="structural_completeness",
            status=structural_status,
            summary="Link, limb, and torso dimensions are internally consistent.",
            details=structural_details,
            category="structural",
        )
    )

    task_details: list[str] = []
    task_status = "pass"
    if candidate.hardrail_passed is False:
        task_status = "fail"
        task_details.extend(candidate.hardrail_rejection_reasons or ["candidate failed hardrail checks"])
    elif (candidate.task_fit_score or 0.0) < 0.55:
        task_status = "warning"
        task_details.append(f"task_fit_score={candidate.task_fit_score} is below preferred threshold")
    if task_status == "fail":
        failure_categories.append("task")
    checks.append(
        ValidationCheckResult(
            name="task_validation",
            status=task_status,
            summary="Task fit and hardrail checks are satisfied.",
            details=task_details,
            category="task",
        )
    )

    compiler_details: list[str] = []
    compiler_status = "pass"
    mjcf_text = render_payload.get("mjcf") if render_payload else None
    render_glb = render_payload.get("render_glb") if render_payload else None
    if not isinstance(mjcf_text, str) or not mjcf_text.strip().startswith("<mujoco"):
        compiler_status = "fail"
        compiler_details.append("MJCF artifact missing or malformed")
    if not isinstance(render_glb, str) or not render_glb.startswith("data:model/gltf-binary;base64,"):
        compiler_status = "fail"
        compiler_details.append("render_glb artifact missing or malformed")
    if compiler_status == "fail":
        failure_categories.append("compiler")
    checks.append(
        ValidationCheckResult(
            name="compiler_outputs",
            status=compiler_status,
            summary="Compiler emitted MJCF and GLB artifacts.",
            details=compiler_details,
            category="compiler",
        )
    )

    render_details: list[str] = []
    render_status = "pass"
    mesh_count = int(render_stats.get("mesh_node_count") or 0)
    material_count = int(render_stats.get("material_count") or 0)
    geometry_profile = str(render_stats.get("task_geometry_profile") or "")
    if mesh_count < 10:
        render_status = "fail"
        render_details.append(f"mesh_node_count too low ({mesh_count})")
    if material_count < 5:
        render_status = "fail"
        render_details.append(f"material_count too low ({material_count})")
    expected_profile = (
        "climbing"
        if "climb" in " ".join([task_spec.task_goal, task_spec.success_criteria]).lower()
        else "slippery_terrain"
        if any(term in " ".join([task_spec.task_goal, task_spec.success_criteria]).lower() for term in ("slippery", "downhill", "slope"))
        else ""
    )
    if expected_profile and expected_profile not in geometry_profile:
        render_status = "warning" if render_status == "pass" else render_status
        render_details.append(f"geometry profile {geometry_profile!r} does not strongly match expected task family")
    if render_status == "fail":
        failure_categories.append("render")
    checks.append(
        ValidationCheckResult(
            name="render_quality",
            status=render_status,
            summary="Engineering render artifact is rich enough for inspection use.",
            details=render_details,
            category="render",
        )
    )

    simulation_details: list[str] = []
    simulation_status = "pass"
    if telemetry.design_quality_score < 0.55:
        simulation_status = "warning"
        simulation_details.append(f"design_quality_score={telemetry.design_quality_score} is below preferred threshold")
    if telemetry.estimated_bandwidth_hz < 40:
        simulation_status = "warning"
        simulation_details.append(f"bandwidth too low for comfortable control ({telemetry.estimated_bandwidth_hz} Hz)")
    if candidate.hardrail_passed is False and simulation_status != "fail":
        simulation_status = "warning"
    checks.append(
        ValidationCheckResult(
            name="simulation_viability",
            status=simulation_status,
            summary="Telemetry suggests the design is viable for screening and control iteration.",
            details=simulation_details,
            category="simulation",
        )
    )

    procurement_details: list[str] = []
    procurement_status = "pass"
    if bom.procurement_confidence < 0.5:
        procurement_status = "fail"
        procurement_details.append(f"procurement confidence too low ({bom.procurement_confidence:.2f})")
    if bom.missing_items:
        if bom.procurement_confidence < 0.75:
            procurement_status = "fail"
        elif procurement_status == "pass":
            procurement_status = "warning"
        procurement_details.extend(f"missing_item:{item}" for item in bom.missing_items)
    if procurement_status == "fail":
        failure_categories.append("procurement")
    checks.append(
        ValidationCheckResult(
            name="procurement_grounding",
            status=procurement_status,
            summary="Critical components are sufficiently resolved for procurement and build planning.",
            details=procurement_details,
            category="procurement",
        )
    )

    deduped_categories = list(dict.fromkeys(failure_categories))
    is_valid = not deduped_categories
    summary = (
        "Validation passed with inspection-grade artifacts and grounded procurement."
        if is_valid
        else "Validation found blocking issues in " + ", ".join(deduped_categories) + "."
    )

    report = DesignValidationReport(
        design_id=design_id,
        revision_id=revision_id,
        candidate_id=candidate.candidate_id,
        is_valid=is_valid,
        summary=summary,
        failure_categories=deduped_categories,
        checks=checks,
        render_checks={
            "engineering_ready": bool(render_stats.get("engineering_ready", False)),
            "mesh_node_count": mesh_count,
            "material_count": material_count,
            "task_geometry_profile": geometry_profile,
        },
        artifact_paths=artifact_paths,
    )

    output_dir = output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{timestamp}-{design_id}-{revision_id}.json"
    output_path.write_text(json.dumps(report.model_dump(), indent=2))
    return report.model_copy(update={"output_path": str(output_path)})
