from __future__ import annotations

from apps.api import prompt_persistence


class FakeSupabaseQuery:
    def __init__(self, client: "FakeSupabaseClient"):
        self.client = client

    def insert(self, payload: dict, **kwargs: object):
        self.client.insert_payload = payload
        self.client.insert_kwargs = kwargs
        return self

    def execute(self):
        self.client.executed = True
        return object()


class FakeSupabaseClient:
    def __init__(self):
        self.table_name = ""
        self.insert_payload: dict | None = None
        self.insert_kwargs: dict[str, object] = {}
        self.executed = False

    def table(self, table_name: str):
        self.table_name = table_name
        return FakeSupabaseQuery(self)


def test_log_prompt_query_inserts_supabase_event(monkeypatch):
    client = FakeSupabaseClient()
    monkeypatch.setattr(prompt_persistence, "_get_prompt_supabase_client", lambda: client)

    event_id = prompt_persistence.log_prompt_query(
        event_type="robot_generation_query",
        prompt="make a quadruped",
        query_text="make a quadruped",
        ingest_job_id="job-1",
        normalized_query={"task_goal": "make a quadruped"},
        population=6,
        langsmith_trace_id="trace-1",
        metadata={"route": "/designs/generate"},
    )

    assert event_id
    assert client.table_name == "PromptQueries"
    assert client.insert_kwargs == {"returning": "minimal"}
    assert client.executed is True
    assert client.insert_payload is not None
    assert client.insert_payload["event_type"] == "robot_generation_query"
    assert client.insert_payload["prompt"] == "make a quadruped"
    assert client.insert_payload["normalized_query_json"]["task_goal"] == "make a quadruped"
    assert client.insert_payload["population"] == 6
    assert client.insert_payload["langsmith_trace_id"] == "trace-1"
    assert client.insert_payload["metadata_json"] == {"route": "/designs/generate"}


def test_log_prompt_query_is_noop_without_supabase(monkeypatch):
    monkeypatch.setattr(prompt_persistence, "_disabled_after_failure", False)
    monkeypatch.setattr(prompt_persistence, "_get_prompt_supabase_client", lambda: None)

    assert prompt_persistence.log_prompt_query(event_type="ingest_prompt_received", prompt="x") is None


def test_placeholder_supabase_env_disables_prompt_client(monkeypatch):
    prompt_persistence._get_prompt_supabase_client.cache_clear()
    monkeypatch.setenv("SUPABASE_URL", "https://<your-project-ref>.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "<your-service-role-key>")

    assert prompt_persistence._get_prompt_supabase_client() is None
    prompt_persistence._get_prompt_supabase_client.cache_clear()


def test_prompt_persistence_disables_after_insert_failure(monkeypatch):
    class FailingQuery:
        def insert(self, *_args: object, **_kwargs: object):
            return self

        def execute(self):
            raise RuntimeError("missing table")

    class FailingClient:
        calls = 0

        def table(self, _table_name: str):
            self.calls += 1
            return FailingQuery()

    client = FailingClient()
    monkeypatch.setattr(prompt_persistence, "_disabled_after_failure", False)
    monkeypatch.setattr(prompt_persistence, "_get_prompt_supabase_client", lambda: client)

    assert prompt_persistence.log_prompt_query(event_type="one") is None
    assert prompt_persistence.log_prompt_query(event_type="two") is None
    assert client.calls == 1
