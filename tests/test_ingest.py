import pytest
from unittest.mock import patch, MagicMock
from demo.services.ingest_service import IngestService


@pytest.fixture
def svc():
    return IngestService(
        gemini_api_key="fake",
        youtube_api_key="fake",
        supabase_url="https://fake.supabase.co",
        supabase_key="fake",
    )


def test_er16_plan_structure(svc):
    mock_resp = MagicMock()
    mock_resp.text = '{"task_goal":"walk","affordances":["biped"],"success_criteria":"reach goal","search_queries":["human walking demo"]}'
    with patch.object(svc._gemini_model, "generate_content", return_value=mock_resp):
        plan = svc.analyze_prompt("make it walk")
    assert "task_goal" in plan
    assert "search_queries" in plan
    assert isinstance(plan["search_queries"], list)


def test_youtube_search_returns_video_id(svc):
    mock_search = MagicMock()
    mock_search.execute.return_value = {
        "items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Walking demo"}}]
    }
    with patch.object(svc, "_youtube_search", return_value=mock_search):
        vid_id = svc.search_youtube("human walking demo")
    assert vid_id == "abc123"
