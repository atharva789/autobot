from __future__ import annotations
import json
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from demo.services.ingest_service import IngestService, resolve_gemini_api_key
from demo.workspace_store import workspace_store

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

_REFERENCE_SELECTION_ERRORS = (
    LookupError,
    RuntimeError,
    ValueError,
    TimeoutError,
    PermissionError,
    ConnectionError,
)

_svc = IngestService(
    gemini_api_key=resolve_gemini_api_key(),
    youtube_api_key=os.environ.get("YOUTUBE_API_KEY", ""),
    supabase_url=os.environ.get("SUPABASE_URL", ""),
    supabase_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
)


class IngestRequest(BaseModel):
    prompt: str


@router.post("", status_code=201)
def start_ingest(req: IngestRequest) -> dict:
    job_id = str(uuid.uuid4())
    stage = "analyze_prompt"
    try:
        plan = _svc.analyze_prompt(req.prompt)
        stage = "validate_plan"
        queries = plan.get("search_queries")
        if not isinstance(queries, list) or not queries:
            raise ValueError(
                "Gemini response did not include any YouTube search queries."
            )
    except (ValueError, RuntimeError) as exc:
        logger.exception("Ingest failed at stage=%s for job_id=%s", stage, job_id)
        raise HTTPException(
            status_code=502,
            detail={
                "stage": stage,
                "error": str(exc),
                "job_id": job_id,
            },
        ) from exc

    selected_query = queries[0]
    selection_rationale = "Task analysis completed; reference video search not attempted yet."
    candidate_reviews: list[dict] = []
    video_id: str | None = None
    gvhmr_job_id: str | None = None
    reference_source_type: str | None = None
    reference_payload: dict | None = None
    status = "analysis_ready"

    skip_youtube = os.environ.get("SKIP_YOUTUBE_SEARCH", "0") == "1"

    if skip_youtube:
        logger.info("Skipping YouTube search (SKIP_YOUTUBE_SEARCH=1) for job_id=%s", job_id)
        selection_rationale = "YouTube search skipped; proceeding with task analysis only."
        reference_source_type = "none"
        status = "reference_skipped"
    else:
        try:
            stage = "select_reference_video"
            selection = _svc.select_reference_video(req.prompt, plan)
            video_id = selection["video_id"]
            selected_query = selection["query"]
            selection_rationale = selection["rationale"]
            candidate_reviews = selection["candidate_reviews"]
            reference_source_type = "youtube"
            reference_payload = {
                "video_id": video_id,
                "query": selected_query,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "candidate_reviews": candidate_reviews,
                "rationale": selection_rationale,
            }
            status = "reference_selected"
        except _REFERENCE_SELECTION_ERRORS as exc:
            logger.warning(
                "Reference video selection degraded for job_id=%s: %s",
                job_id,
                exc,
            )
            selection_rationale = f"Reference video unavailable: {exc}"
            try:
                stage = "select_droid_reference"
                droid_selection = _svc.select_droid_reference(req.prompt, plan)
                if not isinstance(droid_selection, dict) or "reference" not in droid_selection:
                    raise RuntimeError("DROID fallback returned an invalid payload.")
                reference_source_type = droid_selection["source_type"]
                reference_payload = droid_selection
                selected_query = droid_selection["query_text"]
                status = "reference_selected"
                selection_rationale = (
                    "DROID fallback selected after YouTube/GVHMR reference search failed. "
                    f"{selection_rationale} DROID match: {droid_selection['reference']['reason']}"
                )
            except (LookupError, RuntimeError, ValueError) as fallback_exc:
                logger.warning(
                    "DROID fallback unavailable for job_id=%s: %s",
                    job_id,
                    fallback_exc,
                )

    if video_id:
        try:
            stage = "run_gvhmr"
            gvhmr_job_id = _svc.run_gvhmr(f"https://www.youtube.com/watch?v={video_id}")
            status = "processing"
        except RuntimeError as exc:
            logger.warning("GVHMR dispatch degraded for job_id=%s: %s", job_id, exc)
            selection_rationale = (
                f"{selection_rationale} GVHMR dispatch deferred: {exc}"
            )

    workspace_store.save_ingest_job({
        "id": job_id,
        "source_url": (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        ),
        "er16_plan_json": json.dumps(plan),
        "gvhmr_job_id": gvhmr_job_id,
        "status": status,
        "reference_source_type": reference_source_type,
        "selected_query": selected_query,
        "selection_rationale": selection_rationale,
        "candidate_reviews_json": candidate_reviews,
        "reference_payload_json": reference_payload,
    })
    return {
        "job_id": job_id,
        "status": status,
        "er16_plan": plan,
        "video_id": video_id,
        "gvhmr_job_id": gvhmr_job_id,
        "reference_source_type": reference_source_type,
        "reference_payload": reference_payload,
        "selected_query": selected_query,
        "selection_rationale": selection_rationale,
        "candidate_reviews": candidate_reviews,
    }


@router.get("/{job_id}")
def get_ingest(job_id: str) -> dict:
    row = workspace_store.get_ingest_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown ingest job: {job_id}")
    return row
