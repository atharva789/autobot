from __future__ import annotations
import json
import os
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from demo.supabase_client import supa
from demo.services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["ingest"])

_svc = IngestService(
    gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
    youtube_api_key=os.environ.get("YOUTUBE_API_KEY", ""),
    supabase_url=os.environ.get("SUPABASE_URL", ""),
    supabase_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
)


class IngestRequest(BaseModel):
    prompt: str


@router.post("", status_code=201)
def start_ingest(req: IngestRequest) -> dict:
    job_id = str(uuid.uuid4())
    plan = _svc.analyze_prompt(req.prompt)
    video_id = _svc.search_youtube(plan["search_queries"][0])
    gvhmr_job_id = _svc.run_gvhmr(f"https://www.youtube.com/watch?v={video_id}")
    supa.table("ingest_jobs").insert({
        "id": job_id,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "er16_plan_json": json.dumps(plan),
        "gvhmr_job_id": gvhmr_job_id,
        "status": "processing",
    }).execute()
    return {"job_id": job_id, "er16_plan": plan, "video_id": video_id}


@router.get("/{job_id}")
def get_ingest(job_id: str) -> dict:
    resp = supa.table("ingest_jobs").select("*").eq("id", job_id).single().execute()
    return resp.data
