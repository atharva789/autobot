"""Tests for the task-conditioned robot design pipeline."""
from __future__ import annotations

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
    generate_design_candidates,
    candidate_to_morphology_params,
    _validate_candidates,
)
from packages.pipeline.bom_generator import (
    design_to_componentized_morphology,
    componentized_to_bom,
    generate_bom_for_candidate,
)
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
