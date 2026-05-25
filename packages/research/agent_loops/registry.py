"""Runtime registry for app-compatible research agent loops."""

from __future__ import annotations

from typing import Any

from packages.pipeline.observability import get_langsmith_trace_id, langsmith_observation
from packages.research.agent_loops.protocol import (
    AgentLoopConfig,
    AgentLoopResult,
    AgentLoopRunner,
)

_LOOPS: dict[str, AgentLoopRunner] = {}
_BUILTINS_LOADED = False


def _load_builtins() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    from packages.research.agent_loops.grammar_loop import run_grammar_agent_loop

    _LOOPS.setdefault("grammar", run_grammar_agent_loop)
    _BUILTINS_LOADED = True


def register_agent_loop(name: str, runner: AgentLoopRunner) -> None:
    """Register or replace an app-compatible agent loop."""

    normalized = name.strip()
    if not normalized:
        raise ValueError("Agent loop name must not be blank.")
    _LOOPS[normalized] = runner


def get_agent_loop(name: str) -> AgentLoopRunner:
    _load_builtins()
    runner = _LOOPS.get(name)
    if runner is None:
        available = ", ".join(sorted(_LOOPS)) or "none"
        raise ValueError(f"Unknown agent loop: {name!r}. Available: {available}")
    return runner


def list_agent_loops() -> list[str]:
    _load_builtins()
    return sorted(_LOOPS)


def run_agent_loop(
    name: str,
    prompt: str,
    initial_state: dict[str, Any] | None = None,
    *,
    config: AgentLoopConfig | None = None,
) -> AgentLoopResult:
    runner = get_agent_loop(name)
    loop_config = config or AgentLoopConfig()
    with langsmith_observation(
        f"agent_loop.{name}",
        as_type="agent",
        input={
            "prompt": prompt,
            "initial_state": initial_state,
            "config": {
                "population": loop_config.population,
                "max_attempts": loop_config.max_attempts,
                "require_human_confirmation": loop_config.require_human_confirmation,
                "extra": dict(loop_config.extra),
            },
        },
    ) as observation:
        result = runner(prompt, initial_state, config=loop_config)
        trace_id = get_langsmith_trace_id()
        if trace_id and not result.hitl.get("langsmith_trace_id"):
            state = dict(result.state)
            hitl = dict(result.hitl)
            state["langsmith_trace_id"] = trace_id
            hitl["langsmith_trace_id"] = trace_id
            result = AgentLoopResult(state=state, hitl=hitl)
        observation.update(output=result.hitl)
        return result
