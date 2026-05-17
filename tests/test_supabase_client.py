import os
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake")


def test_client_imports():
    from apps.api.supabase_client import supa
    assert supa is not None
