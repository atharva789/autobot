from __future__ import annotations

from pathlib import Path

from demo.workspace_store import WorkspaceStore


def test_workspace_store_ingest_design_and_evolution_crud(tmp_path: Path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite3")

    ingest = store.save_ingest_job(
        {
            "id": "job-1",
            "source_url": "https://youtube.com/watch?v=abc123",
            "er16_plan_json": '{"task_goal":"carry box","search_queries":["person carrying box"]}',
            "gvhmr_job_id": "gvhmr-1",
            "status": "processing",
            "selected_query": "person carrying box",
            "selection_rationale": "Closest motion match.",
            "candidate_reviews": [{"video_id": "abc123", "score": 9}],
        }
    )
    assert ingest["id"] == "job-1"
    assert ingest["candidate_reviews_json"] == [{"video_id": "abc123", "score": 9}]

    store.create_design(
        {
            "id": "design-a",
            "ingest_job_id": "job-1",
            "candidate_id": "A",
            "design_json": {"candidate_id": "A", "embodiment_class": "biped"},
            "render_json": {"mjcf": "<mujoco/>"},
            "is_model_preferred": True,
            "is_user_selected": False,
            "screening_score": 0.91,
        }
    )
    store.create_design(
        {
            "id": "design-b",
            "ingest_job_id": "job-1",
            "candidate_id": "B",
            "design_json": {"candidate_id": "B", "embodiment_class": "quadruped"},
            "render_json": {"mjcf": "<mujoco/>"},
            "is_model_preferred": False,
            "is_user_selected": False,
            "screening_score": 0.72,
        }
    )

    listed = store.list_designs_by_ingest("job-1")
    assert [item["candidate_id"] for item in listed] == ["A", "B"]
    assert listed[0]["render_json"]["mjcf"] == "<mujoco/>"

    store.clear_design_selection("job-1")
    store.update_design("design-b", {"is_user_selected": True})
    assert store.get_design("design-b")["is_user_selected"] is True

    evo = store.create_evolution("run-1", evo_id="evo-1")
    assert evo["id"] == "evo-1"
    store.update_evolution("evo-1", {"design_id": "design-b", "status": "running"})
    assert store.get_evolution("evo-1")["design_id"] == "design-b"

    draft = store.save_program_draft(
        {
            "id": "draft-1",
            "evolution_id": "evo-1",
            "generator": "gemini",
            "draft_content": "# Program",
            "approved": False,
        }
    )
    assert draft["approved"] is False

    store.update_program_draft_by_evolution(
        "evo-1",
        {"approved": True, "user_edited_content": "# User Program"},
    )
    updated_draft = store.get_program_draft_by_evolution("evo-1")
    assert updated_draft["approved"] is True
    assert updated_draft["user_edited_content"] == "# User Program"
