from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Allow running without Supabase in test mode
TESTING = os.environ.get("TESTING", "").lower() in ("1", "true", "yes")

supa: object | None = None

if not url or not key:
    if not TESTING:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set. "
            "Copy .env.example to .env and fill in credentials."
        )
else:
    try:
        from supabase import create_client, Client
        supa = create_client(url, key)
    except ImportError:
        if not TESTING:
            raise ImportError(
                "supabase-py is not installed or not importable. "
                "Run: pip install supabase"
            )
