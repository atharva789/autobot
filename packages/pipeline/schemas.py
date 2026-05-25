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

from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class TaskIntent:
    """Rich, structured representation of a user's robot-design intent.

    Produced by the query-normalizer agent. All collection fields use tuples
    so the dataclass remains hashable and immutable end-to-end.
    """

    task_goal: str
    success_criteria: tuple[str, ...] = ()
    environment: str | None = None
    terrain: tuple[str, ...] = ()
    obstacles: tuple[str, ...] = ()
    contact_requirements: tuple[str, ...] = ()
    payload_requirements: tuple[str, ...] = ()
    manipulation_requirements: tuple[str, ...] = ()
    spatial_constraints: tuple[str, ...] = ()
    stability_requirements: tuple[str, ...] = ()
    sensing_requirements: tuple[str, ...] = ()
    hard_constraints: tuple[str, ...] = ()
    failure_modes_to_avoid: tuple[str, ...] = ()


class RobotDesignCandidate(BaseModel):
    """Flat parameter bundle consumed by the engineering renderer.

    The agent loop populates this from a ``GrammarGraph`` derivation.
    """

    candidate_id: int

    structural_rules: dict[str, list[str]]
    robo_graph: dict[str, list[str]]
    task_prompt: TaskIntent

    friction: float = Field(ge=0.1, le=2.0, default=0.8)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


__all__ = ["TaskIntent", "RobotDesignCandidate"]
