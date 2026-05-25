"""Best-effort Supabase persistence for user prompts and derived robot queries."""

from __future__ import annotations

import logging
import os
import uuid
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
_disabled_after_failure = False


def _enabled() -> bool:
    return os.environ.get("PROMPT_PERSISTENCE_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _configured_value(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return not (
        "<" in value
        or ">" in value
        or lowered in {"fake", "fake-service-key", "your-service-role-key"}
        or "your-project-ref" in lowered
    )


def _configured_supabase_url(value: str | None) -> bool:
    if not _configured_value(value):
        return False
    parsed = urlparse(value or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@lru_cache(maxsize=1)
def _get_prompt_supabase_client() -> Any | None:
    load_dotenv(override=False)
    if not _enabled():
        return None
    url = os.environ.get("PROMPT_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("PROMPT_SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    )
    if not _configured_supabase_url(url) or not _configured_value(key):
        return None
    try:
        from supabase import create_client

        return create_client(url, key)
    except Exception:
        logger.debug("Supabase prompt persistence client unavailable.", exc_info=True)
        return None


def log_prompt_query(
    *,
    event_type: str,
    prompt: str | None = None,
    query_text: str | None = None,
    ingest_job_id: str | None = None,
    normalized_query: dict[str, Any] | None = None,
    population: int | None = None,
    langsmith_trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Insert one prompt/query event into Supabase without blocking generation."""
    global _disabled_after_failure
    if _disabled_after_failure:
        return None

    client = _get_prompt_supabase_client()
    if client is None:
        return None

    event_id = str(uuid.uuid4())
    table = os.environ.get("PROMPT_QUERIES_TABLE", "PromptQueries")
    row = {
        "id": event_id,
        "event_type": event_type,
        "prompt": prompt,
        "query_text": query_text,
        "ingest_job_id": ingest_job_id,
        "normalized_query_json": normalized_query,
        "population": population,
        "langsmith_trace_id": langsmith_trace_id,
        "metadata_json": metadata or {},
    }
    try:
        client.table(table).insert(row, returning="minimal").execute()
        return event_id
    except Exception:
        if os.environ.get("PROMPT_PERSISTENCE_DEBUG", "0") == "1":
            logger.warning(
                "Prompt persistence failed for event_type=%s ingest_job_id=%s",
                event_type,
                ingest_job_id,
                exc_info=True,
            )
            return None
        logger.warning(
            "Prompt persistence skipped after Supabase insert failure for event_type=%s ingest_job_id=%s",
            event_type,
            ingest_job_id,
        )
        if os.environ.get("PROMPT_PERSISTENCE_RETRY_ON_FAILURE", "0") != "1":
            _disabled_after_failure = True
        return None
