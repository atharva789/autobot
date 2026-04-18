"""Database migrations for the robot design pipeline.

Provides schema definitions and SQL generation for:
- designs table (stores 3 design candidates per ingest job)
- evolutions.design_id foreign key
"""
from __future__ import annotations

from typing import Any, Literal


def _get_supa():
    """Lazy import supabase client."""
    from demo.supabase_client import supa
    return supa

# Schema definition for the designs table
DESIGNS_TABLE_SCHEMA: dict[str, dict[str, Any]] = {
    "id": {
        "type": "uuid",
        "primary_key": True,
        "default": "gen_random_uuid()",
    },
    "ingest_job_id": {
        "type": "text",
        "nullable": False,
        "references": "ingest_jobs(id)",
    },
    "candidate_id": {
        "type": "text",
        "nullable": False,
        "check": "candidate_id IN ('A', 'B', 'C')",
    },
    "design_json": {
        "type": "jsonb",
        "nullable": False,
    },
    "bom_json": {
        "type": "jsonb",
        "nullable": True,
    },
    "is_model_preferred": {
        "type": "boolean",
        "default": "FALSE",
    },
    "is_user_selected": {
        "type": "boolean",
        "default": "FALSE",
    },
    "screening_score": {
        "type": "float",
        "nullable": True,
    },
    "created_at": {
        "type": "timestamptz",
        "default": "NOW()",
    },
}

# Column to add to evolutions table
EVOLUTIONS_DESIGN_ID_COLUMN: dict[str, str] = {
    "name": "design_id",
    "type": "uuid",
    "references": "designs(id)",
}


def generate_designs_table_sql() -> str:
    """Generate SQL to create the designs table."""
    columns = []
    constraints = []

    for col_name, col_def in DESIGNS_TABLE_SCHEMA.items():
        col_type = col_def["type"].upper()
        parts = [col_name, col_type]

        if col_def.get("primary_key"):
            parts.append("PRIMARY KEY")
        if col_def.get("default"):
            parts.append(f"DEFAULT {col_def['default']}")
        if col_def.get("nullable") is False:
            parts.append("NOT NULL")

        columns.append(" ".join(parts))

        if col_def.get("references"):
            constraints.append(
                f"FOREIGN KEY ({col_name}) REFERENCES {col_def['references']}"
            )
        if col_def.get("check"):
            constraints.append(f"CHECK ({col_def['check']})")

    all_parts = columns + constraints
    columns_sql = ",\n    ".join(all_parts)

    return f"""CREATE TABLE IF NOT EXISTS designs (
    {columns_sql}
);

-- Index for fast lookup by ingest_job_id
CREATE INDEX IF NOT EXISTS idx_designs_ingest_job_id ON designs(ingest_job_id);

-- Index for finding model-preferred designs
CREATE INDEX IF NOT EXISTS idx_designs_model_preferred ON designs(is_model_preferred) WHERE is_model_preferred = TRUE;

-- Enable RLS
ALTER TABLE designs ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role has full access to designs"
ON designs FOR ALL
TO service_role
USING (true)
WITH CHECK (true);
"""


def generate_evolutions_alter_sql() -> str:
    """Generate SQL to add design_id column to evolutions table."""
    col = EVOLUTIONS_DESIGN_ID_COLUMN
    return f"""ALTER TABLE evolutions
ADD COLUMN IF NOT EXISTS {col['name']} {col['type'].upper()} REFERENCES {col['references']};

-- Index for looking up evolutions by design
CREATE INDEX IF NOT EXISTS idx_evolutions_design_id ON evolutions(design_id);
"""


def generate_full_migration_sql() -> str:
    """Generate complete migration SQL."""
    return f"""-- Migration: Add designs table and link to evolutions
-- Generated for robot design pipeline

{generate_designs_table_sql()}

{generate_evolutions_alter_sql()}
"""


MigrationName = Literal["designs_table", "evolutions_design_id", "full"]


def run_migration(
    migration_name: MigrationName,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run a specific migration.

    Args:
        migration_name: Which migration to run.
        dry_run: If True, return SQL without executing.

    Returns:
        Dict with status and details.
    """
    sql_map = {
        "designs_table": generate_designs_table_sql,
        "evolutions_design_id": generate_evolutions_alter_sql,
        "full": generate_full_migration_sql,
    }

    if migration_name not in sql_map:
        return {"status": "error", "message": f"Unknown migration: {migration_name}"}

    sql = sql_map[migration_name]()

    if dry_run:
        return {"status": "dry_run", "sql": sql}

    try:
        # Execute via Supabase RPC or direct query
        # Note: Supabase MCP execute_sql is preferred for DDL
        supa = _get_supa()
        result = supa.rpc("exec_sql", {"query": sql}).execute()
        return {"status": "success", "result": result.data}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "sql": sql}


def get_migration_sql(migration_name: MigrationName) -> str:
    """Get the SQL for a migration without executing it."""
    result = run_migration(migration_name, dry_run=True)
    return result.get("sql", "")
