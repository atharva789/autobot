# Demo Backend (Hackathon v1)

This is the minimal backend implementation for the 36-hour demo track:
- Seed 3 staged clips
- Create a run from prompt + clip
- Execute a mock retarget/sim pipeline
- Approve the run
- Export an artifact with `.parquet` filename

## API

- `GET /health`
- `GET /clips`
- `POST /runs` (creates and executes synchronously)
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/approve`
- `POST /runs/{run_id}/export`

## Run locally

```bash
uvicorn demo.app:app --reload
```

## TDD test suites

```bash
python3 -m pytest -q tests/test_phase1_store.py
python3 -m pytest -q tests/test_phase2_service.py
python3 -m pytest -q tests/test_phase3_api.py
```

## Notes

- The export path currently writes JSON content to a `.parquet` filename as a
  placeholder until parquet dependencies (`lerobot` + parquet writer stack) are pinned.
- The retarget/sim step currently writes deterministic mock artifacts for the
  hackathon control flow.

