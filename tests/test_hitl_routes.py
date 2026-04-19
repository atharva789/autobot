from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from demo.app import create_app
from demo.workspace_store import WorkspaceStore
from packages.pipeline.schemas import CandidateTelemetry


client = TestClient(create_app())


class _FakeMessenger:
    def __init__(self) -> None:
        self.sent = []

    def send_design_review(self, **kwargs):
        self.sent.append(("poll", kwargs))
        return type(
            "Result",
            (),
            {
                "ok": True,
                "message_id": "msg-poll",
                "payload": kwargs,
                "raw_response": {"id": "msg-poll"},
            },
        )()

    def send_text(self, **kwargs):
        self.sent.append(("text", kwargs))
        return type(
            "Result",
            (),
            {
                "ok": True,
                "message_id": "msg-text",
                "payload": kwargs,
                "raw_response": {"id": "msg-text"},
            },
        )()


def _seed_design(store: WorkspaceStore) -> str:
    design_id = "design-1"
    store.create_design(
        {
            "id": design_id,
            "ingest_job_id": "ing-1",
            "candidate_id": "A",
            "design_json": {"candidate_id": "A", "embodiment_class": "biped"},
            "render_json": {"mjcf": "<mujoco/>"},
            "telemetry_json": CandidateTelemetry(
                candidate_id="A",
                estimated_total_cost_usd=3200.0,
                estimated_mass_kg=18.5,
                payload_capacity_kg=3.0,
                payload_margin_kg=1.0,
                estimated_reach_m=0.72,
                actuator_torque_nm=18.0,
                estimated_backlash_deg=0.12,
                estimated_bandwidth_hz=96.0,
                procurement_confidence=0.9,
                design_quality_score=0.84,
                risk_flags=["heavy_platform"],
                summary="biped with 18.5 kg mass; 3.0 kg payload; reach 0.72 m; est. cost $3200",
            ).model_dump(),
            "is_model_preferred": True,
            "is_user_selected": False,
        }
    )
    return design_id


def test_send_design_poll_uses_persisted_telemetry(tmp_path):
    local_store = WorkspaceStore(Path(tmp_path) / "hitl.sqlite3")
    design_id = _seed_design(local_store)
    messenger = _FakeMessenger()

    with patch("demo.routes.hitl.workspace_store", local_store), patch(
        "demo.routes.hitl._build_messenger", return_value=messenger
    ), patch.dict("os.environ", {"PHOTON_RECIPIENT": "ops@example.com"}, clear=False):
        response = client.post(f"/hitl/designs/{design_id}/poll", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message_id"] == "msg-poll"
    assert payload["payload"]["recipient"] == "ops@example.com"
    assert payload["payload"]["telemetry"]["summary"].startswith("biped")


def test_send_design_text_uses_default_summary(tmp_path):
    local_store = WorkspaceStore(Path(tmp_path) / "hitl-text.sqlite3")
    design_id = _seed_design(local_store)
    messenger = _FakeMessenger()

    with patch("demo.routes.hitl.workspace_store", local_store), patch(
        "demo.routes.hitl._build_messenger", return_value=messenger
    ), patch.dict("os.environ", {"PHOTON_RECIPIENT": "ops@example.com"}, clear=False):
        response = client.post(f"/hitl/designs/{design_id}/text", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message_id"] == "msg-text"
    assert "Robot design A ready for review" in payload["payload"]["text"]


def test_hitl_setup_roundtrip_and_consent_confirmation(tmp_path):
    local_store = WorkspaceStore(Path(tmp_path) / "hitl-setup.sqlite3")

    with patch("demo.routes.hitl.workspace_store", local_store):
        setup = client.post(
            "/hitl/setup",
            json={
                "recipient": "+15551234567",
                "display_name": "Alex",
                "thread_key": "orchard_01",
            },
        )
        pending = client.get("/hitl/setup")
        confirmed = client.post("/hitl/setup/confirm", json={"recipient_id": pending.json()["recipient"]["id"]})
        current = client.get("/hitl/setup")

    assert setup.status_code == 201
    assert pending.status_code == 200
    assert pending.json()["recipient"]["recipient"] == "+15551234567"
    assert pending.json()["recipient"]["consent_status"] == "pending"
    assert confirmed.status_code == 200
    assert current.status_code == 200
    assert current.json()["recipient"]["consent_status"] == "confirmed"
    assert isinstance(current.json()["can_send"], bool)


def test_send_design_poll_uses_saved_setup_recipient_without_env_override(tmp_path):
    local_store = WorkspaceStore(Path(tmp_path) / "hitl-setup-send.sqlite3")
    design_id = _seed_design(local_store)
    messenger = _FakeMessenger()

    with patch("demo.routes.hitl.workspace_store", local_store):
        setup = client.post(
            "/hitl/setup",
            json={
                "recipient": "+15550001111",
                "display_name": "Alex",
            },
        )
        recipient_id = setup.json()["recipient"]["id"]
        client.post("/hitl/setup/confirm", json={"recipient_id": recipient_id})

    with patch("demo.routes.hitl.workspace_store", local_store), patch(
        "demo.routes.hitl._build_messenger", return_value=messenger
    ), patch.dict("os.environ", {"PHOTON_RECIPIENT": ""}, clear=False):
        response = client.post(f"/hitl/designs/{design_id}/poll", json={})

    assert response.status_code == 200
    assert response.json()["payload"]["recipient"] == "+15550001111"


def test_hitl_setup_reports_provider_ready_from_spectrum_credentials(tmp_path):
    local_store = WorkspaceStore(Path(tmp_path) / "hitl-spectrum-ready.sqlite3")

    with patch("demo.routes.hitl.workspace_store", local_store), patch.dict(
        "os.environ",
        {
            "PHOTON_PROJECT_ID": "project-demo",
            "PHOTON_SECRET_KEY": "secret-demo",
            "PHOTON_BASE_URL": "",
        },
        clear=False,
    ):
        current = client.get("/hitl/setup")

    assert current.status_code == 200
    assert current.json()["provider_ready"] is True


def test_send_test_text_uses_spectrum_cli_transport_in_mock_mode(tmp_path):
    local_store = WorkspaceStore(Path(tmp_path) / "hitl-spectrum-send.sqlite3")

    with patch("demo.routes.hitl.workspace_store", local_store), patch.dict(
        "os.environ",
        {
            "PHOTON_PROJECT_ID": "project-demo",
            "PHOTON_SECRET_KEY": "secret-demo",
            "PHOTON_MOCK_MODE": "1",
            "PHOTON_BASE_URL": "",
        },
        clear=False,
    ):
        setup = client.post(
            "/hitl/setup",
            json={
                "recipient": "+15558889999",
                "display_name": "Alex",
                "thread_key": "iMessage;-;+15558889999",
            },
        )
        recipient_id = setup.json()["recipient"]["id"]
        client.post("/hitl/setup/confirm", json={"recipient_id": recipient_id})
        response = client.post("/hitl/setup/test", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message_id"] == "mock-text-message"
    assert payload["raw_response"]["transport"] == "spectrum-cli-mock"
