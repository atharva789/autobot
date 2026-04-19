"""Tests for the task-conditioned robot design pipeline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from packages.pipeline.schemas import (
    TaskSpec,
    RobotDesignCandidate,
    DesignCandidatesResponse,
    BOMOutput,
    FallbackRanking,
)
from packages.pipeline.design_generator import (
    build_render_payload,
    generate_design_candidates,
    candidate_to_morphology_params,
    _validate_candidates,
)
from packages.pipeline.task_conditioning import (
    build_task_capability_graph,
    score_candidate_task_fit,
)
from packages.pipeline.design_diversity import (
    apply_diversity_controls,
    build_design_novelty_signature,
    build_prompt_conditioning_fingerprint,
)
from packages.pipeline.design_validation import build_design_validation_report
from packages.pipeline.task_hardrails import evaluate_candidate_hardrails
from packages.pipeline.bom_generator import (
    design_to_componentized_morphology,
    componentized_to_bom,
    generate_bom_for_candidate,
)
from packages.pipeline.telemetry import build_candidate_telemetry
from packages.pipeline.fallback_chooser import (
    kinematic_feasibility_score,
    static_stability_score,
    retargetability_score,
    rank_candidates_fallback,
    select_best_candidate_fallback,
)


# --- Fixtures ---

@pytest.fixture
def sample_task_spec() -> TaskSpec:
    return TaskSpec(
        task_goal="walk forward at 1 m/s",
        environment="indoor",
        locomotion_type="walking",
        manipulation_required=False,
        payload_kg=0.0,
        success_criteria="maintain stable gait for 10 seconds",
        search_queries=["human walking side view"],
    )


@pytest.fixture
def sample_biped_candidate() -> RobotDesignCandidate:
    return RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="biped",
        num_legs=2,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.4,
        arm_length_m=0.0,
        leg_length_m=0.5,
        arm_dof=0,
        leg_dof=4,
        spine_dof=1,
        actuator_class="servo",
        actuator_torque_nm=12.0,
        total_mass_kg=8.0,
        payload_capacity_kg=0.0,
        sensor_package=["imu", "encoder"],
        rationale="Classic humanoid leg design",
        confidence=0.85,
    )


@pytest.fixture
def sample_quadruped_candidate() -> RobotDesignCandidate:
    return RobotDesignCandidate(
        candidate_id="B",
        embodiment_class="quadruped",
        num_legs=4,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.5,
        arm_length_m=0.0,
        leg_length_m=0.35,
        arm_dof=0,
        leg_dof=3,
        spine_dof=2,
        actuator_class="servo",
        actuator_torque_nm=8.0,
        total_mass_kg=12.0,
        payload_capacity_kg=2.0,
        sensor_package=["imu"],
        rationale="Stable four-legged design",
        confidence=0.80,
    )


@pytest.fixture
def sample_minimal_candidate() -> RobotDesignCandidate:
    return RobotDesignCandidate(
        candidate_id="C",
        embodiment_class="biped",
        num_legs=2,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.3,
        arm_length_m=0.0,
        leg_length_m=0.4,
        arm_dof=0,
        leg_dof=3,
        spine_dof=0,
        actuator_class="servo",
        actuator_torque_nm=6.0,
        total_mass_kg=4.0,
        payload_capacity_kg=0.0,
        sensor_package=["imu"],
        rationale="Minimal viable biped",
        confidence=0.75,
    )


# --- Schema Tests ---

def test_task_spec_validation():
    spec = TaskSpec(
        task_goal="pick up object",
        environment="indoor",
        locomotion_type="stationary",
        manipulation_required=True,
        success_criteria="object lifted",
        search_queries=["human picking up box"],
    )
    assert spec.manipulation_required is True
    assert spec.locomotion_type == "stationary"


def test_robot_design_candidate_bounds():
    with pytest.raises(ValueError):
        RobotDesignCandidate(
            candidate_id="A",
            embodiment_class="biped",
            num_legs=10,  # exceeds max of 8
            num_arms=0,
            has_torso=True,
            torso_length_m=0.4,
            arm_length_m=0.0,
            leg_length_m=0.5,
            arm_dof=0,
            leg_dof=4,
            spine_dof=1,
            actuator_class="servo",
            actuator_torque_nm=12.0,
            total_mass_kg=8.0,
            payload_capacity_kg=0.0,
            sensor_package=["imu"],
            rationale="Invalid",
            confidence=0.5,
        )


# --- Design Generator Tests ---

def test_candidate_to_morphology_params(sample_biped_candidate):
    params = candidate_to_morphology_params(sample_biped_candidate)
    assert params["num_legs"] == 2
    assert params["leg_length"] == 0.5
    assert params["leg_dof"] == 4
    assert params["has_torso"] is True


def test_validate_candidates_rejects_wrong_ids():
    response = DesignCandidatesResponse(
        task_interpretation="test",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="biped",
                num_legs=2,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.4,
                arm_length_m=0.0,
                leg_length_m=0.5,
                arm_dof=0,
                leg_dof=3,
                spine_dof=0,
                actuator_class="servo",
                actuator_torque_nm=5.0,
                total_mass_kg=5.0,
                payload_capacity_kg=0.0,
                sensor_package=[],
                rationale="test",
                confidence=0.5,
            ),
            RobotDesignCandidate(
                candidate_id="A",  # duplicate
                embodiment_class="quadruped",
                num_legs=4,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.5,
                arm_length_m=0.0,
                leg_length_m=0.3,
                arm_dof=0,
                leg_dof=2,
                spine_dof=0,
                actuator_class="servo",
                actuator_torque_nm=5.0,
                total_mass_kg=8.0,
                payload_capacity_kg=0.0,
                sensor_package=[],
                rationale="test",
                confidence=0.5,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="arm",
                num_legs=0,
                num_arms=1,
                has_torso=False,
                torso_length_m=0.1,
                arm_length_m=0.5,
                leg_length_m=0.0,
                arm_dof=5,
                leg_dof=0,
                spine_dof=0,
                actuator_class="servo",
                actuator_torque_nm=3.0,
                total_mass_kg=2.0,
                payload_capacity_kg=1.0,
                sensor_package=[],
                rationale="test",
                confidence=0.5,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="test",
    )
    with pytest.raises(Exception):
        _validate_candidates(response)


def test_generate_design_candidates_uses_current_preview_model(sample_task_spec):
    payload = DesignCandidatesResponse(
        task_interpretation="Flat-ground walking",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="biped",
                num_legs=2,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.4,
                arm_length_m=0.0,
                leg_length_m=0.5,
                arm_dof=0,
                leg_dof=4,
                spine_dof=1,
                actuator_class="servo",
                actuator_torque_nm=12.0,
                total_mass_kg=8.0,
                payload_capacity_kg=0.0,
                sensor_package=["imu", "encoder"],
                rationale="Conventional biped",
                confidence=0.85,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="quadruped",
                num_legs=4,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.5,
                arm_length_m=0.0,
                leg_length_m=0.35,
                arm_dof=0,
                leg_dof=3,
                spine_dof=1,
                actuator_class="servo",
                actuator_torque_nm=10.0,
                total_mass_kg=10.0,
                payload_capacity_kg=1.0,
                sensor_package=["imu"],
                rationale="Stable quadruped",
                confidence=0.8,
            ),
            RobotDesignCandidate(
                candidate_id="C",
                embodiment_class="biped",
                num_legs=2,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.3,
                arm_length_m=0.0,
                leg_length_m=0.4,
                arm_dof=0,
                leg_dof=3,
                spine_dof=0,
                actuator_class="servo",
                actuator_torque_nm=8.0,
                total_mass_kg=4.0,
                payload_capacity_kg=0.0,
                sensor_package=["imu"],
                rationale="Minimal walker",
                confidence=0.75,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="Candidate A is the best balance of complexity and capability.",
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(
        text=payload.model_dump_json()
    )

    with patch("packages.pipeline.design_generator._get_gemini_client", return_value=mock_client):
        result = generate_design_candidates(sample_task_spec)

    assert result.model_preferred_id == "A"
    assert mock_client.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-pro"


def test_generate_design_candidates_uses_compact_provider_schema(sample_task_spec):
    payload = {
        "ti": "Flat-ground walking",
        "c": [
            {
                "i": "A",
                "e": "biped",
                "nl": 2,
                "na": 0,
                "t": True,
                "tl": 0.4,
                "al": 0.0,
                "ll": 0.5,
                "ad": 0,
                "ld": 4,
                "sd": 1,
                "ac": "servo",
                "tq": 12.0,
                "tm": 8.0,
                "pl": 0.0,
                "sp": ["imu", "encoder"],
                "ra": "Conventional biped",
                "cf": 0.85,
            },
            {
                "i": "B",
                "e": "quadruped",
                "nl": 4,
                "na": 0,
                "t": True,
                "tl": 0.5,
                "al": 0.0,
                "ll": 0.35,
                "ad": 0,
                "ld": 3,
                "sd": 1,
                "ac": "servo",
                "tq": 10.0,
                "tm": 10.0,
                "pl": 1.0,
                "sp": ["imu"],
                "ra": "Stable quadruped",
                "cf": 0.8,
            },
            {
                "i": "C",
                "e": "biped",
                "nl": 2,
                "na": 0,
                "t": True,
                "tl": 0.3,
                "al": 0.0,
                "ll": 0.4,
                "ad": 0,
                "ld": 3,
                "sd": 0,
                "ac": "servo",
                "tq": 8.0,
                "tm": 4.0,
                "pl": 0.0,
                "sp": ["imu"],
                "ra": "Minimal walker",
                "cf": 0.75,
            },
        ],
        "mp": "A",
        "sr": "Candidate A is the best balance of complexity and capability.",
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(text=json.dumps(payload))

    with patch("packages.pipeline.design_generator._get_gemini_client", return_value=mock_client):
        result = generate_design_candidates(sample_task_spec)

    schema = mock_client.models.generate_content.call_args.kwargs["config"]["response_json_schema"]
    assert "collapse_report" not in json.dumps(schema)
    assert "task_fit_score" not in json.dumps(schema)
    assert set(schema["properties"].keys()) == {"ti", "c", "mp", "sr"}
    assert result.candidates[0].joint_damping > 0
    assert result.candidates[0].joint_stiffness > 0


def test_generate_design_candidates_falls_back_when_provider_raises_client_error(sample_task_spec):
    class FakeClientError(Exception):
        pass

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = FakeClientError(
        "400 INVALID_ARGUMENT too many states for serving"
    )

    with patch("packages.pipeline.design_generator._get_gemini_client", return_value=mock_client):
        result = generate_design_candidates(sample_task_spec)

    assert len(result.candidates) == 3
    assert "too many states" in result.selection_rationale.lower()


def test_generate_design_candidates_falls_back_to_template_candidates(sample_task_spec):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("gemini unavailable")

    with patch("packages.pipeline.design_generator._get_gemini_client", return_value=mock_client):
        result = generate_design_candidates(sample_task_spec)

    assert len(result.candidates) == 3
    assert {candidate.candidate_id for candidate in result.candidates} == {"A", "B", "C"}
    assert result.model_preferred_id in {"A", "B", "C"}
    assert "fallback" in result.selection_rationale.lower()


def test_build_render_payload_includes_mjcf(sample_biped_candidate):
    payload = build_render_payload(sample_biped_candidate)

    assert payload["candidate_id"] == "A"
    assert payload["view_modes"] == ["concept", "engineering", "joints", "components"]
    assert "<mujoco model=" in payload["mjcf"]
    assert payload["engineering_ready"] is True
    assert payload["render_glb"].startswith("data:model/gltf-binary;base64,")
    assert payload["ui_scene"]["stats"]["engineering_ready"] is True
    assert payload["ui_scene"]["stats"]["material_count"] >= 5
    assert payload["ui_scene"]["stats"]["task_geometry_profile"] == "general"


def test_build_task_capability_graph_for_rock_climbing():
    spec = TaskSpec(
        task_goal="climb a near-vertical rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend the wall while keeping the pack stable",
        search_queries=["rock climber carrying rope pack", "vertical climbing full body"],
    )

    graph = build_task_capability_graph(spec)

    assert graph.task_family == "climbing"
    assert "vertical_support_strategy" in graph.required_capabilities
    assert "surface_attachment_strategy" in graph.required_capabilities
    assert "payload_stability" in graph.required_capabilities
    assert "quadruped_without_attachment" in graph.disallowed_patterns


def test_score_candidate_task_fit_penalizes_generic_climbing_quadruped():
    spec = TaskSpec(
        task_goal="climb a near-vertical rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend the wall while keeping the pack stable",
        search_queries=["rock climber carrying rope pack", "vertical climbing full body"],
    )
    graph = build_task_capability_graph(spec)

    generic_quadruped = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="quadruped",
        num_legs=4,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.6,
        arm_length_m=0.0,
        leg_length_m=0.45,
        arm_dof=0,
        leg_dof=3,
        spine_dof=1,
        actuator_class="bldc",
        actuator_torque_nm=20.0,
        total_mass_kg=24.0,
        payload_capacity_kg=3.0,
        sensor_package=["imu", "camera", "encoder"],
        rationale="Generic advanced quadruped with no explicit climbing mechanism.",
        confidence=0.82,
    )

    fit = score_candidate_task_fit(generic_quadruped, spec, graph)

    assert fit.score < 0.5
    assert "missing_surface_attachment_strategy" in fit.missing_capabilities
    assert "generic_quadruped_without_climbing_mechanism" in fit.risk_flags


def test_generate_design_candidates_reranks_climbing_prompt_away_from_generic_quadruped():
    spec = TaskSpec(
        task_goal="climb a near-vertical rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend the wall while keeping the pack stable",
        search_queries=["rock climber carrying rope pack", "vertical climbing full body"],
    )

    payload = DesignCandidatesResponse(
        task_interpretation="Wall climbing with payload",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="quadruped",
                num_legs=4,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.6,
                arm_length_m=0.0,
                leg_length_m=0.45,
                arm_dof=0,
                leg_dof=3,
                spine_dof=1,
                actuator_class="bldc",
                actuator_torque_nm=20.0,
                total_mass_kg=24.0,
                payload_capacity_kg=3.0,
                sensor_package=["imu", "camera", "encoder"],
                rationale="Generic quadruped with strong legs.",
                confidence=0.9,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="hybrid",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.48,
                arm_length_m=0.58,
                leg_length_m=0.62,
                arm_dof=5,
                leg_dof=4,
                spine_dof=2,
                actuator_class="bldc",
                actuator_torque_nm=26.0,
                total_mass_kg=18.0,
                payload_capacity_kg=4.0,
                sensor_package=["imu", "camera", "force", "encoder"],
                rationale="Lean climber with dual grasping limbs and explicit climbing support strategy.",
                confidence=0.84,
            ),
            RobotDesignCandidate(
                candidate_id="C",
                embodiment_class="biped",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.52,
                arm_length_m=0.5,
                leg_length_m=0.65,
                arm_dof=4,
                leg_dof=4,
                spine_dof=1,
                actuator_class="servo",
                actuator_torque_nm=15.0,
                total_mass_kg=16.0,
                payload_capacity_kg=2.0,
                sensor_package=["imu", "camera", "encoder"],
                rationale="Humanoid-style climber with limited payload margin.",
                confidence=0.74,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="Candidate A is the safest by default.",
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(
        text=payload.model_dump_json()
    )

    with patch("packages.pipeline.design_generator._get_gemini_client", return_value=mock_client):
        result = generate_design_candidates(spec)

    assert result.model_preferred_id == "B"
    ranked = {candidate.candidate_id: candidate for candidate in result.candidates}
    assert "vertical_support_strategy" in ranked["B"].task_fit_evidence
    assert "surface_attachment_strategy" in ranked["B"].task_fit_evidence
    assert "generic_quadruped_without_climbing_mechanism" in ranked["A"].risk_flags


@pytest.mark.skipif(
    not (os.getenv("RUN_LIVE_MODEL_TESTS") == "1" and os.getenv("GEMINI_API_KEY")),
    reason="live Gemini test requires RUN_LIVE_MODEL_TESTS=1 and GEMINI_API_KEY",
)
def test_generate_design_candidates_live_gemini_climbing_task_conditioning():
    spec = TaskSpec(
        task_goal="climb a near-vertical rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend the wall while keeping the pack stable",
        search_queries=["rock climber carrying rope pack", "vertical climbing full body"],
    )

    result = generate_design_candidates(spec)

    assert len(result.candidates) == 3
    assert result.task_capability_graph is not None
    assert result.task_capability_graph.task_family == "climbing"
    preferred = next(
        candidate for candidate in result.candidates if candidate.candidate_id == result.model_preferred_id
    )
    assert preferred.task_fit_score is not None
    assert preferred.task_fit_score >= 0.55
    assert "payload_stability" in preferred.task_fit_evidence


def test_hardrails_reject_generic_climbing_quadruped():
    spec = TaskSpec(
        task_goal="climb a near-vertical rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend the wall while keeping the pack stable",
        search_queries=["rock climber carrying rope pack", "vertical climbing full body"],
    )
    graph = build_task_capability_graph(spec)
    candidate = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="quadruped",
        num_legs=4,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.6,
        arm_length_m=0.0,
        leg_length_m=0.45,
        arm_dof=0,
        leg_dof=3,
        spine_dof=1,
        actuator_class="bldc",
        actuator_torque_nm=20.0,
        total_mass_kg=24.0,
        payload_capacity_kg=3.0,
        sensor_package=["imu", "camera", "encoder"],
        rationale="Generic advanced quadruped with strong legs.",
        confidence=0.82,
    )

    result = evaluate_candidate_hardrails(candidate, spec, graph)

    assert result.rejected is True
    assert "missing_attachment_or_grasp_strategy_for_climbing" in result.rejection_reasons
    assert "generic_quadruped_without_climbing_mechanism" in result.risk_flags


def test_hardrails_reject_upright_crawling_humanoid():
    spec = TaskSpec(
        task_goal="crawl under a low pipe with minimal clearance",
        environment="indoor",
        locomotion_type="crawling",
        manipulation_required=False,
        payload_kg=0.0,
        success_criteria="traverse the pipe while staying below clearance limit",
        search_queries=["crawl under low pipe", "tight crawlspace movement"],
    )
    graph = build_task_capability_graph(spec)
    candidate = RobotDesignCandidate(
        candidate_id="B",
        embodiment_class="biped",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.62,
        arm_length_m=0.45,
        leg_length_m=0.72,
        arm_dof=4,
        leg_dof=4,
        spine_dof=2,
        actuator_class="servo",
        actuator_torque_nm=14.0,
        total_mass_kg=20.0,
        payload_capacity_kg=1.0,
        sensor_package=["imu", "camera", "encoder"],
        rationale="Humanoid crawler with upright torso and long limbs.",
        confidence=0.76,
    )

    result = evaluate_candidate_hardrails(candidate, spec, graph)

    assert result.rejected is True
    assert "upright_profile_exceeds_crawl_clearance" in result.rejection_reasons


def test_hardrails_reject_tall_thin_biped_for_slippery_terrain():
    spec = TaskSpec(
        task_goal="carry a heavy tool case down a slippery incline",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=4.0,
        success_criteria="descend the incline without slipping",
        search_queries=["carry heavy load down slippery slope", "controlled descent incline"],
    )
    graph = build_task_capability_graph(spec)
    candidate = RobotDesignCandidate(
        candidate_id="C",
        embodiment_class="biped",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.58,
        arm_length_m=0.5,
        leg_length_m=0.78,
        arm_dof=4,
        leg_dof=4,
        spine_dof=2,
        actuator_class="servo",
        actuator_torque_nm=16.0,
        total_mass_kg=19.0,
        payload_capacity_kg=4.0,
        sensor_package=["imu", "camera", "encoder"],
        rationale="Tall biped with narrow feet and no explicit traction strategy.",
        confidence=0.74,
    )

    result = evaluate_candidate_hardrails(candidate, spec, graph)

    assert result.rejected is True
    assert "no_traction_or_controlled_descent_strategy" in result.rejection_reasons


def test_generate_design_candidates_hardrails_prevent_rejected_slippery_candidate_from_winning():
    spec = TaskSpec(
        task_goal="carry a heavy tool case down a slippery incline",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=4.0,
        success_criteria="descend the incline without slipping",
        search_queries=["carry heavy load down slippery slope", "controlled descent incline"],
    )
    payload = DesignCandidatesResponse(
        task_interpretation="Slippery downhill transport",
        candidates=[
            RobotDesignCandidate(
                candidate_id="A",
                embodiment_class="biped",
                num_legs=2,
                num_arms=2,
                has_torso=True,
                torso_length_m=0.58,
                arm_length_m=0.5,
                leg_length_m=0.78,
                arm_dof=4,
                leg_dof=4,
                spine_dof=2,
                actuator_class="servo",
                actuator_torque_nm=16.0,
                total_mass_kg=19.0,
                payload_capacity_kg=4.0,
                sensor_package=["imu", "camera", "encoder"],
                rationale="Tall biped with narrow feet and no explicit traction strategy.",
                confidence=0.9,
            ),
            RobotDesignCandidate(
                candidate_id="B",
                embodiment_class="quadruped",
                num_legs=4,
                num_arms=0,
                has_torso=True,
                torso_length_m=0.46,
                arm_length_m=0.0,
                leg_length_m=0.42,
                arm_dof=0,
                leg_dof=3,
                spine_dof=1,
                actuator_class="bldc",
                actuator_torque_nm=24.0,
                total_mass_kg=22.0,
                payload_capacity_kg=5.0,
                sensor_package=["imu", "camera", "force", "encoder"],
                rationale="Low-slung quadruped with rubberized traction pads, wide stance, and controlled descent strategy.",
                confidence=0.81,
            ),
            RobotDesignCandidate(
                candidate_id="C",
                embodiment_class="hybrid",
                num_legs=4,
                num_arms=1,
                has_torso=True,
                torso_length_m=0.5,
                arm_length_m=0.34,
                leg_length_m=0.4,
                arm_dof=4,
                leg_dof=3,
                spine_dof=1,
                actuator_class="bldc",
                actuator_torque_nm=21.0,
                total_mass_kg=21.0,
                payload_capacity_kg=4.5,
                sensor_package=["imu", "camera", "encoder"],
                rationale="Hybrid carrier with stable stance but weaker descent control detail.",
                confidence=0.79,
            ),
        ],
        model_preferred_id="A",
        selection_rationale="Candidate A has the highest raw confidence.",
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(
        text=payload.model_dump_json()
    )

    with patch("packages.pipeline.design_generator._get_gemini_client", return_value=mock_client):
        result = generate_design_candidates(spec)

    assert result.model_preferred_id == "B"
    ranked = {candidate.candidate_id: candidate for candidate in result.candidates}
    assert ranked["A"].hardrail_passed is False
    assert "no_traction_or_controlled_descent_strategy" in ranked["A"].hardrail_rejection_reasons
    assert ranked["B"].hardrail_passed is True


def test_build_design_novelty_signature_uses_geometry_profile_and_render_stats():
    spec = TaskSpec(
        task_goal="climb a rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend a near-vertical wall with the pack retained",
        search_queries=["rock climbing wall side view", "human climber rope pack"],
    )
    candidate = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="hybrid",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.48,
        arm_length_m=0.68,
        leg_length_m=0.74,
        arm_dof=5,
        leg_dof=4,
        spine_dof=2,
        actuator_class="bldc",
        actuator_torque_nm=28.0,
        total_mass_kg=18.0,
        payload_capacity_kg=4.0,
        sensor_package=["imu", "encoder", "camera", "force"],
        rationale="Lean climbing hybrid with grippers and a back-mounted payload pack.",
        confidence=0.83,
    )

    render_payload = build_render_payload(candidate, spec)
    signature = build_design_novelty_signature(candidate, spec, render_payload)

    assert signature.geometry_profile == "climbing_payload"
    assert signature.topology_key.startswith("hybrid:")
    assert "payload_pack" in signature.accessory_profile
    assert "climbing_gripper" in signature.accessory_profile
    assert signature.material_count >= 5
    assert "cylinder" in signature.primitive_keys


def test_apply_diversity_controls_penalizes_same_batch_duplicates():
    spec = TaskSpec(
        task_goal="inspect a vessel interior while carrying a sensor pack",
        environment="indoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=2.0,
        success_criteria="reach into the vessel and keep the sensor pack stable",
        search_queries=["borescope inspection manipulator"],
    )
    response = DesignCandidatesResponse(
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

    render_payloads = {
        candidate.candidate_id: build_render_payload(candidate, spec)
        for candidate in response.candidates
    }
    reranked = apply_diversity_controls(response, spec, render_payloads, prior_design_contexts=[])
    scored = {candidate.candidate_id: candidate for candidate in reranked.candidates}

    assert scored["A"].diversity_penalty > 0
    assert scored["B"].diversity_penalty > 0
    assert reranked.collapse_report is not None
    assert reranked.collapse_report.duplicate_pairs
    assert reranked.model_preferred_id == "C"
    assert "diversity reranking" in reranked.selection_rationale.lower()


def test_apply_diversity_controls_penalizes_history_collapse_for_different_prompt():
    prior_spec = TaskSpec(
        task_goal="climb a rock wall with a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend a near-vertical wall",
        search_queries=["rock climbing wall side view"],
    )
    current_spec = TaskSpec(
        task_goal="descend a slippery slope while carrying a rescue kit",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="descend without slipping and keep the kit stable",
        search_queries=["downhill rescue carry slippery slope"],
    )

    repeated_candidate = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="hybrid",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.48,
        arm_length_m=0.68,
        leg_length_m=0.74,
        arm_dof=5,
        leg_dof=4,
        spine_dof=2,
        actuator_class="bldc",
        actuator_torque_nm=28.0,
        total_mass_kg=18.0,
        payload_capacity_kg=4.0,
        sensor_package=["imu", "encoder", "camera", "force"],
        rationale="Lean hybrid with dual manipulators and generic payload support.",
        confidence=0.84,
        task_fit_score=0.88,
    )
    alternate_candidate = RobotDesignCandidate(
        candidate_id="B",
        embodiment_class="quadruped",
        num_legs=4,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.54,
        arm_length_m=0.0,
        leg_length_m=0.44,
        arm_dof=0,
        leg_dof=4,
        spine_dof=1,
        actuator_class="bldc",
        actuator_torque_nm=22.0,
        total_mass_kg=19.0,
        payload_capacity_kg=4.0,
        sensor_package=["imu", "encoder", "camera", "force"],
        rationale="Low-slung rescue quadruped with traction spikes and a centered rescue payload pack.",
        confidence=0.81,
        task_fit_score=0.84,
    )
    third_candidate = RobotDesignCandidate(
        candidate_id="C",
        embodiment_class="biped",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.62,
        arm_length_m=0.61,
        leg_length_m=0.82,
        arm_dof=5,
        leg_dof=5,
        spine_dof=2,
        actuator_class="servo",
        actuator_torque_nm=20.0,
        total_mass_kg=22.0,
        payload_capacity_kg=3.0,
        sensor_package=["imu", "encoder", "camera"],
        rationale="Upright rescue biped with long reach but less stable downhill behavior.",
        confidence=0.72,
        task_fit_score=0.63,
    )
    response = DesignCandidatesResponse(
        task_interpretation="slippery rescue transport",
        candidates=[repeated_candidate, alternate_candidate, third_candidate],
        model_preferred_id="A",
        selection_rationale="Candidate A remains the model favorite.",
    )

    prior_render = build_render_payload(repeated_candidate, prior_spec)
    current_render_payloads = {
        "A": build_render_payload(repeated_candidate, current_spec),
        "B": build_render_payload(alternate_candidate, current_spec),
        "C": build_render_payload(third_candidate, current_spec),
    }
    prior_contexts = [
        {
            "candidate_id": "A",
            "design_json": repeated_candidate.model_dump(),
            "render_json": prior_render,
            "er16_plan_json": prior_spec.model_dump_json(),
        }
    ]

    reranked = apply_diversity_controls(
        response,
        current_spec,
        current_render_payloads,
        prior_design_contexts=prior_contexts,
    )
    scored = {candidate.candidate_id: candidate for candidate in reranked.candidates}
    fingerprint = build_prompt_conditioning_fingerprint(current_spec)

    assert fingerprint.task_family == "slippery_terrain"
    assert scored["A"].diversity_penalty > scored["B"].diversity_penalty
    assert reranked.collapse_report is not None
    assert reranked.collapse_report.history_matches
    assert reranked.model_preferred_id == "B"
    assert "history-aware diversity reranking" in reranked.selection_rationale.lower()


def test_build_design_validation_report_detects_render_and_procurement_failures(tmp_path):
    spec = TaskSpec(
        task_goal="inspect a vessel interior while carrying a sensor pack",
        environment="indoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=2.0,
        success_criteria="reach into the vessel and keep the sensor pack stable",
        search_queries=["borescope inspection manipulator"],
    )
    candidate = RobotDesignCandidate(
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
        hardrail_passed=True,
    )
    bom = generate_bom_for_candidate(candidate).model_copy(
        update={"procurement_confidence": 0.31, "missing_items": ["harmonic drive", "bearing stack"]}
    )
    telemetry = build_candidate_telemetry(candidate, bom, spec)
    render_payload = build_render_payload(candidate, spec)
    render_payload["ui_scene"]["stats"]["material_count"] = 1
    render_payload["ui_scene"]["stats"]["mesh_node_count"] = 4
    report = build_design_validation_report(
        design_id="design-1",
        revision_id="rev-1",
        task_spec=spec,
        candidate=candidate,
        render_payload=render_payload,
        bom=bom,
        telemetry=telemetry,
        artifact_paths={
            "mjcf": "artifacts/design-1/robot.mjcf",
            "render_glb": "artifacts/design-1/render.glb",
        },
        output_dir=tmp_path,
    )

    assert report.is_valid is False
    assert "render" in report.failure_categories
    assert "procurement" in report.failure_categories
    assert report.output_path is not None
    assert Path(report.output_path).exists()


def test_build_design_validation_report_passes_for_rich_compiled_candidate(tmp_path):
    spec = TaskSpec(
        task_goal="climb a rock wall while carrying a rope pack",
        environment="outdoor",
        locomotion_type="walking",
        manipulation_required=True,
        payload_kg=3.0,
        success_criteria="ascend a near-vertical wall with the pack retained",
        search_queries=["rock climbing wall side view", "human climber rope pack"],
    )
    candidate = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="hybrid",
        num_legs=2,
        num_arms=2,
        has_torso=True,
        torso_length_m=0.48,
        arm_length_m=0.68,
        leg_length_m=0.74,
        arm_dof=5,
        leg_dof=4,
        spine_dof=2,
        actuator_class="bldc",
        actuator_torque_nm=28.0,
        total_mass_kg=18.0,
        payload_capacity_kg=4.0,
        sensor_package=["imu", "encoder", "camera", "force"],
        rationale="Lean climbing hybrid with grippers and a back-mounted payload pack.",
        confidence=0.83,
        task_fit_score=0.9,
        hardrail_passed=True,
    )
    bom = generate_bom_for_candidate(candidate)
    telemetry = build_candidate_telemetry(candidate, bom, spec)
    render_payload = build_render_payload(candidate, spec)
    report = build_design_validation_report(
        design_id="design-2",
        revision_id="rev-2",
        task_spec=spec,
        candidate=candidate,
        render_payload=render_payload,
        bom=bom,
        telemetry=telemetry,
        artifact_paths={
            "mjcf": "artifacts/design-2/robot.mjcf",
            "render_glb": "artifacts/design-2/render.glb",
            "ui_scene": "artifacts/design-2/ui_scene.json",
        },
        output_dir=tmp_path,
    )

    assert report.is_valid is True
    assert report.failure_categories == []
    assert report.render_checks["material_count"] >= 5
    assert report.render_checks["mesh_node_count"] >= 10


# --- BOM Generator Tests ---

def test_design_to_componentized_morphology(sample_biped_candidate):
    morphology = design_to_componentized_morphology(sample_biped_candidate)
    assert morphology.design.candidate_id == "A"
    assert len(morphology.structural_components) > 0
    assert len(morphology.actuators) == sample_biped_candidate.num_legs * sample_biped_candidate.leg_dof


def test_componentized_to_bom(sample_biped_candidate):
    morphology = design_to_componentized_morphology(sample_biped_candidate)
    bom = componentized_to_bom(morphology)
    assert bom.candidate_id == "A"
    assert len(bom.actuator_items) > 0
    assert bom.procurement_confidence >= 0.0
    assert bom.procurement_confidence <= 1.0


def test_generate_bom_for_candidate(sample_quadruped_candidate):
    bom = generate_bom_for_candidate(sample_quadruped_candidate)
    assert bom.candidate_id == "B"
    # Quadruped with 4 legs × 3 DOF = 12 actuators total (may be consolidated)
    total_actuator_qty = sum(item.quantity for item in bom.actuator_items)
    assert total_actuator_qty == 12


def test_bom_includes_electronics(sample_biped_candidate):
    bom = generate_bom_for_candidate(sample_biped_candidate)
    electronics_names = [item.part_name for item in bom.electronics_items]
    assert "Raspberry Pi 5" in electronics_names


# --- Fallback Chooser Tests ---

def test_kinematic_feasibility_biped(sample_biped_candidate):
    score = kinematic_feasibility_score(sample_biped_candidate)
    assert 0.0 <= score <= 1.0
    assert score > 0.5  # Well-formed biped should score reasonably


def test_kinematic_feasibility_invalid_biped():
    invalid = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="biped",
        num_legs=4,  # Wrong for biped
        num_arms=0,
        has_torso=True,
        torso_length_m=0.4,
        arm_length_m=0.0,
        leg_length_m=0.5,
        arm_dof=0,
        leg_dof=4,
        spine_dof=1,
        actuator_class="servo",
        actuator_torque_nm=12.0,
        total_mass_kg=8.0,
        payload_capacity_kg=0.0,
        sensor_package=["imu"],
        rationale="Invalid",
        confidence=0.5,
    )
    score = kinematic_feasibility_score(invalid)
    assert score < 0.5  # Penalized for wrong leg count


def test_static_stability_quadruped_better_than_biped(
    sample_biped_candidate, sample_quadruped_candidate
):
    biped_score = static_stability_score(sample_biped_candidate)
    quad_score = static_stability_score(sample_quadruped_candidate)
    assert quad_score > biped_score  # 4 legs more stable than 2


def test_rank_candidates_fallback(
    sample_biped_candidate, sample_quadruped_candidate, sample_minimal_candidate
):
    candidates = [sample_biped_candidate, sample_quadruped_candidate, sample_minimal_candidate]
    rankings = rank_candidates_fallback(candidates)

    assert len(rankings) == 3
    assert all(isinstance(r, FallbackRanking) for r in rankings)
    # Rankings should be sorted by total_score descending
    assert rankings[0].total_score >= rankings[1].total_score >= rankings[2].total_score


def test_select_best_candidate_fallback(
    sample_biped_candidate, sample_quadruped_candidate, sample_minimal_candidate
):
    candidates = [sample_biped_candidate, sample_quadruped_candidate, sample_minimal_candidate]
    best, ranking = select_best_candidate_fallback(candidates)

    assert best.candidate_id == ranking.candidate_id
    assert ranking.total_score > 0


# --- Integration Tests ---

def test_full_pipeline_no_gemini(
    sample_biped_candidate, sample_quadruped_candidate, sample_minimal_candidate
):
    """Test the full pipeline without calling Gemini."""
    candidates = [sample_biped_candidate, sample_quadruped_candidate, sample_minimal_candidate]

    # Generate BOM for all candidates
    boms = [generate_bom_for_candidate(c) for c in candidates]
    assert all(bom.procurement_confidence > 0 for bom in boms)

    # Rank candidates
    rankings = rank_candidates_fallback(candidates)
    best, _ = select_best_candidate_fallback(candidates)

    # Best should be one of the candidates
    assert best.candidate_id in {"A", "B", "C"}

    # Get BOM for best
    best_bom = next(b for b in boms if b.candidate_id == best.candidate_id)
    assert best_bom.total_cost_usd is None or best_bom.total_cost_usd > 0
