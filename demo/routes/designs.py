"""FastAPI router for robot design generation and selection.

Endpoints:
- POST /designs/generate - Generate 3 design candidates from ingest job
- GET /designs/{design_id} - Get a specific design
- GET /designs/{design_id}/bom - Get BOM for a design
- POST /designs/{design_id}/select - Select a design for evolution
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, UTC
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from packages.pipeline.bom_generator import generate_bom_for_candidate
from packages.pipeline.design_generator import build_render_payload, generate_design_candidates
from packages.pipeline.design_diversity import apply_diversity_controls
from packages.pipeline.design_revision import derive_revised_task_spec, revise_candidate_for_instruction
from packages.pipeline.design_validation import build_design_validation_report
from packages.pipeline.design_runtime import (
    apply_checkpoint_decision,
    build_checkpoints,
    build_export_items,
    build_playback,
    build_workspace_tasks,
    rebuild_revision_payload,
)
from packages.pipeline.fallback_chooser import rank_candidates_fallback
from packages.pipeline.photon import build_photon_messenger_from_env, photon_provider_ready
from packages.pipeline.schemas import (
    BOMOutput,
    CandidateTelemetry,
    CollapseDetectionReport,
    DesignValidationReport,
    DesignCandidatesResponse,
    FallbackRanking,
    RobotDesignCandidate,
    TaskSpec,
)
from packages.pipeline.telemetry import build_candidate_telemetry
from demo.workspace_store import workspace_store

router = APIRouter(prefix="/designs", tags=["designs"])
logger = logging.getLogger(__name__)


class GenerateDesignsRequest(BaseModel):
    ingest_job_id: str


class GenerateDesignsResponse(BaseModel):
    design_ids: dict[Literal["A", "B", "C"], str]
    candidates: list[RobotDesignCandidate]
    model_preferred_id: Literal["A", "B", "C"]
    fallback_rankings: list[FallbackRanking]
    selection_rationale: str
    collapse_report: CollapseDetectionReport | None = None
    render_payloads: dict[Literal["A", "B", "C"], dict]
    candidate_telemetry: dict[Literal["A", "B", "C"], CandidateTelemetry]


class SelectDesignRequest(BaseModel):
    evolution_id: str


class CheckpointDecisionRequest(BaseModel):
    decision: Literal["approved", "denied", "parked"]
    note: str | None = None


class TaskRunRequest(BaseModel):
    task_key: str
    payload: dict | None = None


class RecordClipRequest(BaseModel):
    mode: str = "task_preview"


class ReviseDesignRequest(BaseModel):
    instruction: str


def _append_design_event(
    design_id: str,
    event_type: str,
    data: dict,
    *,
    revision_id: str | None = None,
) -> dict:
    return workspace_store.append_design_event(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": revision_id,
            "event_type": event_type,
            "data_json": data,
        }
    )


def format_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${int(round(value)):,}"


def _artifact_paths_for_design(design_id: str) -> dict[str, str]:
    return {
        item["artifact_key"]: item.get("path") or ""
        for item in workspace_store.list_design_artifacts(design_id)
    }


def _persist_validation_report(
    *,
    design_id: str,
    revision_id: str,
    task_spec: TaskSpec,
    candidate: RobotDesignCandidate,
    render_payload: dict,
    bom: BOMOutput,
    telemetry: CandidateTelemetry,
) -> DesignValidationReport:
    artifact_paths = {
        **_artifact_paths_for_design(design_id),
        "mjcf": f"artifacts/{design_id}/robot.mjcf",
        "render_glb": f"artifacts/{design_id}/render.glb",
        "ui_scene": f"artifacts/{design_id}/ui_scene.json",
    }
    report = build_design_validation_report(
        design_id=design_id,
        revision_id=revision_id,
        task_spec=task_spec,
        candidate=candidate,
        render_payload=render_payload,
        bom=bom,
        telemetry=telemetry,
        artifact_paths=artifact_paths,
    )
    workspace_store.set_design_artifact(
        design_id,
        "validation_report",
        report.model_dump(),
        revision_id=revision_id,
        status="ready" if report.is_valid else "warning",
        path=report.output_path,
    )
    return report


@router.post("/generate", status_code=201)
def generate_designs(req: GenerateDesignsRequest) -> GenerateDesignsResponse:
    """Generate 3 robot design candidates from an ingest job.

    Reads the TaskSpec from the ingest job's er16_plan_json,
    calls Gemini for structured design generation,
    persists all 3 designs to the local workspace store,
    and returns the candidates with fallback rankings.
    """
    ingest_job = workspace_store.get_ingest_job(req.ingest_job_id)
    if not ingest_job:
        raise HTTPException(status_code=404, detail="Ingest job not found")

    try:
        plan_data = json.loads(ingest_job["er16_plan_json"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid er16_plan_json: {exc}"
        ) from exc

    try:
        task_spec = TaskSpec(
            task_goal=plan_data.get("task_goal", ""),
            environment=plan_data.get("environment", "indoor"),
            locomotion_type=plan_data.get("locomotion_type", "walking"),
            manipulation_required=plan_data.get("manipulation_required", False),
            payload_kg=plan_data.get("payload_kg", 0.0),
            success_criteria=plan_data.get("success_criteria", ""),
            search_queries=plan_data.get("search_queries", ["robot task"]),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse TaskSpec: {exc}"
        ) from exc

    try:
        design_response: DesignCandidatesResponse = generate_design_candidates(
            task_spec
        )
    except RuntimeError as exc:
        logger.exception("Design generation failed for ingest_job_id=%s", req.ingest_job_id)
        raise HTTPException(
            status_code=502, detail=f"Gemini design generation failed: {exc}"
        ) from exc

    render_payloads: dict[Literal["A", "B", "C"], dict] = {
        candidate.candidate_id: build_render_payload(candidate, task_spec)
        for candidate in design_response.candidates
    }
    prior_design_contexts = workspace_store.list_recent_design_contexts(
        limit=24,
        exclude_ingest_job_id=req.ingest_job_id,
    )
    design_response = apply_diversity_controls(
        design_response,
        task_spec,
        render_payloads,
        prior_design_contexts=prior_design_contexts,
    )

    fallback_rankings = rank_candidates_fallback(design_response.candidates)
    ranking_map = {ranking.candidate_id: ranking for ranking in fallback_rankings}

    design_ids: dict[Literal["A", "B", "C"], str] = {}
    candidate_telemetry: dict[Literal["A", "B", "C"], CandidateTelemetry] = {}
    for candidate in design_response.candidates:
        design_id = str(uuid.uuid4())
        design_ids[candidate.candidate_id] = design_id
        bom = generate_bom_for_candidate(candidate)
        telemetry = build_candidate_telemetry(candidate, bom, task_spec)
        candidate_telemetry[candidate.candidate_id] = telemetry

        is_model_preferred = (
            candidate.candidate_id == design_response.model_preferred_id
        )
        ranking = ranking_map.get(candidate.candidate_id)

        workspace_store.create_design(
            {
                "id": design_id,
                "ingest_job_id": req.ingest_job_id,
                "candidate_id": candidate.candidate_id,
                "design_json": candidate.model_dump(),
                "render_json": render_payloads[candidate.candidate_id],
                "bom_json": bom.model_dump(),
                "telemetry_json": telemetry.model_dump(),
                "is_model_preferred": is_model_preferred,
                "is_user_selected": False,
                "screening_score": ranking.total_score if ranking else None,
            }
        )
        revision_id = str(uuid.uuid4())
        workspace_store.create_design_revision(
            {
                "id": revision_id,
                "design_id": design_id,
                "revision_number": 1,
                "parent_revision_id": None,
                "design_json": candidate.model_dump(),
                "render_json": render_payloads[candidate.candidate_id],
                "bom_json": bom.model_dump(),
                "telemetry_json": telemetry.model_dump(),
                "delta_json": {
                    "source": "initial_generation",
                    "selection_rationale": design_response.selection_rationale,
                },
            }
        )
        checkpoints = build_checkpoints(candidate, telemetry, bom)
        workspace_store.replace_design_checkpoints(
            design_id,
            revision_id,
            [
                {
                    "id": f"{revision_id}:{checkpoint['checkpoint_key']}",
                    "design_id": design_id,
                    "revision_id": revision_id,
                    **checkpoint,
                }
                for checkpoint in checkpoints
            ],
        )
        for checkpoint in workspace_store.list_design_checkpoints(design_id, revision_id):
            _append_design_event(
                design_id,
                "checkpoint.created",
                checkpoint,
                revision_id=revision_id,
            )
        for task in build_workspace_tasks(task_spec, candidate, telemetry, bom):
            task_run = workspace_store.create_task_run(
                {
                    "id": str(uuid.uuid4()),
                    "design_id": design_id,
                    "revision_id": revision_id,
                    **task,
                    "result_json": None,
                }
            )
            _append_design_event(
                design_id,
                "task.created",
                task_run,
                revision_id=revision_id,
            )
        workspace_store.set_design_artifact(
            design_id,
            "mjcf",
            render_payloads[candidate.candidate_id]["mjcf"],
            revision_id=revision_id,
            status="ready",
            path=f"artifacts/{design_id}/robot.mjcf",
        )
        workspace_store.set_design_artifact(
            design_id,
            "render_glb",
            render_payloads[candidate.candidate_id]["render_glb"],
            revision_id=revision_id,
            status="ready",
            path=f"artifacts/{design_id}/render.glb",
        )
        workspace_store.set_design_artifact(
            design_id,
            "ui_scene",
            render_payloads[candidate.candidate_id]["ui_scene"],
            revision_id=revision_id,
            status="ready",
            path=f"artifacts/{design_id}/ui_scene.json",
        )
        if design_response.collapse_report is not None:
            workspace_store.set_design_artifact(
                design_id,
                "diversity_report",
                design_response.collapse_report.model_dump(),
                revision_id=revision_id,
                status="ready",
                path=f"artifacts/{design_id}/diversity_report.json",
            )
        _persist_validation_report(
            design_id=design_id,
            revision_id=revision_id,
            task_spec=task_spec,
            candidate=candidate,
            render_payload=render_payloads[candidate.candidate_id],
            bom=bom,
            telemetry=telemetry,
        )
        _append_design_event(
            design_id,
            "revision.created",
            {
                "design_id": design_id,
                "revision_id": revision_id,
                "revision_number": 1,
                "spec": {
                    "design_id": design_id,
                    "candidate_id": candidate.candidate_id,
                    "revision_id": revision_id,
                    "revision_number": 1,
                    "design": candidate.model_dump(),
                    "telemetry": telemetry.model_dump(),
                    "bom": bom.model_dump(),
                    "render": render_payloads[candidate.candidate_id],
                    "approval_events": [],
                },
            },
            revision_id=revision_id,
        )

    return GenerateDesignsResponse(
        design_ids=design_ids,
        candidates=design_response.candidates,
        model_preferred_id=design_response.model_preferred_id,
        fallback_rankings=fallback_rankings,
        selection_rationale=design_response.selection_rationale,
        collapse_report=design_response.collapse_report,
        render_payloads=render_payloads,
        candidate_telemetry=candidate_telemetry,
    )


@router.get("/{design_id}")
def get_design(design_id: str) -> dict:
    """Get a specific design by ID."""
    row = workspace_store.get_design(design_id)
    if not row:
        raise HTTPException(status_code=404, detail="Design not found")
    return row


@router.get("/{design_id}/spec")
def get_design_spec(design_id: str) -> dict:
    design = workspace_store.get_design(design_id)
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")
    revision = workspace_store.get_latest_design_revision(design_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Design revision not found")
    return {
        "design_id": design_id,
        "candidate_id": design["candidate_id"],
        "revision_id": revision["id"],
        "revision_number": revision["revision_number"],
        "design": revision["design_json"],
        "telemetry": revision.get("telemetry_json"),
        "bom": revision.get("bom_json"),
        "render": revision.get("render_json"),
        "approval_events": workspace_store.list_approval_events(design_id),
    }


@router.get("/{design_id}/checkpoints")
def get_design_checkpoints(design_id: str) -> dict:
    revision = workspace_store.get_latest_design_revision(design_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Design revision not found")
    items = []
    for checkpoint in workspace_store.list_design_checkpoints(design_id, revision["id"]):
        items.append(
            {
                "id": checkpoint["checkpoint_key"],
                "db_id": checkpoint["id"],
                **{k: v for k, v in checkpoint.items() if k != "id"},
            }
        )
    return {
        "design_id": design_id,
        "revision_id": revision["id"],
        "items": items,
    }


@router.get("/{design_id}/tasks")
def get_design_tasks(design_id: str) -> dict:
    if not workspace_store.get_design(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    return {
        "design_id": design_id,
        "items": workspace_store.list_task_runs(design_id),
    }


@router.get("/{design_id}/events")
def stream_design_events(
    design_id: str,
    after_seq: int = 0,
    follow: bool = True,
    limit: int = 200,
    replay_delay_ms: int = 80,
):
    if not workspace_store.get_design(design_id):
        raise HTTPException(status_code=404, detail="Design not found")

    def iter_events():
        cursor = after_seq
        while True:
            rows = workspace_store.list_design_events(design_id, after_seq=cursor, limit=limit)
            for row in rows:
                cursor = max(cursor, int(row["seq"]))
                payload = {
                    "seq": row["seq"],
                    "event_type": row["event_type"],
                    "revision_id": row.get("revision_id"),
                    "created_at": row.get("created_at"),
                    "data": row.get("data_json"),
                }
                yield f"id: {row['seq']}\nevent: {row['event_type']}\ndata: {json.dumps(payload)}\n\n"
                if replay_delay_ms > 0:
                    time.sleep(replay_delay_ms / 1000.0)
            if not follow:
                break
            yield ": keep-alive\n\n"
            time.sleep(0.35)

    return StreamingResponse(iter_events(), media_type="text/event-stream")


@router.get("/{design_id}/exports")
def get_design_exports(design_id: str) -> dict:
    if not workspace_store.get_design(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    artifacts = {
        item["artifact_key"]: item
        for item in workspace_store.list_design_artifacts(design_id)
    }
    return {
        "design_id": design_id,
        "items": build_export_items(artifacts),
        "artifacts": artifacts,
    }


@router.get("/{design_id}/validation")
def get_design_validation(design_id: str) -> dict:
    if not workspace_store.get_design(design_id):
        raise HTTPException(status_code=404, detail="Design not found")
    artifacts = workspace_store.list_design_artifacts(design_id)
    validation_artifact = next(
        (item for item in artifacts if item["artifact_key"] == "validation_report"),
        None,
    )
    if validation_artifact is None:
        raise HTTPException(status_code=404, detail="Validation report not found")
    return {
        "design_id": design_id,
        "report": validation_artifact.get("data_json"),
        "artifacts": artifacts,
    }


@router.get("/{design_id}/bom")
def get_design_bom(design_id: str) -> BOMOutput:
    """Get the BOM for a specific design."""
    row = workspace_store.get_design(design_id)
    if not row:
        raise HTTPException(status_code=404, detail="Design not found")

    if row.get("bom_json"):
        return BOMOutput.model_validate(row["bom_json"])

    try:
        candidate = RobotDesignCandidate.model_validate(row["design_json"])
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse design_json: {exc}"
        ) from exc

    bom = generate_bom_for_candidate(candidate)

    workspace_store.update_design(design_id, {"bom_json": bom.model_dump()})

    return bom


@router.post("/{design_id}/checkpoints/{checkpoint_key}/decision")
def decide_checkpoint(
    design_id: str,
    checkpoint_key: str,
    req: CheckpointDecisionRequest,
) -> dict:
    design = workspace_store.get_design(design_id)
    if not design:
        raise HTTPException(status_code=404, detail="Design not found")
    ingest = workspace_store.get_ingest_job(design["ingest_job_id"])
    revision = workspace_store.get_latest_design_revision(design_id)
    if not ingest or not revision:
        raise HTTPException(status_code=404, detail="Design runtime state not found")
    plan_data = json.loads(ingest["er16_plan_json"])
    task_spec = TaskSpec.model_validate(plan_data)
    current_candidate = RobotDesignCandidate.model_validate(revision["design_json"])
    checkpoint = next(
        (
            item
            for item in workspace_store.list_design_checkpoints(design_id, revision["id"])
            if item["checkpoint_key"] == checkpoint_key
        ),
        None,
    )
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    approval_event = workspace_store.create_approval_event(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": revision["id"],
            "checkpoint_id": checkpoint["id"],
            "decision": req.decision,
            "note": req.note,
        }
    )
    workspace_store.update_design_checkpoint(
        checkpoint["id"],
        {
            "decision": req.decision,
            "note": req.note,
            "status": "done" if req.decision != "parked" else "waiting",
            "decided_at": datetime.now(UTC).isoformat(),
        },
    )
    _append_design_event(
        design_id,
        "checkpoint.decided",
        {
            "checkpoint_key": checkpoint_key,
            "decision": req.decision,
            "note": req.note,
            "approval_event": approval_event,
        },
        revision_id=revision["id"],
    )

    mutated_candidate, delta = apply_checkpoint_decision(
        task_spec,
        current_candidate,
        checkpoint_key,
        req.decision,
        req.note,
    )
    _, render_payload, bom, telemetry = rebuild_revision_payload(task_spec, mutated_candidate)
    new_revision = workspace_store.create_design_revision(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_number": int(revision["revision_number"]) + 1,
            "parent_revision_id": revision["id"],
            "design_json": mutated_candidate.model_dump(),
            "render_json": render_payload,
            "bom_json": bom.model_dump(),
            "telemetry_json": telemetry.model_dump(),
            "delta_json": delta,
        }
    )
    refreshed_checkpoints = build_checkpoints(mutated_candidate, telemetry, bom)
    for item in refreshed_checkpoints:
        if item["checkpoint_key"] == checkpoint_key:
            item["decision"] = req.decision
            item["status"] = "done" if req.decision != "parked" else "waiting"
            item["metadata_json"] = {
                **(item.get("metadata_json") or {}),
                "applied_note": req.note,
            }
    workspace_store.replace_design_checkpoints(
        design_id,
        new_revision["id"],
        [
            {
                "id": f"{new_revision['id']}:{item['checkpoint_key']}",
                "design_id": design_id,
                "revision_id": new_revision["id"],
                **item,
            }
            for item in refreshed_checkpoints
        ],
    )
    workspace_store.update_design(
        design_id,
        {
            "design_json": mutated_candidate.model_dump(),
            "render_json": render_payload,
            "bom_json": bom.model_dump(),
            "telemetry_json": telemetry.model_dump(),
        },
    )
    workspace_store.set_design_artifact(
        design_id,
        "mjcf",
        render_payload["mjcf"],
        revision_id=new_revision["id"],
        status="ready",
        path=f"artifacts/{design_id}/robot.mjcf",
    )
    workspace_store.set_design_artifact(
        design_id,
        "render_glb",
        render_payload["render_glb"],
        revision_id=new_revision["id"],
        status="ready",
        path=f"artifacts/{design_id}/render.glb",
    )
    workspace_store.set_design_artifact(
        design_id,
        "ui_scene",
        render_payload["ui_scene"],
        revision_id=new_revision["id"],
        status="ready",
        path=f"artifacts/{design_id}/ui_scene.json",
    )
    _persist_validation_report(
        design_id=design_id,
        revision_id=new_revision["id"],
        task_spec=task_spec,
        candidate=mutated_candidate,
        render_payload=render_payload,
        bom=bom,
        telemetry=telemetry,
    )
    _append_design_event(
        design_id,
        "revision.created",
        {
            "design_id": design_id,
            "revision_id": new_revision["id"],
            "revision_number": new_revision["revision_number"],
            "spec": {
                "design_id": design_id,
                "candidate_id": design["candidate_id"],
                "revision_id": new_revision["id"],
                "revision_number": new_revision["revision_number"],
                "design": mutated_candidate.model_dump(),
                "telemetry": telemetry.model_dump(),
                "bom": bom.model_dump(),
                "render": render_payload,
                "approval_events": workspace_store.list_approval_events(design_id),
            },
        },
        revision_id=new_revision["id"],
    )

    return {
        "design_id": design_id,
        "revision_id": new_revision["id"],
        "revision_number": new_revision["revision_number"],
        "approval_event": approval_event,
        "design": mutated_candidate.model_dump(),
        "telemetry": telemetry.model_dump(),
    }


@router.post("/{design_id}/tasks", status_code=201)
def run_design_task(design_id: str, req: TaskRunRequest) -> dict:
    design = workspace_store.get_design(design_id)
    revision = workspace_store.get_latest_design_revision(design_id)
    if not design or not revision:
        raise HTTPException(status_code=404, detail="Design runtime state not found")
    ingest = workspace_store.get_ingest_job(design["ingest_job_id"])
    task_spec = TaskSpec.model_validate(json.loads(ingest["er16_plan_json"]))
    candidate = RobotDesignCandidate.model_validate(revision["design_json"])
    telemetry = CandidateTelemetry.model_validate(revision["telemetry_json"])
    bom = BOMOutput.model_validate(revision["bom_json"])

    task_run = workspace_store.create_task_run(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": revision["id"],
            "task_key": req.task_key,
            "status": "running",
            "summary": f"Running {req.task_key}",
            "payload_json": req.payload or {},
            "result_json": None,
        }
    )
    _append_design_event(
        design_id,
        "task.created",
        task_run,
        revision_id=revision["id"],
    )
    result: dict | None = None
    summary = task_run["summary"]

    if req.task_key == "cost_bom_vs_budget":
        budget_status = "within budget" if telemetry.payload_margin_kg >= 0 else "over budget"
        summary = (
            f"Cost {format_money(bom.total_cost_usd)} vs payload budget: {budget_status}; "
            f"payload margin {telemetry.payload_margin_kg:.2f} kg."
        )
        result = {
            "estimated_total_cost_usd": bom.total_cost_usd,
            "payload_margin_kg": telemetry.payload_margin_kg,
        }
    elif req.task_key == "export_urdf":
        urdf_text = f"<robot name=\"design-{design_id}\"></robot>"
        workspace_store.set_design_artifact(
            design_id,
            "urdf",
            urdf_text,
            revision_id=revision["id"],
            status="ready",
            path=f"artifacts/{design_id}/robot.urdf",
        )
        summary = "URDF export compiled and staged."
        result = {"path": f"artifacts/{design_id}/robot.urdf"}
    elif req.task_key == "send_review_poll":
        if not photon_provider_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Photon is not configured. Set PHOTON_PROJECT_ID and PHOTON_SECRET_KEY "
                    "for Spectrum delivery, or PHOTON_BASE_URL for the local HTTP shim."
                ),
            )
        recipient_record = workspace_store.get_default_hitl_recipient("photon")
        recipient = ""
        if recipient_record and recipient_record.get("consent_status") == "confirmed":
            recipient = str(recipient_record.get("recipient") or "").strip()
            thread_key = str(recipient_record.get("thread_key") or "").strip() or None
        else:
            thread_key = None
        if not recipient:
            recipient = os.environ.get("PHOTON_RECIPIENT", "").strip()
        if not recipient:
            raise HTTPException(status_code=400, detail="A confirmed Photon recipient must be configured.")
        messenger = build_photon_messenger_from_env()
        dispatch = messenger.send_design_review(
            recipient=recipient,
            design_id=design_id,
            candidate_id=str(design["candidate_id"]),
            telemetry=telemetry,
            thread_key=thread_key,
        )
        summary = "Photon review poll sent."
        result = {
            "ok": dispatch.ok,
            "message_id": dispatch.message_id,
            "payload": dispatch.payload,
            "raw_response": dispatch.raw_response,
        }
    else:
        summary = f"Task {req.task_key} completed."
        result = {"task_key": req.task_key}

    workspace_store.update_task_run(
        task_run["id"],
        {
            "status": "done",
            "summary": summary,
            "result_json": result,
        },
    )
    updated_task = workspace_store.get_task_run(task_run["id"])
    _append_design_event(
        design_id,
        "task.updated",
        updated_task,
        revision_id=revision["id"],
    )
    return {"task_run": updated_task}


@router.post("/{design_id}/record-clip", status_code=201)
def record_clip(design_id: str, req: RecordClipRequest) -> dict:
    design = workspace_store.get_design(design_id)
    revision = workspace_store.get_latest_design_revision(design_id)
    if not design or not revision:
        raise HTTPException(status_code=404, detail="Design runtime state not found")
    ingest = workspace_store.get_ingest_job(design["ingest_job_id"])
    task_spec = TaskSpec.model_validate(json.loads(ingest["er16_plan_json"]))
    candidate = RobotDesignCandidate.model_validate(revision["design_json"])
    telemetry = CandidateTelemetry.model_validate(revision["telemetry_json"])
    playback = build_playback(task_spec, candidate, telemetry, ingest)
    summary = (
        f"{playback['motion_profile']} playback prepared from {playback['source_type']}"
        if playback["source_ready"]
        else f"{playback['motion_profile']} preview prepared without a verified motion source"
    )
    task_run = workspace_store.create_task_run(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": revision["id"],
            "task_key": "record_clip",
            "status": "done",
            "summary": summary,
            "payload_json": {"mode": req.mode},
            "result_json": playback,
        }
    )
    _append_design_event(
        design_id,
        "playback.ready",
        {
            "task_run": task_run,
            "playback": playback,
        },
        revision_id=revision["id"],
    )
    return {"task_run": task_run, "playback": playback}


@router.post("/{design_id}/revise", status_code=201)
def revise_design(design_id: str, req: ReviseDesignRequest) -> dict:
    design = workspace_store.get_design(design_id)
    revision = workspace_store.get_latest_design_revision(design_id)
    if not design or not revision:
        raise HTTPException(status_code=404, detail="Design runtime state not found")
    ingest = workspace_store.get_ingest_job(design["ingest_job_id"])
    if not ingest:
        raise HTTPException(status_code=404, detail="Ingest job not found")

    task_spec = TaskSpec.model_validate(json.loads(ingest["er16_plan_json"]))
    revised_task_spec = derive_revised_task_spec(task_spec, req.instruction)
    current_candidate = RobotDesignCandidate.model_validate(revision["design_json"])
    revised_candidate, delta = revise_candidate_for_instruction(
        current_candidate,
        revised_task_spec,
        req.instruction,
    )
    _, render_payload, bom, telemetry = rebuild_revision_payload(revised_task_spec, revised_candidate)

    new_revision = workspace_store.create_design_revision(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_number": int(revision["revision_number"]) + 1,
            "parent_revision_id": revision["id"],
            "design_json": revised_candidate.model_dump(),
            "render_json": render_payload,
            "bom_json": bom.model_dump(),
            "telemetry_json": telemetry.model_dump(),
            "delta_json": delta,
        }
    )
    workspace_store.update_design(
        design_id,
        {
            "design_json": revised_candidate.model_dump(),
            "render_json": render_payload,
            "bom_json": bom.model_dump(),
            "telemetry_json": telemetry.model_dump(),
        },
    )
    checkpoints = build_checkpoints(revised_candidate, telemetry, bom)
    workspace_store.replace_design_checkpoints(
        design_id,
        new_revision["id"],
        [
            {
                "id": f"{new_revision['id']}:{item['checkpoint_key']}",
                "design_id": design_id,
                "revision_id": new_revision["id"],
                **item,
            }
            for item in checkpoints
        ],
    )
    workspace_store.set_design_artifact(
        design_id,
        "mjcf",
        render_payload["mjcf"],
        revision_id=new_revision["id"],
        status="ready",
        path=f"artifacts/{design_id}/robot.mjcf",
    )
    workspace_store.set_design_artifact(
        design_id,
        "render_glb",
        render_payload["render_glb"],
        revision_id=new_revision["id"],
        status="ready",
        path=f"artifacts/{design_id}/render.glb",
    )
    workspace_store.set_design_artifact(
        design_id,
        "ui_scene",
        render_payload["ui_scene"],
        revision_id=new_revision["id"],
        status="ready",
        path=f"artifacts/{design_id}/ui_scene.json",
    )
    _persist_validation_report(
        design_id=design_id,
        revision_id=new_revision["id"],
        task_spec=revised_task_spec,
        candidate=revised_candidate,
        render_payload=render_payload,
        bom=bom,
        telemetry=telemetry,
    )
    task_run = workspace_store.create_task_run(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": new_revision["id"],
            "task_key": "revise_design",
            "status": "done",
            "summary": f"Revised design for: {revised_task_spec.task_goal}",
            "payload_json": {"instruction": req.instruction},
            "result_json": delta,
        }
    )
    _append_design_event(
        design_id,
        "task.created",
        task_run,
        revision_id=new_revision["id"],
    )
    _append_design_event(
        design_id,
        "revision.created",
        {
            "design_id": design_id,
            "revision_id": new_revision["id"],
            "revision_number": new_revision["revision_number"],
            "spec": {
                "design_id": design_id,
                "candidate_id": design["candidate_id"],
                "revision_id": new_revision["id"],
                "revision_number": new_revision["revision_number"],
                "design": revised_candidate.model_dump(),
                "telemetry": telemetry.model_dump(),
                "bom": bom.model_dump(),
                "render": render_payload,
                "approval_events": workspace_store.list_approval_events(design_id),
            },
        },
        revision_id=new_revision["id"],
    )
    return {
        "design_id": design_id,
        "revision_id": new_revision["id"],
        "revision_number": new_revision["revision_number"],
        "spec": {
            "design_id": design_id,
            "candidate_id": design["candidate_id"],
            "revision_id": new_revision["id"],
            "revision_number": new_revision["revision_number"],
            "design": revised_candidate.model_dump(),
            "telemetry": telemetry.model_dump(),
            "bom": bom.model_dump(),
            "render": render_payload,
            "approval_events": workspace_store.list_approval_events(design_id),
        },
        "task_run": task_run,
    }


@router.post("/{design_id}/select")
def select_design(design_id: str, req: SelectDesignRequest) -> dict:
    """Select a design for an evolution.

    Marks the design as user_selected and updates the evolution to reference it.
    """
    design_row = workspace_store.get_design(design_id)
    if not design_row:
        raise HTTPException(status_code=404, detail="Design not found")

    workspace_store.clear_design_selection(design_row["ingest_job_id"])
    workspace_store.update_design(design_id, {"is_user_selected": True})
    workspace_store.update_evolution(req.evolution_id, {"design_id": design_id})

    return {
        "status": "selected",
        "design_id": design_id,
        "candidate_id": design_row["candidate_id"],
        "evolution_id": req.evolution_id,
    }


@router.get("/by-ingest/{ingest_job_id}")
def get_designs_by_ingest(ingest_job_id: str) -> list[dict]:
    """Get all designs for an ingest job."""
    return workspace_store.list_designs_by_ingest(ingest_job_id)
