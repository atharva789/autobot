from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.pipeline.bom_generator import generate_bom_for_candidate
from packages.pipeline.design_generator import build_render_payload
from packages.pipeline.schemas import (
    BOMOutput,
    CandidateTelemetry,
    RobotDesignCandidate,
    TaskSpec,
)
from packages.pipeline.telemetry import build_candidate_telemetry


def count_dof(candidate: RobotDesignCandidate) -> int:
    return (
        candidate.num_legs * candidate.leg_dof
        + candidate.num_arms * candidate.arm_dof
        + candidate.spine_dof
    )


def topology_label(candidate: RobotDesignCandidate) -> str:
    return (
        f"{candidate.embodiment_class} · {candidate.num_legs}L · "
        f"{candidate.num_arms}A · {candidate.spine_dof}S"
    )


def build_workspace_tasks(
    task_spec: TaskSpec,
    candidate: RobotDesignCandidate,
    telemetry: CandidateTelemetry,
    bom: BOMOutput,
) -> list[dict[str, Any]]:
    return [
        {
            "task_key": "design",
            "status": "review",
            "summary": f"Design {count_dof(candidate)}-DoF {task_spec.task_goal}",
            "payload_json": {
                "candidate_id": candidate.candidate_id,
                "topology": topology_label(candidate),
            },
        },
        {
            "task_key": "reach",
            "status": "active",
            "summary": f"{telemetry.estimated_reach_m:.2f} m estimated reach",
            "payload_json": {"target_reach_m": telemetry.estimated_reach_m},
        },
        {
            "task_key": "payload",
            "status": "done" if telemetry.payload_margin_kg >= 0 else "review",
            "summary": f"{candidate.payload_capacity_kg:.2f} kg capacity",
            "payload_json": {"payload_margin_kg": telemetry.payload_margin_kg},
        },
        {
            "task_key": "isaac",
            "status": "waiting",
            "summary": "USD conversion target",
            "payload_json": {"target": "usd"},
        },
        {
            "task_key": "cost",
            "status": "active" if bom.total_cost_usd is not None else "waiting",
            "summary": (
                f"${int(round(bom.total_cost_usd)):,}"
                if bom.total_cost_usd is not None
                else "pricing still resolving"
            ),
            "payload_json": {
                "estimated_total_cost_usd": bom.total_cost_usd,
                "procurement_confidence": bom.procurement_confidence,
            },
        },
    ]


def build_checkpoints(
    candidate: RobotDesignCandidate,
    telemetry: CandidateTelemetry,
    bom: BOMOutput,
) -> list[dict[str, Any]]:
    actuator_item = bom.actuator_items[0] if bom.actuator_items else None
    actuator_reference_cost = (
        actuator_item.unit_price_usd
        if actuator_item and actuator_item.unit_price_usd is not None
        else telemetry.estimated_total_cost_usd or 1200
    )
    actuator_before_cost = max(
        120,
        round(actuator_reference_cost * 0.72),
    )
    actuator_after_cost = (
        actuator_item.unit_price_usd
        if actuator_item and actuator_item.unit_price_usd is not None
        else max(180, round(((telemetry.estimated_total_cost_usd or 1200) * 0.14)))
    )

    platform_mass_before = max(0.5, telemetry.estimated_mass_kg * 0.86)
    margin_before = telemetry.payload_margin_kg + 0.22
    bandwidth_before = telemetry.estimated_bandwidth_hz + 16

    return [
        {
            "checkpoint_key": "actuator",
            "label": "Checkpoint",
            "title": (
                "Approve actuator · J2 shoulder"
                if candidate.num_arms > 0
                else "Approve actuator · J1 drivetrain"
            ),
            "summary": (
                f"{candidate.actuator_class.upper()} selected over the lower-cost baseline. "
                f"Torque +{max(1, round(candidate.actuator_torque_nm * 0.22))} Nm, "
                f"backlash ≤ {telemetry.estimated_backlash_deg:.1f}°, "
                f"BOM +${int(round(actuator_after_cost - actuator_before_cost)):,} per unit."
            ),
            "rows_json": [
                {
                    "field": "type",
                    "before": _baseline_actuator_name(candidate),
                    "after": _actuator_display_name(candidate, bom),
                },
                {
                    "field": "torque",
                    "before": f"{max(1, round(candidate.actuator_torque_nm * 0.78))} Nm",
                    "after": f"{round(candidate.actuator_torque_nm)} Nm",
                },
                {
                    "field": "backlash",
                    "before": f"{max(0.2, telemetry.estimated_backlash_deg * 3.8):.1f}°",
                    "after": f"≤ {telemetry.estimated_backlash_deg:.1f}°",
                },
                {
                    "field": "unit cost",
                    "before": _format_money(float(actuator_before_cost)),
                    "after": _format_money(float(actuator_after_cost)),
                },
            ],
            "metadata_json": {
                "mutation": "actuator_upgrade",
                "torque_scale": 1.12,
                "cost_scale": 1.11,
            },
            "status": "review",
            "decision": "pending",
        },
        {
            "checkpoint_key": "payload",
            "label": "Budget",
            "title": "Confirm payload budget",
            "summary": (
                f"Payload margin is {telemetry.payload_margin_kg:.2f} kg after the current sensor "
                "and end-effector assumptions. Still within spec, but future margin is tight."
            ),
            "rows_json": [
                {
                    "field": "mass",
                    "before": f"{platform_mass_before:.2f} kg",
                    "after": f"{telemetry.estimated_mass_kg:.2f} kg",
                },
                {
                    "field": "margin",
                    "before": f"{margin_before:.2f} kg",
                    "after": f"{telemetry.payload_margin_kg:.2f} kg",
                },
                {
                    "field": "bandwidth",
                    "before": f"{bandwidth_before:.0f} Hz",
                    "after": f"{telemetry.estimated_bandwidth_hz:.0f} Hz",
                },
            ],
            "metadata_json": {
                "mutation": "payload_budget",
                "mass_scale": 1.06,
                "payload_scale": 0.92,
            },
            "status": "review",
            "decision": "pending",
        },
    ]


