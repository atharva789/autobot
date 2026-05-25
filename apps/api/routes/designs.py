from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.api.prompt_persistence import log_prompt_query
from apps.api.workspace_store import workspace_store
from packages.pipeline.grammar_graph import (
    DEFAULT_ROBOT_POPULATION,
)
from packages.research.agent_loops import AgentLoopConfig, list_agent_loops, run_agent_loop

router = APIRouter(prefix="/designs", tags=["designs"])

CandidateId = str


class GenerateDesignsRequest(BaseModel):
    ingest_job_id: str
    population: int | None = Field(default=None, ge=1, le=64)
    agent_loop: str | None = None


class CheckpointDecisionRequest(BaseModel):
    decision: Literal["approved", "denied", "parked"]
    note: str | None = None


class TaskRunRequest(BaseModel):
    task_key: str
    payload: dict[str, Any] | None = None


class ReviseDesignRequest(BaseModel):
    instruction: str


class SelectDesignRequest(BaseModel):
    evolution_id: str


@router.post("/generate")
def generate_designs(req: GenerateDesignsRequest) -> dict[str, Any]:
    ingest = workspace_store.get_ingest_job(req.ingest_job_id)
    if ingest is None:
        raise HTTPException(status_code=404, detail=f"Unknown ingest job: {req.ingest_job_id}")

    plan = _load_plan(ingest.get("er16_plan_json"))
    prompt = str(plan.get("task_goal") or ingest.get("selected_query") or "generate robot morphology")
    population = req.population or DEFAULT_ROBOT_POPULATION
    agent_loop = req.agent_loop or "grammar"
    try:
        loop_result = run_agent_loop(
            agent_loop,
            prompt,
            {"prompt": prompt, "candidates": [], "population": population},
            config=AgentLoopConfig(population=population),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    grammar_state = loop_result.state
    grammar_hitl = loop_result.hitl
    grammar_hitl.setdefault("population", population)
    grammar_state.setdefault("population", population)
    grammar_state.setdefault("hitl", grammar_hitl)
    log_prompt_query(
        event_type="robot_generation_query",
        prompt=prompt,
        query_text=prompt,
        ingest_job_id=req.ingest_job_id,
        normalized_query=grammar_hitl.get("spec"),
        population=population,
        langsmith_trace_id=grammar_hitl.get("langsmith_trace_id"),
        metadata={
            "route": "/designs/generate",
            "agent_loop": agent_loop,
            "compile_safe": grammar_hitl.get("compile_safe"),
            "rule_count": len(grammar_hitl.get("structural_rules") or {}),
        },
    )

    candidates = [
        _candidate_from_grammar(_candidate_label(index), grammar_hitl, variant=index)
        for index in range(population)
    ]
    model_preferred_id: CandidateId = candidates[0]["candidate_id"]
    design_ids: dict[CandidateId, str] = {}
    candidate_telemetry: dict[CandidateId, dict[str, Any]] = {}
    render_payloads: dict[CandidateId, dict[str, Any]] = {}

    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        design_id = str(uuid.uuid4())
        revision_id = str(uuid.uuid4())
        telemetry = _telemetry_for_candidate(candidate)
        render = _render_payload_for_candidate(candidate, grammar_hitl)
        bom = _bom_for_candidate(candidate, telemetry)

        workspace_store.create_design(
            {
                "id": design_id,
                "ingest_job_id": req.ingest_job_id,
                "candidate_id": candidate_id,
                "design_json": candidate,
                "render_json": render,
                "bom_json": bom,
                "telemetry_json": telemetry,
                "is_model_preferred": candidate_id == model_preferred_id,
                "screening_score": max(0.15, 0.86 - 0.04 * candidate["population_index"]),
            }
        )
        workspace_store.create_design_revision(
            {
                "id": revision_id,
                "design_id": design_id,
                "revision_number": 1,
                "parent_revision_id": None,
                "design_json": candidate,
                "render_json": render,
                "bom_json": bom,
                "telemetry_json": telemetry,
                "delta_json": {"source": "grammar_graph"},
            }
        )
        workspace_store.replace_design_checkpoints(
            design_id,
            revision_id,
            _checkpoints_for_grammar_hitl(design_id, revision_id, grammar_hitl),
        )

        design_ids[candidate_id] = design_id
        candidate_telemetry[candidate_id] = telemetry
        render_payloads[candidate_id] = render

    return {
        "agent_loop": agent_loop,
        "design_ids": design_ids,
        "candidates": candidates,
        "model_preferred_id": model_preferred_id,
        "population": population,
        "fallback_rankings": _rankings(candidates),
        "selection_rationale": "Candidate A best preserves the grammar checklist while keeping the morphology compact.",
        "candidate_telemetry": candidate_telemetry,
        "render_payloads": render_payloads,
        "grammar_hitl": grammar_hitl,
    }


@router.get("/agent-loops")
def list_design_agent_loops() -> dict[str, Any]:
    return {
        "default": "grammar",
        "agent_loops": list_agent_loops(),
    }


@router.get("/{design_id}/spec")
def get_design_spec(design_id: str) -> dict[str, Any]:
    design = _get_design_or_404(design_id)
    revision = workspace_store.get_latest_design_revision(design_id)
    return _spec_response(design, revision)


@router.get("/{design_id}/checkpoints")
def get_design_checkpoints(design_id: str) -> dict[str, Any]:
    design = _get_design_or_404(design_id)
    revision = workspace_store.get_latest_design_revision(design_id)
    items = [_checkpoint_response(item) for item in workspace_store.list_design_checkpoints(design_id)]
    return {"design_id": design["id"], "revision_id": (revision or {}).get("id", ""), "items": items}


@router.post("/{design_id}/checkpoints/{checkpoint_id}/decision")
def decide_checkpoint(
    design_id: str,
    checkpoint_id: str,
    req: CheckpointDecisionRequest,
) -> dict[str, Any]:
    _get_design_or_404(design_id)
    checkpoint = workspace_store.get_design_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail=f"Unknown checkpoint: {checkpoint_id}")
    workspace_store.update_design_checkpoint(
        checkpoint_id,
        {
            "decision": req.decision,
            "status": "done" if req.decision == "approved" else "review",
            "note": req.note,
        },
    )
    workspace_store.create_approval_event(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": checkpoint["revision_id"],
            "checkpoint_id": checkpoint_id,
            "decision": req.decision,
            "note": req.note,
        }
    )
    return {"ok": True}


