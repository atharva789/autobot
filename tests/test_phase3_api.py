from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from demo.app import create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        db_path=tmp_path / "demo.sqlite3",
        replays_dir=tmp_path / "data" / "replays",
        exports_dir=tmp_path / "data" / "exports",
    )
    return TestClient(app)


def test_list_clips(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.get("/clips")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) >= 1
    assert "id" in payload["items"][0]


def test_create_approve_export_run_happy_path(tmp_path: Path) -> None:
    client = _client(tmp_path)
    clips = client.get("/clips").json()["items"]
    clip_id = clips[0]["id"]

    created = client.post("/runs", json={"prompt": "wave both arms", "clip_id": clip_id})
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "completed"

    approved = client.post(f"/runs/{run['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["approved"] is True

    exported = client.post(f"/runs/{run['id']}/export")
    assert exported.status_code == 201
    export_payload = exported.json()
    assert export_payload["parquet_path"].endswith(".parquet")


def test_export_without_approval_is_blocked(tmp_path: Path) -> None:
    client = _client(tmp_path)
    clip_id = client.get("/clips").json()["items"][0]["id"]
    created = client.post("/runs", json={"prompt": "wave both arms", "clip_id": clip_id}).json()

    exported = client.post(f"/runs/{created['id']}/export")
    assert exported.status_code == 400
    assert "approved" in exported.json()["detail"]

