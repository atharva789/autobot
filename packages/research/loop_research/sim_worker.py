"""Compute-plane worker for spec-012 build order step 6 (plan.md §4's `sim-worker` service,
run by `infra/loop-research/docker-compose.yml` at 2 replicas).

Consumes rollout jobs from the `queue` Redis service, runs them against the schema+rollout
machinery build-order step 1 already produced (`mujoco_compiler.compile_scaffold`,
`rollout.run_batch`), and reports the resulting `RolloutBatch` back through the `artifacts` MinIO
service plus a Redis results list.

No producer exists yet — step 7 (the real loop) is what will eventually push real jobs onto the
queue this module reads. Today's job is exactly what step 6 asks for and no more: prove the wiring
(queue in, physics, artifacts out) works end to end, on an honest job format documented below.
`main()` idles on an empty queue rather than fabricate a source of jobs to keep busy.

Job format, popped from `QUEUE_KEY` (a Redis list, via BRPOP — one job per pop):

    {
      "job_id": "job_...",
      "scaffold": <TrainingScaffold, as produced by dataclasses.asdict>,
      "schema_id": "dev-a" | "dev-b",
      "policy": "zeros",                 # the only policy implemented so far; see _POLICIES
      "episodes": 8,
      "step_budget": 300,
      "seed": 7
    }

Result batches are stored as JSON in the artifacts bucket at "<job_id>.json"; the batch id is also
pushed to `RESULTS_KEY` so a caller polling the queue can learn a job finished without touching
MinIO for that lookup. Step 7 owns replacing the single "zeros" policy once there is a real one to
run.
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
from dataclasses import asdict
from typing import Any, Mapping, Protocol

import numpy as np

from packages.research.loop_research.baselines import DEV_A_SCHEMA, DEV_B_SCHEMA
from packages.research.loop_research.entity_table import load_model_and_entities
from packages.research.loop_research.mujoco_compiler import compile_scaffold
from packages.research.loop_research.rollout import run_batch
from packages.research.loop_research.scaffold import scaffold_from_dict

logger = logging.getLogger("loop_research.sim_worker")

_SCHEMA_BY_ID = {"dev-a": DEV_A_SCHEMA, "dev-b": DEV_B_SCHEMA}
_POLL_TIMEOUT = 5


def _zeros_policy(n_actuators: int):
    def policy(constants, step):
        return np.zeros(n_actuators)

    return policy


_POLICIES = {"zeros": _zeros_policy}


class JobError(ValueError):
    """A job was malformed or named an unknown schema/policy — not a system fault, so `serve`
    logs and moves on rather than crashing the worker over one bad message."""


def process_job(job: Mapping[str, Any]) -> dict:
    """Runs one rollout job. Pure with respect to I/O — takes and returns plain dicts, so it is
    testable without a live queue or storage backend."""

    schema_id = job.get("schema_id")
    schema_path = _SCHEMA_BY_ID.get(schema_id)
    if schema_path is None:
        raise JobError(f"unknown schema_id {schema_id!r}; expected one of {sorted(_SCHEMA_BY_ID)}")

    policy_name = job.get("policy", "zeros")
    policy_factory = _POLICIES.get(policy_name)
    if policy_factory is None:
        raise JobError(f"unknown policy {policy_name!r}; expected one of {sorted(_POLICIES)}")

    scaffold = scaffold_from_dict(job["scaffold"])
    model, entities = load_model_and_entities(schema_path)
    compiled_factory = lambda: compile_scaffold(scaffold, model, entities)  # noqa: E731

    batch = run_batch(
        scaffold,
        model,
        compiled_factory,
        policy_factory(model.nu),
        batch_id=f"rb_{uuid.uuid4().hex[:12]}",
        episodes=int(job.get("episodes", 8)),
        max_steps=int(job.get("step_budget", 300)),
        seed=int(job.get("seed", 0)),
    )
    return asdict(batch)


class Queue(Protocol):
    def pop_job(self, timeout: int) -> dict | None: ...
    def push_result(self, job_id: str, batch_id: str) -> None: ...


class Storage(Protocol):
    def put_json(self, key: str, payload: Mapping[str, Any]) -> None: ...


class RedisQueue:
    def __init__(self, client: Any, queue_key: str, results_key: str) -> None:
        self._client = client
        self._queue_key = queue_key
        self._results_key = results_key

    def pop_job(self, timeout: int) -> dict | None:
        item = self._client.brpop(self._queue_key, timeout=timeout)
        if item is None:
            return None
        _, raw = item
        return json.loads(raw)

    def push_result(self, job_id: str, batch_id: str) -> None:
        self._client.lpush(self._results_key, json.dumps({"job_id": job_id, "batch_id": batch_id}))


class MinioStorage:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        if self._client.bucket_exists(bucket):
            return
        try:
            self._client.make_bucket(bucket)
        except Exception as exc:  # noqa: BLE001 - only swallow the one known race, below
            # docker-compose.yml runs 2 sim-worker replicas that start together and both call
            # this at once; verified by actually running 2 replicas that both raced
            # bucket_exists() -> False before either had created it, and the loser's
            # make_bucket() raised exactly this -- a benign "someone else already made it"
            # outcome, not a real failure. minio.error.S3Error only exists when the real client
            # library is installed, so this checks by attribute rather than importing the type,
            # keeping the fakes in tests/test_loop_research_sim_worker.py free to raise plain
            # exceptions for the "not this race" branch below.
            if getattr(exc, "code", None) != "BucketAlreadyOwnedByYou":
                raise

    def put_json(self, key: str, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._client.put_object(
            self._bucket, key, io.BytesIO(body), length=len(body), content_type="application/json"
        )


def serve(
    queue: Queue,
    storage: Storage,
    *,
    poll_timeout: int = _POLL_TIMEOUT,
    max_iterations: int | None = None,
) -> int:
    """Runs the poll loop; returns the number of jobs successfully processed.

    `max_iterations` bounds an otherwise-infinite loop for tests; production `main()` leaves it
    unset and runs until the process is stopped, same as any other queue consumer.
    """

    processed = 0
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        job = queue.pop_job(poll_timeout)
        if job is None:
            continue
        job_id = job.get("job_id", f"job_{uuid.uuid4().hex[:12]}")
        try:
            batch = process_job(job)
        except JobError as exc:
            logger.warning("job %s rejected: %s", job_id, exc)
            continue
        storage.put_json(f"{job_id}.json", batch)
        queue.push_result(job_id, batch["batch_id"])
        processed += 1
        logger.info("job %s -> batch %s", job_id, batch["batch_id"])
    return processed


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    import redis
    from minio import Minio

    queue_url = os.environ["QUEUE_URL"]
    # redis-py's default socket_timeout (5s in the version this was verified against) races
    # BRPOP's own server-side block timeout (also `_POLL_TIMEOUT` below) -- if they're equal, the
    # client's read can time out a moment before the server would have replied, raising
    # redis.exceptions.TimeoutError on a perfectly healthy, empty queue. Caught by actually
    # running this against a live redis service (docker compose up), not by inspection: the
    # client needs strictly more patience than the timeout it's asking the server to honor.
    redis_client = redis.Redis.from_url(queue_url, socket_timeout=_POLL_TIMEOUT + 5)
    queue = RedisQueue(
        redis_client,
        queue_key=os.environ.get("QUEUE_KEY", "loop:jobs"),
        results_key=os.environ.get("RESULTS_KEY", "loop:results"),
    )

    endpoint = os.environ["ARTIFACTS_ENDPOINT"].split("://", 1)[-1]
    minio_client = Minio(
        endpoint,
        access_key=os.environ["ARTIFACTS_KEY"],
        secret_key=os.environ["ARTIFACTS_SECRET"],
        secure=False,
    )
    bucket = os.environ.get("ARTIFACTS_BUCKET", "loop-research")
    storage = MinioStorage(minio_client, bucket=bucket)

    logger.info("sim_worker ready: queue=%s bucket=%s", queue_url, bucket)
    serve(queue, storage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
