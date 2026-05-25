from __future__ import annotations

from uuid import UUID

from evals.backfill_langfuse_trace_spans import (
    _io_payload,
    _langsmith_run_type,
    _observation_metadata,
    _synthetic_summarize_hitl_run_tree,
)


def test_io_payload_parses_json_strings() -> None:
    assert _io_payload('{"prompt": "quadruped", "population": 3}', field_name="input") == {
        "prompt": "quadruped",
        "population": 3,
    }
    assert _io_payload("not-json", field_name="output") == {"output": "not-json"}


def test_observation_metadata_marks_graph_tool_and_agent_roles() -> None:
    graph_agent = {
        "id": "obs-1",
        "traceId": "trace-1",
        "parentObservationId": "root",
        "name": "build_structural_rules",
        "type": "AGENT",
        "startTime": "2026-05-21T14:35:01.288Z",
        "endTime": "2026-05-21T14:35:07.178Z",
        "level": "DEFAULT",
        "statusMessage": "",
        "metadata": {"attempt": 1},
    }

    metadata = _observation_metadata(graph_agent)

    assert metadata["source"] == "langfuse-backfill"
    assert metadata["grammar_loop_node"] == "build_structural_rules"
    assert metadata["langgraph_node"] == "build_structural_rules"
    assert metadata["agent_call"] == "build_structural_rules"
    assert metadata["span_roles"] == ["graph_node", "agent_call"]
    assert metadata["attempt"] == 1


def test_compile_observation_is_langsmith_tool_with_tool_role() -> None:
    observation = {
        "id": "obs-2",
        "traceId": "trace-1",
        "parentObservationId": "root",
        "name": "compile_structural_rules",
        "type": "TOOL",
    }

    assert _langsmith_run_type(observation) == "tool"
    metadata = _observation_metadata(observation)
    assert metadata["span_kind"] == "tool_call"
    assert metadata["tool_name"] == "compile_structural_rules"
    assert "graph_node" in metadata["span_roles"]
    assert "tool_call" in metadata["span_roles"]


def test_synthetic_summarize_hitl_span_is_marked_as_graph_node() -> None:
    class Root:
        id = "019e5086-2d42-7e32-bc49-b1b1505da1cb"
        trace_id = id
        dotted_order = "20260522T163031235619Z019e5086-2d42-7e32-bc49-b1b1505da1cb"
        inputs = {"input": {"prompt": "quadruped"}}
        outputs = {"output": {"awaiting_human": False}}
        extra = {
            "metadata": {
                "langfuse_trace_id": "trace-1",
                "langfuse_observation_id": "root-observation",
            }
        }

    run = _synthetic_summarize_hitl_run_tree(
        project_name="project",
        root=Root(),
        root_trace_id=UUID(Root.trace_id),
        root_id=UUID(Root.id),
        root_dotted_order=Root.dotted_order,
    )

    metadata = run.extra["metadata"]
    assert run.name == "summarize_hitl"
    assert run.outputs == {"output": {"awaiting_human": False}}
    assert metadata["synthetic_span"] is True
    assert metadata["grammar_loop_node"] == "summarize_hitl"
    assert metadata["span_roles"] == ["graph_node"]
