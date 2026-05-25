"""Function contract for app-compatible research agent loops."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from packages.pipeline.schemas import TaskIntent


@dataclass(frozen=True)
class AgentLoopConfig:
    """Runtime options the backend can pass to any registered agent loop."""

    population: int | None = None
    max_attempts: int = 2
    confirmed_spec: TaskIntent | dict[str, Any] | None = None
    normalizer_agent: Any | None = None
    rule_builder_agent: Any | None = None
    evaluator_agent: Any | None = None
    require_human_confirmation: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentLoopResult:
    """Standard result consumed by the backend and notebooks."""

    state: dict[str, Any]
    hitl: dict[str, Any]


@runtime_checkable
class AgentLoopRunner(Protocol):
    """Callable signature every app-compatible LangGraph loop must expose."""

    def __call__(
        self,
        prompt: str,
        initial_state: dict[str, Any] | None = None,
        *,
        config: AgentLoopConfig | None = None,
    ) -> AgentLoopResult: ...
