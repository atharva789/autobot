"""
TDD tests for Phase 7: Agentic simulation loop.

Tests for the design -> compile -> validate -> simulate -> rank pipeline.
"""

import pytest
from conftest import make_physical_link
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    JointLimits,
    ActuatorSlot,
    Vector3,
)


class TestDesignCandidate:
    """Tests for design candidate structure."""

    def test_candidate_has_id(self):
        """Each candidate has a unique ID."""
        from packages.pipeline.simulation.candidate import DesignCandidate

        ir = RobotDesignIR(name="robot1", links=[], joints=[])
        candidate = DesignCandidate(ir=ir)

        assert candidate.id is not None
        assert len(candidate.id) > 0

    def test_candidate_wraps_ir(self):
        """Candidate wraps a RobotDesignIR."""
        from packages.pipeline.simulation.candidate import DesignCandidate

        ir = RobotDesignIR(
            name="test_robot",
            links=[LinkIR(name="base")],
            joints=[],
        )
        candidate = DesignCandidate(ir=ir)

        assert candidate.ir.name == "test_robot"
        assert len(candidate.ir.links) == 1


class TestValidator:
    """Tests for design validation."""

    def test_validate_empty_robot(self):
        """Empty robot is valid but flagged."""
        from packages.pipeline.simulation.validator import validate_design

        ir = RobotDesignIR(name="empty", links=[], joints=[])
        result = validate_design(ir)

        assert result.is_valid is True
        assert len(result.warnings) > 0

    def test_validate_missing_parent_link(self):
        """Invalid if joint references missing link."""
        from packages.pipeline.simulation.validator import validate_design

        ir = RobotDesignIR(
            name="bad_robot",
            links=[LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="missing_base",
                    child_link="arm",
                )
            ],
        )
        result = validate_design(ir)

        assert result.is_valid is False
        assert any("missing_base" in e for e in result.errors)

    def test_validate_good_robot(self):
        """Valid robot passes validation."""
        from packages.pipeline.simulation.validator import validate_design

        ir = RobotDesignIR(
            name="good_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                )
            ],
        )
        result = validate_design(ir)

        assert result.is_valid is True
        assert len(result.errors) == 0


def _physical_ir(name: str = "test_robot") -> RobotDesignIR:
    """Build a minimal physically valid IR for MuJoCo screening tests."""
    return RobotDesignIR(
        name=name,
        links=[make_physical_link("base"), make_physical_link("arm")],
        joints=[
            JointIR(
                name="j1",
                joint_type=JointType.REVOLUTE,
                parent_link="base",
                child_link="arm",
                axis=Vector3(x=0.0, y=1.0, z=0.0),
                limits=JointLimits(lower=-1.047, upper=1.047, effort=1.0),
                actuator=ActuatorSlot(actuator_type="position", max_torque=1.0),
            )
        ],
    )


class TestMuJoCoScreening:
    """Tests for MuJoCo screening service."""

    def test_screening_compiles_mjcf(self):
        """Screening compiles to MJCF first."""
        from packages.pipeline.simulation.mujoco_screening import screen_design

        result = screen_design(_physical_ir("screen_robot"))
        assert result.mjcf_compiled is True

    def test_screening_checks_stability(self):
        """Screening includes static stability check."""
        from packages.pipeline.simulation.mujoco_screening import screen_design

        result = screen_design(_physical_ir("stable_robot"))
        assert hasattr(result, "stability_score")

    def test_screening_returns_score(self):
        """Screening returns overall score."""
        from packages.pipeline.simulation.mujoco_screening import screen_design

        result = screen_design(_physical_ir("scored_robot"))
        assert 0.0 <= result.overall_score <= 1.0


class TestCandidateRanking:
    """Tests for ranking multiple candidates."""

    def test_rank_candidates_by_score(self):
        """Candidates are ranked by overall score."""
        from packages.pipeline.simulation.ranking import rank_candidates
        from packages.pipeline.simulation.candidate import DesignCandidate
        from packages.pipeline.simulation.mujoco_screening import ScreeningResult

        candidates = [
            DesignCandidate(
                ir=RobotDesignIR(name="low", links=[], joints=[]),
                screening_result=ScreeningResult(overall_score=0.3),
            ),
            DesignCandidate(
                ir=RobotDesignIR(name="high", links=[], joints=[]),
                screening_result=ScreeningResult(overall_score=0.9),
            ),
            DesignCandidate(
                ir=RobotDesignIR(name="mid", links=[], joints=[]),
                screening_result=ScreeningResult(overall_score=0.6),
            ),
        ]

        ranked = rank_candidates(candidates)

        assert ranked[0].ir.name == "high"
        assert ranked[1].ir.name == "mid"
        assert ranked[2].ir.name == "low"


class TestSimulationOrchestrator:
    """Tests for full pipeline orchestration."""

    def test_orchestrate_single_candidate(self):
        """Orchestrator processes single candidate."""
        from packages.pipeline.simulation.orchestrator import SimulationOrchestrator

        orchestrator = SimulationOrchestrator()
        result = orchestrator.process([_physical_ir("orchestrated_robot")])

        assert len(result.candidates) == 1
        assert result.candidates[0].screening_result is not None

    def test_orchestrate_multiple_candidates(self):
        """Orchestrator processes and ranks multiple candidates."""
        from packages.pipeline.simulation.orchestrator import SimulationOrchestrator

        designs = [_physical_ir(f"robot_{i}") for i in range(3)]

        orchestrator = SimulationOrchestrator()
        result = orchestrator.process(designs)

        assert len(result.candidates) == 3
        assert result.top_candidate is not None

    def test_orchestrate_returns_artifacts(self):
        """Orchestrator returns compiled artifacts."""
        from packages.pipeline.simulation.orchestrator import SimulationOrchestrator

        orchestrator = SimulationOrchestrator()
        result = orchestrator.process([_physical_ir("artifact_robot")])

        assert result.artifacts is not None
        assert "mjcf" in result.artifacts
