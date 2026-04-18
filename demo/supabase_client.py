from __future__ import annotations
import os
from unittest.mock import MagicMock

from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_SERVICE_KEY", "")

try:
    from supabase import create_client, Client
    supa: object = create_client(url, key)
except (ImportError, Exception):
    # supabase not fully installed or credentials missing — use a mock stub
    supa = MagicMock()
