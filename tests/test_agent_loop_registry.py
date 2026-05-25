from __future__ import annotations

from contextlib import contextmanager

import packages.research.agent_loops.registry as registry
from packages.research.agent_loops import grammar_loop
from packages.research.agent_loops import (
    AgentLoopConfig,
    AgentLoopResult,
    list_agent_loops,
    register_agent_loop,
    run_agent_loop,
)


def test_agent_loop_registry_runs_function_contract(monkeypatch) -> None:
    @contextmanager
    def fake_observation(*_args, **_kwargs):
        class FakeObservation:
            def update(self, **_update_kwargs):
                return None

        yield FakeObservation()

    monkeypatch.setattr(registry, "langsmith_observation", fake_observation)
    monkeypatch.setattr(registry, "get_langsmith_trace_id", lambda: "trace-registry")

    def tiny_loop(
        prompt: str,
        initial_state: dict | None = None,
        *,
        config: AgentLoopConfig | None = None,
    ) -> AgentLoopResult:
        assert config is not None
        state = {
            "prompt": prompt,
            "population": config.population,
            "initial": initial_state or {},
        }
        return AgentLoopResult(
            state=state,
            hitl={
                "spec": {"task_goal": prompt},
                "structural_rules": {"S": ["BODY"]},
                "population": config.population,
                "compile_safe": True,
            },
        )

    register_agent_loop("tiny-test-loop", tiny_loop)

    result = run_agent_loop(
        "tiny-test-loop",
        "make a small robot",
        {"seed": 7},
        config=AgentLoopConfig(population=3),
    )

    assert "tiny-test-loop" in list_agent_loops()
    assert result.state["initial"] == {"seed": 7}
    assert result.hitl["spec"]["task_goal"] == "make a small robot"
    assert result.hitl["population"] == 3
    assert result.hitl["langsmith_trace_id"] == "trace-registry"


def test_existing_grammar_loop_is_registered() -> None:
    assert "grammar" in list_agent_loops()


def test_grammar_loop_exports_reusable_nodes_and_tools() -> None:
    expected_nodes = (
        "normalize_query",
        "await_human_confirmation",
        "make_initial_checklist",
        "build_structural_rules",
        "resolve_grammar_node_names",
        "compile_structural_rules",
        "evaluate_rules",
        "summarize_hitl",
    )

    assert grammar_loop.STRUCTURAL_RULE_GRAPH_NODE_ORDER == expected_nodes
    assert tuple(grammar_loop.STRUCTURAL_RULE_GRAPH_NODES) == expected_nodes
    assert (
        grammar_loop.STRUCTURAL_RULE_GRAPH_NODES["normalize_query"]
        is grammar_loop.normalize_query_node
    )
    assert (
        grammar_loop.GRAMMAR_LOOP_TOOLS["compile_structural_rules"]
        is grammar_loop.compile_structural_rules
    )

    context = grammar_loop.StructuralRuleLoopContext()
    state = grammar_loop.build_initial_structural_rule_state("make a robot")
    update = grammar_loop.normalize_query_node(state, context)

    assert update["prompt"] == "make a robot"
    assert update["spec"].task_goal == "make a robot"


def test_grammar_loop_wraps_swappable_chat_model_as_rule_builder_agent() -> None:
    class FakeChatModel:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages

            class Response:
                content = '{"structural_rules": {"S": ["BODY"]}}'

            return Response()

    model = FakeChatModel()
    agent = grammar_loop.make_structured_agent_from_chat_model(
        model,
        grammar_loop.StructuralRules,
        role="rule_builder_agent",
    )

    response = agent.invoke(
        [
            grammar_loop.SystemMessage(content="Vocabulary: S, BODY"),
            grammar_loop.HumanMessage(content="Build rules."),
        ]
    )

    assert response.content == '{"structural_rules": {"S": ["BODY"]}}'
    assert "You are rule_builder_agent." in model.messages[0].content
    assert "Return only valid JSON" in model.messages[0].content
    assert model.messages[1].content == "Vocabulary: S, BODY"
