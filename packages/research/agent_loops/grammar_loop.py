"""RoboGrammar LangGraph agent loop registered on the research side.

This module owns the experimental loop structure. It depends on
packages.pipeline.grammar_graph for grammar catalog tools, prompt builders, and
shared state/output types so notebooks can change orchestration without changing
the product backend.
"""

from __future__ import annotations

import ast
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import TypeAdapter

from packages.pipeline import grammar_graph as grammar_tools
from packages.pipeline.observability import (
    get_langsmith_trace_id,
    langsmith_observation,
    langsmith_trace_context,
)
from packages.pipeline.schemas import TaskIntent
from packages.research.agent_loops.protocol import AgentLoopConfig, AgentLoopResult

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - optional local test/runtime dependency
    END = START = None
    StateGraph = None

from packages.research.local_chat_models import make_structured_llm

_TASK_INTENT_ADAPTER: TypeAdapter[TaskIntent] = TypeAdapter(TaskIntent)

DEFAULT_ROBOT_POPULATION = grammar_tools.DEFAULT_ROBOT_POPULATION
DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES = grammar_tools.DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES
RULE_BUILDER_AGENT_SYSTEM_PROMPT = grammar_tools.RULE_BUILDER_AGENT_SYSTEM_PROMPT
HumanMessage = grammar_tools.HumanMessage
SystemMessage = grammar_tools.SystemMessage
Criteria = grammar_tools.Criteria
TODO = grammar_tools.TODO
StructuralRules = grammar_tools.StructuralRules
CompilerError = grammar_tools.CompilerError
CompileResult = grammar_tools.CompileResult
CompileAttempt = grammar_tools.CompileAttempt
RoboGraphState = grammar_tools.RoboGraphState


def build_query_normalizer_prompt(raw_prompt: str) -> str:
    """Create the prompt used to turn a raw user request into TaskIntent JSON.

    Call this first when you only have the user's natural-language task, for
    example ``"build a stair-climbing quadruped"``. Pass one non-empty string
    as ``raw_prompt``. The return value is a plain text prompt; send it to a
    structured model that returns ``TaskIntent``. Do not pass structural rules
    or graph nodes here.
    """
    return grammar_tools.build_query_normalizer_prompt(raw_prompt)


def build_evaluator_system_prompt(state: RoboGraphState):
    """Build messages for creating the first TODO checklist for a rule graph.

    Pass the current ``RoboGraphState`` dict after ``state["spec"]`` has been
    filled by ``normalize_query_node``. The return value is
    ``(SystemMessage, HumanMessage)`` for an evaluator model. Use this before
    structural rules exist, so the evaluator can define concrete criteria the
    rule builder should satisfy.
    """
    return grammar_tools.build_evaluator_system_prompt(state)


def build_checklist_prompt(state: RoboGraphState):
    """Build messages for checking generated structural rules against TODOs.

    Pass the current ``RoboGraphState`` dict after ``state["structural_rules"]``
    has been generated and compiled. The return value is
    ``(SystemMessage, HumanMessage)`` for an evaluator model. Use this after a
    rule-building attempt to mark checklist items successful or failed and to
    produce short critiques for another attempt.
    """
    return grammar_tools.build_checklist_prompt(state)


def build_rule_builder_system_prompt(*args: Any, **kwargs: Any) -> str:
    """Create the system prompt for ``rule_builder_agent``.

    Preferred call: ``build_rule_builder_system_prompt(query=task_intent)``.
    ``query`` must be a ``TaskIntent`` object, not a raw string. Optional
    keyword args are ``example_families``, ``examples_per_family``,
    ``grammar_node_limit``, and ``active_only``. The returned prompt includes
    current GrammarNodes vocabulary plus compile-valid few-shot structural-rule
    examples. Send it with ``_rule_builder_user_prompt(state)`` to an agent that
    returns only ``{"structural_rules": dict[str, list[str]]}``.
    """
    with langsmith_observation(
        "build_rule_builder_system_prompt",
        as_type="tool",
        input={"args": [str(arg) for arg in args], "kwargs": kwargs},
    ) as observation:
        result = grammar_tools.build_rule_builder_system_prompt(*args, **kwargs)
        observation.update(output={"prompt_chars": len(result)})
        return result


def sample_rule_builder_examples(*args: Any, **kwargs: Any):
    """Fetch few-shot structural-rule examples for the rule builder.

    Call with keyword args such as
    ``example_families=("quadruped", "snake")`` and
    ``examples_per_family=2``. Optional ``known_nodes`` can be a set of valid
    GrammarNodes short IDs; examples using unknown nodes are filtered out. The
    return value is ``{family: {production_rule: description}}``. Use these as
    style examples, not as rules that must always be copied.
    """
    with langsmith_observation(
        "sample_rule_builder_examples",
        as_type="tool",
        input={"args": [str(arg) for arg in args], "kwargs": kwargs},
    ) as observation:
        result = grammar_tools.sample_rule_builder_examples(*args, **kwargs)
        observation.update(
            output={
                "families": list(result),
                "example_count": sum(len(items) for items in result.values()),
            }
        )
        return result


def fetch_grammar_from_db(*args: Any, **kwargs: Any):
    """Fetch valid GrammarNodes IDs that structural rules are allowed to use.

    Call with optional keyword args: ``limit``, ``active_only``,
    ``morphology_family``, and ``node_type``. The return value is a list of
    ``(short_form_name, long_name)`` tuples. Use ``short_form_name`` exactly as
    the node ID in ``structural_rules``. Use this before inventing any node name.
    """
    with langsmith_observation(
        "fetch_grammar_from_db",
        as_type="tool",
        input={"args": [str(arg) for arg in args], "kwargs": kwargs},
    ) as observation:
        result = grammar_tools.fetch_grammar_from_db(*args, **kwargs)
        observation.update(output={"row_count": len(result), "rows": result[:25]})
        return result


