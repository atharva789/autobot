import os
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake")
os.environ.setdefault("GEMINI_API_KEY", "fake")
os.environ.setdefault("YOUTUBE_API_KEY", "fake")

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
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
        mock_svc.search_youtube.return_value = "abc123"
        mock_svc.run_gvhmr.return_value = "gvhmr-job-1"
        with patch("demo.routes.ingest.supa") as mock_supa:
            mock_supa.table.return_value.insert.return_value.execute.return_value = MagicMock()
            r = client.post("/ingest", json={"prompt": "make it walk"})
    assert r.status_code == 201
    assert "job_id" in r.json()
    assert r.json()["video_id"] == "abc123"
