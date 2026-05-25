"""Pluggable agent loops for robot generation experiments and app runs."""

from packages.research.agent_loops.protocol import AgentLoopConfig, AgentLoopResult, AgentLoopRunner
from packages.research.agent_loops.registry import (
    get_agent_loop,
    list_agent_loops,
    register_agent_loop,
    run_agent_loop,
)

__all__ = [
    "AgentLoopConfig",
    "AgentLoopResult",
    "AgentLoopRunner",
    "get_agent_loop",
    "list_agent_loops",
    "register_agent_loop",
    "run_agent_loop",
]
