"""Render-facing schema kept alive after the grammar-graph migration.

The hard-coded task-categorization layer (task specs, capability graphs,
embodiment taxonomies, climbing / indoor / outdoor strategies, Q-vector
generation, BOM, telemetry, validation reports) moved to
:mod:`packages.pipeline.grammar_graph`. What remains here is the flat
parameter bundle the existing engineering renderer consumes. The agent
loop is responsible for projecting a ``GrammarGraph`` onto a
``RobotDesignCandidate`` before invoking the renderer; ``embodiment_class``
is a free-form summary label the agent loop derives from the derivation
tree, not a gatekept enum.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RobotDesignCandidate(BaseModel):
    """Flat parameter bundle consumed by the engineering renderer.

    The agent loop populates this from a ``GrammarGraph`` derivation.
    """

    candidate_id: Literal["A", "B", "C"]
    embodiment_class: str
    num_legs: int = Field(ge=0, le=8)
    num_arms: int = Field(ge=0, le=4)
    has_torso: bool
    torso_length_m: float = Field(ge=0.05, le=2.0)
    arm_length_m: float = Field(ge=0.0, le=1.5)
    leg_length_m: float = Field(ge=0.0, le=1.5)
    arm_dof: int = Field(ge=0, le=7)
    leg_dof: int = Field(ge=0, le=6)
    spine_dof: int = Field(ge=0, le=4)
    actuator_class: Literal["servo", "bldc", "stepper", "hydraulic"]
    actuator_torque_nm: float = Field(ge=0.1, le=500.0)
    total_mass_kg: float = Field(ge=0.1, le=500.0)
    payload_capacity_kg: float = Field(ge=0.0, le=200.0)
    sensor_package: list[Literal["imu", "camera", "lidar", "force", "encoder"]]
    joint_damping: float = Field(ge=0.01, le=10.0, default=0.5)
    joint_stiffness: float = Field(ge=1.0, le=1000.0, default=100.0)
    friction: float = Field(ge=0.1, le=2.0, default=0.8)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


__all__ = ["RobotDesignCandidate"]
