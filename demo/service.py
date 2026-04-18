from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from demo.models import ExportRecord, Run
from demo.store import DemoStore


class DemoService:
    def __init__(self, store: DemoStore, replays_dir: Path, exports_dir: Path) -> None:
        self.store = store
        self.replays_dir = replays_dir
        self.exports_dir = exports_dir
        self.replays_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def start_run(self, prompt: str, clip_id: str) -> Run:
        clip = self.store.get_clip(clip_id)
        if clip is None:
            raise ValueError(f"Unknown clip id: {clip_id}")
        return self.store.create_run(prompt=prompt, clip_id=clip.id)

    def execute_run(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run id: {run_id}")

        self.store.update_run(run_id=run_id, status="processing")
        replay_path = self.replays_dir / f"{run_id}.mp4"
        npz_path = self.replays_dir / f"{run_id}.npz"

        # This is intentionally a deterministic demo placeholder for hackathon UI flow.
        replay_path.write_bytes(b"MOCK_MP4_CONTENT")
        qpos = np.linspace(0.0, 1.0, 21, dtype=np.float32).reshape(1, -1)
        np.savez(npz_path, qpos=qpos, clip_id=run.clip_id)

        self.store.update_run(
            run_id=run_id,
            status="completed",
            replay_path=str(replay_path),
            retarget_npz_path=str(npz_path),
        )
        completed = self.store.get_run(run_id)
        assert completed is not None
        return completed

    def approve_run(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run id: {run_id}")
        if run.status != "completed":
            raise ValueError("Run must be completed before approval")
        self.store.set_run_approved(run_id, True)
        approved = self.store.get_run(run_id)
        assert approved is not None
        return approved

    def export_run(self, run_id: str) -> ExportRecord:
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Unknown run id: {run_id}")
        if not run.approved:
            raise ValueError("Run must be approved before export")

        export_path = self.exports_dir / f"{run_id}.parquet"
        export_payload = {
            "format": "mock_parquet",
            "run_id": run.id,
            "clip_id": run.clip_id,
            "task": run.prompt,
            "retarget_npz_path": run.retarget_npz_path,
            "created_at": datetime.now(UTC).isoformat(),
        }
        # We intentionally write JSON content into a .parquet path until parquet
        # dependencies are pinned for the demo runtime.
        export_path.write_text(json.dumps(export_payload, indent=2))
        return self.store.create_export(run_id=run.id, parquet_path=str(export_path))

