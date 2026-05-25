"""Shared database connection helpers for pipeline modules."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - only hit when dependency is missing
    create_client = None


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """Create a cached Supabase client from grammar-specific or default env vars."""
    load_dotenv(override=False)
    url = os.environ.get("GRAMMAR_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = (
        os.environ.get("GRAMMAR_SUPABASE_SERVICE_KEY")
        or os.environ.get("GRAMMAR_SUPABASE_KEY")
        or os.environ.get("GRAMMAR_SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and a Supabase key must be set, or provide "
            "GRAMMAR_SUPABASE_URL with GRAMMAR_SUPABASE_SERVICE_KEY, "
            "GRAMMAR_SUPABASE_KEY, or GRAMMAR_SUPABASE_PUBLISHABLE_KEY."
        )
    if create_client is None:
        raise RuntimeError(
            "The PyPI package `supabase` is required for grammar database access "
            "(this is the supabase-py client that provides `supabase.create_client`)."
        )
    return create_client(url, key)
