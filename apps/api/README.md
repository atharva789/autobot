# Backend

This is the FastAPI backend for the IL Ideation workspace.

For the full project overview, current architecture, and environment setup, start at the repo root:
- [../README.md](../README.md)

## Local run

```bash
source .venv/bin/activate
uvicorn demo.app:app --reload
```

Default local URL:
- `http://localhost:8000`

## Main route groups

- `/ingest`
- `/designs`
- `/exports`
- `/hitl`
- `/evolutions`

## Notes

- The backend is local-first for design workspace state.
- Design generation uses compact provider output plus deterministic expansion.
- Engineering render artifacts, checkpoints, task streams, validation reports, and HITL state are served from this app.
