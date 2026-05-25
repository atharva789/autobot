from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import nbformat

from packages.pipeline.schemas import TaskIntent


NOTEBOOK_PATH = Path("packages/research/notebooks/rl_playground.ipynb")


def _notebook_source() -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text())
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def _load_loop_helpers() -> dict[str, object]:
    namespace: dict[str, object] = {}
    notebook = nbformat.read(NOTEBOOK_PATH, as_version=4)
    with contextlib.redirect_stdout(io.StringIO()):
        for cell_index in (3, 4, 5):
            source = "".join(notebook.cells[cell_index].source)
            exec(compile(source, f"{NOTEBOOK_PATH.name}:cell-{cell_index}", "exec"), namespace)
    return namespace


class SequencedRuleBuilder:
    def __init__(self, rules: list[dict[str, list[str]]]) -> None:
        self.rules = rules
        self.calls = 0

    def invoke(self, _messages: object) -> dict[str, dict[str, list[str]]]:
        self.calls += 1
        index = min(self.calls - 1, len(self.rules) - 1)
        return {"structural_rules": self.rules[index]}


class SuccessfulEvaluator:
    def invoke(self, _messages: object) -> dict[str, list[dict[str, object]]]:
        return {
            "criteria": [
                {
                    "description": (
                        "Generated structural rules compile against GrammarNodes vocabulary."
                    ),
                    "isSuccessful": True,
                    "critiques": [],
                }
            ]
        }


def test_rl_playground_compiler_centric_loop_keeps_traced_compile_router() -> None:
    source = _notebook_source()

    assert "def _route_after_compiling(state: RoboGraphState) -> str:" in source
    assert 'compile_result = state.get("compile_result")' in source
    assert "elif attempts < max_attempts:" in source
    assert '"route_after_compiling"' in source
    assert 'metadata={"router_decision": decision}' in source
    assert 'observation.update(output={"decision": decision})' in source
    assert "_compile_result_prompt_payload(compile_result)" in source


def test_rl_playground_compiler_centric_loop_uses_reusable_nodes_and_traces_loop() -> None:
    source = _notebook_source()

    assert "def _compiler_centric_loop(*, context: StructuralRuleLoopContext) -> Any:" in source
    assert "_bind_structural_rule_node(STRUCTURAL_RULE_GRAPH_NODES[node_name], context)" in source
    assert 'graph.add_conditional_edges(\n        "compile_structural_rules",\n        _route_after_compiling,' in source
    assert "def run_compiler_centric_loop(" in source
    assert '"robogrammar.compiler_centric_loop"' in source
    assert "with langsmith_trace_context():" in source
    assert 'final_state["hitl"] = summarize_hitl_state(final_state)' in source


def test_rl_playground_compiler_feedback_loop_records_rca_and_routes_through_feedback() -> None:
    source = _notebook_source()

    assert "Root cause: compile-invalid retries need exact compiler feedback" in source
    assert "def _compiler_feedback_node(" in source
    assert '"Compiler feedback is resolved."' in source
    assert '"compiler_feedback"' in source
    assert 'graph.add_edge("compile_structural_rules", "compiler_feedback")' in source
    assert 'graph.add_conditional_edges(\n        "compiler_feedback",\n        _route_after_compiling,' in source
    assert "def run_compiler_feedback_loop(" in source
    assert '"robogrammar.compiler_feedback_loop"' in source


def test_rl_playground_new_loops_execute_with_deterministic_agents() -> None:
    helpers = _load_loop_helpers()
    make_context = helpers["make_structural_rule_loop_context"]
    run_compiler_centric_loop = helpers["run_compiler_centric_loop"]
    run_compiler_feedback_loop = helpers["run_compiler_feedback_loop"]

    centric_builder = SequencedRuleBuilder([{"S": ["BODY"]}])
    centric_context = make_context(
        confirmed_spec=TaskIntent(task_goal="Design a compact body robot."),
        rule_builder_agent=centric_builder,
        evaluator_agent=SuccessfulEvaluator(),
    )

    centric_state = run_compiler_centric_loop(
        "Design a compact body robot.",
        context=centric_context,
        max_attempts=2,
    )

    assert centric_builder.calls == 1
    assert centric_state["attempts"] == 1
    assert centric_state["hitl"]["compile_safe"] is True

    feedback_builder = SequencedRuleBuilder(
        [
            {"S": ["JETPACK"]},
            {"S": ["BODY"]},
        ]
    )
    feedback_context = make_context(
        confirmed_spec=TaskIntent(task_goal="Design a compact body robot."),
        rule_builder_agent=feedback_builder,
        evaluator_agent=SuccessfulEvaluator(),
    )

    feedback_state = run_compiler_feedback_loop(
        "Design a compact body robot.",
        context=feedback_context,
        max_attempts=2,
    )

    assert feedback_builder.calls == 2
    assert feedback_state["attempts"] == 2
    assert feedback_state["hitl"]["compile_safe"] is True
    assert any("compiler_feedback:" in message for message in feedback_state["messages"])