@router.get("/{design_id}/tasks")
def get_tasks(design_id: str) -> dict[str, Any]:
    _get_design_or_404(design_id)
    return {"design_id": design_id, "items": workspace_store.list_task_runs(design_id)}


@router.post("/{design_id}/tasks")
def run_task(design_id: str, req: TaskRunRequest) -> dict[str, Any]:
    _get_design_or_404(design_id)
    revision = workspace_store.get_latest_design_revision(design_id)
    task = workspace_store.create_task_run(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": (revision or {}).get("id"),
            "task_key": req.task_key,
            "status": "done",
            "summary": _task_summary(req.task_key),
            "payload_json": req.payload or {},
            "result_json": {"handled": True},
        }
    )
    workspace_store.append_design_event(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_id": (revision or {}).get("id"),
            "event_type": "task.created",
            "data_json": task,
        }
    )
    return {"task_run": task}


@router.get("/{design_id}/exports")
def get_exports(design_id: str) -> dict[str, Any]:
    _get_design_or_404(design_id)
    return {
        "design_id": design_id,
        "items": [
            {"label": "MJCF", "subtitle": "MuJoCo model", "status": "ready"},
            {"label": "BOM", "subtitle": "Procurement estimate", "status": "ready"},
            {"label": "checklist", "subtitle": "Grammar HITL review", "status": "review"},
        ],
        "artifacts": {"source": "grammar_graph"},
    }