def build_export_items(
    artifacts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    artifacts = artifacts or {}
    return [
        {
            "label": "URDF",
            "subtitle": "ROS 2 Humble",
            "status": "ready" if artifacts.get("urdf") else "queued",
        },
        {
            "label": "MJCF",
            "subtitle": "MuJoCo 3.2",
            "status": "ready" if artifacts.get("mjcf") else "queued",
        },
        {
            "label": "USD",
            "subtitle": "Isaac Sim 4.5",
            "status": "ready" if artifacts.get("usd") else "queued",
        },
        {
            "label": "STEP",
            "subtitle": "CAD",
            "status": "ready" if artifacts.get("step") else "queued",
        },
    ]


def apply_checkpoint_decision(
    task_spec: TaskSpec,
    candidate: RobotDesignCandidate,
    checkpoint_key: str,
    decision: str,
    note: str | None = None,
) -> tuple[RobotDesignCandidate, dict[str, Any]]:
    updated = deepcopy(candidate.model_dump())
    delta: dict[str, Any] = {
        "checkpoint_key": checkpoint_key,
        "decision": decision,
        "note": note,
    }

    if checkpoint_key == "actuator" and decision == "approved":
        updated["actuator_torque_nm"] = round(candidate.actuator_torque_nm * 1.12, 2)
        updated["joint_stiffness"] = round(candidate.joint_stiffness * 1.08, 2)
        updated["rationale"] = (
            f"{candidate.rationale} Approved actuator upgrade to improve climbing authority."
        ).strip()
        delta["changes"] = {
            "actuator_torque_nm": updated["actuator_torque_nm"],
            "joint_stiffness": updated["joint_stiffness"],
        }
    elif checkpoint_key == "payload" and decision == "approved":
        updated["total_mass_kg"] = round(candidate.total_mass_kg * 1.06, 2)
        updated["payload_capacity_kg"] = round(candidate.payload_capacity_kg * 0.92, 2)
        updated["rationale"] = (
            f"{candidate.rationale} Payload budget checkpoint accepted with a heavier wrist package."
        ).strip()
        delta["changes"] = {
            "total_mass_kg": updated["total_mass_kg"],
            "payload_capacity_kg": updated["payload_capacity_kg"],
        }
    elif decision == "denied":
        updated["rationale"] = (
            f"{candidate.rationale} Rejected {checkpoint_key} modification pending a safer alternative."
        ).strip()
        delta["changes"] = {"rationale": updated["rationale"]}
    else:
        updated["rationale"] = (
            f"{candidate.rationale} {checkpoint_key} left parked for further guidance."
        ).strip()
        delta["changes"] = {"rationale": updated["rationale"]}

    mutated = RobotDesignCandidate.model_validate(updated)
    return mutated, delta


def rebuild_revision_payload(
    task_spec: TaskSpec,
    candidate: RobotDesignCandidate,
) -> tuple[RobotDesignCandidate, dict[str, Any], BOMOutput, CandidateTelemetry]:
    render_payload = build_render_payload(candidate, task_spec)
    bom = generate_bom_for_candidate(candidate)
    telemetry = build_candidate_telemetry(candidate, bom, task_spec)
    return candidate, render_payload, bom, telemetry


def build_playback(
    task_spec: TaskSpec,
    candidate: RobotDesignCandidate,
    telemetry: CandidateTelemetry,
    ingest_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal = task_spec.task_goal.lower()
    if any(term in goal for term in ("climb", "wall", "vertical")):
        motion_profile = "climbing"
    elif any(term in goal for term in ("carry", "lift", "payload")):
        motion_profile = "load_carry"
    else:
        motion_profile = "mobility_preview"

    source_type = "unavailable"
    source_ready = False
    source_ref: dict[str, Any] = {}
    provenance_summary = (
        "No motion source is available for truthful replay yet. "
        "The system can only show a non-source-backed preview scaffold."
    )

    if ingest_job:
        reference_source_type = str(ingest_job.get("reference_source_type") or "").strip()
        reference_payload = ingest_job.get("reference_payload_json")
        selected_query = ingest_job.get("selected_query")
        gvhmr_job_id = ingest_job.get("gvhmr_job_id")
        source_url = ingest_job.get("source_url")

        if (reference_source_type == "youtube" or (not reference_source_type and source_url)) and source_url:
            source_type = "youtube_gvhmr" if gvhmr_job_id else "youtube_reference"
            source_ready = gvhmr_job_id is not None
            source_ref = {
                "video_url": source_url,
                "video_id": _video_id_from_url(str(source_url)),
                "gvhmr_job_id": gvhmr_job_id,
                "selected_query": selected_query,
            }
            provenance_summary = (
                "Replay sourced from YouTube reference motion with GVHMR extraction."
                if gvhmr_job_id
                else "Replay sourced from YouTube reference selection only; GVHMR extraction is not ready."
            )
        elif reference_source_type == "droid" and isinstance(reference_payload, dict):
            reference = reference_payload.get("reference")
            if isinstance(reference, dict):
                trajectory_window = reference.get("trajectory_window")
                source_type = (
                    "droid_window"
                    if isinstance(trajectory_window, (list, tuple)) and len(trajectory_window) == 2
                    else "droid_episode"
                )
                source_ready = True
                source_ref = {
                    "episode_id": reference.get("episode_id"),
                    "source_format": reference.get("source_format"),
                    "action_path": reference.get("action_path"),
                    "state_path": reference.get("state_path"),
                    "camera_refs": reference.get("camera_refs") or {},
                    "trajectory_window": list(trajectory_window)
                    if isinstance(trajectory_window, tuple)
                    else trajectory_window,
                    "query_text": reference_payload.get("query_text"),
                }
                provenance_summary = (
                    "Replay sourced from DROID window retrieval."
                    if source_type == "droid_window"
                    else "Replay sourced from full DROID episode retrieval."
                )

    return {
        "candidate_id": candidate.candidate_id,
        "task_goal": task_spec.task_goal,
        "motion_profile": motion_profile,
        "duration_s": 8.0,
        "camera_mode": "engineering_follow",
        "estimated_reach_m": telemetry.estimated_reach_m,
        "source_type": source_type,
        "source_ready": source_ready,
        "source_ref": source_ref,
        "provenance_summary": provenance_summary,
    }


def _video_id_from_url(url: str) -> str | None:
    if "watch?v=" in url:
        return url.split("watch?v=", 1)[1].split("&", 1)[0]
    return None


def _baseline_actuator_name(candidate: RobotDesignCandidate) -> str:
    mapping = {
        "bldc": "servo · S-18",
        "servo": "stepper · N24",
        "stepper": "servo · S-18",
        "hydraulic": "bldc · BX-45",
    }
    return mapping.get(candidate.actuator_class, "servo · S-18")


def _actuator_display_name(candidate: RobotDesignCandidate, bom: BOMOutput) -> str:
    primary = bom.actuator_items[0] if bom.actuator_items else None
    if primary and primary.sku:
        return f"{candidate.actuator_class} · {primary.sku}"
    return f"{candidate.actuator_class} · T{round(candidate.actuator_torque_nm)}"


def _format_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${int(round(value)):,}"
