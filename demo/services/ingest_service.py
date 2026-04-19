from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from packages.pipeline.droid_fallback import DroidFallbackIndex, DroidFallbackQuery

_ER16_PROMPT = """You are preparing a human reference-video search plan for robot learning.
Given a robot task description, extract the physical task and generate YouTube queries that look for
real humans performing the analogous task.

Return ONLY valid JSON using the requested schema.

Rules for search_queries:
- Never search for robots, reinforcement learning, simulation, policies, or code.
- Search for a real person or human performing the analogous physical task.
- Use concrete action words from the user's request.
- If the object is too niche for good search recall, broaden it to a more common physical analog while preserving body mechanics.
- Query 1 should be the most literal human analog of the task.
- Query 2 should be a broader, higher-recall human-motion analog of the same task.
- Query 3 should optimize for camera quality and full-body visibility.
- Prefer side view, full-body visibility, and fixed or mostly static camera when helpful.
- Return exactly 3 distinct search queries.

Task: {prompt}"""

_VIDEO_SELECTION_PROMPT = """You are choosing the best human reference video for robot-learning data.
The user's task is:
{task_prompt}

The extracted task goal is:
{task_goal}

Selection criteria:
- Prefer a real human, or at worst a clearly humanoid analog, performing the same physical task.
- Strongly prefer videos with a fixed or mostly static camera, visible full body, and minimal cuts.
- Reject videos that are robots, simulations, animations, compilations, reaction videos, or unrelated.
- Reject videos where the relevant action is not shown clearly.
- You are reviewing the actual candidate videos, not just thumbnails. Use the video content as the primary source of truth.
- If several candidates are partially correct, prefer the one with the clearest body visibility and least camera motion.
- If every candidate is bad, set proceed=false and propose 3 better YouTube queries.

Return ONLY valid JSON using the requested schema."""

_GVHMR_MODAL_APP_NAME = os.environ.get("GVHMR_MODAL_APP_NAME", "gvhmr-probe")
_GVHMR_MODAL_FUNCTION_NAME = os.environ.get("GVHMR_MODAL_FUNCTION_NAME", "run_probe")

_MIN_VIDEO_SECONDS = 8
_MAX_VIDEO_SECONDS = 180
_SEARCH_PROFILE_LIMIT = 3
def _droid_fallback_index_path() -> str:
    return os.environ.get("DROID_FALLBACK_INDEX_PATH", "").strip()


def _parse_iso8601_duration(duration: str) -> int:
    """Convert ISO 8601 duration string (e.g. PT1M30S) to total seconds."""
    if not duration:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


class IngestPlan(BaseModel):
    task_goal: str
    affordances: list[str]
    success_criteria: str
    search_queries: list[str] = Field(min_length=3, max_length=3)


class SearchCandidate(BaseModel):
    video_id: str
    title: str
    description: str = ""
    channel_title: str = ""
    query: str
    url: str
    duration_seconds: int = 0
    view_count: int = 0
    search_profile: str = "default"


class CandidateReview(BaseModel):
    video_id: str
    verdict: Literal["good", "bad"]
    score: int = Field(ge=0, le=10)
    reason: str


class VideoSelection(BaseModel):
    proceed: bool
    best_video_id: str | None = None
    rationale: str
    refined_queries: list[str] = Field(default_factory=list)
    candidate_reviews: list[CandidateReview] = Field(default_factory=list)


