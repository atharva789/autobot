from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Iterable

from demo.models import Clip, ExportRecord, Run


class DemoStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    video_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    clip_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    replay_path TEXT,
                    retarget_npz_path TEXT,
                    approved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (clip_id) REFERENCES clips(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exports (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    parquet_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                )
                """
            )

    def seed_clips(self, clips: Iterable[dict[str, str]]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO clips(id, label, video_path)
                VALUES(:id, :label, :video_path)
                ON CONFLICT(id) DO UPDATE SET
                    label=excluded.label,
                    video_path=excluded.video_path
                """,
                list(clips),
            )

    def list_clips(self) -> list[Clip]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, label, video_path FROM clips ORDER BY id"
            ).fetchall()
        return [Clip(id=row["id"], label=row["label"], video_path=row["video_path"]) for row in rows]

    def get_clip(self, clip_id: str) -> Clip | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, label, video_path FROM clips WHERE id = ?",
                (clip_id,),
            ).fetchone()
        if row is None:
            return None
        return Clip(id=row["id"], label=row["label"], video_path=row["video_path"])

    def create_run(self, prompt: str, clip_id: str) -> Run:
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs(id, clip_id, prompt, status, approved)
                VALUES(?, ?, ?, 'queued', 0)
                """,
                (run_id, clip_id, prompt),
            )
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_run(row)

    def get_run(self, run_id: str) -> Run | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return _row_to_run(row)

    def update_run(
        self,
        run_id: str,
        status: str,
        replay_path: str | None = None,
        retarget_npz_path: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?,
                    replay_path = COALESCE(?, replay_path),
                    retarget_npz_path = COALESCE(?, retarget_npz_path)
                WHERE id = ?
                """,
                (status, replay_path, retarget_npz_path, run_id),
            )

    def set_run_approved(self, run_id: str, approved: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET approved = ? WHERE id = ?",
                (1 if approved else 0, run_id),
            )

    def create_export(self, run_id: str, parquet_path: str) -> ExportRecord:
        export_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO exports(id, run_id, parquet_path)
                VALUES(?, ?, ?)
                """,
                (export_id, run_id, parquet_path),
            )
            row = conn.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
        return _row_to_export(row)

    def get_export(self, export_id: str) -> ExportRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM exports WHERE id = ?", (export_id,)).fetchone()
        if row is None:
            return None
        return _row_to_export(row)


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"],
        clip_id=row["clip_id"],
        prompt=row["prompt"],
        status=row["status"],
        replay_path=row["replay_path"],
        retarget_npz_path=row["retarget_npz_path"],
        approved=bool(row["approved"]),
        created_at=row["created_at"],
    )


def _row_to_export(row: sqlite3.Row) -> ExportRecord:
    return ExportRecord(
        id=row["id"],
        run_id=row["run_id"],
        parquet_path=row["parquet_path"],
        created_at=row["created_at"],
    )
