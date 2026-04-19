"""Structured DROID fallback retrieval.

DROID is treated as a trajectory/episode retrieval backend, not as web video.
The retrieval unit is the episode, with optional trajectory windows attached
to the returned reference object.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DroidDatasetFormat(str, Enum):
    RLDS = "rlds"
    RAW = "raw"
    LEROBOT_V3 = "lerobot_v3"


@dataclass(frozen=True)
class DroidEpisodeRecord:
    episode_id: str
    dataset_format: DroidDatasetFormat
    task_text: str
    language_annotations: list[str] = field(default_factory=list)
    action_path: str = ""
    state_path: str = ""
    camera_refs: dict[str, str] = field(default_factory=dict)
    confidence_hint: float = 0.0
    trajectory_window: tuple[int, int] | None = None


@dataclass(frozen=True)
class DroidFallbackQuery:
    query_text: str
    required_task_terms: list[str] = field(default_factory=list)
    preferred_camera_terms: list[str] = field(default_factory=list)
    max_results: int = 5


@dataclass(frozen=True)
class DroidFallbackResult:
    episode_id: str
    source_format: DroidDatasetFormat
    task_text: str
    language_annotations: list[str]
    action_path: str
    state_path: str
    camera_refs: dict[str, str]
    match_score: float
    reason: str
    retrieval_unit: str = "episode"
    trajectory_window: tuple[int, int] | None = None


class DroidFallbackIndex:
    def __init__(self, episodes: list[DroidEpisodeRecord]) -> None:
        self.episodes = episodes

    @classmethod
    def load_jsonl(cls, path: str | Path) -> "DroidFallbackIndex":
        records: list[DroidEpisodeRecord] = []
        for line in Path(path).read_text().splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            records.append(_record_from_dict(raw))
        return cls(records)

    def retrieve(self, query: DroidFallbackQuery) -> DroidFallbackResult:
        if not self.episodes:
            raise LookupError("DROID fallback index is empty.")

        ranked = self.rank(query)
        if not ranked:
            raise LookupError("No DROID episodes matched the fallback query.")
        return ranked[0]

    def rank(self, query: DroidFallbackQuery) -> list[DroidFallbackResult]:
        scored: list[DroidFallbackResult] = []
        for episode in self.episodes:
            score, reason = _score_episode(episode, query)
            if score <= 0:
                continue
            scored.append(
                DroidFallbackResult(
                    episode_id=episode.episode_id,
                    source_format=episode.dataset_format,
                    task_text=episode.task_text,
                    language_annotations=episode.language_annotations,
                    action_path=episode.action_path,
                    state_path=episode.state_path,
                    camera_refs=episode.camera_refs,
                    match_score=round(score, 3),
                    reason=reason,
                    trajectory_window=episode.trajectory_window,
                )
            )
        scored.sort(key=lambda item: item.match_score, reverse=True)
        return scored[: query.max_results]


def _record_from_dict(raw: dict[str, Any]) -> DroidEpisodeRecord:
    dataset_format = DroidDatasetFormat(raw.get("dataset_format", "rlds"))
    trajectory_window = raw.get("trajectory_window")
    if isinstance(trajectory_window, list) and len(trajectory_window) == 2:
        trajectory_window = (int(trajectory_window[0]), int(trajectory_window[1]))
    elif not isinstance(trajectory_window, tuple):
        trajectory_window = None
    return DroidEpisodeRecord(
        episode_id=str(raw["episode_id"]),
        dataset_format=dataset_format,
        task_text=str(raw.get("task_text", "")),
        language_annotations=list(raw.get("language_annotations", [])),
        action_path=str(raw.get("action_path", "")),
        state_path=str(raw.get("state_path", "")),
        camera_refs=dict(raw.get("camera_refs", {})),
        confidence_hint=float(raw.get("confidence_hint", 0.0)),
        trajectory_window=trajectory_window,
    )


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }


def _score_episode(
    episode: DroidEpisodeRecord,
    query: DroidFallbackQuery,
) -> tuple[float, str]:
    query_tokens = _tokenize(query.query_text)
    episode_tokens = _tokenize(episode.task_text + " " + " ".join(episode.language_annotations))
    overlap = len(query_tokens & episode_tokens)
    required_terms = [term.lower() for term in query.required_task_terms]
    required_hits = sum(1 for term in required_terms if term in episode_tokens or term in query_tokens)
    camera_terms = [term.lower() for term in query.preferred_camera_terms]
    camera_bonus = 0.0
    camera_hints = " ".join(episode.camera_refs.keys()).lower() + " ".join(episode.camera_refs.values()).lower()
    if camera_terms:
        camera_bonus = 0.05 * sum(1 for term in camera_terms if term in camera_hints)

    score = 0.18 * overlap + 0.12 * required_hits + 0.2 * episode.confidence_hint + camera_bonus
    reason_bits = [
        f"matched {overlap} text tokens",
        f"{required_hits}/{len(required_terms)} required terms matched",
        f"confidence hint {episode.confidence_hint:.2f}",
    ]
    if required_terms:
        reason_bits.append("required terms: " + ", ".join(required_terms))

    if required_terms and required_hits < len(required_terms):
        score -= 0.2
        reason_bits.append("missing at least one required task term")

    if episode.state_path.strip() or episode.action_path.strip():
        score += 0.05
        reason_bits.append("trajectory pointers available")

    return max(score, 0.0), "; ".join(reason_bits)
