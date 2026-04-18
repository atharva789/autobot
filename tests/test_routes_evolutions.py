import os
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake")
os.environ.setdefault("GEMINI_API_KEY", "fake")
os.environ.setdefault("YOUTUBE_API_KEY", "fake")

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
