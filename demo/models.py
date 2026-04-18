from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Clip:
    id: str
    label: str
    video_path: str


@dataclass(frozen=True)
class Run:
    id: str
    clip_id: str
    prompt: str
    status: str
    replay_path: str | None
    retarget_npz_path: str | None
    approved: bool
    created_at: str


@dataclass(frozen=True)
class ExportRecord:
    id: str
    run_id: str
    parquet_path: str
    created_at: str

