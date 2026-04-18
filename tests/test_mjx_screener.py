"""Tests for MuJoCo MJX lightweight screening."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import numpy as np

from packages.pipeline.schemas import RobotDesignCandidate


@pytest.fixture
def sample_biped() -> RobotDesignCandidate:
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
def sample_quadruped() -> RobotDesignCandidate:
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


# --- MJCF Generation Tests ---

def test_generate_mjcf_from_candidate(sample_biped):
    """Test MJCF XML generation from design candidate."""
    from packages.pipeline.mjx_screener import generate_mjcf_from_candidate

    mjcf = generate_mjcf_from_candidate(sample_biped)

    assert "<mujoco" in mjcf
    assert 'model="candidate_A"' in mjcf
    assert "<body" in mjcf
    assert "<joint" in mjcf
    assert "<actuator" in mjcf


def test_mjcf_has_correct_body_count(sample_biped):
    """Verify MJCF has correct number of leg bodies."""
    from packages.pipeline.mjx_screener import generate_mjcf_from_candidate

    mjcf = generate_mjcf_from_candidate(sample_biped)

    # Biped with 2 legs, 4 DOF each = 8 leg segments + torso
    assert mjcf.count("<body") >= sample_biped.num_legs


def test_mjcf_has_correct_actuator_count(sample_biped):
    """Verify MJCF has actuators matching design DOF."""
    from packages.pipeline.mjx_screener import generate_mjcf_from_candidate

    mjcf = generate_mjcf_from_candidate(sample_biped)

    # 2 legs × 4 DOF + 1 spine = 9 actuators
    expected_actuators = (
        sample_biped.num_legs * sample_biped.leg_dof + sample_biped.spine_dof
    )
    assert mjcf.count("<motor") == expected_actuators


def test_mjcf_quadruped_structure(sample_quadruped):
    """Verify quadruped MJCF structure."""
    from packages.pipeline.mjx_screener import generate_mjcf_from_candidate

    mjcf = generate_mjcf_from_candidate(sample_quadruped)

    assert "<mujoco" in mjcf
    assert 'model="candidate_B"' in mjcf
    # 4 legs × 3 DOF + 2 spine = 14 actuators
    expected_actuators = (
        sample_quadruped.num_legs * sample_quadruped.leg_dof + sample_quadruped.spine_dof
    )
    assert mjcf.count("<motor") == expected_actuators


# --- Screening Score Tests ---

def test_compute_stability_score():
    """Test stability score computation from simulation data."""
    from packages.pipeline.mjx_screener import compute_stability_score

    # Simulated COM trajectory - stable robot has low variance
    com_trajectory = np.array([
        [0.0, 0.0, 0.5],
        [0.01, 0.0, 0.5],
        [0.02, 0.0, 0.5],
        [0.03, 0.0, 0.5],
    ])

    score = compute_stability_score(com_trajectory)

    assert 0.0 <= score <= 1.0
    assert score > 0.8  # Stable trajectory should score high


def test_compute_stability_score_unstable():
    """Test stability score for unstable trajectory."""
    from packages.pipeline.mjx_screener import compute_stability_score

    # Unstable - large vertical oscillations
    com_trajectory = np.array([
        [0.0, 0.0, 0.5],
        [0.0, 0.0, 0.1],
        [0.0, 0.0, 0.8],
        [0.0, 0.0, 0.2],
    ])

    score = compute_stability_score(com_trajectory)

    assert 0.0 <= score <= 1.0
    assert score < 0.5  # Unstable trajectory should score low


def test_compute_motion_tracking_score():
    """Test motion tracking score against reference trajectory."""
    from packages.pipeline.mjx_screener import compute_motion_tracking_score

    reference = np.array([
        [0.0, 0.0, 0.5],
        [0.1, 0.0, 0.5],
        [0.2, 0.0, 0.5],
    ])
    simulated = np.array([
        [0.0, 0.0, 0.5],
        [0.11, 0.0, 0.5],
        [0.21, 0.0, 0.5],
    ])

    score = compute_motion_tracking_score(simulated, reference)

    assert 0.0 <= score <= 1.0
    assert score > 0.9  # Close tracking should score high


def test_compute_motion_tracking_score_poor():
    """Test motion tracking score for poor tracking."""
    from packages.pipeline.mjx_screener import compute_motion_tracking_score

    reference = np.array([
        [0.0, 0.0, 0.5],
        [1.0, 0.0, 0.5],
        [2.0, 0.0, 0.5],
    ])
    simulated = np.array([
        [0.0, 0.0, 0.5],
        [0.1, 0.0, 0.5],
        [0.2, 0.0, 0.5],
    ])

    score = compute_motion_tracking_score(simulated, reference)

    assert 0.0 <= score <= 1.0
    assert score < 0.5  # Poor tracking should score low


# --- MJX Screening Result Tests ---

def test_screening_result_schema():
    """Test MJXScreeningResult schema."""
    from packages.pipeline.mjx_screener import MJXScreeningResult

    result = MJXScreeningResult(
        candidate_id="A",
        stability_score=0.85,
        tracking_score=0.75,
        energy_efficiency=0.70,
        combined_score=0.77,
        simulation_steps=1000,
        fell_over=False,
        error_message=None,
    )

    assert result.candidate_id == "A"
    assert result.combined_score == 0.77
    assert result.fell_over is False


def test_screening_result_with_failure():
    """Test screening result when robot falls."""
    from packages.pipeline.mjx_screener import MJXScreeningResult

    result = MJXScreeningResult(
        candidate_id="B",
        stability_score=0.0,
        tracking_score=0.0,
        energy_efficiency=0.0,
        combined_score=0.0,
        simulation_steps=150,
        fell_over=True,
        error_message="Robot fell at step 150",
    )

    assert result.fell_over is True
    assert result.combined_score == 0.0
    assert "fell" in result.error_message.lower()


# --- Integration Tests (mocked MJX) ---

def test_screen_candidate_mocked(sample_biped):
    """Test full screening pipeline with mocked MJX."""
    from packages.pipeline.mjx_screener import screen_candidate, MJXScreeningResult

    with patch("packages.pipeline.mjx_screener._run_mjx_simulation") as mock_sim:
        mock_sim.return_value = {
            "com_trajectory": np.array([[0.0, 0.0, 0.5]] * 100),
            "joint_positions": np.zeros((100, 9)),
            "energy_used": 50.0,
            "steps": 1000,
            "fell": False,
        }

        result = screen_candidate(sample_biped, reference_trajectory=None)

        assert isinstance(result, MJXScreeningResult)
        assert result.candidate_id == "A"
        assert result.stability_score > 0
        assert result.fell_over is False


def test_screen_candidate_with_reference(sample_biped):
    """Test screening with reference motion trajectory."""
    from packages.pipeline.mjx_screener import screen_candidate

    reference = np.array([[i * 0.01, 0.0, 0.5] for i in range(100)])

    with patch("packages.pipeline.mjx_screener._run_mjx_simulation") as mock_sim:
        mock_sim.return_value = {
            "com_trajectory": np.array([[i * 0.01, 0.0, 0.5] for i in range(100)]),
            "joint_positions": np.zeros((100, 9)),
            "energy_used": 50.0,
            "steps": 1000,
            "fell": False,
        }

        result = screen_candidate(sample_biped, reference_trajectory=reference)

        assert result.tracking_score > 0.9


def test_screen_multiple_candidates(sample_biped, sample_quadruped):
    """Test screening multiple candidates and ranking."""
    from packages.pipeline.mjx_screener import screen_candidates, MJXScreeningResult

    candidates = [sample_biped, sample_quadruped]

    with patch("packages.pipeline.mjx_screener._run_mjx_simulation") as mock_sim:
        mock_sim.side_effect = [
            {
                "com_trajectory": np.array([[0.0, 0.0, 0.5]] * 100),
                "joint_positions": np.zeros((100, 9)),
                "energy_used": 50.0,
                "steps": 1000,
                "fell": False,
            },
            {
                "com_trajectory": np.array([[0.0, 0.0, 0.4]] * 100),
                "joint_positions": np.zeros((100, 14)),
                "energy_used": 80.0,
                "steps": 1000,
                "fell": False,
            },
        ]

        results = screen_candidates(candidates, reference_trajectory=None)

        assert len(results) == 2
        assert all(isinstance(r, MJXScreeningResult) for r in results)
        # Results should be sorted by combined_score descending
        assert results[0].combined_score >= results[1].combined_score


def test_screen_candidate_handles_failure(sample_biped):
    """Test screening gracefully handles simulation failure."""
    from packages.pipeline.mjx_screener import screen_candidate

    with patch("packages.pipeline.mjx_screener._run_mjx_simulation") as mock_sim:
        mock_sim.return_value = {
            "com_trajectory": np.array([[0.0, 0.0, 0.1]] * 50),
            "joint_positions": np.zeros((50, 9)),
            "energy_used": 10.0,
            "steps": 50,
            "fell": True,
        }

        result = screen_candidate(sample_biped, reference_trajectory=None)

        assert result.fell_over is True
        assert result.combined_score == 0.0