@router.get("/{design_id}/bom")
def get_bom(design_id: str) -> dict[str, Any]:
    design = _get_design_or_404(design_id)
    return design.get("bom_json") or _bom_for_candidate(design["design_json"], design.get("telemetry_json") or {})


@router.post("/{design_id}/select")
def select_design(design_id: str, req: SelectDesignRequest) -> dict[str, Any]:
    design = _get_design_or_404(design_id)
    workspace_store.clear_design_selection(design["ingest_job_id"])
    workspace_store.update_design(design_id, {"is_user_selected": True})
    if workspace_store.get_evolution(req.evolution_id):
        workspace_store.update_evolution(req.evolution_id, {"design_id": design_id})
    return {"design_id": design_id, "selected": True}


@router.get("/{design_id}/events")
def design_events(design_id: str, follow: bool = False, replay_delay_ms: int = 0) -> StreamingResponse:
    _get_design_or_404(design_id)

    def stream():
        for event in workspace_store.list_design_events(design_id):
            yield f"event: {event['event_type']}\ndata: {json.dumps(event)}\n\n"
        if follow:
            yield ": end\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/{design_id}/record-clip")
def record_clip(design_id: str, mode: str = "task_preview") -> dict[str, Any]:
    design = _get_design_or_404(design_id)
    playback = {
        "candidate_id": design["candidate_id"],
        "task_goal": "grammar-derived robot preview",
        "motion_profile": "static morphology review",
        "duration_s": 4.0,
        "camera_mode": mode,
        "estimated_reach_m": design["design_json"].get("arm_length_m", 0.35),
        "source_type": "simulated_policy",
        "source_ready": True,
        "source_ref": {"design_id": design_id},
        "provenance_summary": "Preview generated from the stored grammar candidate.",
    }
    return {"playback": playback}


@router.post("/{design_id}/revise")
def revise_design(design_id: str, req: ReviseDesignRequest) -> dict[str, Any]:
    design = _get_design_or_404(design_id)
    revision = workspace_store.create_design_revision(
        {
            "id": str(uuid.uuid4()),
            "design_id": design_id,
            "revision_number": len(workspace_store.list_design_revisions(design_id)) + 1,
            "parent_revision_id": (workspace_store.get_latest_design_revision(design_id) or {}).get("id"),
            "design_json": design["design_json"],
            "render_json": design.get("render_json"),
            "bom_json": design.get("bom_json"),
            "telemetry_json": design.get("telemetry_json"),
            "delta_json": {"instruction": req.instruction},
        }
    )
    return {
        "design_id": design_id,
        "revision_id": revision["id"],
        "revision_number": revision["revision_number"],
        "spec": _spec_response(design, revision),
    }


@router.get("/by-ingest/{ingest_job_id}")
def by_ingest(ingest_job_id: str) -> list[dict[str, Any]]:
    return workspace_store.list_designs_by_ingest(ingest_job_id)


def _get_design_or_404(design_id: str) -> dict[str, Any]:
    design = workspace_store.get_design(design_id)
    if design is None:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    return design


def _load_plan(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"task_goal": raw}
    return {}


def _candidate_label(index: int) -> str:
    label = ""
    value = index
    while True:
        label = chr(ord("A") + (value % 26)) + label
        value = value // 26 - 1
        if value < 0:
            return label


