from __future__ import annotations

import json
from pathlib import Path

from apps.api.routes import designs
from apps.api.workspace_store import WorkspaceStore
from packages.pipeline import grammar_graph
from packages.research.agent_loops import AgentLoopConfig, AgentLoopResult, register_agent_loop


def test_generate_designs_returns_visible_grammar_hitl(
    monkeypatch,
    tmp_path: Path,
):
    store = WorkspaceStore(tmp_path / "workspace.sqlite3")
    prompt_events: list[dict] = []
    monkeypatch.setattr(designs, "workspace_store", store)
    monkeypatch.setattr(designs, "log_prompt_query", lambda **kwargs: prompt_events.append(kwargs) or "event-1")
    monkeypatch.setattr(
        grammar_graph,
        "fetch_grammar_from_db",
        lambda **_kwargs: [
            ("S", "Start"),
            ("BODY_CHAIN", "Body Chain"),
            ("BODY_SEG", "Body Segment"),
            ("LEG_PAIR", "Leg Pair"),
        ],
    )
    monkeypatch.setattr(
        grammar_graph,
        "fetch_rules_from_db",
        lambda **_kwargs: {
            "S -> BODY_CHAIN": "Start recursive body chain.",
            "BODY_CHAIN -> BODY_SEG LEG_PAIR": "Attach paired limbs to a segment.",
        },
    )
    store.save_ingest_job(
        {
            "id": "job-1",
            "source_url": None,
            "er16_plan_json": json.dumps(
                {
                    "task_goal": "build a stable quadruped",
                    "affordances": ["stable locomotion"],
                    "success_criteria": "grammar compiles",
                    "search_queries": ["quadruped robot"],
                }
            ),
            "status": "analysis_ready",
        }
    )

    response = designs.generate_designs(designs.GenerateDesignsRequest(ingest_job_id="job-1"))

    assert response["model_preferred_id"] == "A"
    assert response["population"] == 6
    assert len(response["candidates"]) == 6
    assert response["grammar_hitl"]["compile_safe"] is True
    assert response["grammar_hitl"]["structural_rules"]["S"] == ["BODY_CHAIN"]
    assert prompt_events[0]["event_type"] == "robot_generation_query"
    assert prompt_events[0]["prompt"] == "build a stable quadruped"
    assert prompt_events[0]["normalized_query"]["task_goal"] == "build a stable quadruped"
    assert response["grammar_hitl"]["inferred_morphology"] == "quadruped"
    assert prompt_events[0]["population"] == 6

    preferred_id = response["model_preferred_id"]
    spec = designs.get_design_spec(response["design_ids"][preferred_id])
    checkpoints = designs.get_design_checkpoints(response["design_ids"][preferred_id])

    assert spec["design"]["candidate_id"] == preferred_id
    assert checkpoints["items"]
    assert checkpoints["items"][0]["db_id"] == checkpoints["items"][0]["id"]

    custom_response = designs.generate_designs(
        designs.GenerateDesignsRequest(ingest_job_id="job-1", population=4)
    )

    assert custom_response["population"] == 4
    assert len(custom_response["candidates"]) == 4
    assert set(custom_response["design_ids"]) == {
        candidate["candidate_id"] for candidate in custom_response["candidates"]
    }


def test_generate_designs_can_select_registered_agent_loop(
    monkeypatch,
    tmp_path: Path,
):
    store = WorkspaceStore(tmp_path / "workspace.sqlite3")
    monkeypatch.setattr(designs, "workspace_store", store)
    monkeypatch.setattr(designs, "log_prompt_query", lambda **_kwargs: "event-1")

    def tiny_loop(
        prompt: str,
        initial_state: dict | None = None,
        *,
        config: AgentLoopConfig | None = None,
    ) -> AgentLoopResult:
        assert initial_state == {
            "prompt": "build a tiny walker",
            "candidates": [],
            "population": 2,
        }
        assert config is not None
        return AgentLoopResult(
            state={
                "prompt": prompt,
                "population": config.population,
                "hitl": {
                    "spec": {"task_goal": prompt},
                    "inferred_morphology": "biped",
                    "checklist": {"criteria": []},
                    "structural_rules": {"S": ["BODY"]},
                    "node_resolution": {"corrections": [], "unresolved": []},
                    "invalid_grammar_nodes": [],
                    "population": config.population,
                    "compile_safe": True,
                    "compile_error": None,
                    "awaiting_human": False,
                    "langsmith_trace_id": None,
                    "messages": [],
                },
            },
            hitl={
                "spec": {"task_goal": prompt},
                "inferred_morphology": "biped",
                "checklist": {"criteria": []},
                "structural_rules": {"S": ["BODY"]},
                "node_resolution": {"corrections": [], "unresolved": []},
                "invalid_grammar_nodes": [],
                "population": config.population,
                "compile_safe": True,
                "compile_error": None,
                "awaiting_human": False,
                "langsmith_trace_id": None,
                "messages": [],
            },
        )

    register_agent_loop("tiny-route-loop", tiny_loop)
    store.save_ingest_job(
        {
            "id": "job-1",
            "source_url": None,
            "er16_plan_json": json.dumps({"task_goal": "build a tiny walker"}),
            "status": "analysis_ready",
        }
    )

    response = designs.generate_designs(
        designs.GenerateDesignsRequest(
            ingest_job_id="job-1",
            population=2,
            agent_loop="tiny-route-loop",
        )
    )

    assert response["agent_loop"] == "tiny-route-loop"
    assert response["population"] == 2
    assert response["grammar_hitl"]["structural_rules"] == {"S": ["BODY"]}


def test_list_design_agent_loops_includes_default() -> None:
    response = designs.list_design_agent_loops()

    assert response["default"] == "grammar"
    assert "grammar" in response["agent_loops"]
