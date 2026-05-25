"""Core protocols for generation strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from packages.research.prompts.registry import PromptRegistry

from packages.pipeline.ir.design_ir import RobotDesignIR


@dataclass(frozen=True)
class StrategyConfig:
    """Immutable configuration envelope for a strategy run."""

    seed: int
    model_id: str
    max_candidates: int = 6
    prompt_registry: PromptRegistry | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IRMaterializer(Protocol):
    """Bridges strategy-specific output to canonical RobotDesignIR.

    Grammar strategies produce structural_rules (dict[str, list[str]]),
    not RobotDesignIR. Each strategy provides its own materializer.
    """

    def materialize(
        self,
        raw_output: dict[str, Any],
        prompt: str,
        config: StrategyConfig,
    ) -> list[RobotDesignIR]: ...


@runtime_checkable
class GenerationStrategy(Protocol):
    """Pluggable robot generation strategy.

    The agent loop lives INSIDE the strategy. The experimentation
    layer calls generate() and receives finished designs.
    """

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def generate(
        self,
        prompt: str,
        config: StrategyConfig,
    ) -> list[RobotDesignIR]: ...


@dataclass(frozen=True)
class LoopEvent:
    """Optional callback event for strategies that expose loop internals."""

    iteration: int
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)


LoopCallback = Any  # Callable[[LoopEvent], None] | None
