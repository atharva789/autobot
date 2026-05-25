from __future__ import annotations

from pathlib import Path

from apps.api.routes import ingest
from apps.api.workspace_store import WorkspaceStore


class FakeIngestService:
    def analyze_prompt(self, prompt: str):
        return {
            "task_goal": prompt,
            "affordances": ["stable locomotion"],
            "success_criteria": "grammar compiles",
            "search_queries": ["quadruped robot"],
        }


def test_ingest_logs_raw_prompt_and_selected_query(monkeypatch, tmp_path: Path):
    events: list[dict] = []
    monkeypatch.setenv("SKIP_YOUTUBE_SEARCH", "1")
    monkeypatch.setattr(ingest, "_svc", FakeIngestService())
    monkeypatch.setattr(ingest, "workspace_store", WorkspaceStore(tmp_path / "workspace.sqlite3"))
    monkeypatch.setattr(ingest, "log_prompt_query", lambda **kwargs: events.append(kwargs) or "event-1")

    response = ingest.start_ingest(ingest.IngestRequest(prompt="make a robot that skates"))

    assert response["status"] == "reference_skipped"
    assert [event["event_type"] for event in events] == [
        "ingest_prompt_received",
        "ingest_query_selected",
    ]
    assert events[0]["prompt"] == "make a robot that skates"
    assert events[0]["query_text"] == "make a robot that skates"
    assert events[1]["query_text"] == "quadruped robot"
    assert events[1]["metadata"]["status"] == "reference_skipped"