def _candidate_from_grammar(candidate_id: CandidateId, grammar_hitl: dict[str, Any], *, variant: int) -> dict[str, Any]:
    spec = grammar_hitl.get("spec") or {}
    target = str(grammar_hitl.get("inferred_morphology") or spec.get("inferred_morphology") or "quadruped")
    base = _base_morphology(target)
    scale = 1.0 + 0.08 * variant
    actuator_classes = ["servo", "bldc", "stepper"]
    return {
        "candidate_id": candidate_id,
        "population_index": variant,
        "embodiment_class": target,
        "num_legs": base["num_legs"],
        "num_arms": base["num_arms"],
        "has_torso": base["has_torso"],
        "torso_length_m": round(base["torso_length_m"] * scale, 2),
        "leg_length_m": round(base["leg_length_m"] * scale, 2),
        "arm_length_m": round(base["arm_length_m"] * scale, 2),
        "leg_dof": base["leg_dof"],
        "arm_dof": base["arm_dof"],
        "spine_dof": base["spine_dof"] + variant,
        "actuator_class": actuator_classes[variant % len(actuator_classes)],
        "actuator_torque_nm": round(12.0 + 3.0 * variant + base["num_legs"], 1),
        "total_mass_kg": round(7.5 + 1.8 * variant + base["num_legs"] * 0.7, 1),
        "payload_capacity_kg": round(1.5 + variant + base["num_legs"] * 0.25, 1),
        "sensor_package": ["imu", "depth_camera", "foot_contact"],
        "rationale": f"Generated from {len(grammar_hitl.get('structural_rules') or {})} compile-checked RoboGrammar structural rules.",
        "confidence": round(max(0.2, 0.82 - 0.04 * variant), 2),
    }


def _base_morphology(target: str) -> dict[str, Any]:
    table = {
        "humanoid": dict(num_legs=2, num_arms=2, has_torso=True, torso_length_m=0.72, leg_length_m=0.58, arm_length_m=0.48, leg_dof=5, arm_dof=5, spine_dof=2),
        "biped": dict(num_legs=2, num_arms=0, has_torso=True, torso_length_m=0.48, leg_length_m=0.64, arm_length_m=0.0, leg_dof=4, arm_dof=0, spine_dof=1),
        "snake": dict(num_legs=0, num_arms=0, has_torso=False, torso_length_m=0.18, leg_length_m=0.0, arm_length_m=0.0, leg_dof=0, arm_dof=0, spine_dof=8),
        "centipede": dict(num_legs=12, num_arms=0, has_torso=False, torso_length_m=0.9, leg_length_m=0.16, arm_length_m=0.0, leg_dof=2, arm_dof=0, spine_dof=6),
        "bird": dict(num_legs=2, num_arms=2, has_torso=True, torso_length_m=0.42, leg_length_m=0.32, arm_length_m=0.55, leg_dof=3, arm_dof=2, spine_dof=2),
    }
    return table.get(target, dict(num_legs=4, num_arms=0, has_torso=True, torso_length_m=0.58, leg_length_m=0.46, arm_length_m=0.0, leg_dof=3, arm_dof=0, spine_dof=2))


def _telemetry_for_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    index = int(candidate.get("population_index", 0))
    return {
        "candidate_id": candidate_id,
        "estimated_total_cost_usd": 1800 + index * 450,
        "estimated_mass_kg": candidate["total_mass_kg"],
        "payload_capacity_kg": candidate["payload_capacity_kg"],
        "payload_margin_kg": round(candidate["payload_capacity_kg"] * 0.35, 2),
        "estimated_reach_m": max(candidate["arm_length_m"], candidate["leg_length_m"]),
        "actuator_torque_nm": candidate["actuator_torque_nm"],
        "estimated_backlash_deg": 1.4 + index * 0.4,
        "estimated_bandwidth_hz": max(1, 18 - index),
        "procurement_confidence": max(0.2, 0.78 - index * 0.04),
        "design_quality_score": max(0.2, 0.86 - index * 0.05),
        "risk_flags": [] if index == 0 else ["review actuator sizing"],
        "summary": "Grammar-generated baseline candidate.",
    }


def _render_payload_for_candidate(candidate: dict[str, Any], grammar_hitl: dict[str, Any]) -> dict[str, Any]:
    joint_count = candidate["num_legs"] * candidate["leg_dof"] + candidate["num_arms"] * candidate["arm_dof"] + candidate["spine_dof"]
    return {
        "candidate_id": candidate["candidate_id"],
        "topology_label": f"{candidate['embodiment_class']} · {candidate['num_legs']}L · {candidate['num_arms']}A · {candidate['spine_dof']}S",
        "view_modes": ["concept", "engineering", "joints", "components"],
        "engineering_ready": True,
        "render_glb": "",
        "ui_scene": {"render_mode": "grammar", "nodes": [], "joints": [], "stats": {"grammar_hitl": grammar_hitl}},
        "mjcf": f"<mujoco model=\"grammar_{candidate['candidate_id']}\" />",
        "joint_count": joint_count,
    }


