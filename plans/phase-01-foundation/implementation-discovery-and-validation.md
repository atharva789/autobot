# Phase 01: Foundation (Hackathon)

## Scope
Stand up the minimum software bones in 4 hours: monorepo, one FastAPI app, one Next.js app, SQLite, local `./data/` directory. No microservices, no queue, no multi-tenancy, no compliance scaffolding.

## Pinned Decisions
- Single FastAPI backend + single Next.js frontend. Python 3.11, Node 20.
- SQLite via SQLAlchemy. One database file at `./data/app.db`.
- Local filesystem storage under `./data/{videos,smpl,retargeted,replays,exports}/`.
- Async = `FastAPI.BackgroundTasks`. No Celery / Redis / Temporal / Arq.
- UUIDv4 IDs per row.
- Auth = none. Localhost single user.
- Observability = `print()` + uvicorn access logs.
- Env management = `uv` or `poetry`. Pick one in the first 30 minutes.

## Hours 0–4 Checklist
- [ ] Initialize monorepo: `apps/web/` (Next.js), `apps/api/` (FastAPI), `packages/pipeline/` (Python lib).
- [ ] Pin dependencies: fastapi, uvicorn, sqlalchemy, pydantic v2, python-multipart, mujoco, numpy, torch, huggingface-lerobot.
- [ ] Scaffold SQLite schema: `clips(id, title, video_path, smpl_path, tags)`, `runs(id, clip_id, prompt, status, replay_path, approved, created_at)`, `exports(id, run_id, parquet_path, created_at)`.
- [ ] Scaffold FastAPI routes: `GET /health`, `GET /clips`, `POST /runs`, `GET /runs/{id}`, `POST /runs/{id}/approve`, `POST /runs/{id}/export`, `GET /exports/{id}/download`.
- [ ] Scaffold Next.js `/` page with `fetch('/clips')` wired through a Next.js API proxy or direct to `localhost:8000`.
- [ ] Verify: `uvicorn` boots, `next dev` boots, `GET /health` returns 200, MuJoCo imports and loads `g1.urdf` without error.
- [ ] Commit a README with one-command boot (`make dev` or `just dev`).

## Explicitly Out of Scope
- Multi-tenant, orgs / projects / users / auth / RBAC.
- Job queues, retries, idempotency, dead letter.
- Object storage, S3, MinIO, presigned URLs.
- Vector index, embeddings, provenance ledger, audit log.
- Service maps, domain events, CQRS, sagas.
- Compliance posture, retention, takedown, deletion propagation.

## Exit Criteria
- `make dev` boots both servers.
- `curl localhost:8000/clips` returns the 3 pre-staged clip rows.
- `python -c "import mujoco; mujoco.MjModel.from_xml_path('assets/g1/g1.xml')"` loads without error.

## Handoff to Phase 02
- Clip seed data lives in `config/clips.yaml` and is loaded into SQLite at startup.
- API route surface exists; phase 02 just fills in handlers.
