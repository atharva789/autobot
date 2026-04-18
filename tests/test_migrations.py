"""Tests for database migrations - designs table."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class MockSupabaseResponse:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error


@pytest.fixture
def mock_supa():
    """Mock Supabase client."""
    mock = MagicMock()
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.insert.return_value = mock
    mock.update.return_value = mock
    mock.eq.return_value = mock
    mock.single.return_value = mock
    mock.order.return_value = mock
    mock.execute.return_value = MockSupabaseResponse(data=[])
    return mock


def test_designs_table_has_required_columns(mock_supa):
    """Verify designs table schema has all required columns."""
    from demo.migrations import DESIGNS_TABLE_SCHEMA

    required_columns = {
        "id",
        "ingest_job_id",
        "candidate_id",
        "design_json",
        "bom_json",
        "is_model_preferred",
        "is_user_selected",
        "screening_score",
        "created_at",
    }

    actual_columns = set(DESIGNS_TABLE_SCHEMA.keys())
    assert required_columns <= actual_columns, f"Missing columns: {required_columns - actual_columns}"


def test_designs_table_has_correct_types():
    """Verify designs table column types."""
    from demo.migrations import DESIGNS_TABLE_SCHEMA

    assert DESIGNS_TABLE_SCHEMA["id"]["type"] == "uuid"
    assert DESIGNS_TABLE_SCHEMA["candidate_id"]["type"] == "text"
    assert DESIGNS_TABLE_SCHEMA["design_json"]["type"] == "jsonb"
    assert DESIGNS_TABLE_SCHEMA["is_model_preferred"]["type"] == "boolean"
    assert DESIGNS_TABLE_SCHEMA["screening_score"]["type"] == "float"


def test_evolutions_table_has_design_id_column():
    """Verify evolutions table has design_id foreign key."""
    from demo.migrations import EVOLUTIONS_DESIGN_ID_COLUMN

    assert EVOLUTIONS_DESIGN_ID_COLUMN["name"] == "design_id"
    assert EVOLUTIONS_DESIGN_ID_COLUMN["type"] == "uuid"
    assert EVOLUTIONS_DESIGN_ID_COLUMN["references"] == "designs(id)"


def test_generate_designs_migration_sql():
    """Test SQL generation for designs table migration."""
    from demo.migrations import generate_designs_table_sql

    sql = generate_designs_table_sql()

    assert "CREATE TABLE" in sql
    assert "designs" in sql
    assert "id UUID PRIMARY KEY" in sql
    assert "ingest_job_id TEXT" in sql
    assert "design_json JSONB" in sql
    assert "is_model_preferred BOOLEAN" in sql


def test_generate_evolutions_alter_sql():
    """Test SQL generation for evolutions table alter."""
    from demo.migrations import generate_evolutions_alter_sql

    sql = generate_evolutions_alter_sql()

    assert "ALTER TABLE evolutions" in sql
    assert "ADD COLUMN IF NOT EXISTS design_id UUID" in sql
    assert "REFERENCES designs(id)" in sql


def test_run_migration_executes_sql(mock_supa):
    """Test that run_migration executes the SQL via Supabase."""
    from demo.migrations import run_migration

    with patch("demo.migrations._get_supa", return_value=mock_supa):
        mock_supa.rpc.return_value.execute.return_value = MockSupabaseResponse(data={"success": True})

        result = run_migration("designs_table")

        assert result["status"] == "success"