def compile_structural_rules(*args: Any, **kwargs: Any):
    """Check whether structural rules reference only known GrammarNodes IDs.

    Preferred call:
    ``compile_structural_rules({"S": ["BODY", "LEG_PAIR"]})``. The input must
    be a dict mapping each left-hand-side short node ID to a list of right-hand
    side short node IDs. The return value has ``compile_safe`` and
    ``invalid_nodes``. Use this after generating or repairing rules; if
    ``compile_safe`` is false, repair or regenerate before materializing a robot.
    """
    with langsmith_observation(
        "compile_structural_rules",
        as_type="tool",
        input={"args": args, "kwargs": kwargs},
    ) as observation:
        result = grammar_tools.compile_structural_rules(*args, **kwargs)
        observation.update(
            output={
                "compile_safe": result.compile_safe,
                "invalid_nodes": list(result.invalid_nodes.nodes),
                "invalid_nodes_error": result.invalid_nodes.error,
                "unreachable_nodes": list(result.unreachable_nodes.nodes),
                "unreachable_nodes_error": result.unreachable_nodes.error,
            }
        )
        return result


def repair_structural_rule_node_names(*args: Any, **kwargs: Any):
    """Repair close-but-invalid GrammarNodes names in generated rules.

    Preferred call:
    ``repair_structural_rule_node_names({"S": ["body", "leg pair"]})``. The
    input is the same dict shape used by ``compile_structural_rules``. Optional
    keyword arg: ``active_only``. The return value is
    ``(repaired_rules, node_resolution)`` where ``node_resolution`` lists
    corrections and unresolved names. Use this when a model used near-miss node
    names instead of exact short IDs.
    """
    with langsmith_observation(
        "repair_structural_rule_node_names",
        as_type="tool",
        input={"args": args, "kwargs": kwargs},
    ) as observation:
        repaired_rules, node_resolution = grammar_tools.repair_structural_rule_node_names(
            *args, **kwargs
        )
        observation.update(
            output={
                "structural_rules": repaired_rules,
                "node_resolution": node_resolution,
            }
        )
        return repaired_rules, node_resolution


def repair_structural_rule_node_names_safely(*args: Any, **kwargs: Any):
    """Safely repair structural-rule node names without crashing the loop.

    Preferred call:
    ``repair_structural_rule_node_names_safely(structural_rules)`` where
    ``structural_rules`` is ``dict[str, list[str]]``. This wraps
    ``repair_structural_rule_node_names`` and returns the original rules with a
    ``status="skipped"`` resolution payload if the GrammarNodes vocabulary is
    unavailable. Use this inside automated loops where a database/tool failure
    should not stop the whole graph.
    """
    with langsmith_observation(
        "repair_structural_rule_node_names_safely",
        as_type="tool",
        input={"args": args, "kwargs": kwargs},
    ) as observation:
        repaired_rules, node_resolution = (
            grammar_tools._repair_structural_rule_node_names_safely(*args, **kwargs)
        )
        observation.update(
            output={
                "structural_rules": repaired_rules,
                "node_resolution": node_resolution,
            }
        )
        return repaired_rules, node_resolution


_repair_structural_rule_node_names_safely = repair_structural_rule_node_names_safely


GRAMMAR_LOOP_TOOLS: dict[str, Callable[..., Any]] = {
    "build_query_normalizer_prompt": build_query_normalizer_prompt,
    "build_evaluator_system_prompt": build_evaluator_system_prompt,
    "build_checklist_prompt": build_checklist_prompt,
    "build_rule_builder_system_prompt": build_rule_builder_system_prompt,
    "sample_rule_builder_examples": sample_rule_builder_examples,
    "fetch_grammar_from_db": fetch_grammar_from_db,
    "compile_structural_rules": compile_structural_rules,
    "repair_structural_rule_node_names": repair_structural_rule_node_names,
    "repair_structural_rule_node_names_safely": repair_structural_rule_node_names_safely,
}


_parse_production_rule = grammar_tools._parse_production_rule
_format_query_context = grammar_tools._format_query_context
_string_or_none = grammar_tools._string_or_none
_exception_payload = grammar_tools._exception_payload
_status_message = grammar_tools._status_message


@dataclass(frozen=True)
class LangChainStructuredAgent:
    """Small adapter that lets any LangChain chat model drive one loop agent.

    The grammar loop expects injected agents to expose ``invoke(...)`` and to
    return JSON parseable as a target schema. This adapter keeps that contract
    independent of a specific provider, so notebooks can swap in Qwen, OpenAI,
    Codex, Claude, or any other LangChain-compatible chat model.
    """

    model: Any
    schema: Any
    role: str

    def invoke(self, prompt_or_messages: Any) -> Any:
        messages = _normalize_agent_messages(prompt_or_messages)
        return self.model.invoke(
            [
                SystemMessage(content=_structured_agent_instruction(self.schema, self.role)),
                *messages,
            ]
        )


def make_structured_agent_from_chat_model(
    model: Any,
    schema: Any,
    *,
    role: str | None = None,
) -> LangChainStructuredAgent:
    """Wrap a LangChain chat model so it can be injected into the grammar loop.

    Use this when you already have a model object, for example a Qwen
    ``ChatOpenAI(base_url="http://127.0.0.1:8001/v1", ...)`` instance in a
    notebook. The returned object has ``invoke(...)`` and can be passed as
    ``normalizer_agent``, ``rule_builder_agent``, or ``evaluator_agent``.
    """
    return LangChainStructuredAgent(
        model=model,
        schema=schema,
        role=role or _schema_role_name(schema),
    )


def make_structural_rule_agents_from_chat_model(
    model: Any,
    *,
    normalizer_model: Any | None = None,
    rule_builder_model: Any | None = None,
    evaluator_model: Any | None = None,
) -> dict[str, LangChainStructuredAgent]:
    """Build all injectable grammar-loop agents from swappable chat models.

    Pass one ``model`` to use it for every stage, or override individual stages
    with ``normalizer_model``, ``rule_builder_model``, and ``evaluator_model``.
    The returned dict is ready to unpack into ``build_structural_rules(...)`` or
    ``AgentLoopConfig(...)``.
    """
    return {
        "normalizer_agent": make_structured_agent_from_chat_model(
            normalizer_model or model,
            TaskIntent,
            role="query_normalizer_agent",
        ),
        "rule_builder_agent": make_structured_agent_from_chat_model(
            rule_builder_model or model,
            StructuralRules,
            role="rule_builder_agent",
        ),
        "evaluator_agent": make_structured_agent_from_chat_model(
            evaluator_model or model,
            TODO,
            role="evaluator_agent",
        ),
    }


@dataclass(frozen=True)
class StructuralRuleLoopContext:
    """Injected dependencies shared by reusable grammar-loop nodes."""

    confirmed_spec: TaskIntent | dict[str, Any] | None = None
    normalizer_agent: Any | None = None
    rule_builder_agent: Any | None = None
    evaluator_agent: Any | None = None
    require_human_confirmation: bool = False


