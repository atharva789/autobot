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
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from postgrest.exceptions import APIError
from pydantic import BaseModel

from demo.supabase_client import supa
from packages.pipeline.bom_generator import generate_bom_for_candidate
from packages.pipeline.design_generator import generate_design_candidates
from packages.pipeline.fallback_chooser import rank_candidates_fallback
from packages.pipeline.schemas import (
    BOMOutput,
    DesignCandidatesResponse,
    FallbackRanking,
    RobotDesignCandidate,
    TaskSpec,
)

router = APIRouter(prefix="/designs", tags=["designs"])
logger = logging.getLogger(__name__)
_DESIGNS_MIGRATION_PATH = "supabase/migrations/0002_design_pipeline.sql"


class GenerateDesignsRequest(BaseModel):
    ingest_job_id: str


class GenerateDesignsResponse(BaseModel):
    design_ids: dict[Literal["A", "B", "C"], str]
    candidates: list[RobotDesignCandidate]
    model_preferred_id: Literal["A", "B", "C"]
    fallback_rankings: list[FallbackRanking]


class SelectDesignRequest(BaseModel):
    evolution_id: str


def _raise_for_missing_designs_table(exc: APIError, *, stage: str) -> None:
    if exc.code == "PGRST205" and "public.designs" in str(exc):
        raise HTTPException(
            status_code=503,
            detail={
                "stage": stage,
                "error": "Supabase schema is missing public.designs.",
                "migration": _DESIGNS_MIGRATION_PATH,
            },
        ) from exc
    raise exc


@router.post("/generate", status_code=201)
def generate_designs(req: GenerateDesignsRequest) -> GenerateDesignsResponse:
    """Generate 3 robot design candidates from an ingest job.

    Reads the TaskSpec from the ingest job's er16_plan_json,
    calls Gemini 3.1 Pro Preview for structured design generation,
    persists all 3 designs to the designs table,
    and returns the candidates with fallback rankings.
    """
    ingest_resp = (
        supa.table("ingest_jobs")
        .select("id, er16_plan_json, status")
        .eq("id", req.ingest_job_id)
        .single()
        .execute()
    )
    if not ingest_resp.data:
        raise HTTPException(status_code=404, detail="Ingest job not found")

    try:
        plan_data = json.loads(ingest_resp.data["er16_plan_json"])
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

    fallback_rankings = rank_candidates_fallback(design_response.candidates)

    design_ids: dict[Literal["A", "B", "C"], str] = {}
    for candidate in design_response.candidates:
        design_id = str(uuid.uuid4())
        design_ids[candidate.candidate_id] = design_id

        is_model_preferred = (
            candidate.candidate_id == design_response.model_preferred_id
        )
        ranking = next(
            (r for r in fallback_rankings if r.candidate_id == candidate.candidate_id),
            None,
        )

        try:
            supa.table("designs").insert(
                {
                    "id": design_id,
                    "ingest_job_id": req.ingest_job_id,
                    "candidate_id": candidate.candidate_id,
                    "design_json": candidate.model_dump(),
                    "is_model_preferred": is_model_preferred,
                    "is_user_selected": False,
                    "screening_score": ranking.total_score if ranking else None,
                }
            ).execute()
        except APIError as exc:
            _raise_for_missing_designs_table(exc, stage="persist_designs")

    return GenerateDesignsResponse(
        design_ids=design_ids,
        candidates=design_response.candidates,
        model_preferred_id=design_response.model_preferred_id,
        fallback_rankings=fallback_rankings,
    )


@router.get("/{design_id}")
def get_design(design_id: str) -> dict:
    """Get a specific design by ID."""
    try:
        resp = supa.table("designs").select("*").eq("id", design_id).single().execute()
    except APIError as exc:
        _raise_for_missing_designs_table(exc, stage="fetch_design")
    if not resp.data:
        raise HTTPException(status_code=404, detail="Design not found")
    return resp.data


@router.get("/{design_id}/bom")
def get_design_bom(design_id: str) -> BOMOutput:
    """Get the BOM for a specific design."""
    try:
        resp = (
            supa.table("designs")
            .select("design_json, bom_json, candidate_id")
            .eq("id", design_id)
            .single()
            .execute()
        )
    except APIError as exc:
        _raise_for_missing_designs_table(exc, stage="fetch_bom")
    if not resp.data:
        raise HTTPException(status_code=404, detail="Design not found")

    if resp.data.get("bom_json"):
        return BOMOutput.model_validate(resp.data["bom_json"])

    try:
        candidate = RobotDesignCandidate.model_validate(resp.data["design_json"])
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse design_json: {exc}"
        ) from exc

    bom = generate_bom_for_candidate(candidate)

    try:
        supa.table("designs").update({"bom_json": bom.model_dump()}).eq(
            "id", design_id
        ).execute()
    except APIError as exc:
        _raise_for_missing_designs_table(exc, stage="persist_bom")

    return bom


@router.post("/{design_id}/select")
def select_design(design_id: str, req: SelectDesignRequest) -> dict:
    """Select a design for an evolution.

    Marks the design as user_selected and updates the evolution to reference it.
    """
    try:
        design_resp = (
            supa.table("designs")
            .select("id, ingest_job_id, candidate_id")
            .eq("id", design_id)
            .single()
            .execute()
        )
    except APIError as exc:
        _raise_for_missing_designs_table(exc, stage="select_design")
    if not design_resp.data:
        raise HTTPException(status_code=404, detail="Design not found")

    try:
        supa.table("designs").update({"is_user_selected": False}).eq(
            "ingest_job_id", design_resp.data["ingest_job_id"]
        ).execute()

        supa.table("designs").update({"is_user_selected": True}).eq(
            "id", design_id
        ).execute()
    except APIError as exc:
        _raise_for_missing_designs_table(exc, stage="persist_selection")

    supa.table("evolutions").update({"design_id": design_id}).eq(
        "id", req.evolution_id
    ).execute()

    return {
        "status": "selected",
        "design_id": design_id,
        "candidate_id": design_resp.data["candidate_id"],
        "evolution_id": req.evolution_id,
    }


@router.get("/by-ingest/{ingest_job_id}")
def get_designs_by_ingest(ingest_job_id: str) -> list[dict]:
    """Get all designs for an ingest job."""
    try:
        resp = (
            supa.table("designs")
            .select("*")
            .eq("ingest_job_id", ingest_job_id)
            .order("candidate_id")
            .execute()
        )
    except APIError as exc:
        _raise_for_missing_designs_table(exc, stage="list_designs")
    return resp.data or []
