from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

_ER16_PROMPT = """You are preparing a human reference-video search plan for robot learning.
Given a robot task description, extract the physical task and generate YouTube queries that look for
real humans performing the analogous task.

Return ONLY valid JSON using the requested schema.

Rules for search_queries:
- Never search for robots, reinforcement learning, simulation, policies, or code.
- Search for a real person or human performing the analogous physical task.
- Use concrete object and action words from the user's request.
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
- If every candidate is bad, set proceed=false and propose 3 better YouTube queries.

Return ONLY valid JSON using the requested schema."""

_GVHMR_MODAL_APP_NAME = os.environ.get("GVHMR_MODAL_APP_NAME", "gvhmr-probe")
_GVHMR_MODAL_FUNCTION_NAME = os.environ.get("GVHMR_MODAL_FUNCTION_NAME", "run_probe")

_MIN_VIDEO_SECONDS = 8
_MAX_VIDEO_SECONDS = 180


def _parse_iso8601_duration(duration: str) -> int:
    """Convert ISO 8601 duration string (e.g. PT1M30S) to total seconds."""
    if not duration:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _fetch_thumbnail_bytes(video_id: str) -> bytes | None:
    """Fetch YouTube thumbnail bytes. Falls back from maxres → hq."""
    for quality in ("maxresdefault", "hqdefault"):
        url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                if resp.status == 200:
                    return resp.read()
        except Exception:  # noqa: BLE001
            continue
    return None


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

    def _youtube_search(self, query: str, max_results: int = 5):
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
            relevanceLanguage="en",
            safeSearch="moderate",
            videoEmbeddable="true",
        )

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
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("YouTube search query must not be empty.")

        try:
            result = self._youtube_search(cleaned_query, max_results=max_results).execute()
        except Exception as exc:
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
        per_query: int = 4,
        shortlist_size: int = 3,
    ) -> list[SearchCandidate]:
        seen_ids: set[str] = set()
        errors: list[str] = []
        query_buckets: list[list[SearchCandidate]] = []
        pool_size = shortlist_size * 2  # over-collect to absorb duration filtering

        for raw_query in queries:
            query = raw_query.strip() if isinstance(raw_query, str) else ""
            if not query:
                continue
            try:
                raw_candidates = [
                    SearchCandidate.model_validate(candidate)
                    for candidate in self.search_youtube_candidates(
                        query,
                        max_results=per_query,
                    )
                ]
            except (LookupError, RuntimeError, ValueError) as exc:
                errors.append(str(exc))
                continue

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
        for candidate in pool:
            d = details.get(candidate.video_id, {})
            dur = d.get("duration_seconds", 0)
            vc = d.get("view_count", 0)
            if dur > 0 and (dur < _MIN_VIDEO_SECONDS or dur > _MAX_VIDEO_SECONDS):
                continue
            shortlisted.append(candidate.model_copy(update={"duration_seconds": dur, "view_count": vc}))
            if len(shortlisted) >= shortlist_size:
                break

        # Fall back to unenriched pool if duration filtering removed everything
        return shortlisted if shortlisted else pool[:shortlist_size]

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
                        f"description: {candidate.description[:500]}"
                    )
                )
            )
            thumb = _fetch_thumbnail_bytes(candidate.video_id)
            if thumb is not None:
                parts.append(
                    types.Part(
                        inline_data=types.Blob(data=thumb, mime_type="image/jpeg")
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
