import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from demo.app import create_app
from demo.workspace_store import WorkspaceStore
from packages.pipeline.schemas import (
    BOMOutput,
    DesignCandidatesResponse,
    FallbackRanking,
    RobotDesignCandidate,
)


def _client() -> TestClient:
    return TestClient(create_app())


def _sample_candidates_response() -> DesignCandidatesResponse:
    return DesignCandidatesResponse(
        task_interpretation="Robot should climb vertical terrain while carrying a rope pack.",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="biped",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.55,
                arm_length_m=0.72,
                leg_length_m=0.92,
                arm_dof=6,
                leg_dof=5,
                spine_dof=2,
                actuator_class="bldc",
                actuator_torque_nm=34.0,
                total_mass_kg=24.0,
                payload_capacity_kg=6.0,
                sensor_package=["imu", "encoder", "camera", "force"],
                rationale="Tall climbing-capable biped with dual grasping arms and high reach.",
                confidence=0.89,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="hybrid",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.48,
                arm_length_m=0.66,
                leg_length_m=0.76,
                arm_dof=5,
                leg_dof=4,
                spine_dof=2,
                actuator_class="bldc",
                actuator_torque_nm=28.0,
                total_mass_kg=21.0,
                payload_capacity_kg=4.5,
                sensor_package=["imu", "encoder", "camera"],
                rationale="Lean hybrid climber with arm-assisted ascent and reduced mass.",
                confidence=0.82,
            ),
            RobotDesignCandidate(
                candidate_id="C",
                embodiment_class="quadruped",
                num_legs=4,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.62,
                arm_length_m=0.0,
                leg_length_m=0.54,
                arm_dof=0,
                leg_dof=4,
                spine_dof=1,
                actuator_class="servo",
                actuator_torque_nm=18.0,
                total_mass_kg=20.0,
                payload_capacity_kg=3.0,
                sensor_package=["imu", "encoder", "camera"],
                rationale="Stable fallback climber with simpler support geometry.",
                confidence=0.68,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="Candidate A best satisfies vertical reach, dual-arm manipulation, and payload carrying.",
    )


def _prepare_ingest_job(store: WorkspaceStore) -> None:
    store.save_ingest_job(
        {
            "id": "ing-climb",
            "source_url": "https://youtube.com/watch?v=climb123",
            "er16_plan_json": '{"task_goal":"climb a rock wall while carrying a rope pack","environment":"outdoor","locomotion_type":"walking","manipulation_required":true,"payload_kg":3.0,"success_criteria":"ascend a near-vertical wall while retaining the pack","search_queries":["rock climbing wall side view full body","human climber carrying rope pack"]}',
            "gvhmr_job_id": "gvhmr-1",
            "status": "processing",
        }
    )


def _patch_workspace(store: WorkspaceStore):
    return patch.multiple(
        "demo.routes.designs",
        workspace_store=store,
    )


