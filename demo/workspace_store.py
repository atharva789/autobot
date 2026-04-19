from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Any


JSON_FIELDS = {
    "design_json",
    "render_json",
    "bom_json",
    "candidate_reviews_json",
    "telemetry_json",
    "reference_payload_json",
    "delta_json",
    "rows_json",
    "metadata_json",
    "payload_json",
    "result_json",
    "data_json",
}

BOOL_FIELDS = {
    "approved",
    "is_model_preferred",
    "is_user_selected",
    "is_default",
}


def _default_db_path() -> Path:
    return Path(
        os.environ.get(
            "WORKSPACE_DB_PATH",
            str(Path(tempfile.gettempdir()) / "il_ideation" / "workspace.sqlite3"),
        )
    )


class WorkspaceStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ingest_jobs (
                    id TEXT PRIMARY KEY,
                    source_url TEXT,
                    er16_plan_json TEXT,
                    gvhmr_job_id TEXT,
                    smpl_path TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reference_source_type TEXT,
                    selected_query TEXT,
                    selection_rationale TEXT,
                    candidate_reviews_json TEXT,
                    reference_payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS designs (
                    id TEXT PRIMARY KEY,
                    ingest_job_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    design_json TEXT NOT NULL,
                    render_json TEXT,
                    bom_json TEXT,
                    telemetry_json TEXT,
                    is_model_preferred INTEGER NOT NULL DEFAULT 0,
                    is_user_selected INTEGER NOT NULL DEFAULT 0,
                    screening_score REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_designs_ingest_job_id
                    ON designs(ingest_job_id);

                CREATE TABLE IF NOT EXISTS design_revisions (
                    id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL,
                    parent_revision_id TEXT,
                    design_json TEXT NOT NULL,
                    render_json TEXT,
                    bom_json TEXT,
                    telemetry_json TEXT,
                    delta_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_design_revisions_design_id
                    ON design_revisions(design_id, revision_number DESC);

                CREATE TABLE IF NOT EXISTS design_checkpoints (
                    id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    checkpoint_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    rows_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review',
                    decision TEXT NOT NULL DEFAULT 'pending',
                    note TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_design_checkpoints_design_id
                    ON design_checkpoints(design_id, revision_id);

                CREATE TABLE IF NOT EXISTS approval_events (
                    id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_approval_events_design_id
                    ON approval_events(design_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL,
                    revision_id TEXT,
                    task_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'waiting',
                    summary TEXT,
                    payload_json TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_task_runs_design_id
                    ON task_runs(design_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS hitl_recipients (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL DEFAULT 'photon',
                    recipient TEXT NOT NULL,
                    display_name TEXT,
                    thread_key TEXT,
                    consent_status TEXT NOT NULL DEFAULT 'pending',
                    is_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_hitl_recipients_channel
                    ON hitl_recipients(channel, is_default DESC, created_at DESC);

                CREATE TABLE IF NOT EXISTS design_artifacts (
                    id TEXT PRIMARY KEY,
                    design_id TEXT NOT NULL,
                    revision_id TEXT,
                    artifact_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    path TEXT,
                    data_text TEXT,
                    data_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_design_artifacts_design_id
                    ON design_artifacts(design_id, artifact_key);

                CREATE TABLE IF NOT EXISTS design_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL,
                    design_id TEXT NOT NULL,
                    revision_id TEXT,
                    event_type TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_design_events_design_id
                    ON design_events(design_id, seq ASC);

                CREATE TABLE IF NOT EXISTS evolutions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    program_md TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    best_iteration_id TEXT,
                    design_id TEXT,
                    total_cost_usd REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS program_md_drafts (
                    id TEXT PRIMARY KEY,
                    evolution_id TEXT NOT NULL,
                    generator TEXT,
                    draft_content TEXT,
                    approved INTEGER NOT NULL DEFAULT 0,
                    approved_at TEXT,
                    user_edited_content TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_program_md_drafts_evolution_id
                    ON program_md_drafts(evolution_id);

                CREATE TABLE IF NOT EXISTS iterations (
                    id TEXT PRIMARY KEY,
                    evolution_id TEXT NOT NULL,
                    iter_num INTEGER NOT NULL,
                    morphology_id TEXT,
                    controller_ckpt_url TEXT,
                    trajectory_npz_url TEXT,
                    replay_mp4_url TEXT,
                    fitness_score REAL,
                    tracking_error REAL,
                    er16_success_prob REAL,
                    reasoning_log TEXT,
                    train_py_diff TEXT,
                    morph_factory_diff TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_iterations_evolution_id
                    ON iterations(evolution_id);
                """
            )
        self._ensure_columns(
            "ingest_jobs",
            {
                "reference_source_type": "TEXT",
                "reference_payload_json": "TEXT",
            },
        )
        self._ensure_columns(
            "designs",
            {
                "telemetry_json": "TEXT",
            },
        )

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        with self._connect() as conn:
            existing = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        for field in JSON_FIELDS:
            if field in data and data[field]:
                try:
                    data[field] = json.loads(data[field])
                except json.JSONDecodeError:
                    pass
        for field in BOOL_FIELDS:
            if field in data and data[field] is not None:
                data[field] = bool(data[field])
        return data

    def _normalize_values(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in JSON_FIELDS:
                normalized[key] = json.dumps(value) if not isinstance(value, str) else value
            elif key in BOOL_FIELDS:
                normalized[key] = 1 if value else 0
            else:
                normalized[key] = value
        return normalized

    def _upsert(self, table: str, payload: dict[str, Any], *, primary_key: str = "id") -> None:
        normalized = self._normalize_values(payload)
        columns = ", ".join(normalized.keys())
        placeholders = ", ".join("?" for _ in normalized)
        updates = ", ".join(
            f"{column}=excluded.{column}" for column in normalized.keys() if column != primary_key
        )
        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {table} ({columns})
                VALUES ({placeholders})
                ON CONFLICT({primary_key}) DO UPDATE SET {updates}
                """,
                tuple(normalized.values()),
            )
            conn.commit()

    def _update(self, table: str, where: dict[str, Any], fields: dict[str, Any]) -> None:
        normalized = self._normalize_values(fields)
        set_clause = ", ".join(f"{key}=?" for key in normalized.keys())
        where_clause = " AND ".join(f"{key}=?" for key in where.keys())
        with self._connect() as conn:
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
                tuple(normalized.values()) + tuple(where.values()),
            )
            conn.commit()

    def save_ingest_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "candidate_reviews" in payload and "candidate_reviews_json" not in payload:
            payload = dict(payload)
            payload["candidate_reviews_json"] = payload.pop("candidate_reviews")
        self._upsert("ingest_jobs", payload)
        return self.get_ingest_job(payload["id"])

    def get_ingest_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ingest_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def create_design(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("designs", payload)
        return self.get_design(payload["id"])

    def get_design(self, design_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM designs WHERE id = ?",
                (design_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def list_designs_by_ingest(self, ingest_job_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM designs WHERE ingest_job_id = ? ORDER BY candidate_id",
                (ingest_job_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def list_recent_design_contexts(
        self,
        *,
        limit: int = 24,
        exclude_ingest_job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT d.*, i.er16_plan_json
            FROM designs d
            LEFT JOIN ingest_jobs i ON i.id = d.ingest_job_id
        """
        params: list[Any] = []
        if exclude_ingest_job_id:
            query += " WHERE d.ingest_job_id <> ?"
            params.append(exclude_ingest_job_id)
        query += """
            ORDER BY d.is_user_selected DESC, d.is_model_preferred DESC, d.created_at DESC
            LIMIT ?
        """
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def update_design(self, design_id: str, fields: dict[str, Any]) -> None:
        self._update("designs", {"id": design_id}, fields)

    def create_design_revision(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("design_revisions", payload)
        return self.get_design_revision(payload["id"])

    def get_design_revision(self, revision_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM design_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def get_latest_design_revision(self, design_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM design_revisions
                WHERE design_id = ?
                ORDER BY revision_number DESC, created_at DESC
                LIMIT 1
                """,
                (design_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def list_design_revisions(self, design_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM design_revisions
                WHERE design_id = ?
                ORDER BY revision_number ASC, created_at ASC
                """,
                (design_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def replace_design_checkpoints(
        self,
        design_id: str,
        revision_id: str,
        checkpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM design_checkpoints WHERE design_id = ? AND revision_id = ?",
                (design_id, revision_id),
            )
            conn.commit()
        for checkpoint in checkpoints:
            self._upsert("design_checkpoints", checkpoint)
        return self.list_design_checkpoints(design_id, revision_id)

    def list_design_checkpoints(
        self,
        design_id: str,
        revision_id: str | None = None,
    ) -> list[dict[str, Any]]:
        latest = self.get_latest_design_revision(design_id)
        revision_id = revision_id or (latest or {}).get("id")
        if revision_id is None:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM design_checkpoints
                WHERE design_id = ? AND revision_id = ?
                ORDER BY created_at ASC
                """,
                (design_id, revision_id),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def get_design_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM design_checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def update_design_checkpoint(self, checkpoint_id: str, fields: dict[str, Any]) -> None:
        self._update("design_checkpoints", {"id": checkpoint_id}, fields)

    def create_approval_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("approval_events", payload)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approval_events WHERE id = ?",
                (payload["id"],),
            ).fetchone()
        return self._row_to_dict(row)

    def list_approval_events(self, design_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM approval_events
                WHERE design_id = ?
                ORDER BY created_at ASC
                """,
                (design_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def create_task_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("task_runs", payload)
        return self.get_task_run(payload["id"])

    def get_task_run(self, task_run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE id = ?",
                (task_run_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def update_task_run(self, task_run_id: str, fields: dict[str, Any]) -> None:
        self._update("task_runs", {"id": task_run_id}, fields)

    def list_task_runs(self, design_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM task_runs
                WHERE design_id = ?
                ORDER BY created_at ASC
                """,
                (design_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def append_design_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_values(payload)
        columns = ", ".join(normalized.keys())
        placeholders = ", ".join("?" for _ in normalized)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO design_events ({columns}) VALUES ({placeholders})",
                tuple(normalized.values()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM design_events WHERE seq = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return self._row_to_dict(row)

    def list_design_events(
        self,
        design_id: str,
        *,
        after_seq: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM design_events
                WHERE design_id = ? AND seq > ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (design_id, after_seq, limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def upsert_hitl_recipient(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("hitl_recipients", payload)
        return self.get_hitl_recipient(payload["id"])

    def get_hitl_recipient(self, recipient_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM hitl_recipients WHERE id = ?",
                (recipient_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def get_default_hitl_recipient(self, channel: str = "photon") -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM hitl_recipients
                WHERE channel = ?
                ORDER BY is_default DESC, updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (channel,),
            ).fetchone()
        return self._row_to_dict(row)

    def list_hitl_recipients(self, channel: str = "photon") -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM hitl_recipients
                WHERE channel = ?
                ORDER BY is_default DESC, updated_at DESC, created_at DESC
                """,
                (channel,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def update_hitl_recipient(self, recipient_id: str, fields: dict[str, Any]) -> None:
        self._update("hitl_recipients", {"id": recipient_id}, fields)

    def set_design_artifact(
        self,
        design_id: str,
        artifact_key: str,
        data: Any | None = None,
        *,
        revision_id: str | None = None,
        status: str = "ready",
        path: str | None = None,
    ) -> dict[str, Any]:
        artifact_id = f"{design_id}:{revision_id or 'latest'}:{artifact_key}"
        payload = {
            "id": artifact_id,
            "design_id": design_id,
            "revision_id": revision_id,
            "artifact_key": artifact_key,
            "status": status,
            "path": path,
            "data_text": data if isinstance(data, str) else None,
            "data_json": data if not isinstance(data, str) else None,
        }
        self._upsert("design_artifacts", payload)
        return self.get_design_artifact_row(design_id, artifact_key, revision_id)

    def get_design_artifact_row(
        self,
        design_id: str,
        artifact_key: str,
        revision_id: str | None = None,
    ) -> dict[str, Any] | None:
        revision_id = revision_id or (self.get_latest_design_revision(design_id) or {}).get("id")
        with self._connect() as conn:
            if revision_id:
                row = conn.execute(
                    """
                    SELECT * FROM design_artifacts
                    WHERE design_id = ? AND artifact_key = ? AND revision_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (design_id, artifact_key, revision_id),
                ).fetchone()
                if row is not None:
                    return self._row_to_dict(row)
            row = conn.execute(
                """
                SELECT * FROM design_artifacts
                WHERE design_id = ? AND artifact_key = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (design_id, artifact_key),
            ).fetchone()
        return self._row_to_dict(row)

    def get_design_artifact(
        self,
        design_id: str,
        artifact_key: str,
        revision_id: str | None = None,
    ) -> Any | None:
        row = self.get_design_artifact_row(design_id, artifact_key, revision_id)
        if row is None:
            return None
        return row.get("data_text") if row.get("data_text") is not None else row.get("data_json")

    def list_design_artifacts(
        self,
        design_id: str,
        revision_id: str | None = None,
    ) -> list[dict[str, Any]]:
        revision_id = revision_id or (self.get_latest_design_revision(design_id) or {}).get("id")
        with self._connect() as conn:
            if revision_id:
                rows = conn.execute(
                    """
                    SELECT * FROM design_artifacts
                    WHERE design_id = ? AND revision_id = ?
                    ORDER BY artifact_key ASC
                    """,
                    (design_id, revision_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM design_artifacts
                    WHERE design_id = ?
                    ORDER BY artifact_key ASC
                    """,
                    (design_id,),
                ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    def clear_design_selection(self, ingest_job_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE designs SET is_user_selected = 0 WHERE ingest_job_id = ?",
                (ingest_job_id,),
            )
            conn.commit()

    def create_evolution(self, run_id: str, evo_id: str | None = None) -> dict[str, Any]:
        evo_id = evo_id or str(uuid.uuid4())
        payload = {
            "id": evo_id,
            "run_id": run_id,
            "status": "pending",
        }
        self._upsert("evolutions", payload)
        return self.get_evolution(evo_id)

    def get_evolution(self, evo_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM evolutions WHERE id = ?",
                (evo_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def update_evolution(self, evo_id: str, fields: dict[str, Any]) -> None:
        self._update("evolutions", {"id": evo_id}, fields)

    def save_program_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("program_md_drafts", payload)
        return self.get_program_draft_by_evolution(payload["evolution_id"])

    def get_program_draft_by_evolution(self, evolution_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM program_md_drafts
                WHERE evolution_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (evolution_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def update_program_draft_by_evolution(self, evolution_id: str, fields: dict[str, Any]) -> None:
        draft = self.get_program_draft_by_evolution(evolution_id)
        if draft is None:
            return
        self._update("program_md_drafts", {"id": draft["id"]}, fields)

    def record_iteration(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._upsert("iterations", payload)
        return self.get_iteration(payload["id"])

    def get_iteration(self, iteration_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM iterations WHERE id = ?",
                (iteration_id,),
            ).fetchone()
        return self._row_to_dict(row)

    def list_iterations(self, evolution_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM iterations WHERE evolution_id = ? ORDER BY iter_num ASC, created_at ASC",
                (evolution_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]


workspace_store = WorkspaceStore()