def resolve_gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def _extract_response_text(response: Any) -> str | None:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text

    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None

    first_candidate = candidates[0]
    content = getattr(first_candidate, "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        return None

    texts = [
        getattr(part, "text", None)
        for part in parts
        if isinstance(getattr(part, "text", None), str)
    ]
    joined = "".join(texts).strip()
    return joined or None


def _coerce_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _looks_like_nonreference_video(candidate: SearchCandidate) -> bool:
    haystack = " ".join(
        [candidate.title, candidate.description, candidate.channel_title]
    ).lower()
    blocked_terms = [
        "robot dog",
        "quadruped",
        "boston dynamics",
        "simulation",
        "simulator",
        "animated",
        "animation",
        "minecraft",
        "gta",
        "roblox",
        "lego",
        "reaction",
        "compilation",
        "shorts",
        "meme",
        "ai generated",
    ]
    return any(term in haystack for term in blocked_terms)


class IngestService:
    def __init__(
        self,
        gemini_api_key: str,
        youtube_api_key: str,
        supabase_url: str,
        supabase_key: str,
    ) -> None:
        self._gemini_client = None
        self._genai_types = None
        try:
            from google import genai
            from google.genai import types

            self._gemini_client = genai.Client(api_key=gemini_api_key)
            self._genai_types = types
        except ImportError:
            self._gemini_client = None
            self._genai_types = None
        self._youtube_api_key = youtube_api_key

    def _require_gemini(self) -> None:
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY must be set before using /ingest.")
        if self._gemini_client is None:
            raise RuntimeError(
                "Gemini SDK is not installed. Install `google-genai` in the "
                "project virtualenv before using /ingest."
            )
        if self._genai_types is None:
            raise RuntimeError("Gemini SDK types are unavailable.")

    def _generate_structured_json(
        self,
        *,
        model: str,
        contents: Any,
        schema: type[BaseModel],
        error_context: str,
    ) -> dict[str, Any]:
        self._require_gemini()
        response = self._gemini_client.models.generate_content(
            model=model,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": schema.model_json_schema(),
            },
        )
        text = _extract_response_text(response)
        if not isinstance(text, str):
            raise RuntimeError(
                f"Gemini returned a non-text response for {error_context}."
            )
        text = _coerce_json_text(text)
        try:
            validated = schema.model_validate_json(text)
        except ValidationError as exc:
            raise RuntimeError(
                f"Gemini returned invalid JSON for {error_context}: {text[:300]}"
            ) from exc
        return validated.model_dump()

    def analyze_prompt(self, prompt: str) -> dict:
        return self._generate_structured_json(
            model="gemini-2.5-pro",
            contents=_ER16_PROMPT.format(prompt=prompt),
            schema=IngestPlan,
            error_context="ingest planning",
        )

    def _youtube_search(
        self,
        query: str,
        max_results: int = 10,
        *,
        order: str = "relevance",
        video_duration: str = "short",
        video_definition: str = "high",
        video_caption: str | None = None,
    ):
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "YouTube SDK is not installed. Install `google-api-python-client` "
                "in the project virtualenv before using /ingest."
            ) from exc
        yt = build("youtube", "v3", developerKey=self._youtube_api_key)
        return yt.search().list(
            q=query,
            part="id,snippet",
            type="video",
            maxResults=max_results,
            order=order,
            relevanceLanguage="en",
            safeSearch="moderate",
            videoEmbeddable="true",
            videoDuration=video_duration,
            videoDefinition=video_definition,
            videoCaption=video_caption if video_caption else None,
        )

    def _search_profiles(self) -> list[dict[str, str | None]]:
        return [
            {
                "name": "captioned_relevance",
                "order": "relevance",
                "video_duration": "short",
                "video_definition": "high",
                "video_caption": "closedCaption",
            },
            {
                "name": "high_def_relevance",
                "order": "relevance",
                "video_duration": "short",
                "video_definition": "high",
                "video_caption": None,
            },
            {
                "name": "popular_short",
                "order": "viewCount",
                "video_duration": "short",
                "video_definition": "high",
                "video_caption": None,
            },
        ]

    def _fetch_video_details(self, video_ids: list[str]) -> dict[str, dict]:
        """Batch-fetch duration and view count for given video IDs."""
        if not video_ids:
            return {}
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "YouTube SDK is not installed. Install `google-api-python-client`."
            ) from exc
        yt = build("youtube", "v3", developerKey=self._youtube_api_key)
        result = yt.videos().list(
            id=",".join(video_ids),
            part="contentDetails,statistics",
        ).execute()
        details: dict[str, dict] = {}
        for item in result.get("items", []):
            vid = item["id"]
            cd = item.get("contentDetails", {})
            stats = item.get("statistics", {})
            details[vid] = {
                "duration_seconds": _parse_iso8601_duration(cd.get("duration", "")),
                "view_count": int(stats.get("viewCount", 0)),
            }
        return details

    def search_youtube_candidates(
        self,
        query: str,
        max_results: int = 10,
        *,
        search_options: dict[str, str | None] | None = None,
    ) -> list[dict[str, Any]]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("YouTube search query must not be empty.")
        search_options = search_options or {}
        profile_name = str(search_options.get("name") or "default")

        try:
            result = self._youtube_search(
                cleaned_query,
                max_results=max_results,
                order=str(search_options.get("order") or "relevance"),
                video_duration=str(search_options.get("video_duration") or "short"),
                video_definition=str(search_options.get("video_definition") or "high"),
                video_caption=(
                    str(search_options["video_caption"])
                    if search_options.get("video_caption")
                    else None
                ),
            ).execute()
        except Exception as exc:
            err_str = str(exc)
            if "invalid_grant" in err_str or "Bad Request" in err_str:
                raise RuntimeError(
                    f"YouTube API authentication failed. The YOUTUBE_API_KEY may be "
                    f"invalid or expired. Please verify your YouTube Data API key in "
                    f"the Google Cloud Console. Error: {exc}"
                ) from exc
            if "quotaExceeded" in err_str:
                raise RuntimeError(
                    f"YouTube API quota exceeded. Try again tomorrow or use a different "
                    f"API key. Error: {exc}"
                ) from exc
            raise RuntimeError(
                f"YouTube search failed for query '{cleaned_query}': {exc}"
            ) from exc

        items = result.get("items")
        if not isinstance(items, list) or not items:
            raise LookupError(f"No YouTube videos found for query '{cleaned_query}'.")

        candidates: list[dict[str, Any]] = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            if not video_id:
                continue
            candidate = SearchCandidate(
                video_id=video_id,
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                channel_title=snippet.get("channelTitle", ""),
                query=cleaned_query,
                url=f"https://www.youtube.com/watch?v={video_id}",
                search_profile=profile_name,
            )
            candidates.append(candidate.model_dump())

        if not candidates:
            raise LookupError(
                f"No playable YouTube video IDs found for query '{cleaned_query}'."
            )
        return candidates

    def search_youtube(self, query: str) -> str:
        return self.search_youtube_candidates(query, max_results=1)[0]["video_id"]

    def find_video_for_queries(self, queries: list[str]) -> tuple[str, str]:
        errors: list[str] = []
        for raw_query in queries:
            query = raw_query.strip() if isinstance(raw_query, str) else ""
            if not query:
                continue
            try:
                return self.search_youtube(query), query
            except (LookupError, RuntimeError, ValueError) as exc:
                errors.append(str(exc))

        if not errors:
            raise ValueError("No valid YouTube search queries were provided.")

        raise LookupError(
            "Unable to find a usable YouTube video for any generated query. "
            + " ".join(errors)
        )

    def _collect_candidate_videos(
        self,
        queries: list[str],
        *,
        per_query: int = 10,
        shortlist_size: int = 8,
    ) -> list[SearchCandidate]:
        seen_ids: set[str] = set()
        errors: list[str] = []
        query_buckets: list[list[SearchCandidate]] = []
        pool_size = min(shortlist_size * 2, 12)

        for raw_query in queries:
            query = raw_query.strip() if isinstance(raw_query, str) else ""
            if not query:
                continue
            raw_candidates: list[SearchCandidate] = []
            for search_profile in self._search_profiles()[:_SEARCH_PROFILE_LIMIT]:
                try:
                    profile_candidates = [
                        SearchCandidate.model_validate(candidate)
                        for candidate in self.search_youtube_candidates(
                            query,
                            max_results=per_query,
                            search_options=search_profile,
                        )
                    ]
                except (LookupError, RuntimeError, ValueError) as exc:
                    errors.append(str(exc))
                    continue
                raw_candidates.extend(profile_candidates)

            preferred = [
                candidate
                for candidate in raw_candidates
                if not _looks_like_nonreference_video(candidate)
            ]
            query_buckets.append(preferred or raw_candidates)

        # Interleave results across query buckets up to pool_size
        pool: list[SearchCandidate] = []
        for rank_idx in range(per_query):
            for bucket in query_buckets:
                if rank_idx >= len(bucket):
                    continue
                candidate = bucket[rank_idx]
                if candidate.video_id in seen_ids:
                    continue
                pool.append(candidate)
                seen_ids.add(candidate.video_id)
                if len(pool) >= pool_size:
                    break
            if len(pool) >= pool_size:
                break

        if not pool:
            if errors:
                raise LookupError(" ".join(errors))
            raise LookupError("No viable YouTube candidates were found.")

        # Enrich pool with duration + view count; filter out-of-range durations
        try:
            details = self._fetch_video_details([c.video_id for c in pool])
        except Exception:  # noqa: BLE001
            details = {}

        shortlisted: list[SearchCandidate] = []
        unknown_duration_candidates: list[SearchCandidate] = []
        for candidate in pool:
            d = details.get(candidate.video_id, {})
            dur = d.get("duration_seconds", 0)
            vc = d.get("view_count", 0)
            enriched = candidate.model_copy(update={"duration_seconds": dur, "view_count": vc})
            if dur <= 0:
                unknown_duration_candidates.append(enriched)
                continue
            if dur < _MIN_VIDEO_SECONDS or dur > _MAX_VIDEO_SECONDS:
                continue
            shortlisted.append(enriched)
            if len(shortlisted) >= shortlist_size:
                break

        if shortlisted:
            return shortlisted

        if unknown_duration_candidates:
            return unknown_duration_candidates[:shortlist_size]

        raise LookupError(
            "All collected YouTube candidates were outside the preferred duration range."
        )

    def _review_video_candidates(
        self,
        task_prompt: str,
        plan: dict[str, Any],
        candidates: list[SearchCandidate],
    ) -> dict[str, Any]:
        self._require_gemini()
        types = self._genai_types
        parts: list[Any] = [
            types.Part(
                text=_VIDEO_SELECTION_PROMPT.format(
                    task_prompt=task_prompt,
                    task_goal=plan.get("task_goal", task_prompt),
                )
            )
        ]
        for idx, candidate in enumerate(candidates, start=1):
            duration_str = (
                f"{candidate.duration_seconds}s" if candidate.duration_seconds else "unknown"
            )
            view_str = (
                f"{candidate.view_count:,}" if candidate.view_count else "unknown"
            )
            parts.append(
                types.Part(
                    text=(
                        f"Candidate {idx} metadata:\n"
                        f"video_id: {candidate.video_id}\n"
                        f"query: {candidate.query}\n"
                        f"title: {candidate.title}\n"
                        f"channel_title: {candidate.channel_title}\n"
                        f"duration: {duration_str}\n"
                        f"view_count: {view_str}\n"
                        f"search_profile: {candidate.search_profile}\n"
                        f"description: {candidate.description[:500]}"
                    )
                )
            )
            parts.append(
                types.Part(
                    file_data=types.FileData(
                        file_uri=candidate.url,
                        mime_type="video/*",
                    )
                )
            )

        contents = types.Content(parts=parts)
        return self._generate_structured_json(
            model="gemini-2.5-flash",
            contents=contents,
            schema=VideoSelection,
            error_context="reference video selection",
        )

    def _resolve_selected_candidate(
        self,
        selection: dict[str, Any],
        candidates: list[SearchCandidate],
    ) -> SearchCandidate | None:
        by_id = {candidate.video_id: candidate for candidate in candidates}
        best_video_id = selection.get("best_video_id")
        if isinstance(best_video_id, str) and best_video_id in by_id:
            return by_id[best_video_id]

        best_review: CandidateReview | None = None
        for review_data in selection.get("candidate_reviews", []):
            try:
                review = CandidateReview.model_validate(review_data)
            except ValidationError:
                continue
            if review.video_id not in by_id:
                continue
            if best_review is None or review.score > best_review.score:
                best_review = review

        if best_review and best_review.verdict == "good" and best_review.score >= 7:
            return by_id[best_review.video_id]
        return None

    def select_reference_video(
        self,
        task_prompt: str,
        plan: dict[str, Any],
        *,
        max_rounds: int = 2,
    ) -> dict[str, Any]:
        queries = plan.get("search_queries")
        if not isinstance(queries, list) or not queries:
            raise ValueError("No valid YouTube search queries were provided.")

        current_queries = [query for query in queries if isinstance(query, str) and query.strip()]
        if not current_queries:
            raise ValueError("No valid YouTube search queries were provided.")

        last_selection: dict[str, Any] | None = None
        last_candidates: list[SearchCandidate] = []

        for _round in range(max_rounds):
            candidates = self._collect_candidate_videos(current_queries)
            last_candidates = candidates
            selection = self._review_video_candidates(task_prompt, plan, candidates)
            last_selection = selection
            chosen = self._resolve_selected_candidate(selection, candidates)
            if selection.get("proceed") and chosen is not None:
                return {
                    "video_id": chosen.video_id,
                    "query": chosen.query,
                    "url": chosen.url,
                    "rationale": selection.get("rationale", ""),
                    "candidate_reviews": selection.get("candidate_reviews", []),
                }

            refined_queries = [
                query.strip()
                for query in selection.get("refined_queries", [])
                if isinstance(query, str) and query.strip()
            ]
            if not refined_queries:
                break
            current_queries = refined_queries

        review_summary = ""
        if last_selection:
            review_summary = last_selection.get("rationale", "")
        candidate_ids = ", ".join(candidate.video_id for candidate in last_candidates)
        raise LookupError(
            "Unable to find a strong human reference video after search refinement. "
            f"Last rationale: {review_summary or 'no rationale provided'}. "
            f"Last candidate ids: {candidate_ids or 'none'}."
        )

    def _build_droid_query(self, task_prompt: str, plan: dict[str, Any]) -> DroidFallbackQuery:
        task_goal = str(plan.get("task_goal") or task_prompt).strip()
        search_terms = [
            term
            for term in plan.get("search_queries", [])
            if isinstance(term, str) and term.strip()
        ]
        task_terms = [word for word in re.findall(r"[a-z0-9]+", task_goal.lower()) if len(word) > 2]
        search_tokens = [
            token
            for term in search_terms[:3]
            for token in re.findall(r"[a-z0-9]+", term.lower())
            if len(token) > 2
        ]
        required_terms = list(dict.fromkeys(
            [term for term in task_terms if term not in {"robot", "design"}] + search_tokens
        ))
        return DroidFallbackQuery(
            query_text=" ".join(
                [
                    task_prompt.strip(),
                    task_goal,
                    " ".join(search_terms[:3]),
                ]
            ).strip(),
            required_task_terms=required_terms[:4],
            preferred_camera_terms=["fixed camera", "side view", "full body"],
            max_results=3,
        )

    def select_droid_reference(
        self,
        task_prompt: str,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        index_path = _droid_fallback_index_path()
        if not index_path:
            raise RuntimeError(
                "DROID fallback index path is not configured. Set "
                "DROID_FALLBACK_INDEX_PATH to a JSONL episode index."
            )
        path = Path(index_path)
        if not path.exists():
            raise RuntimeError(
                f"DROID fallback index not found at {path}. Provide a JSONL file "
                "with episode records."
            )
        query = self._build_droid_query(task_prompt, plan)
        index = DroidFallbackIndex.load_jsonl(path)
        result = index.retrieve(query)
        return {
            "source_type": "droid",
            "query_text": query.query_text,
            "required_task_terms": query.required_task_terms,
            "preferred_camera_terms": query.preferred_camera_terms,
            "reference": asdict(result),
        }

    def download_clip(self, video_id: str, dest_dir: Path) -> Path:
        url = f"https://www.youtube.com/watch?v={video_id}"
        out = dest_dir / f"{video_id}.mp4"
        subprocess.run(["yt-dlp", "-f", "mp4", "-o", str(out), url], check=True)
        return out

    def run_gvhmr(self, video_url: str) -> str:
        """Dispatch to existing Modal GVHMR endpoint. Returns job_id."""
        try:
            import modal
        except ImportError as exc:
            missing_name = getattr(exc, "name", "")
            if missing_name == "modal":
                raise RuntimeError(
                    "Modal SDK is not installed. Install `modal` in the project "
                    "virtualenv before using /ingest."
                ) from exc
            raise RuntimeError(
                "GVHMR Modal endpoint not deployed. Run: modal deploy scripts/gvhmr_modal_probe.py"
            ) from exc
        try:
            remote_fn = modal.Function.from_name(
                _GVHMR_MODAL_APP_NAME,
                _GVHMR_MODAL_FUNCTION_NAME,
            )
            function_call = remote_fn.spawn(video_url=video_url, static_cam=True)
            return function_call.object_id
        except Exception as exc:
            message = str(exc)
            if "has not been hydrated" in message:
                raise RuntimeError(
                    "GVHMR Modal function is not being invoked from a deployed lookup. "
                    "Ensure the server is using the updated code path."
                ) from exc
            if "not found" in message.lower():
                raise RuntimeError(
                    "GVHMR Modal deployment was not found. Run: "
                    "modal deploy scripts/gvhmr_modal_probe.py"
                ) from exc
            raise RuntimeError(f"GVHMR dispatch failed for {video_url}: {exc}") from exc