StructuralRuleNode = Callable[
    [RoboGraphState, StructuralRuleLoopContext],
    dict[str, Any],
]


def make_structural_rule_loop_context(
    *,
    confirmed_spec: TaskIntent | dict[str, Any] | None = None,
    normalizer_agent: Any | None = None,
    rule_builder_agent: Any | None = None,
    evaluator_agent: Any | None = None,
    require_human_confirmation: bool = False,
) -> StructuralRuleLoopContext:
    return StructuralRuleLoopContext(
        confirmed_spec=confirmed_spec,
        normalizer_agent=normalizer_agent or _make_structured_agent(TaskIntent),
        rule_builder_agent=rule_builder_agent or _make_structured_agent(StructuralRules),
        evaluator_agent=evaluator_agent or _make_structured_agent(TODO),
        require_human_confirmation=require_human_confirmation,
    )


def build_initial_structural_rule_state(
    prompt: str,
    initial_state: RoboGraphState | None = None,
    *,
    population: int | None = None,
    max_attempts: int = 2,
) -> RoboGraphState:
    state: RoboGraphState = {
        "prompt": prompt,
        "population": DEFAULT_ROBOT_POPULATION,
        "attempts": 0,
        "max_attempts": max(1, max_attempts),
        "langsmith_trace_id": None,
        "spec": None,
        "structural_rules": None,
        "node_resolution": {"corrections": [], "unresolved": []},
        "compile_result": CompileResult(False),
        "candidates": [],
        "messages": [],
        "checklist": None,
        "awaiting_human": False,
    }
    if initial_state:
        for key, value in initial_state.items():
            if key == "prompt" and _string_or_none(value) is None:
                continue
            if key in {
                "compile_safe",
                "invalid_grammar_nodes",
                "unreachable_grammar_nodes",
                "compile_error",
            }:
                continue
            state[key] = value
    state["population"] = _normalize_population(
        population if population is not None else state.get("population")
    )
    state["max_attempts"] = max(1, int(state.get("max_attempts") or max_attempts))
    return state


