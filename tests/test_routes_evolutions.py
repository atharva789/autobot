import os
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake")
os.environ.setdefault("GEMINI_API_KEY", "fake")
os.environ.setdefault("YOUTUBE_API_KEY", "fake")

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from demo.app import create_app

client = TestClient(create_app())


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_accessible():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/ingest" in paths
    assert "/evolutions" in paths


def test_ingest_post_returns_job_id():
    with patch("demo.routes.ingest._svc") as mock_svc:
        mock_svc.analyze_prompt.return_value = {
            "task_goal": "walk", "affordances": [],
            "success_criteria": "reach", "search_queries": ["walk demo"]
        }
        mock_svc.select_reference_video.return_value = {
            "video_id": "abc123",
            "query": "person walking side view",
            "rationale": "Best candidate had a stable side view.",
            "candidate_reviews": [],
        }
        mock_svc.run_gvhmr.return_value = "gvhmr-job-1"
        with patch("demo.routes.ingest.supa") as mock_supa:
            mock_supa.table.return_value.insert.return_value.execute.return_value = MagicMock()
            r = client.post("/ingest", json={"prompt": "make it walk"})
    assert r.status_code == 201
    assert "job_id" in r.json()
    assert r.json()["video_id"] == "abc123"
    assert r.json()["selected_query"] == "person walking side view"


def test_ingest_post_returns_stage_on_upstream_failure():
    with patch("demo.routes.ingest._svc") as mock_svc:
        mock_svc.analyze_prompt.side_effect = RuntimeError("boom")
        r = client.post("/ingest", json={"prompt": "make it walk"})
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["stage"] == "analyze_prompt"
    assert detail["error"] == "boom"
    assert "job_id" in detail


def test_create_evolution_returns_stage_on_orchestrator_failure():
    with patch("demo.routes.evolutions._evo_svc") as mock_evo_svc, \
         patch("demo.routes.evolutions.supa") as mock_supa, \
         patch("demo.routes.evolutions.CLIOrchestrator") as mock_orch:
        mock_evo_svc.create.return_value = "evo-1"
        mock_supa.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={"er16_plan_json": '{"task_goal":"walk","search_queries":["walk demo"],"affordances":[],"success_criteria":"reach"}'}
        )
        mock_orch.return_value.draft_program_md.side_effect = RuntimeError("claude failed")
        r = client.post("/evolutions", json={"run_id": "run-1", "ingest_job_id": "ing-1"})

    assert r.status_code == 502
    assert r.json()["detail"]["stage"] == "draft_program_md"
    assert r.json()["detail"]["error"] == "claude failed"


def test_generate_designs_returns_migration_hint_when_designs_table_missing():
    with patch("demo.routes.designs.generate_design_candidates") as mock_generate, \
         patch("demo.routes.designs.rank_candidates_fallback") as mock_rank, \
         patch("demo.routes.designs.supa") as mock_supa:
        mock_supa.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "ing-1",
                "status": "processing",
                "er16_plan_json": '{"task_goal":"walk","environment":"indoor","locomotion_type":"walking","manipulation_required":false,"payload_kg":0.0,"success_criteria":"reach","search_queries":["human walking side view"]}',
            }
        )
        mock_generate.return_value = MagicMock(
            candidates=[
                MagicMock(candidate_id="A", model_dump=lambda: {"candidate_id": "A"}),
                MagicMock(candidate_id="B", model_dump=lambda: {"candidate_id": "B"}),
                MagicMock(candidate_id="C", model_dump=lambda: {"candidate_id": "C"}),
            ],
            model_preferred_id="A",
        )
        mock_rank.return_value = [
            MagicMock(candidate_id="A", total_score=0.9),
            MagicMock(candidate_id="B", total_score=0.7),
            MagicMock(candidate_id="C", total_score=0.5),
        ]
        mock_supa.table.return_value.insert.return_value.execute.side_effect = APIError(
            {
                "message": "Could not find the table 'public.designs' in the schema cache",
                "code": "PGRST205",
                "hint": None,
                "details": None,
            }
        )

        r = client.post("/designs/generate", json={"ingest_job_id": "ing-1"})

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["stage"] == "persist_designs"
    assert detail["migration"] == "supabase/migrations/0002_design_pipeline.sql"
