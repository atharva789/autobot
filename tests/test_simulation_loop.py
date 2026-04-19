"""
TDD tests for Phase 7: Agentic simulation loop.

Tests for the design -> compile -> validate -> simulate -> rank pipeline.
"""

import pytest
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    ActuatorSlot,
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


class TestMuJoCoScreening:
    """Tests for MuJoCo screening service."""

    def test_screening_compiles_mjcf(self):
        """Screening compiles to MJCF first."""
        from packages.pipeline.simulation.mujoco_screening import screen_design

        ir = RobotDesignIR(
            name="screen_robot",
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
        result = screen_design(ir)

        assert result.mjcf_compiled is True

    def test_screening_checks_stability(self):
        """Screening includes static stability check."""
        from packages.pipeline.simulation.mujoco_screening import screen_design

        ir = RobotDesignIR(
            name="stable_robot",
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
        result = screen_design(ir)

        assert hasattr(result, "stability_score")

    def test_screening_returns_score(self):
        """Screening returns overall score."""
        from packages.pipeline.simulation.mujoco_screening import screen_design

        ir = RobotDesignIR(
            name="scored_robot",
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
        result = screen_design(ir)

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

        ir = RobotDesignIR(
            name="orchestrated_robot",
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

        orchestrator = SimulationOrchestrator()
        result = orchestrator.process([ir])

        assert len(result.candidates) == 1
        assert result.candidates[0].screening_result is not None

    def test_orchestrate_multiple_candidates(self):
        """Orchestrator processes and ranks multiple candidates."""
        from packages.pipeline.simulation.orchestrator import SimulationOrchestrator

        designs = [
            RobotDesignIR(
                name=f"robot_{i}",
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
            for i in range(3)
        ]

        orchestrator = SimulationOrchestrator()
        result = orchestrator.process(designs)

        assert len(result.candidates) == 3
        assert result.top_candidate is not None

    def test_orchestrate_returns_artifacts(self):
        """Orchestrator returns compiled artifacts."""
        from packages.pipeline.simulation.orchestrator import SimulationOrchestrator

        ir = RobotDesignIR(
            name="artifact_robot",
            links=[LinkIR(name="base")],
            joints=[],
        )

        orchestrator = SimulationOrchestrator()
        result = orchestrator.process([ir])

        assert result.artifacts is not None
        assert "mjcf" in result.artifacts