def _bom_for_candidate(candidate: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "structural_items": [_bom_item("Aluminum link set", 1, 320)],
        "actuator_items": [_bom_item(f"{candidate['actuator_class']} actuator", max(1, telemetry.get("actuator_torque_nm", 1) // 6), 85)],
        "electronics_items": [_bom_item("IMU + depth camera", 1, 180)],
        "fastener_items": [_bom_item("M3 fastener kit", 1, 35)],
        "total_cost_usd": telemetry.get("estimated_total_cost_usd"),
        "procurement_confidence": telemetry.get("procurement_confidence", 0.75),
        "missing_items": [],
    }


def _bom_item(part_name: str, quantity: int | float, unit_price_usd: float) -> dict[str, Any]:
    return {
        "part_name": part_name,
        "sku": None,
        "quantity": int(quantity),
        "unit_price_usd": unit_price_usd,
        "vendor": None,
        "availability": "unknown",
        "requires_review": False,
    }


def _rankings(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": candidate["candidate_id"],
            "kinematic_feasibility": round(candidate["confidence"], 2),
            "static_stability": round(max(0.2, 0.82 - 0.03 * index), 2),
            "bom_confidence": round(max(0.2, 0.78 - 0.04 * index), 2),
            "retargetability": round(max(0.2, 0.74 - 0.02 * index), 2),
            "total_score": round(max(0.2, 0.8 - 0.04 * index), 2),
        }
        for index, candidate in enumerate(candidates)
    ]


def _checkpoints_for_grammar_hitl(
    design_id: str,
    revision_id: str,
    grammar_hitl: dict[str, Any],
) -> list[dict[str, Any]]:
    criteria = (grammar_hitl.get("checklist") or {}).get("criteria") or []
    checkpoints = []
    for index, criterion in enumerate(criteria):
        checkpoint_id = str(uuid.uuid4())
        success = bool(criterion.get("isSuccessful"))
        checkpoints.append(
            {
                "id": checkpoint_id,
                "design_id": design_id,
                "revision_id": revision_id,
                "checkpoint_key": f"grammar_{index}",
                "label": "Grammar",
                "title": criterion.get("description", "Grammar checkpoint"),
                "summary": "; ".join(criterion.get("critiques") or []) or "Criterion passed.",
                "rows_json": [
                    {
                        "field": "status",
                        "before": "pending",
                        "after": "pass" if success else "review",
                    }
                ],
                "status": "done" if success else "review",
                "decision": "approved" if success else "pending",
                "metadata_json": {"source": "grammar_graph"},
            }
        )
    return checkpoints


def _checkpoint_response(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "db_id": row["id"]}


def _spec_response(design: dict[str, Any], revision: dict[str, Any] | None) -> dict[str, Any]:
    revision = revision or {}
    return {
        "design_id": design["id"],
        "candidate_id": design["candidate_id"],
        "revision_id": revision.get("id", ""),
        "revision_number": revision.get("revision_number", 1),
        "design": revision.get("design_json") or design["design_json"],
        "telemetry": revision.get("telemetry_json") or design.get("telemetry_json"),
        "bom": revision.get("bom_json") or design.get("bom_json"),
        "render": revision.get("render_json") or design.get("render_json"),
        "approval_events": workspace_store.list_approval_events(design["id"]),
    }


def _task_summary(task_key: str) -> str:
    return {
        "compare_candidate_b": "Compared selected candidate against candidate B.",
        "send_review_poll": "Review poll queued for configured HITL recipient.",
        "export_urdf": "URDF export target prepared.",
        "cost_bom_vs_budget": "BOM estimate checked against nominal budget.",
    }.get(task_key, f"Completed {task_key.replace('_', ' ')}.")