def normalize_query_node(
    state: RoboGraphState,
    context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    raw_prompt = state.get("prompt") or ""
    with langsmith_observation(
        "normalize_query",
        as_type="chain",
        input={"prompt": raw_prompt},
    ) as observation:
        spec = (
            _coerce_task_intent(context.confirmed_spec)
            if context.confirmed_spec
            else state.get("spec")
        )
        if spec is None:
            legacy_query = cast(dict[str, Any], state).get("query")
            spec = _coerce_task_intent(legacy_query)
        if spec is None:
            spec = _normalize_prompt(raw_prompt, context.normalizer_agent)
        output = (
            _TASK_INTENT_ADAPTER.dump_python(spec)
            if isinstance(spec, TaskIntent)
            else spec
        )
        observation.update(output=output)
        return {
            "prompt": raw_prompt,
            "spec": spec,
            "messages": ["normalize_query: TaskIntent ready."],
        }


def await_human_confirmation_node(
    _state: RoboGraphState,
    _context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    with langsmith_observation(
        "await_human_confirmation",
        as_type="chain",
    ) as observation:
        output = {
            "awaiting_human": True,
            "messages": [
                "Awaiting human confirmation of TaskIntent before structural rule generation.",
            ],
        }
        observation.update(output=output)
        return output


def make_initial_checklist_node(
    state: RoboGraphState,
    context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    with langsmith_observation(
        "make_initial_checklist",
        as_type="evaluator",
        input=_state_summary_for_prompt(state),
    ) as observation:
        checklist = _make_initial_checklist(
            state,
            evaluator_agent=context.evaluator_agent,
        )
        observation.update(
            output=checklist,
            metadata={"criteria_count": len(checklist["criteria"])},
        )
        return {
            "awaiting_human": False,
            "checklist": checklist,
            "messages": ["make_initial_checklist: evaluator checklist ready."],
        }


def build_structural_rules_node(
    state: RoboGraphState,
    context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    attempt = int(state.get("attempts") or 0) + 1
    with langsmith_observation(
        "build_structural_rules",
        as_type="agent",
        input=_rule_builder_user_prompt(state),
        metadata={"attempt": attempt},
    ) as observation:
        structural_rules = _build_rules_for_state(
            state,
            rule_builder_agent=context.rule_builder_agent,
        )
        observation.update(
            output=structural_rules,
            metadata={"rule_count": len(structural_rules["structural_rules"])},
        )
        return {
            "attempts": attempt,
            "structural_rules": structural_rules,
            "messages": [
                f"rule_builder_attempt_{attempt}: structural rules generated."
            ],
        }


def resolve_grammar_node_names_node(
    state: RoboGraphState,
    _context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    structural_rules = state.get("structural_rules")
    with langsmith_observation(
        "resolve_grammar_node_names",
        as_type="span",
        input=structural_rules,
        metadata={"langgraph_node": "resolve_grammar_node_names"},
    ) as observation:
        rules_payload = _rules_payload_for_node_resolution(structural_rules)
        repaired_rules, node_resolution = _repair_structural_rule_node_names_safely(
            rules_payload
        )
        update_kwargs: dict[str, Any] = {
            "output": {
                "structural_rules": repaired_rules,
                "node_resolution": node_resolution,
            },
            "metadata": {
                "resolution_status": node_resolution.get("status"),
                "correction_count": len(node_resolution["corrections"]),
                "unresolved_count": len(node_resolution["unresolved"]),
            },
        }
        if node_resolution.get("status") == "skipped":
            update_kwargs["level"] = "WARNING"
            update_kwargs["status_message"] = _status_message(
                str(node_resolution["reason"]),
                {
                    "error_type": str(node_resolution["error_type"]),
                    "error_message": str(node_resolution["error_message"]),
                },
            )
        observation.update(**update_kwargs)
        message = (
            "resolve_grammar_node_names: fuzzy node-name resolution skipped; "
            f"{node_resolution.get('error_type')}: {node_resolution.get('error_message')}."
            if node_resolution.get("status") == "skipped"
            else "resolve_grammar_node_names: fuzzy node-name resolution complete."
        )
        return {
            "structural_rules": {"structural_rules": repaired_rules},
            "node_resolution": node_resolution,
            "messages": [message],
        }


def compile_structural_rules_node(
    state: RoboGraphState,
    _context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    structural_rules = state.get("structural_rules") or {"structural_rules": {}}
    with langsmith_observation(
        "compile_structural_rules",
        as_type="tool",
        input=structural_rules,
    ) as observation:
        compile_attempt = _compile_structural_rules_safely(
            structural_rules["structural_rules"]
        )
        compile_result = compile_attempt.result
        output: dict[str, Any] = _compile_result_prompt_payload(compile_result)
        update_kwargs = {"output": output}
        if compile_result.compile_error is not None:
            update_kwargs["level"] = "WARNING"
            update_kwargs["status_message"] = _status_message(
                "compile_structural_rules could not validate against GrammarNodes",
                compile_result.compile_error,
            )
            update_kwargs["metadata"] = {"compile_error": compile_result.compile_error}
        observation.update(**update_kwargs)
        message = f"compile_structural_rules: {compile_attempt}."
        return {
            "compile_result": compile_result,
            "messages": [message],
        }


def evaluate_rules_node(
    state: RoboGraphState,
    context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    with langsmith_observation(
        "evaluate_rules",
        as_type="evaluator",
        input=_state_summary_for_prompt(state),
    ) as observation:
        checklist = _evaluate_rules_for_state(
            state,
            evaluator_agent=context.evaluator_agent,
        )
        observation.update(
            output=checklist,
            metadata={"successful": _checklist_is_successful(checklist)},
        )
        return {
            "checklist": checklist,
            "messages": ["evaluate_rules: evaluator pass complete."],
        }


def summarize_hitl_node(
    state: RoboGraphState,
    _context: StructuralRuleLoopContext,
) -> dict[str, Any]:
    with langsmith_observation(
        "summarize_hitl",
        as_type="chain",
        input=_state_summary_for_prompt(state),
    ) as observation:
        hitl = summarize_hitl_state(state)
        observation.update(output=hitl)
        return {"hitl": hitl}


def route_after_normalize(
    _state: RoboGraphState,
    context: StructuralRuleLoopContext,
) -> str:
    if context.require_human_confirmation and context.confirmed_spec is None:
        return "await_human_confirmation"
    return "make_initial_checklist"


def route_after_evaluation(
    state: RoboGraphState,
    _context: StructuralRuleLoopContext,
) -> str:
    if _checklist_is_successful(state.get("checklist")):
        return "summarize_hitl"
    if int(state.get("attempts") or 0) < int(state.get("max_attempts") or 1):
        return "build_structural_rules"
    return "summarize_hitl"


STRUCTURAL_RULE_GRAPH_NODE_ORDER: tuple[str, ...] = (
    "normalize_query",
    "await_human_confirmation",
    "make_initial_checklist",
    "build_structural_rules",
    "resolve_grammar_node_names",
    "compile_structural_rules",
    "evaluate_rules",
    "summarize_hitl",
)

STRUCTURAL_RULE_GRAPH_NODES: dict[str, StructuralRuleNode] = {
    "normalize_query": normalize_query_node,
    "await_human_confirmation": await_human_confirmation_node,
    "make_initial_checklist": make_initial_checklist_node,
    "build_structural_rules": build_structural_rules_node,
    "resolve_grammar_node_names": resolve_grammar_node_names_node,
    "compile_structural_rules": compile_structural_rules_node,
    "evaluate_rules": evaluate_rules_node,
    "summarize_hitl": summarize_hitl_node,
}


def build_structural_rules(
    prompt: str,
    initial_state: RoboGraphState | None = None,
    *,
    confirmed_spec: TaskIntent | dict[str, Any] | None = None,
    normalizer_agent: Any | None = None,
    rule_builder_agent: Any | None = None,
    evaluator_agent: Any | None = None,
    population: int | None = None,
    max_attempts: int = 2,
    require_human_confirmation: bool = False,
) -> RoboGraphState:
    """Run the main grammar-only normalize/checklist/build/evaluate agent loop.

    The loop is deterministic when no LLM agents are provided. Optional agents
    can be injected in tests or production and are expected to expose
    ``invoke(...)``. The returned state includes a ``hitl`` payload that the API
    can surface directly while robot generation is running.
    """
    state = build_initial_structural_rule_state(
        prompt,
        initial_state,
        population=population,
        max_attempts=max_attempts,
    )
    context = make_structural_rule_loop_context(
        confirmed_spec=confirmed_spec,
        normalizer_agent=normalizer_agent,
        rule_builder_agent=rule_builder_agent,
        evaluator_agent=evaluator_agent,
        require_human_confirmation=require_human_confirmation,
    )

    if StateGraph is None or os.environ.get("RESEARCH_USE_LANGGRAPH_AUTO_INVOKE") != "1":
        return _run_structural_rules_without_langgraph(
            state,
            context=context,
        )

    graph = _compile_structural_rule_graph(context=context)
    with langsmith_observation(
        "robogrammar.structural_rule_graph",
        as_type="agent",
        input={"prompt": state.get("prompt"), "population": state.get("population")},
        metadata={"max_attempts": state.get("max_attempts")},
    ) as observation:
        with langsmith_trace_context():
            final_state = cast(RoboGraphState, graph.invoke(state, config={"callbacks": []}))
        trace_id = get_langsmith_trace_id()
        if trace_id:
            final_state["langsmith_trace_id"] = trace_id
            final_state["hitl"] = summarize_hitl_state(final_state)
        observation.update(
            output=summarize_hitl_state(final_state),
            metadata={
                **_compile_result_prompt_payload(_compile_result_from_state(final_state)),
                "attempts": int(final_state.get("attempts") or 0),
            },
        )
        return final_state


def _compile_structural_rule_graph(*, context: StructuralRuleLoopContext) -> Any:
    graph = StateGraph(RoboGraphState)
    for node_name in STRUCTURAL_RULE_GRAPH_NODE_ORDER:
        graph.add_node(
            node_name,
            _bind_structural_rule_node(STRUCTURAL_RULE_GRAPH_NODES[node_name], context),
        )

    graph.add_edge(START, "normalize_query")
    graph.add_conditional_edges(
        "normalize_query",
        lambda state: route_after_normalize(state, context),
        {
            "await_human_confirmation": "await_human_confirmation",
            "make_initial_checklist": "make_initial_checklist",
        },
    )
    graph.add_edge("await_human_confirmation", "summarize_hitl")
    graph.add_edge("make_initial_checklist", "build_structural_rules")
    graph.add_edge("build_structural_rules", "resolve_grammar_node_names")
    graph.add_edge("resolve_grammar_node_names", "compile_structural_rules")
    graph.add_edge("compile_structural_rules", "evaluate_rules")
    graph.add_conditional_edges(
        "evaluate_rules",
        lambda state: route_after_evaluation(state, context),
        {
            "build_structural_rules": "build_structural_rules",
            "summarize_hitl": "summarize_hitl",
        },
    )
    graph.add_edge("summarize_hitl", END)
    return graph.compile()


def _bind_structural_rule_node(
    node: StructuralRuleNode,
    context: StructuralRuleLoopContext,
) -> Callable[[RoboGraphState], dict[str, Any]]:
    def bound_node(state: RoboGraphState) -> dict[str, Any]:
        return node(state, context)

    bound_node.__name__ = node.__name__
    return bound_node


def _run_structural_rules_without_langgraph(
    state: RoboGraphState,
    *,
    context: StructuralRuleLoopContext,
) -> RoboGraphState:
    with langsmith_observation(
        "robogrammar.structural_rule_graph",
        as_type="agent",
        input={"prompt": state.get("prompt"), "population": state.get("population")},
        metadata={"max_attempts": state.get("max_attempts")},
    ):
        _apply_node_update(
            state,
            normalize_query_node(state, context),
            append_messages=True,
        )

        trace_id = get_langsmith_trace_id()
        if trace_id:
            state["langsmith_trace_id"] = trace_id

        if route_after_normalize(state, context) == "await_human_confirmation":
            _apply_node_update(
                state,
                await_human_confirmation_node(state, context),
                append_messages=True,
            )
            _apply_node_update(
                state,
                summarize_hitl_node(state, context),
                append_messages=False,
            )
            return state

        _apply_node_update(
            state,
            make_initial_checklist_node(state, context),
            append_messages=False,
        )

        attempts = int(state.get("max_attempts") or 1)
        for _attempt in range(attempts):
            _apply_node_update(
                state,
                build_structural_rules_node(state, context),
                append_messages=False,
            )
            _apply_node_update(
                state,
                resolve_grammar_node_names_node(state, context),
                append_messages=False,
            )
            _apply_node_update(
                state,
                compile_structural_rules_node(state, context),
                append_messages=False,
            )
            _apply_node_update(
                state,
                evaluate_rules_node(state, context),
                append_messages=False,
            )
            if _checklist_is_successful(state["checklist"]):
                break

        state["awaiting_human"] = False
        _apply_node_update(
            state,
            summarize_hitl_node(state, context),
            append_messages=False,
        )
        return state


def _apply_node_update(
    state: RoboGraphState,
    update: dict[str, Any],
    *,
    append_messages: bool,
) -> None:
    for key, value in update.items():
        if key == "messages":
            if append_messages:
                state["messages"] = [*_as_list(state.get("messages")), *_as_list(value)]
            continue
        state[key] = value


def summarize_hitl_state(state: RoboGraphState) -> dict[str, Any]:
    """Return the UI-facing grammar HITL payload for robot generation."""
    spec = state.get("spec")
    structural_rules = state.get("structural_rules") or {"structural_rules": {}}
    compile_result = _compile_result_from_state(state)
    compile_payload = _compile_result_prompt_payload(compile_result)
    return {
        "spec": _TASK_INTENT_ADAPTER.dump_python(spec) if isinstance(spec, TaskIntent) else spec,
        "inferred_morphology": _infer_morphology_family(spec) if isinstance(spec, TaskIntent) else None,
        "checklist": state.get("checklist") or {"criteria": []},
        "structural_rules": structural_rules.get("structural_rules", {}),
        "node_resolution": state.get("node_resolution") or {"corrections": [], "unresolved": []},
        "compile_result": compile_payload,
        "invalid_grammar_nodes": compile_payload["invalid_grammar_nodes"],
        "unreachable_grammar_nodes": compile_payload["unreachable_grammar_nodes"],
        "population": _normalize_population(state.get("population")),
        "compile_safe": compile_payload["compile_safe"],
        "compile_error": compile_payload["compile_error"],
        "awaiting_human": bool(state.get("awaiting_human")),
        "langsmith_trace_id": state.get("langsmith_trace_id"),
        "messages": [str(message) for message in _as_list(state.get("messages"))],
    }


def _normalize_prompt(prompt: str, normalizer_agent: Any | None) -> TaskIntent:
    if normalizer_agent is not None:
        try:
            response = normalizer_agent.invoke(build_query_normalizer_prompt(prompt))
            coerced = _coerce_task_intent(response)
            if coerced is not None:
                return coerced
        except Exception:
            pass
    return _fallback_task_intent(prompt)


def _fallback_task_intent(prompt: str) -> TaskIntent:
    return TaskIntent(task_goal=prompt.strip())


def _build_rules_for_state(
    state: RoboGraphState,
    *,
    rule_builder_agent: Any | None,
) -> StructuralRules:
    spec = state.get("spec")
    if not isinstance(spec, TaskIntent):
        raise ValueError("RoboGraphState.spec must be a TaskIntent.")

    if rule_builder_agent is not None:
        try:
            system_prompt = build_rule_builder_system_prompt(query=spec)
        except Exception:
            system_prompt = "\n\n".join(
                [
                    RULE_BUILDER_AGENT_SYSTEM_PROMPT.strip(),
                    _format_query_context(query=spec),
                ]
            )
        try:
            response = rule_builder_agent.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=_rule_builder_user_prompt(state)),
                ]
            )
            structural_rules = _coerce_structural_rules(response)
            if structural_rules["structural_rules"]:
                return structural_rules
        except Exception:
            pass

    return _build_rules_from_examples(spec)


def _build_rules_from_examples(spec: TaskIntent) -> StructuralRules:
    families: list[str] = []
    inferred = _infer_morphology_family(spec)
    if inferred:
        families.append(inferred)
    families.extend(
        family
        for family in ("shared", *DEFAULT_RULE_BUILDER_EXAMPLE_FAMILIES)
        if family not in families
    )

    rules: dict[str, list[str]] = {}
    try:
        examples = sample_rule_builder_examples(
            example_families=families,
            examples_per_family=4,
        )
    except Exception:
        examples = {}

    for family_rules in examples.values():
        for production in family_rules:
            parsed = _parse_production_rule(production)
            if parsed is None:
                continue
            lhs, rhs = parsed
            rules.setdefault(lhs, rhs)

    if not rules:
        rules = _fallback_seed_rules()
    return {"structural_rules": rules}


def _fallback_seed_rules() -> dict[str, list[str]]:
    try:
        known_nodes = {short_name for short_name, _long_name in fetch_grammar_from_db()}
    except Exception:
        known_nodes = set()
    if {"S", "BODY"}.issubset(known_nodes):
        return {"S": ["BODY"]}
    if {"S", "BODY_CHAIN"}.issubset(known_nodes):
        return {"S": ["BODY_CHAIN"]}
    return {}


def _evaluate_rules_for_state(
    state: RoboGraphState,
    *,
    evaluator_agent: Any | None,
) -> TODO:
    if evaluator_agent is not None:
        try:
            response = evaluator_agent.invoke(list(build_checklist_prompt(state)))
            checklist = _coerce_todo(response)
            if checklist["criteria"]:
                return checklist
        except Exception:
            pass
    return _evaluate_rules_deterministically(state)


def _evaluate_rules_deterministically(state: RoboGraphState) -> TODO:
    structural_rules = (state.get("structural_rules") or {"structural_rules": {}})[
        "structural_rules"
    ]
    compile_result = _compile_result_from_state(state)
    compile_safe = bool(compile_result)
    non_empty = bool(structural_rules)
    recursive_or_grouped = _has_recursive_or_grouped_structure(structural_rules)

    checklist = state.get("checklist")
    if not checklist or not checklist.get("criteria"):
        checklist = _fallback_initial_checklist(state)

    criteria: list[Criteria] = []
    for criterion in checklist["criteria"]:
        description = criterion["description"]
        lowered = description.lower()
        if "compile" in lowered or "grammarnodes" in lowered or "vocabulary" in lowered:
            successful = compile_safe
            invalid_nodes = list(compile_result.invalid_nodes.nodes)
            unreachable_nodes = list(compile_result.unreachable_nodes.nodes)
            compile_error = compile_result.compile_error
            if successful:
                critiques = []
            elif compile_error:
                critiques = [
                    "Compile check could not run: "
                    f"{compile_error.get('error_type')}: "
                    f"{compile_error.get('error_message')}"
                ]
            elif invalid_nodes:
                critiques = [
                    "Nodes "
                    + ", ".join(invalid_nodes)
                    + " were NOT in GrammarNodes vocabulary."
                ]
            elif unreachable_nodes:
                critiques = [
                    "Nodes "
                    + ", ".join(unreachable_nodes)
                    + " were valid but unreachable from S."
                ]
            else:
                critiques = ["At least one LHS/RHS node is missing from GrammarNodes."]
        elif "non-empty" in lowered or "structural rules" in lowered and "generated" in lowered:
            successful = non_empty
            critiques = [] if successful else ["No structural rules were generated."]
        elif any(token in lowered for token in ("recursive", "grouped", "repeat", "pair", "chain", "symmetry", "symmetric")):
            successful = recursive_or_grouped
            critiques = [] if successful else ["Prefer recursive chain or pair/group nodes instead of flat terminal-only rules."]
        else:
            successful = compile_safe and non_empty
            critiques = [] if successful else ["Satisfy this proxy goal with compile-safe structural topology."]
        criteria.append(
            {
                "description": description,
                "isSuccessful": successful,
                "critiques": critiques,
            }
        )
    return {"criteria": criteria}


def _has_recursive_or_grouped_structure(rules: dict[str, list[str]]) -> bool:
    group_tokens = {"LEG_PAIR", "ARM_PAIR", "WING_PAIR", "SPRAWLED_LEG_PAIR", "APPENDAGE_PAIR"}
    chain_tokens = {"BODY_CHAIN", "SEG_CHAIN", "SIDEWINDER_CHAIN", "SPINE_CHAIN", "THORAX_CHAIN"}
    for lhs, rhs in rules.items():
        rhs_set = set(rhs)
        if lhs in rhs_set:
            return True
        if rhs_set & group_tokens:
            return True
        if lhs in chain_tokens or rhs_set & chain_tokens:
            return True
    return False


def _checklist_is_successful(checklist: TODO | None) -> bool:
    return bool(checklist and all(item["isSuccessful"] for item in checklist["criteria"]))


def _compile_structural_rules_safely(rules: dict[str, list[str]]) -> CompileAttempt:
    try:
        return CompileAttempt(compile_structural_rules(rules))
    except Exception as exc:
        error = _exception_payload(exc)
        return CompileAttempt(
            CompileResult(False, CompilerError(error=error), compile_error=error)
        )


def _compile_result_prompt_payload(result: CompileResult) -> dict[str, Any]:
    return {
        "compile_safe": result.compile_safe,
        "invalid_grammar_nodes": list(result.invalid_nodes.nodes),
        "unreachable_grammar_nodes": list(result.unreachable_nodes.nodes),
        "compile_error": result.compile_error,
    }


def _compile_result_from_state(state: RoboGraphState) -> CompileResult:
    result = state.get("compile_result")
    if isinstance(result, CompileResult):
        return result
    return CompileResult(
        bool(state.get("compile_safe", False)),
        CompilerError(
            nodes=tuple(str(node) for node in _as_list(state.get("invalid_grammar_nodes")))
        ),
        CompilerError(
            nodes=tuple(
                str(node) for node in _as_list(state.get("unreachable_grammar_nodes"))
            )
        ),
        state.get("compile_error"),
    )


def _make_initial_checklist(
    state: RoboGraphState,
    *,
    evaluator_agent: Any | None,
) -> TODO:
    if evaluator_agent is not None:
        try:
            checklist = _coerce_todo(evaluator_agent.invoke(list(build_evaluator_system_prompt(state))))
            if checklist["criteria"]:
                return checklist
        except Exception:
            pass
    return _fallback_initial_checklist(state)


def _fallback_initial_checklist(state: RoboGraphState) -> TODO:
    spec = state.get("spec")
    criteria: list[Criteria] = [
        {
            "description": "Structural rules are non-empty and generated from current grammar context.",
            "isSuccessful": False,
            "critiques": ["Awaiting rule generation."],
        },
        {
            "description": "Generated structural rules compile against GrammarNodes vocabulary.",
            "isSuccessful": False,
            "critiques": ["Awaiting compiler check."],
        },
        {
            "description": "Rules use recursive or grouped RoboGrammar topology for repeatable structures.",
            "isSuccessful": False,
            "critiques": ["Awaiting evaluator pass."],
        },
    ]
    if isinstance(spec, TaskIntent):
        criteria.extend(_query_proxy_criteria(spec))
    return {"criteria": criteria}


def _query_proxy_criteria(spec: TaskIntent) -> list[Criteria]:
    criteria: list[Criteria] = []
    inferred = _infer_morphology_family(spec)
    if inferred:
        criteria.append(
            {
                "description": (
                    f"Rules include a {inferred} topology proxy using body scaffolds, "
                    "repeatable modules, or symmetric attachments where appropriate."
                ),
                "isSuccessful": False,
                "critiques": ["Awaiting evaluator pass."],
            }
        )
    capabilities = [*spec.contact_requirements, *spec.stability_requirements, *spec.success_criteria]
    if not capabilities:
        capabilities = _extract_capability_keywords(spec.task_goal)
    for capability in capabilities[:4]:
        criteria.append(
            {
                "description": _capability_proxy_goal(capability),
                "isSuccessful": False,
                "critiques": ["Awaiting evaluator pass."],
            }
        )
    for constraint in spec.hard_constraints[:3]:
        criteria.append(
            {
                "description": f"Rules include a structural proxy for constraint '{constraint}'.",
                "isSuccessful": False,
                "critiques": ["Awaiting evaluator pass."],
            }
        )
    return criteria


def _extract_capability_keywords(text: str) -> list[str]:
    lowered = text.lower()
    return [
        keyword
        for keyword in ("climb", "carry", "stable", "inspect", "crawl", "turn", "balance", "walk", "grasp", "push", "pull")
        if keyword in lowered
    ]


def _capability_proxy_goal(capability: str) -> str:
    lowered = capability.lower()
    if "climb" in lowered:
        return "Rules include a climbing proxy: repeated contact-capable appendage groups or segmented body support for rocky terrain."
    if "carry" in lowered or "payload" in lowered:
        return "Rules include a payload proxy: a central body scaffold with symmetric support modules."
    if "stable" in lowered or "balance" in lowered:
        return "Rules include a stability proxy: paired or mirrored support structures around the body scaffold."
    if "inspect" in lowered or "sensor" in lowered:
        return "Rules include an inspection proxy: a stable body module that can support sensor-bearing components downstream."
    if "crawl" in lowered:
        return "Rules include a crawling proxy: low-profile repeated body or limb modules."
    if "turn" in lowered:
        return "Rules include a turning proxy: articulated body-chain or appendage groups that allow directional changes."
    return f"Rules include a structural proxy for capability '{capability}'."


def _normalize_agent_messages(prompt_or_messages: Any) -> list[Any]:
    if isinstance(prompt_or_messages, str):
        return [HumanMessage(content=prompt_or_messages)]
    if isinstance(prompt_or_messages, tuple):
        prompt_or_messages = list(prompt_or_messages)
    if isinstance(prompt_or_messages, list):
        messages = []
        for item in prompt_or_messages:
            if hasattr(item, "content"):
                messages.append(item)
            elif isinstance(item, str):
                messages.append(HumanMessage(content=item))
            else:
                messages.append(HumanMessage(content=str(item)))
        return messages
    return [HumanMessage(content=str(prompt_or_messages))]


def _structured_agent_instruction(schema: Any, role: str) -> str:
    try:
        schema_json = json.dumps(TypeAdapter(schema).json_schema(), indent=2)
    except Exception:
        schema_json = json.dumps({"type": "object"}, indent=2)
    return "\n\n".join(
        [
            f"You are {role}.",
            "Return only valid JSON. Do not return markdown, comments, code fences, or prose.",
            "The JSON must validate against this schema:",
            schema_json,
            "If the schema is StructuralRules, every key and every list item must be an exact GrammarNodes short-form node ID from the prompt vocabulary.",
        ]
    )


def _schema_role_name(schema: Any) -> str:
    if schema is TaskIntent:
        return "query_normalizer_agent"
    if schema is StructuralRules:
        return "rule_builder_agent"
    if schema is TODO:
        return "evaluator_agent"
    return getattr(schema, "__name__", "structured_agent")


def _make_structured_agent(schema: Any) -> Any | None:
    model = os.environ.get("RESEARCH_LLM_MODEL") or os.environ.get("OPENAI_MODEL")
    return make_structured_llm(model, schema)


def _rule_builder_user_prompt(state: RoboGraphState) -> str:
    return "\n\n".join(
        [
            "Generate compile-safe structural_rules for this state.",
            "Treat each TODO criterion as a proxy goal to satisfy with graph topology.",
            _state_summary_for_prompt(state),
        ]
    )


def _state_summary_for_prompt(state: RoboGraphState) -> str:
    spec = state.get("spec")
    structural_rules = state.get("structural_rules")
    compile_result = _compile_result_from_state(state)
    payload = {
        "prompt": state.get("prompt"),
        "spec": _TASK_INTENT_ADAPTER.dump_python(spec) if isinstance(spec, TaskIntent) else spec,
        "structural_rules": structural_rules,
        "node_resolution": state.get("node_resolution"),
        "compile_result": _compile_result_prompt_payload(compile_result),
        "checklist": state.get("checklist"),
        "population": _normalize_population(state.get("population")),
    }
    return json.dumps(payload, indent=2, default=str)


def _normalize_population(value: Any) -> int:
    try:
        population = int(value)
    except (TypeError, ValueError):
        return DEFAULT_ROBOT_POPULATION
    return max(1, population)


_MORPHOLOGY_KEYWORD_MAP: dict[str, tuple[str, ...]] = {
    "quadruped": ("quadruped", "four-legged", "4-legged", "dog-like", "spot-like"),
    "humanoid": ("humanoid", "bipedal", "two-legged", "human-like"),
    "biped": ("biped",),
    "snake": ("snake", "serpentine"),
    "bird": ("bird", "avian", "winged"),
    "hexapod": ("hexapod", "six-legged", "insect-like"),
    "centipede": ("centipede",),
    "lizard": ("lizard",),
    "arachnid": ("arachnid", "spider"),
    "hybrid": ("hybrid",),
    "wheeled": ("wheeled", "wheel-based"),
}


def _infer_morphology_family(intent: TaskIntent) -> str | None:
    text = " ".join([
        intent.task_goal,
        " ".join(intent.terrain),
        " ".join(intent.contact_requirements),
    ]).lower()
    for family, keywords in _MORPHOLOGY_KEYWORD_MAP.items():
        if any(kw in text for kw in keywords):
            return family
    return None


def _coerce_task_intent(value: Any) -> TaskIntent | None:
    if value is None:
        return None
    if isinstance(value, TaskIntent):
        return value
    payload = _coerce_payload(value)
    if not isinstance(payload, dict) or "task_goal" not in payload:
        return None
    try:
        return _TASK_INTENT_ADAPTER.validate_python(payload)
    except Exception:
        return None


def _rules_payload_for_node_resolution(value: Any) -> dict[str, list[str]]:
    node_name = "resolve_grammar_node_names"
    if not isinstance(value, dict):
        raise ValueError(
            f"{node_name} expected state['structural_rules'] to be a dict payload "
            f"with key 'structural_rules', got {type(value).__name__}."
        )
    if "structural_rules" not in value:
        available_keys = ", ".join(sorted(str(key) for key in value.keys())) or "none"
        raise ValueError(
            f"{node_name} expected state['structural_rules']['structural_rules']; "
            f"available state['structural_rules'] keys: {available_keys}."
        )

    raw_rules = value["structural_rules"]
    if not isinstance(raw_rules, dict):
        raise ValueError(
            f"{node_name} expected state['structural_rules']['structural_rules'] "
            f"to be dict[str, list[str]], got {type(raw_rules).__name__}."
        )

    invalid_entries: list[str] = []
    for lhs, rhs in raw_rules.items():
        lhs_id = _string_or_none(lhs)
        lhs_label = repr(lhs)
        if lhs_id is None:
            invalid_entries.append(f"{lhs_label} has a non-string or blank LHS")
        if not isinstance(rhs, list):
            invalid_entries.append(
                f"{lhs_label} RHS is {type(rhs).__name__}, not list[str]"
            )
            continue
        bad_rhs_nodes = [repr(node) for node in rhs if _string_or_none(node) is None]
        if bad_rhs_nodes:
            invalid_entries.append(
                f"{lhs_label} RHS has non-string or blank nodes: "
                + ", ".join(bad_rhs_nodes[:3])
            )

    if invalid_entries:
        shown_entries = "; ".join(invalid_entries[:5])
        if len(invalid_entries) > 5:
            shown_entries += f"; ... {len(invalid_entries) - 5} more"
        raise ValueError(
            f"{node_name} expected structural_rules as dict[str, list[str]] "
            f"with non-empty string GrammarNodes IDs; invalid entries: {shown_entries}."
        )

    return cast(dict[str, list[str]], raw_rules)


def _coerce_structural_rules(value: Any) -> StructuralRules:
    payload = _coerce_payload(value)
    if isinstance(payload, dict):
        raw_rules = payload.get("structural_rules", payload.get("rules", {}))
        if isinstance(raw_rules, dict):
            rules = {
                str(lhs): [str(node) for node in rhs]
                for lhs, rhs in raw_rules.items()
                if isinstance(rhs, list)
            }
            return {"structural_rules": rules}
    return {"structural_rules": {}}


def _coerce_todo(value: Any) -> TODO:
    payload = _coerce_payload(value)
    criteria: list[Criteria] = []
    if isinstance(payload, dict) and isinstance(payload.get("criteria"), list):
        for raw in payload["criteria"]:
            if not isinstance(raw, dict):
                continue
            description = _string_or_none(raw.get("description"))
            if description is None:
                continue
            critiques = raw.get("critiques", [])
            criteria.append(
                {
                    "description": description,
                    "isSuccessful": bool(raw.get("isSuccessful")),
                    "critiques": [str(item) for item in critiques] if isinstance(critiques, list) else [str(critiques)],
                }
            )
    return {"criteria": criteria}


def _coerce_payload(value: Any) -> Any | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    content = getattr(value, "content", None)
    if isinstance(content, str):
        return _loads_structured_text(content)
    if isinstance(value, str):
        return _loads_structured_text(value)
    return None


def _loads_structured_text(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def run_grammar_agent_loop(
    prompt: str,
    initial_state: dict[str, Any] | None = None,
    *,
    config: AgentLoopConfig | None = None,
) -> AgentLoopResult:
    """Run the default grammar loop through the app-compatible function contract."""

    loop_config = config or AgentLoopConfig()
    state = build_structural_rules(
        prompt=prompt,
        initial_state=cast(RoboGraphState | None, initial_state),
        confirmed_spec=loop_config.confirmed_spec,
        normalizer_agent=loop_config.normalizer_agent,
        rule_builder_agent=loop_config.rule_builder_agent,
        evaluator_agent=loop_config.evaluator_agent,
        population=loop_config.population,
        max_attempts=loop_config.max_attempts,
        require_human_confirmation=loop_config.require_human_confirmation,
    )
    return AgentLoopResult(state=dict(state), hitl=summarize_hitl_state(state))


__all__ = [
    "AgentLoopConfig",
    "AgentLoopResult",
    "CompileAttempt",
    "CompileResult",
    "Criteria",
    "DEFAULT_ROBOT_POPULATION",
    "GRAMMAR_LOOP_TOOLS",
    "LangChainStructuredAgent",
    "RoboGraphState",
    "STRUCTURAL_RULE_GRAPH_NODE_ORDER",
    "STRUCTURAL_RULE_GRAPH_NODES",
    "StructuralRuleLoopContext",
    "StructuralRuleNode",
    "StructuralRules",
    "TODO",
    "await_human_confirmation_node",
    "build_initial_structural_rule_state",
    "build_query_normalizer_prompt",
    "build_structural_rules_node",
    "build_structural_rules",
    "compile_structural_rules",
    "compile_structural_rules_node",
    "evaluate_rules_node",
    "fetch_grammar_from_db",
    "make_initial_checklist_node",
    "make_structural_rule_loop_context",
    "make_structural_rule_agents_from_chat_model",
    "make_structured_agent_from_chat_model",
    "normalize_query_node",
    "repair_structural_rule_node_names",
    "repair_structural_rule_node_names_safely",
    "resolve_grammar_node_names_node",
    "route_after_evaluation",
    "route_after_normalize",
    "run_grammar_agent_loop",
    "sample_rule_builder_examples",
    "summarize_hitl_state",
    "summarize_hitl_node",
]
