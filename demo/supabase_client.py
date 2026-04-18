from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not url or not key:
    raise EnvironmentError(
        "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set. "
        "Copy .env.example to .env and fill in credentials."
    )

try:
    from supabase import create_client, Client
    supa: object = create_client(url, key)
except ImportError as exc:
    raise ImportError(
        "supabase-py is not installed or not importable. "
        "Run: pip install supabase"
    ) from exc
