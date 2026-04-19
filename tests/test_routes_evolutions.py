import os
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake")
os.environ.setdefault("GEMINI_API_KEY", "fake")
os.environ.setdefault("YOUTUBE_API_KEY", "fake")

from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from demo.app import create_app
import demo.routes.evolutions as evolutions_module
from demo.workspace_store import WorkspaceStore
from packages.pipeline.schemas import (
    BOMItem,
    BOMOutput,
    DesignCandidatesResponse,
    FallbackRanking,
    RobotDesignCandidate,
)

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
    assert "/designs/generate" in paths


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


def test_ingest_post_degrades_when_reference_video_search_fails():
    with patch("demo.routes.ingest._svc") as mock_svc:
        mock_svc.analyze_prompt.return_value = {
            "task_goal": "carry folded clothes",
            "affordances": ["payload"],
            "success_criteria": "carry without dropping",
            "search_queries": ["person carrying folded clothes side view"],
        }
        mock_svc.select_reference_video.side_effect = LookupError("No strong human reference video found")

        response = client.post("/ingest", json={"prompt": "carry folded clothes"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "analysis_ready"
    assert payload["video_id"] is None
    assert payload["selected_query"] == "person carrying folded clothes side view"
    assert "Reference video unavailable" in payload["selection_rationale"]


def test_ingest_post_uses_droid_fallback_when_youtube_search_fails():
    with patch("demo.routes.ingest._svc") as mock_svc:
        mock_svc.analyze_prompt.return_value = {
            "task_goal": "carry a box downstairs",
            "affordances": ["stairs", "payload"],
            "success_criteria": "carry without dropping",
            "search_queries": ["person carrying box downstairs side view"],
        }
        mock_svc.select_reference_video.side_effect = LookupError("No strong human reference video found")
        mock_svc.select_droid_reference.return_value = {
            "source_type": "droid",
            "query_text": "carry a box downstairs person carrying box downstairs side view",
            "required_task_terms": ["carry", "box", "downstairs"],
            "preferred_camera_terms": ["fixed camera", "side view", "full body"],
            "reference": {
                "episode_id": "ep-42",
                "source_format": "rlds",
                "task_text": "carry box downstairs",
                "language_annotations": ["carry box downstairs"],
                "action_path": "gs://droid/ep-42/trajectory.h5",
                "state_path": "gs://droid/ep-42/trajectory.h5",
                "camera_refs": {"front": "gs://droid/ep-42/front.mp4"},
                "match_score": 0.92,
                "reason": "matched carry and downstairs; trajectory pointers available",
                "retrieval_unit": "episode",
                "trajectory_window": None,
            },
        }
        response = client.post("/ingest", json={"prompt": "carry a box downstairs"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "reference_selected"
    assert payload["video_id"] is None
    assert payload["gvhmr_job_id"] is None
    assert payload["reference_source_type"] == "droid"
    assert payload["reference_payload"]["reference"]["episode_id"] == "ep-42"
    assert "DROID fallback selected" in payload["selection_rationale"]


def test_ingest_post_uses_droid_fallback_when_youtube_times_out():
    with patch("demo.routes.ingest._svc") as mock_svc:
        mock_svc.analyze_prompt.return_value = {
            "task_goal": "climb a rock wall",
            "affordances": ["vertical_locomotion", "grasping"],
            "success_criteria": "ascend while maintaining three points of contact",
            "search_queries": ["human rock climbing side view"],
        }
        mock_svc.select_reference_video.side_effect = TimeoutError("YouTube search timed out")
        mock_svc.select_droid_reference.return_value = {
            "source_type": "droid",
            "query_text": "climb a rock wall human rock climbing side view",
            "required_task_terms": ["climb", "rock", "wall"],
            "preferred_camera_terms": ["side view", "full body"],
            "reference": {
                "episode_id": "ep-climb-7",
                "source_format": "lerobot_v3",
                "task_text": "robot climbs steep fixture with gripper contact transitions",
                "language_annotations": ["vertical climbing with grippers"],
                "action_path": "hf://droid/ep-climb-7/actions.parquet",
                "state_path": "hf://droid/ep-climb-7/states.parquet",
                "camera_refs": {"front_left": "hf://droid/ep-climb-7/front_left.mp4"},
                "match_score": 0.88,
                "reason": "matched climb and wall; trajectory pointers available",
                "retrieval_unit": "window",
                "trajectory_window": [90, 180],
            },
        }
        response = client.post("/ingest", json={"prompt": "climb a rock wall"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "reference_selected"
    assert payload["reference_source_type"] == "droid"
    assert payload["reference_payload"]["reference"]["episode_id"] == "ep-climb-7"
    assert "timed out" in payload["selection_rationale"].lower()
    assert "droid fallback selected" in payload["selection_rationale"].lower()


def test_create_evolution_returns_stage_on_orchestrator_failure():
    local_store = WorkspaceStore(Path("/tmp") / "test-create-evolution.sqlite3")
    local_store.save_ingest_job(
        {
            "id": "ing-1",
            "source_url": "https://youtube.com/watch?v=abc123",
            "er16_plan_json": '{"task_goal":"walk","search_queries":["walk demo"],"affordances":[],"success_criteria":"reach"}',
            "gvhmr_job_id": "gvhmr-1",
            "status": "processing",
        }
    )

    with patch("demo.routes.evolutions.workspace_store", local_store), \
         patch.object(evolutions_module._evo_svc, "store", local_store), \
         patch(
             "demo.routes.evolutions._evo_svc.create",
             side_effect=lambda run_id: local_store.create_evolution(run_id, evo_id="evo-1")["id"],
         ), \
         patch("demo.routes.evolutions.CLIOrchestrator") as mock_orch:
        mock_orch.return_value.draft_program_md.side_effect = RuntimeError("claude failed")
        r = client.post("/evolutions", json={"run_id": "run-1", "ingest_job_id": "ing-1"})

    assert r.status_code == 502
    assert r.json()["detail"]["stage"] == "draft_program_md"
    assert r.json()["detail"]["error"] == "claude failed"


def _sample_candidates_response() -> DesignCandidatesResponse:
    return DesignCandidatesResponse(
        task_interpretation="Robot should carry payload on stairs.",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="biped",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.52,
                arm_length_m=0.42,
                leg_length_m=0.72,
                arm_dof=4,
                leg_dof=5,
                spine_dof=2,
                actuator_class="bldc",
                actuator_torque_nm=24.0,
                total_mass_kg=22.0,
                payload_capacity_kg=5.0,
                sensor_package=["imu", "encoder", "camera"],
                rationale="Humanoid stair-carrying design.",
                confidence=0.88,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="quadruped",
                num_legs=4,
                num_arms=1,
                has_torso=True,
                torso_length_m=0.6,
                arm_length_m=0.36,
                leg_length_m=0.45,
                arm_dof=4,
                leg_dof=3,
                spine_dof=1,
                actuator_class="bldc",
                actuator_torque_nm=18.0,
                total_mass_kg=20.0,
                payload_capacity_kg=3.0,
                sensor_package=["imu", "encoder", "camera"],
                rationale="Stable quadruped with manipulator.",
                confidence=0.8,
            ),
            RobotDesignCandidate(
                candidate_id="C",
                embodiment_class="hybrid",
                num_legs=2,
                num_arms=1,
                has_torso=True,
                torso_length_m=0.44,
                arm_length_m=0.35,
                leg_length_m=0.48,
                arm_dof=4,
                leg_dof=3,
                spine_dof=1,
                actuator_class="servo",
                actuator_torque_nm=12.0,
                total_mass_kg=14.0,
                payload_capacity_kg=2.0,
                sensor_package=["imu", "encoder"],
                rationale="Simpler hybrid platform for quick prototyping.",
                confidence=0.72,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="Candidate A best matches the task and payload needs.",
    )


def test_generate_designs_returns_render_payloads_and_persists_local_designs(tmp_path):
    local_store = WorkspaceStore(tmp_path / "designs.sqlite3")
    local_store.save_ingest_job(
        {
            "id": "ing-1",
            "source_url": "https://youtube.com/watch?v=abc123",
            "er16_plan_json": '{"task_goal":"carry a box upstairs","environment":"indoor","locomotion_type":"walking","manipulation_required":true,"payload_kg":4.0,"success_criteria":"carry without dropping","search_queries":["person carrying box upstairs side view"]}',
            "gvhmr_job_id": "gvhmr-1",
            "status": "processing",
        }
    )

    rankings = [
        FallbackRanking(candidate_id="A", kinematic_feasibility=0.91, static_stability=0.7, bom_confidence=0.82, retargetability=0.86, total_score=0.84),
        FallbackRanking(candidate_id="B", kinematic_feasibility=0.82, static_stability=0.89, bom_confidence=0.76, retargetability=0.71, total_score=0.8),
        FallbackRanking(candidate_id="C", kinematic_feasibility=0.71, static_stability=0.63, bom_confidence=0.68, retargetability=0.65, total_score=0.67),
    ]

    with patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()), \
         patch("demo.routes.designs.rank_candidates_fallback", return_value=rankings):
        response = client.post("/designs/generate", json={"ingest_job_id": "ing-1"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["model_preferred_id"] == "A"
    assert payload["selection_rationale"] == "Candidate A best matches the task and payload needs."
    assert set(payload["design_ids"].keys()) == {"A", "B", "C"}
    assert set(payload["render_payloads"].keys()) == {"A", "B", "C"}
    assert payload["render_payloads"]["A"]["view_modes"] == ["concept", "engineering", "joints", "components"]
    assert payload["render_payloads"]["A"]["engineering_ready"] is True
    assert payload["render_payloads"]["A"]["render_glb"].startswith("data:model/gltf-binary;base64,")
    assert payload["render_payloads"]["A"]["ui_scene"]["stats"]["engineering_ready"] is True
    assert payload["render_payloads"]["A"]["ui_scene"]["stats"]["material_count"] >= 8
    assert payload["render_payloads"]["A"]["ui_scene"]["stats"]["panel_node_count"] >= 8
    assert "candidate_telemetry" in payload
    assert payload["candidate_telemetry"]["A"]["estimated_total_cost_usd"] is not None
    assert payload["candidate_telemetry"]["A"]["estimated_mass_kg"] == 22.0
    assert payload["candidate_telemetry"]["A"]["estimated_backlash_deg"] >= 0

    stored = local_store.list_designs_by_ingest("ing-1")
    assert len(stored) == 3
    assert stored[0]["render_json"]["mjcf"].startswith("<mujoco")
    assert stored[0]["telemetry_json"]["estimated_total_cost_usd"] is not None
    assert [item["screening_score"] for item in stored] == [0.84, 0.8, 0.67]


def test_generate_designs_uses_task_spec_for_geometry_profile(tmp_path):
    local_store = WorkspaceStore(tmp_path / "climbing-designs.sqlite3")
    local_store.save_ingest_job(
        {
            "id": "ing-climb",
            "source_url": "https://youtube.com/watch?v=rock123",
            "er16_plan_json": '{"task_goal":"climb a rock wall while carrying a rope pack","environment":"outdoor","locomotion_type":"walking","manipulation_required":true,"payload_kg":4.0,"success_criteria":"ascend while keeping the pack stable","search_queries":["rock climber carrying rope pack","vertical climbing side view"]}',
            "gvhmr_job_id": "gvhmr-2",
            "status": "processing",
        }
    )

    rankings = [
        FallbackRanking(candidate_id="A", kinematic_feasibility=0.92, static_stability=0.72, bom_confidence=0.81, retargetability=0.88, total_score=0.87),
        FallbackRanking(candidate_id="B", kinematic_feasibility=0.84, static_stability=0.71, bom_confidence=0.77, retargetability=0.79, total_score=0.8),
        FallbackRanking(candidate_id="C", kinematic_feasibility=0.68, static_stability=0.63, bom_confidence=0.7, retargetability=0.61, total_score=0.66),
    ]

    with patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()), \
         patch("demo.routes.designs.rank_candidates_fallback", return_value=rankings):
        response = client.post("/designs/generate", json={"ingest_job_id": "ing-climb"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["render_payloads"]["A"]["ui_scene"]["stats"]["task_geometry_profile"] == "climbing_payload"
    assert payload["render_payloads"]["A"]["ui_scene"]["stats"]["accessory_node_count"] >= 4


def test_generate_designs_applies_diversity_reranking_and_returns_collapse_report(tmp_path):
    local_store = WorkspaceStore(tmp_path / "designs-diversity.sqlite3")
    local_store.save_ingest_job(
        {
            "id": "ing-diversity",
            "source_url": "https://youtube.com/watch?v=div123",
            "er16_plan_json": '{"task_goal":"inspect a vessel interior while carrying a sensor pack","environment":"indoor","locomotion_type":"walking","manipulation_required":true,"payload_kg":2.0,"success_criteria":"reach into the vessel and keep the sensor pack stable","search_queries":["borescope inspection manipulator"]}',
            "gvhmr_job_id": "gvhmr-div",
            "status": "processing",
        }
    )

    duplicate_response = DesignCandidatesResponse(
        task_interpretation="inspection manipulator",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="hybrid",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.52,
                arm_length_m=0.66,
                leg_length_m=0.70,
                arm_dof=5,
                leg_dof=4,
                spine_dof=2,
                actuator_class="bldc",
                actuator_torque_nm=26.0,
                total_mass_kg=18.0,
                payload_capacity_kg=3.0,
                sensor_package=["imu", "encoder", "camera", "force"],
                rationale="Conservative hybrid vessel inspector with dual reach arms and borescope tooling.",
                confidence=0.87,
                task_fit_score=0.91,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="hybrid",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.51,
                arm_length_m=0.65,
                leg_length_m=0.69,
                arm_dof=5,
                leg_dof=4,
                spine_dof=2,
                actuator_class="bldc",
                actuator_torque_nm=25.5,
                total_mass_kg=17.6,
                payload_capacity_kg=3.0,
                sensor_package=["imu", "encoder", "camera", "force"],
                rationale="Alternate hybrid inspector with the same borescope reach strategy and back-mounted sensor pack.",
                confidence=0.85,
                task_fit_score=0.9,
            ),
            RobotDesignCandidate(
                candidate_id="C",
                embodiment_class="arm",
                num_legs=0,
                num_arms=1,
                has_torso=False,
                torso_length_m=0.18,
                arm_length_m=0.84,
                leg_length_m=0.0,
                arm_dof=6,
                leg_dof=0,
                spine_dof=0,
                actuator_class="bldc",
                actuator_torque_nm=18.0,
                total_mass_kg=11.0,
                payload_capacity_kg=2.5,
                sensor_package=["camera", "encoder", "force"],
                rationale="Single-arm insertion inspector with compact base and dedicated vessel-entry tooling.",
                confidence=0.8,
                task_fit_score=0.86,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="Candidate A has the best direct task fit.",
    )

    rankings = [
        FallbackRanking(candidate_id="A", kinematic_feasibility=0.88, static_stability=0.72, bom_confidence=0.82, retargetability=0.86, total_score=0.83),
        FallbackRanking(candidate_id="B", kinematic_feasibility=0.87, static_stability=0.71, bom_confidence=0.81, retargetability=0.85, total_score=0.82),
        FallbackRanking(candidate_id="C", kinematic_feasibility=0.84, static_stability=0.79, bom_confidence=0.78, retargetability=0.82, total_score=0.8),
    ]

    with patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.designs.generate_design_candidates", return_value=duplicate_response), \
         patch("demo.routes.designs.rank_candidates_fallback", return_value=rankings):
        response = client.post("/designs/generate", json={"ingest_job_id": "ing-diversity"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["model_preferred_id"] == "C"
    assert payload["collapse_report"]["duplicate_pairs"]
    assert "diversity reranking" in payload["selection_rationale"].lower()


def test_get_design_bom_caches_generated_bom(tmp_path):
    local_store = WorkspaceStore(tmp_path / "bom-cache.sqlite3")
    local_store.create_design(
        {
            "id": "design-a",
            "ingest_job_id": "ing-1",
            "candidate_id": "A",
            "design_json": _sample_candidates_response().candidates[0].model_dump(),
            "render_json": {"mjcf": "<mujoco/>"},
            "is_model_preferred": True,
            "is_user_selected": False,
        }
    )
    bom = BOMOutput(
        candidate_id="A",
        actuator_items=[
            BOMItem(
                part_name="Dynamixel XM540-W270",
                quantity=8,
                vendor="robotis",
                sku="XM540-W270-R",
                unit_price_usd=359.9,
                availability="in_stock",
            )
        ],
        procurement_confidence=0.82,
        total_cost_usd=2879.2,
    )

    with patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.designs.generate_bom_for_candidate", return_value=bom) as mock_generate:
        first = client.get("/designs/design-a/bom")
        second = client.get("/designs/design-a/bom")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert mock_generate.call_count == 1
    assert local_store.get_design("design-a")["bom_json"]["total_cost_usd"] == 2879.2


def test_ingest_and_designs_use_local_store_when_supabase_is_unreachable(tmp_path):
    local_store = WorkspaceStore(tmp_path / "workspace.sqlite3")

    with patch("demo.routes.ingest.workspace_store", local_store), \
         patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.ingest._svc") as mock_svc:
        mock_svc.analyze_prompt.return_value = {
            "task_goal": "carry a box upstairs",
            "affordances": ["stairs", "payload"],
            "success_criteria": "carry without dropping",
            "search_queries": ["person carrying box upstairs side view"],
        }
        mock_svc.select_reference_video.return_value = {
            "video_id": "abc123",
            "query": "person carrying box upstairs side view",
            "rationale": "Stable side-view reference clip.",
            "candidate_reviews": [{"video_id": "abc123", "score": 9}],
        }
        mock_svc.run_gvhmr.return_value = "gvhmr-job-1"

        create_resp = client.post("/ingest", json={"prompt": "carry a box upstairs"})

    assert create_resp.status_code == 201
    job_id = create_resp.json()["job_id"]

    with patch("demo.routes.ingest.workspace_store", local_store):
        get_resp = client.get(f"/ingest/{job_id}")

    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id
    assert "er16_plan_json" in get_resp.json()

    with patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()), \
         patch("demo.routes.designs.rank_candidates_fallback", return_value=[
             FallbackRanking(candidate_id="A", kinematic_feasibility=0.9, static_stability=0.7, bom_confidence=0.8, retargetability=0.75, total_score=0.9),
             FallbackRanking(candidate_id="B", kinematic_feasibility=0.8, static_stability=0.9, bom_confidence=0.7, retargetability=0.6, total_score=0.7),
             FallbackRanking(candidate_id="C", kinematic_feasibility=0.6, static_stability=0.6, bom_confidence=0.5, retargetability=0.5, total_score=0.5),
         ]):
        generate_resp = client.post("/designs/generate", json={"ingest_job_id": job_id})

    assert generate_resp.status_code == 201
    payload = generate_resp.json()
    assert payload["model_preferred_id"] == "A"
    assert payload["selection_rationale"] == "Candidate A best matches the task and payload needs."
    assert set(payload["design_ids"].keys()) == {"A", "B", "C"}

    with patch("demo.routes.designs.workspace_store", local_store):
        listed = client.get(f"/designs/by-ingest/{job_id}")

    assert listed.status_code == 200
    assert len(listed.json()) == 3


def test_select_design_clears_previous_user_selection_and_updates_evolution(tmp_path):
    local_store = WorkspaceStore(tmp_path / "selection.sqlite3")
    local_store.create_evolution("run-1", evo_id="evo-1")
    local_store.create_design(
        {
            "id": "design-a",
            "ingest_job_id": "ing-1",
            "candidate_id": "A",
            "design_json": _sample_candidates_response().candidates[0].model_dump(),
            "render_json": {"mjcf": "<mujoco/>"},
            "is_model_preferred": True,
            "is_user_selected": False,
        }
    )
    local_store.create_design(
        {
            "id": "design-b",
            "ingest_job_id": "ing-1",
            "candidate_id": "B",
            "design_json": _sample_candidates_response().candidates[1].model_dump(),
            "render_json": {"mjcf": "<mujoco/>"},
            "is_model_preferred": False,
            "is_user_selected": False,
        }
    )

    with patch("demo.routes.designs.workspace_store", local_store):
        first = client.post("/designs/design-a/select", json={"evolution_id": "evo-1"})
        second = client.post("/designs/design-b/select", json={"evolution_id": "evo-1"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert local_store.get_design("design-a")["is_user_selected"] is False
    assert local_store.get_design("design-b")["is_user_selected"] is True
    assert local_store.get_evolution("evo-1")["design_id"] == "design-b"


def test_get_evolution_returns_404_for_unknown_id(tmp_path):
    local_store = WorkspaceStore(tmp_path / "missing-evolution.sqlite3")
    with patch("demo.routes.evolutions.workspace_store", local_store), \
         patch.object(evolutions_module._evo_svc, "store", local_store):
        response = client.get("/evolutions/missing-evo")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evolution not found"


def test_local_route_crud_flow_covers_ingest_design_bom_evolution_and_selection(tmp_path):
    local_store = WorkspaceStore(tmp_path / "flow.sqlite3")

    with patch("demo.routes.ingest.workspace_store", local_store), \
         patch("demo.routes.designs.workspace_store", local_store), \
         patch("demo.routes.evolutions.workspace_store", local_store), \
         patch.object(evolutions_module._evo_svc, "store", local_store), \
         patch("demo.routes.ingest._svc") as mock_svc, \
         patch("demo.routes.evolutions.CLIOrchestrator") as mock_orch, \
         patch(
             "demo.routes.evolutions._evo_svc.create",
             side_effect=lambda run_id: local_store.create_evolution(run_id, evo_id="evo-1")["id"],
         ), \
         patch("demo.routes.designs.generate_design_candidates", return_value=_sample_candidates_response()):
        mock_svc.analyze_prompt.return_value = {
            "task_goal": "carry a box upstairs",
            "affordances": ["stairs", "payload"],
            "success_criteria": "carry without dropping",
            "search_queries": ["person carrying box upstairs side view"],
        }
        mock_svc.select_reference_video.return_value = {
            "video_id": "abc123",
            "query": "person carrying box upstairs side view",
            "rationale": "Stable side-view reference clip.",
            "candidate_reviews": [{"video_id": "abc123", "score": 9}],
        }
        mock_svc.run_gvhmr.return_value = "gvhmr-job-1"
        mock_orch.return_value.draft_program_md.return_value = ("# Program", "gemini")

        ingest_response = client.post("/ingest", json={"prompt": "carry a box upstairs"})
        assert ingest_response.status_code == 201
        job_id = ingest_response.json()["job_id"]

        designs_response = client.post("/designs/generate", json={"ingest_job_id": job_id})
        assert designs_response.status_code == 201
        design_ids = designs_response.json()["design_ids"]
        selected_design_id = design_ids["A"]

        design_detail = client.get(f"/designs/{selected_design_id}")
        assert design_detail.status_code == 200
        assert design_detail.json()["candidate_id"] == "A"
        assert design_detail.json()["render_json"]["joint_count"] > 0

        bom_response = client.get(f"/designs/{selected_design_id}/bom")
        assert bom_response.status_code == 200
        assert bom_response.json()["candidate_id"] == "A"
        assert bom_response.json()["procurement_confidence"] > 0

        cached_bom_response = client.get(f"/designs/{selected_design_id}/bom")
        assert cached_bom_response.status_code == 200
        assert cached_bom_response.json() == bom_response.json()

        evolution_response = client.post("/evolutions", json={"run_id": "run-1", "ingest_job_id": job_id})
        assert evolution_response.status_code == 201
        assert evolution_response.json()["evolution_id"] == "evo-1"

        select_response = client.post(
            f"/designs/{selected_design_id}/select",
            json={"evolution_id": "evo-1"},
        )
        assert select_response.status_code == 200
        assert select_response.json()["status"] == "selected"

        evolution_detail = client.get("/evolutions/evo-1")
        assert evolution_detail.status_code == 200
        assert evolution_detail.json()["design_id"] == selected_design_id
        assert local_store.get_design(selected_design_id)["is_user_selected"] is True
