"""Tests for the sim-worker compute-plane process (build-order step 6).

`process_job`/`serve` are exercised against in-memory fakes only — no live Redis or MinIO — so
this suite runs the same in CI (no Compose stack) as it does against the real services. The real
services are exercised separately, outside pytest, when the Compose stack itself is brought up.
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from packages.research.loop_research.baselines import build_dev_a_baseline
from packages.research.loop_research.sim_worker import JobError, MinioStorage, process_job, serve


def _job(**overrides) -> dict:
    scaffold = build_dev_a_baseline()
    job = {
        "job_id": "job_test",
        "scaffold": asdict(scaffold),
        "schema_id": "dev-a",
        "policy": "zeros",
        "episodes": 2,
        "step_budget": 20,
        "seed": 1,
    }
    job.update(overrides)
    return job


def test_process_job_returns_a_valid_rollout_batch() -> None:
    batch = process_job(_job())
    assert batch["episodes"] == 2
    assert batch["step_budget"] == 20
    assert sum(batch["termination_histogram"].values()) == 2
    assert batch["batch_id"].startswith("rb_")


def test_process_job_rejects_unknown_schema() -> None:
    with pytest.raises(JobError):
        process_job(_job(schema_id="not-a-real-schema"))


def test_process_job_rejects_unknown_policy() -> None:
    with pytest.raises(JobError):
        process_job(_job(policy="ppo_v7"))


class _FakeQueue:
    def __init__(self, jobs: list[dict | None]) -> None:
        self._jobs = list(jobs)
        self.results: list[tuple[str, str]] = []

    def pop_job(self, timeout: int) -> dict | None:
        return self._jobs.pop(0) if self._jobs else None

    def push_result(self, job_id: str, batch_id: str) -> None:
        self.results.append((job_id, batch_id))


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}

    def put_json(self, key: str, payload: dict) -> None:
        self.objects[key] = payload


def test_serve_processes_one_job_end_to_end() -> None:
    queue = _FakeQueue([_job()])
    storage = _FakeStorage()

    processed = serve(queue, storage, poll_timeout=0, max_iterations=1)

    assert processed == 1
    assert "job_test.json" in storage.objects
    assert len(queue.results) == 1
    job_id, batch_id = queue.results[0]
    assert job_id == "job_test"
    assert storage.objects["job_test.json"]["batch_id"] == batch_id


def test_serve_skips_empty_polls_without_erroring() -> None:
    queue = _FakeQueue([None, None])
    storage = _FakeStorage()

    processed = serve(queue, storage, poll_timeout=0, max_iterations=2)

    assert processed == 0


def test_serve_logs_and_continues_past_a_malformed_job() -> None:
    queue = _FakeQueue([_job(schema_id="bogus"), _job()])
    storage = _FakeStorage()

    processed = serve(queue, storage, poll_timeout=0, max_iterations=2)

    assert processed == 1
    assert len(storage.objects) == 1


class _FakeMinioClient:
    def __init__(self, existing_buckets: set[str] | None = None) -> None:
        self._buckets = set(existing_buckets or ())
        self.made_buckets: list[str] = []
        self.put_objects: list[tuple[str, str]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self._buckets

    def make_bucket(self, bucket: str) -> None:
        self._buckets.add(bucket)
        self.made_buckets.append(bucket)

    def put_object(self, bucket, key, stream, length, content_type):
        self.put_objects.append((bucket, key))


def test_minio_storage_creates_bucket_when_missing() -> None:
    client = _FakeMinioClient(existing_buckets=set())
    MinioStorage(client, bucket="loop-research")
    assert client.made_buckets == ["loop-research"]


def test_minio_storage_reuses_existing_bucket() -> None:
    client = _FakeMinioClient(existing_buckets={"loop-research"})
    MinioStorage(client, bucket="loop-research")
    assert client.made_buckets == []


def test_minio_storage_put_json_writes_the_bucket_and_key() -> None:
    client = _FakeMinioClient(existing_buckets={"loop-research"})
    storage = MinioStorage(client, bucket="loop-research")
    storage.put_json("job_test.json", {"a": 1})
    assert client.put_objects == [("loop-research", "job_test.json")]


class _RaceLoserMinioClient(_FakeMinioClient):
    """Reproduces the real race docker-compose.yml's 2 sim-worker replicas hit: both see
    bucket_exists() == False, then the loser's make_bucket() raises. Verified against a real
    MinIO service, not just guessed at -- running 2 replicas concretely produced
    `S3Error: ... code: BucketAlreadyOwnedByYou`."""

    def make_bucket(self, bucket: str) -> None:
        error = Exception("S3 operation failed; code: BucketAlreadyOwnedByYou")
        error.code = "BucketAlreadyOwnedByYou"
        raise error


def test_minio_storage_treats_bucket_already_owned_race_as_success() -> None:
    client = _RaceLoserMinioClient(existing_buckets=set())
    MinioStorage(client, bucket="loop-research")  # must not raise


class _OtherFailureMinioClient(_FakeMinioClient):
    def make_bucket(self, bucket: str) -> None:
        error = Exception("S3 operation failed; code: AccessDenied")
        error.code = "AccessDenied"
        raise error


def test_minio_storage_reraises_unrelated_bucket_errors() -> None:
    client = _OtherFailureMinioClient(existing_buckets=set())
    with pytest.raises(Exception, match="AccessDenied"):
        MinioStorage(client, bucket="loop-research")