def test_generate_designs_initializes_runtime_state(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "runtime.sqlite3")
    _prepare_ingest_job(store)
    rankings = [
        FallbackRanking(candidate_id="A", kinematic_feasibility=0.94, static_stability=0.77, bom_confidence=0.83, retargetability=0.9, total_score=0.88),
        FallbackRanking(candidate_id="B", kinematic_feasibility=0.86, static_stability=0.72, bom_confidence=0.79, retargetability=0.84, total_score=0.81),
        FallbackRanking(candidate_id="C", kinematic_feasibility=0.68, static_stability=0.8, bom_confidence=0.77, retargetability=0.51, total_score=0.69),
    ]

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.exports.workspace_store", store
    ), patch("demo.routes.hitl.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch("demo.routes.designs.rank_candidates_fallback", return_value=rankings):
        client = _client()
        generate = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"})

        assert generate.status_code == 201
        design_id = generate.json()["design_ids"]["A"]

        spec = client.get(f"/designs/{design_id}/spec")
        checkpoints = client.get(f"/designs/{design_id}/checkpoints")
        tasks = client.get(f"/designs/{design_id}/tasks")
        exports = client.get(f"/designs/{design_id}/exports")
        validation = client.get(f"/designs/{design_id}/validation")

    assert spec.status_code == 200
    assert spec.json()["candidate_id"] == "A"
    assert spec.json()["design"]["actuator_torque_nm"] == 34.0
    assert spec.json()["revision_number"] == 1
    assert spec.json()["render"]["engineering_ready"] is True
    assert spec.json()["render"]["render_glb"].startswith("data:model/gltf-binary;base64,")
    assert spec.json()["render"]["ui_scene"]["stats"]["engineering_ready"] is True

    assert checkpoints.status_code == 200
    checkpoint_ids = {item["id"] for item in checkpoints.json()["items"]}
    assert {"actuator", "payload"} <= checkpoint_ids
    assert all(item["status"] == "review" for item in checkpoints.json()["items"])

    assert tasks.status_code == 200
    task_ids = {item["task_key"] for item in tasks.json()["items"]}
    assert {"design", "reach", "payload", "isaac", "cost"} <= task_ids

    assert exports.status_code == 200
    export_labels = {item["label"] for item in exports.json()["items"]}
    assert {"URDF", "MJCF", "USD", "STEP"} <= export_labels
    assert validation.status_code == 200
    assert validation.json()["report"]["revision_id"] == spec.json()["revision_id"]
    assert "summary" in validation.json()["report"]
    artifact_keys = {item["artifact_key"] for item in validation.json()["artifacts"]}
    assert "validation_report" in artifact_keys


def test_checkpoint_decision_creates_revision_and_mutates_design(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "revisions.sqlite3")
    _prepare_ingest_job(store)

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["A"]

        before = client.get(f"/designs/{design_id}/spec").json()
        response = client.post(
            f"/designs/{design_id}/checkpoints/actuator/decision",
            json={"decision": "approved", "note": "increase shoulder torque for climbing"},
        )
        after = client.get(f"/designs/{design_id}/spec").json()
        validation = client.get(f"/designs/{design_id}/validation").json()["report"]
        checkpoints = client.get(f"/designs/{design_id}/checkpoints").json()["items"]

    assert response.status_code == 200
    body = response.json()
    assert body["revision_number"] == 2
    assert body["approval_event"]["decision"] == "approved"
    assert after["revision_number"] == 2
    assert after["design"]["actuator_torque_nm"] > before["design"]["actuator_torque_nm"]
    assert after["telemetry"]["estimated_total_cost_usd"] >= before["telemetry"]["estimated_total_cost_usd"]
    assert validation["revision_id"] == after["revision_id"]
    assert "output_path" in validation
    actuator_checkpoint = next(item for item in checkpoints if item["id"] == "actuator")
    assert actuator_checkpoint["decision"] == "approved"


def test_task_runs_and_record_clip_are_backend_driven(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "tasks.sqlite3")
    _prepare_ingest_job(store)

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["A"]

        cost_task = client.post(f"/designs/{design_id}/tasks", json={"task_key": "cost_bom_vs_budget"})
        export_task = client.post(f"/designs/{design_id}/tasks", json={"task_key": "export_urdf"})
        clip = client.post(f"/designs/{design_id}/record-clip", json={"mode": "task_preview"})
        tasks = client.get(f"/designs/{design_id}/tasks")
        exports = client.get(f"/designs/{design_id}/exports")

    assert cost_task.status_code == 201
    assert cost_task.json()["task_run"]["status"] == "done"
    assert "budget" in cost_task.json()["task_run"]["summary"].lower()
    assert export_task.status_code == 201
    assert export_task.json()["task_run"]["status"] == "done"
    assert "urdf" in export_task.json()["task_run"]["summary"].lower()

    assert clip.status_code == 201
    assert clip.json()["playback"]["task_goal"].startswith("climb a rock wall")
    assert clip.json()["playback"]["motion_profile"] == "climbing"
    assert clip.json()["playback"]["candidate_id"] == "A"
    assert clip.json()["playback"]["source_type"] == "youtube_gvhmr"
    assert clip.json()["playback"]["source_ready"] is True
    assert clip.json()["playback"]["source_ref"]["gvhmr_job_id"] == "gvhmr-1"
    assert clip.json()["playback"]["provenance_summary"].startswith("Replay sourced from YouTube")

    task_keys = [item["task_key"] for item in tasks.json()["items"]]
    assert "cost_bom_vs_budget" in task_keys
    assert "record_clip" in task_keys
    urdf_export = next(item for item in exports.json()["items"] if item["label"] == "URDF")
    assert urdf_export["status"] == "ready"


def test_design_events_stream_replays_seeded_tasks_in_order(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "events.sqlite3")
    _prepare_ingest_job(store)

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["A"]

        with client.stream(
            "GET",
            f"/designs/{design_id}/events?follow=false&replay_delay_ms=0",
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    payload_lines = [line for line in lines if line.startswith("data: ")]
    assert payload_lines, "Expected SSE payload lines"
    events = [json.loads(line.removeprefix("data: ")) for line in payload_lines]
    task_events = [event for event in events if event["event_type"] == "task.created"]
    assert [event["data"]["task_key"] for event in task_events[:5]] == ["design", "reach", "payload", "isaac", "cost"]


def test_design_events_stream_includes_task_updates_and_playback_ready(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "events-updates.sqlite3")
    _prepare_ingest_job(store)

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["A"]
        before = store.list_design_events(design_id)

        client.post(f"/designs/{design_id}/tasks", json={"task_key": "cost_bom_vs_budget"})
        client.post(f"/designs/{design_id}/record-clip", json={"mode": "task_preview"})

        with client.stream(
            "GET",
            f"/designs/{design_id}/events?follow=false&after_seq={before[-1]['seq'] if before else 0}&replay_delay_ms=0",
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: ")]
    event_types = [event["event_type"] for event in events]
    assert "task.updated" in event_types
    assert "playback.ready" in event_types


def test_revise_design_creates_new_revision_and_reorients_candidate_for_climbing(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "revise.sqlite3")
    _prepare_ingest_job(store)

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["C"]
        response = client.post(
            f"/designs/{design_id}/revise",
            json={"instruction": "make this a lean rock-climbing robot with hands and a rope pack on its back"},
        )
        spec = client.get(f"/designs/{design_id}/spec")
        tasks = client.get(f"/designs/{design_id}/tasks")

    assert response.status_code == 201
    body = response.json()
    assert body["revision_number"] == 2
    assert body["spec"]["design"]["num_arms"] >= 2
    assert body["spec"]["design"]["embodiment_class"] == "hybrid"
    assert body["spec"]["design"]["payload_capacity_kg"] >= 3.0
    assert spec.json()["revision_number"] == 2
    assert spec.json()["design"]["num_arms"] >= 2
    assert any(item["task_key"] == "revise_design" for item in tasks.json()["items"])


def test_record_clip_uses_droid_window_provenance_when_ingest_fell_back(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "droid-playback.sqlite3")
    store.save_ingest_job(
            {
                "id": "ing-droid",
                "source_url": None,
                "er16_plan_json": '{"task_goal":"crawl through a narrow duct","environment":"indoor","locomotion_type":"crawling","manipulation_required":false,"payload_kg":0.5,"success_criteria":"clear the duct without collisions","search_queries":["human crawl through narrow tunnel"]}',
            "gvhmr_job_id": None,
            "status": "reference_selected",
            "reference_source_type": "droid",
            "reference_payload_json": {
                "source_type": "droid",
                "query_text": "crawl through a narrow duct human crawl through narrow tunnel",
                "reference": {
                    "episode_id": "ep-crawl-3",
                    "source_format": "lerobot_v3",
                    "task_text": "robot crawls through a constrained duct section",
                    "language_annotations": ["crawl through narrow tunnel"],
                    "action_path": "hf://droid/ep-crawl-3/actions.parquet",
                    "state_path": "hf://droid/ep-crawl-3/states.parquet",
                    "camera_refs": {"overhead": "hf://droid/ep-crawl-3/overhead.mp4"},
                    "match_score": 0.91,
                    "reason": "matched crawl and narrow tunnel; trajectory pointers available",
                    "retrieval_unit": "window",
                    "trajectory_window": [24, 96],
                },
            },
        }
    )

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-droid"}).json()["design_ids"]["A"]
        clip = client.post(f"/designs/{design_id}/record-clip", json={"mode": "task_preview"})

    assert clip.status_code == 201
    playback = clip.json()["playback"]
    assert playback["source_type"] == "droid_window"
    assert playback["source_ready"] is True
    assert playback["source_ref"]["episode_id"] == "ep-crawl-3"
    assert playback["source_ref"]["trajectory_window"] == [24, 96]
    assert playback["provenance_summary"].startswith("Replay sourced from DROID window")


def test_record_clip_reports_unavailable_motion_source_explicitly(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "no-motion-source.sqlite3")
    store.save_ingest_job(
            {
                "id": "ing-none",
                "source_url": None,
                "er16_plan_json": '{"task_goal":"walk between markers","environment":"indoor","locomotion_type":"walking","manipulation_required":false,"payload_kg":0.0,"success_criteria":"walk the path","search_queries":["person walking fixed camera"]}',
            "gvhmr_job_id": None,
            "status": "analysis_ready",
            "reference_source_type": None,
            "reference_payload_json": None,
        }
    )

    with patch("demo.routes.designs.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-none"}).json()["design_ids"]["A"]
        clip = client.post(f"/designs/{design_id}/record-clip", json={"mode": "task_preview"})

    assert clip.status_code == 201
    playback = clip.json()["playback"]
    assert playback["source_type"] == "unavailable"
    assert playback["source_ready"] is False
    assert playback["source_ref"] == {}
    assert "No motion source is available" in playback["provenance_summary"]


def test_send_review_poll_task_hits_http_photon_boundary(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "photon-runtime.sqlite3")
    _prepare_ingest_job(store)
    captured: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            captured["path"] = self.path
            captured["auth"] = self.headers.get("Authorization")
            captured["body"] = body
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"message_id":"msg-1"}')

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {
        "PHOTON_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "PHOTON_API_KEY": "test-key",
        "PHOTON_RECIPIENT": "",
        "PHOTON_PROJECT_ID": "",
        "PHOTON_SECRET_KEY": "",
    }

    store.upsert_hitl_recipient(
        {
            "id": "recipient-1",
            "channel": "photon",
            "recipient": "+15551234567",
            "display_name": "Ops",
            "thread_key": "orchard_01",
            "consent_status": "confirmed",
            "is_default": True,
        }
    )

    try:
        with patch.dict(os.environ, env, clear=False), patch(
            "demo.routes.designs.workspace_store", store
        ), patch("demo.routes.hitl.workspace_store", store), patch(
            "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
        ), patch(
            "demo.routes.designs.rank_candidates_fallback",
            return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
        ):
            client = _client()
            design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["A"]
            response = client.post(f"/designs/{design_id}/tasks", json={"task_key": "send_review_poll"})
    finally:
        server.shutdown()
        thread.join(timeout=3)

    assert response.status_code == 201
    assert response.json()["task_run"]["status"] == "done"
    assert captured["path"] == "/polls"
    assert captured["auth"] == "Bearer test-key"
    assert "+15551234567" in captured["body"]
    assert "Approve design checkpoint" in captured["body"]


def test_send_review_poll_task_uses_spectrum_cli_transport_when_project_credentials_exist(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "photon-runtime-spectrum.sqlite3")
    _prepare_ingest_job(store)

    store.upsert_hitl_recipient(
        {
            "id": "recipient-spectrum",
            "channel": "photon",
            "recipient": "+15554443333",
            "display_name": "Ops",
            "thread_key": "iMessage;-;+15554443333",
            "consent_status": "confirmed",
            "is_default": True,
        }
    )

    env = {
        "PHOTON_PROJECT_ID": "project-demo",
        "PHOTON_SECRET_KEY": "secret-demo",
        "PHOTON_MOCK_MODE": "1",
        "PHOTON_BASE_URL": "",
        "PHOTON_RECIPIENT": "",
    }

    with patch.dict(os.environ, env, clear=False), patch(
        "demo.routes.designs.workspace_store", store
    ), patch("demo.routes.hitl.workspace_store", store), patch(
        "demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()
    ), patch(
        "demo.routes.designs.rank_candidates_fallback",
        return_value=[FallbackRanking(candidate_id=i, kinematic_feasibility=0.9, static_stability=0.8, bom_confidence=0.8, retargetability=0.8, total_score=0.82) for i in ["A", "B", "C"]],
    ):
        client = _client()
        design_id = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"}).json()["design_ids"]["A"]
        response = client.post(f"/designs/{design_id}/tasks", json={"task_key": "send_review_poll"})

    assert response.status_code == 201
    task_run = response.json()["task_run"]
    assert task_run["status"] == "done"
    assert task_run["result_json"]["raw_response"]["transport"] == "spectrum-cli-mock"
    assert task_run["result_json"]["raw_response"]["space_id"] == "iMessage;-;+15554443333"
