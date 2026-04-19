import os
import builtins
import pytest
from unittest.mock import patch, MagicMock
from demo.services.ingest_service import (
    IngestService,
    SearchCandidate,
    resolve_gemini_api_key,
    _parse_iso8601_duration,
    _MIN_VIDEO_SECONDS,
    _MAX_VIDEO_SECONDS,
)


@pytest.fixture
def svc():
    return IngestService(
        gemini_api_key="fake",
        youtube_api_key="fake",
        supabase_url="https://fake.supabase.co",
        supabase_key="fake",
    )


def test_er16_plan_structure(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = MagicMock()
    svc._genai_types = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = (
        '{"task_goal":"walk","affordances":["biped"],'
        '"success_criteria":"reach goal",'
        '"search_queries":["person walking side view","human walking fixed camera","person walking full body"]}'
    )
    with patch.object(svc._gemini_client.models, "generate_content", return_value=mock_resp):
        plan = svc.analyze_prompt("make it walk")
    assert "task_goal" in plan
    assert "search_queries" in plan
    assert isinstance(plan["search_queries"], list)


def test_resolve_gemini_api_key_reads_only_gemini_name(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert resolve_gemini_api_key() == ""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    assert resolve_gemini_api_key() == "gemini-key"


def test_analyze_prompt_raises_if_gemini_sdk_missing(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = None
    with pytest.raises(RuntimeError, match="Gemini SDK is not installed"):
        svc.analyze_prompt("make it walk")


def test_analyze_prompt_requires_gemini_api_key(svc, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    svc._gemini_client = MagicMock()
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY must be set"):
        svc.analyze_prompt("make it walk")


def test_analyze_prompt_raises_if_gemini_response_not_text(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = MagicMock()
    svc._genai_types = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = MagicMock()
    with patch.object(svc._gemini_client.models, "generate_content", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="non-text response"):
            svc.analyze_prompt("make it walk")


def test_analyze_prompt_raises_if_gemini_response_not_json(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = MagicMock()
    svc._genai_types = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "not json"
    with patch.object(svc._gemini_client.models, "generate_content", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            svc.analyze_prompt("make it walk")


def test_analyze_prompt_accepts_markdown_fenced_json(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = MagicMock()
    svc._genai_types = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = (
        "```json\n"
        '{"task_goal":"walk","affordances":["biped"],'
        '"success_criteria":"reach goal","search_queries":["person walking side view","human walking fixed camera","person walking full body"]}\n'
        "```"
    )
    with patch.object(svc._gemini_client.models, "generate_content", return_value=mock_resp):
        plan = svc.analyze_prompt("make it walk")
    assert plan["task_goal"] == "walk"


def test_youtube_search_candidates_return_video_metadata(svc):
    mock_search = MagicMock()
    mock_search.execute.return_value = {
        "items": [{
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Person carrying box upstairs",
                "description": "A person carries a box up a staircase.",
                "channelTitle": "Reference Channel",
            },
        }]
    }
    with patch.object(svc, "_youtube_search", return_value=mock_search):
        candidates = svc.search_youtube_candidates("person carrying box upstairs")
    assert candidates[0]["video_id"] == "abc123"
    assert candidates[0]["query"] == "person carrying box upstairs"
    assert "youtube.com/watch?v=abc123" in candidates[0]["url"]


def test_youtube_search_raises_on_empty_results(svc):
    mock_search = MagicMock()
    mock_search.execute.return_value = {"items": []}
    with patch.object(svc, "_youtube_search", return_value=mock_search):
        with pytest.raises(LookupError, match="No YouTube videos found"):
            svc.search_youtube_candidates("human walking demo")


def test_youtube_search_raises_if_sdk_missing(svc):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "googleapiclient.discovery":
            raise ImportError("No module named 'googleapiclient'")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="YouTube SDK is not installed"):
            svc.search_youtube_candidates("human walking demo")


def test_youtube_search_raises_on_missing_video_ids(svc):
    mock_search = MagicMock()
    mock_search.execute.return_value = {
        "items": [{"id": {}, "snippet": {"title": "Walking demo"}}]
    }
    with patch.object(svc, "_youtube_search", return_value=mock_search):
        with pytest.raises(LookupError, match="No playable YouTube video IDs found"):
            svc.search_youtube_candidates("human walking demo")

def test_youtube_search_uses_reliability_filters(svc):
    mock_build = MagicMock()
    mock_build.return_value.search.return_value.list.return_value = "request"

    with patch("googleapiclient.discovery.build", mock_build):
        request = svc._youtube_search("person carrying box upstairs")

    assert request == "request"
    mock_build.assert_called_once_with("youtube", "v3", developerKey="fake")
    mock_build.return_value.search.return_value.list.assert_called_once_with(
        q="person carrying box upstairs",
        part="id,snippet",
        type="video",
        maxResults=10,
        order="relevance",
        relevanceLanguage="en",
        safeSearch="moderate",
        videoEmbeddable="true",
        videoDuration="short",
        videoDefinition="high",
        videoCaption=None,
    )


def test_collect_candidates_uses_multiple_search_profiles_and_deduplicates(svc):
    def fake_candidates(video_id: str, *, query: str, profile: str) -> list[dict]:
        return [
            {
                "video_id": video_id,
                "title": f"{profile} {video_id}",
                "description": "",
                "channel_title": "Reference Channel",
                "query": query,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "search_profile": profile,
            }
        ]

    with patch.object(
        svc,
        "search_youtube_candidates",
        side_effect=[
            fake_candidates("vid-a", query="human carrying box upstairs", profile="captioned_relevance")
            + fake_candidates("vid-shared", query="human carrying box upstairs", profile="captioned_relevance"),
            fake_candidates("vid-shared", query="human carrying box upstairs", profile="high_def_relevance")
            + fake_candidates("vid-b", query="human carrying box upstairs", profile="high_def_relevance"),
            fake_candidates("vid-c", query="human carrying box upstairs", profile="popular_short"),
        ],
    ) as mock_search, patch.object(
        svc,
        "_fetch_video_details",
        return_value={
            "vid-a": {"duration_seconds": 25, "view_count": 1000},
            "vid-shared": {"duration_seconds": 30, "view_count": 2000},
            "vid-b": {"duration_seconds": 35, "view_count": 3000},
            "vid-c": {"duration_seconds": 40, "view_count": 4000},
        },
    ):
        result = svc._collect_candidate_videos(
            ["human carrying box upstairs"],
            shortlist_size=4,
        )

    assert [candidate.video_id for candidate in result] == [
        "vid-a",
        "vid-shared",
        "vid-b",
        "vid-c",
    ]
    assert [call.kwargs["search_options"]["name"] for call in mock_search.call_args_list] == [
        "captioned_relevance",
        "high_def_relevance",
        "popular_short",
    ]


def test_select_reference_video_refines_when_first_round_is_bad(svc):
    initial_candidates = [
        SearchCandidate(
            video_id="bad-1",
            title="Awkward handheld stairs",
            description="",
            channel_title="Channel A",
            query="person carrying box upstairs",
            url="https://www.youtube.com/watch?v=bad-1",
            duration_seconds=40,
            search_profile="captioned_relevance",
        ),
        SearchCandidate(
            video_id="bad-2",
            title="Occluded staircase carry",
            description="",
            channel_title="Channel B",
            query="person carrying box upstairs",
            url="https://www.youtube.com/watch?v=bad-2",
            duration_seconds=38,
            search_profile="high_def_relevance",
        ),
    ]
    refined_candidates = [
        SearchCandidate(
            video_id="good-1",
            title="Person carrying a box up stairs side view",
            description="",
            channel_title="Channel D",
            query="person carrying box up stairs side view",
            url="https://www.youtube.com/watch?v=good-1",
            duration_seconds=44,
            search_profile="captioned_relevance",
        ),
        SearchCandidate(
            video_id="good-2",
            title="Human carrying package upstairs fixed camera",
            description="",
            channel_title="Channel E",
            query="person carrying box up stairs side view",
            url="https://www.youtube.com/watch?v=good-2",
            duration_seconds=41,
            search_profile="high_def_relevance",
        ),
    ]

    with patch.object(
        svc,
        "_collect_candidate_videos",
        side_effect=[initial_candidates, refined_candidates],
    ) as mock_collect, patch.object(
        svc,
        "_review_video_candidates",
        side_effect=[
            {
                "proceed": False,
                "best_video_id": None,
                "rationale": "All three have too much camera motion.",
                "refined_queries": [
                    "person carrying box up stairs side view",
                ],
                "candidate_reviews": [],
            },
            {
                "proceed": True,
                "best_video_id": "good-1",
                "rationale": "This one has the clearest side view and stable camera.",
                "refined_queries": [],
                "candidate_reviews": [
                    {
                        "video_id": "good-1",
                        "verdict": "good",
                        "score": 9,
                        "reason": "Clear full-body view with stable framing.",
                    }
                ],
            },
        ],
    ):
        selected = svc.select_reference_video(
            "I want the robot to carry a box up a flight of stairs.",
            {
                "task_goal": "carry a box up a flight of stairs",
                "search_queries": ["person carrying box upstairs"],
            },
        )

    assert selected["video_id"] == "good-1"
    assert selected["query"] == "person carrying box up stairs side view"
    assert mock_collect.call_args_list[0].args[0] == ["person carrying box upstairs"]
    assert mock_collect.call_args_list[1].args[0] == ["person carrying box up stairs side view"]


def test_select_reference_video_raises_when_queries_invalid(svc):
    with pytest.raises(ValueError, match="No valid YouTube search queries"):
        svc.select_reference_video("lift a box", {"search_queries": ["", "  ", None]})


# --- Duration parsing ---

def test_parse_iso8601_duration_seconds_only():
    assert _parse_iso8601_duration("PT30S") == 30


def test_parse_iso8601_duration_minutes_and_seconds():
    assert _parse_iso8601_duration("PT1M30S") == 90


def test_parse_iso8601_duration_hours():
    assert _parse_iso8601_duration("PT1H") == 3600


def test_parse_iso8601_duration_empty():
    assert _parse_iso8601_duration("") == 0


def test_parse_iso8601_duration_invalid():
    assert _parse_iso8601_duration("not-a-duration") == 0


# --- Duration-based filtering in _collect_candidate_videos ---

def _make_candidate(video_id, query="q"):
    return {
        "video_id": video_id,
        "title": f"Video {video_id}",
        "description": "",
        "channel_title": "Channel",
        "query": query,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "search_profile": "captioned_relevance",
    }


def test_duration_filter_rejects_too_short(svc):
    with patch.object(
        svc, "search_youtube_candidates", return_value=[_make_candidate("short-1")]
    ), patch.object(
        svc,
        "_fetch_video_details",
        return_value={"short-1": {"duration_seconds": 3, "view_count": 5000}},
    ):
        with pytest.raises(LookupError, match="outside the preferred duration range"):
            svc._collect_candidate_videos(["human walking"], shortlist_size=3)


def test_duration_filter_rejects_too_long(svc):
    with patch.object(
        svc,
        "search_youtube_candidates",
        return_value=[_make_candidate("long-1"), _make_candidate("ok-1")],
    ), patch.object(
        svc,
        "_fetch_video_details",
        return_value={
            "long-1": {"duration_seconds": 600, "view_count": 1000},
            "ok-1": {"duration_seconds": 45, "view_count": 1000},
        },
    ):
        result = svc._collect_candidate_videos(["human walking"], shortlist_size=1)
    assert result[0].video_id == "ok-1"


def test_duration_filter_keeps_boundary_values(svc):
    with patch.object(
        svc,
        "search_youtube_candidates",
        return_value=[_make_candidate("min-v"), _make_candidate("max-v")],
    ), patch.object(
        svc,
        "_fetch_video_details",
        return_value={
            "min-v": {"duration_seconds": _MIN_VIDEO_SECONDS, "view_count": 1000},
            "max-v": {"duration_seconds": _MAX_VIDEO_SECONDS, "view_count": 1000},
        },
    ):
        result = svc._collect_candidate_videos(["human walking"], shortlist_size=2)
    ids = [c.video_id for c in result]
    assert "min-v" in ids
    assert "max-v" in ids


def test_duration_filter_uses_unknown_duration_when_no_in_range(svc):
    with patch.object(
        svc,
        "search_youtube_candidates",
        return_value=[_make_candidate("unknown-duration")],
    ), patch.object(
        svc,
        "_fetch_video_details",
        return_value={},
    ):
        result = svc._collect_candidate_videos(["human walking"], shortlist_size=3)
    assert len(result) == 1
    assert result[0].video_id == "unknown-duration"
    assert result[0].duration_seconds == 0


def test_duration_filter_raises_when_all_known_out_of_range(svc):
    with patch.object(
        svc,
        "search_youtube_candidates",
        return_value=[_make_candidate("too-short"), _make_candidate("too-long")],
    ), patch.object(
        svc,
        "_fetch_video_details",
        return_value={
            "too-short": {"duration_seconds": 4, "view_count": 1000},
            "too-long": {"duration_seconds": 240, "view_count": 2000},
        },
    ):
        with pytest.raises(LookupError, match="outside the preferred duration range"):
            svc._collect_candidate_videos(["human walking"], shortlist_size=3)


def test_collect_candidates_tolerates_video_details_failure(svc):
    """If _fetch_video_details raises, candidates are returned without filtering."""
    with patch.object(
        svc,
        "search_youtube_candidates",
        return_value=[_make_candidate("vid-a")],
    ), patch.object(
        svc, "_fetch_video_details", side_effect=RuntimeError("API quota")
    ):
        result = svc._collect_candidate_videos(["human walking"], shortlist_size=3)
    assert result[0].video_id == "vid-a"


# --- Actual video review usage in _review_video_candidates ---

def test_review_uses_youtube_url_file_data_not_thumbnail_blob(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = MagicMock()
    mock_types = MagicMock()
    svc._genai_types = mock_types

    mock_resp = MagicMock()
    mock_resp.text = (
        '{"proceed":true,"best_video_id":"vid1","rationale":"good",'
        '"refined_queries":[],"candidate_reviews":[]}'
    )

    candidates = [
        SearchCandidate(
            video_id="vid1",
            title="Person walking side view",
            description="",
            channel_title="Chan",
            query="person walking side view",
            url="https://www.youtube.com/watch?v=vid1",
            duration_seconds=30,
            view_count=50000,
        )
    ]

    with patch.object(svc._gemini_client.models, "generate_content", return_value=mock_resp):
        svc._review_video_candidates("make robot walk", {"task_goal": "walk"}, candidates)

    mock_types.FileData.assert_called_once_with(
        file_uri="https://www.youtube.com/watch?v=vid1",
        mime_type="video/*",
    )
    mock_types.Blob.assert_not_called()


def test_review_attaches_each_candidate_as_video_input(svc):
    os.environ["GEMINI_API_KEY"] = "fake"
    svc._gemini_client = MagicMock()
    mock_types = MagicMock()
    svc._genai_types = mock_types

    mock_resp = MagicMock()
    mock_resp.text = (
        '{"proceed":true,"best_video_id":"vid1","rationale":"good",'
        '"refined_queries":[],"candidate_reviews":[]}'
    )

    candidates = [
        SearchCandidate(
            video_id="vid1",
            title="Person walking",
            description="",
            channel_title="Chan",
            query="person walking",
            url="https://www.youtube.com/watch?v=vid1",
        )
        ,
        SearchCandidate(
            video_id="vid2",
            title="Person jogging",
            description="",
            channel_title="Chan",
            query="person walking",
            url="https://www.youtube.com/watch?v=vid2",
        ),
    ]

    with patch.object(svc._gemini_client.models, "generate_content", return_value=mock_resp):
        svc._review_video_candidates("make robot walk", {"task_goal": "walk"}, candidates)

    assert mock_types.FileData.call_count == 2
    mock_types.Blob.assert_not_called()


def test_run_gvhmr_raises_if_modal_sdk_missing(svc):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "modal":
            raise ImportError("No module named 'modal'", name="modal")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="Modal SDK is not installed"):
            svc.run_gvhmr("https://www.youtube.com/watch?v=abc123")


def test_run_gvhmr_uses_run_probe_when_available(svc):
    fake_call = MagicMock()
    fake_call.object_id = "fc-123"
    fake_remote = MagicMock()
    fake_remote.spawn.return_value = fake_call

    with patch("modal.Function.from_name", return_value=fake_remote) as from_name:
        job_id = svc.run_gvhmr("https://www.youtube.com/watch?v=abc123")

    assert job_id == "fc-123"
    from_name.assert_called_once_with("gvhmr-probe", "run_probe")
    fake_remote.spawn.assert_called_once_with(
        video_url="https://www.youtube.com/watch?v=abc123",
        static_cam=True,
    )
