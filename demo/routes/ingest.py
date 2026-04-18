from __future__ import annotations
import json
import logging
import os
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from demo.supabase_client import supa
from demo.services.ingest_service import IngestService, resolve_gemini_api_key

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

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
        stage = "select_reference_video"
        selection = _svc.select_reference_video(req.prompt, plan)
        video_id = selection["video_id"]
        stage = "run_gvhmr"
        gvhmr_job_id = _svc.run_gvhmr(f"https://www.youtube.com/watch?v={video_id}")
    except (ValueError, LookupError, RuntimeError) as exc:
        logger.exception("Ingest failed at stage=%s for job_id=%s", stage, job_id)
        raise HTTPException(
            status_code=502,
            detail={
                "stage": stage,
                "error": str(exc),
                "job_id": job_id,
            },
        ) from exc

    stage = "persist_job"
    supa.table("ingest_jobs").insert({
        "id": job_id,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "er16_plan_json": json.dumps(plan),
        "gvhmr_job_id": gvhmr_job_id,
        "status": "processing",
    }).execute()
    return {
        "job_id": job_id,
        "er16_plan": plan,
        "video_id": video_id,
        "selected_query": selection["query"],
        "selection_rationale": selection["rationale"],
        "candidate_reviews": selection["candidate_reviews"],
    }


@router.get("/{job_id}")
def get_ingest(job_id: str) -> dict:
    resp = supa.table("ingest_jobs").select("*").eq("id", job_id).single().execute()
    return resp.data
