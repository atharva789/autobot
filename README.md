# IL Ideation

IL Ideation is a local-first robotics design workspace.

It takes a task prompt, finds or falls back to motion references, generates robot design candidates, compiles engineering render artifacts, exposes human-in-the-loop checkpoints, and tracks revision/export state through a FastAPI backend and a Next.js frontend.

## Current Scope

This repo currently includes:
- task ingest with YouTube-first motion lookup and DROID fallback
- Gemini-assisted design generation with deterministic post-processing
- task-conditioned ranking, hardrails, diversity controls, and validation reports
- engineering render artifact generation (`render_glb` + `ui_scene`)
- BOM generation and design telemetry
- revisioned HITL checkpoints and task/event streaming
- Photon/Spectrum setup and notification plumbing
- MuJoCo-oriented artifact generation paths and export scaffolding

This repo does **not** yet provide full CAD-grade geometry or production robotics exports across every target. The engineering renderer is materially richer than the original primitive viewer, but it is still a deterministic GLB scaffolding pipeline rather than a full authored CAD/mesh pipeline.

## Architecture

High-level flow:

```text
Prompt
  -> ingest job
  -> task spec / motion-source selection
  -> design candidate generation
  -> hardrails + task conditioning + diversity ranking
  -> engineering render + BOM + telemetry + validation
  -> revision / HITL decisions / tasks
  -> export and replay artifacts
```

Primary runtime surfaces:
- Backend: `demo/`
- Frontend: `apps/web/`
- Pipeline logic: `packages/pipeline/`
- Tests: `tests/`
- Plans and research notes: `plans/`, `research/`, `docs/architecture/`

Important backend routes:
- `POST /ingest`
- `GET /ingest/{id}`
- `POST /designs/generate`
- `GET /designs/{id}/spec`
- `GET /designs/{id}/checkpoints`
- `POST /designs/{id}/checkpoints/{checkpoint}/decision`
- `GET /designs/{id}/tasks`
- `POST /designs/{id}/tasks`
- `GET /designs/{id}/exports`
- `GET /designs/{id}/validation`
- `POST /designs/{id}/record-clip`
- `GET /designs/{id}/events`
- `GET /hitl/setup`
- `POST /hitl/setup`

## Repository Layout

```text
apps/web/                Next.js workspace UI
  app/                   app router pages
  components/            viewer + workspace components
  lib/                   frontend API/types

demo/                    FastAPI app and route layer
  routes/                ingest, designs, exports, HITL, evolutions
  services/              orchestration helpers

packages/pipeline/       core generation / validation / rendering logic
  design_generator.py    Gemini-facing design generation
  task_conditioning.py   task-fit scoring and reranking
  task_hardrails.py      climbing/crawling/slippery-terrain guards
  design_diversity.py    anti-collapse candidate diversity
  design_validation.py   validation loop reports
  engineering_render.py  backend GLB + scene generation
  droid_fallback.py      DROID retrieval fallback
  photon.py              Photon/Spectrum integration

tests/                   Python and contract tests
plans/                   implementation roadmap(s)
research/                deeper notes, evaluation runs, research track
```

## Requirements

- Python `>=3.11`
- Node.js `>=20`
- npm
- local virtualenv recommended

Heavy optional dependencies already declared in `pyproject.toml` include:
- `mujoco`
- `torch`
- `torch-geometric`
- `pinocchio`
- `pink`

If you only need the web/backend shell, you can still install the repo dependencies as declared and run the app locally.

## Environment

Copy `.env.example` to `.env` and fill what you need.

Main variables:

```bash
# Supabase (optional / legacy compatibility)
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=

# Google / Gemini / YouTube
GEMINI_API_KEY=
YOUTUBE_API_KEY=
GEMINI_MODEL=gemini-2.5-pro

# Modal / GVHMR
MODAL_TOKEN_ID=
MODAL_TOKEN_SECRET=
GVHMR_MODAL_APP_NAME=gvhmr-probe
GVHMR_MODAL_FUNCTION_NAME=run_probe

# App
NEXT_PUBLIC_API_URL=http://localhost:8000
EVOLUTION_ARTIFACTS_DIR=/tmp/il_ideation/evolutions

# Photon / Spectrum
PHOTON_PROJECT_ID=
PHOTON_SECRET_KEY=
# Optional local-only testing
# PHOTON_MOCK_MODE=1
```

### Minimum useful local setup
For the main workspace to function meaningfully, set at least:
- `GEMINI_API_KEY`
- `NEXT_PUBLIC_API_URL`

Recommended for full motion ingest:
- `YOUTUBE_API_KEY`
- Modal / GVHMR credentials

Recommended for HITL texting:
- `PHOTON_PROJECT_ID`
- `PHOTON_SECRET_KEY`

## Install

### Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Frontend

```bash
cd apps/web
npm install
cd ../..
```

## Run Locally

Backend:

```bash
source .venv/bin/activate
uvicorn demo.app:app --reload
```

Frontend:

```bash
cd apps/web
npm run dev
```

Then open:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

There is also a convenience target:

```bash
make dev
```

Note: `make dev` backgrounds the backend and starts the frontend; for debugging, running them in separate terminals is usually clearer.

## Test And Verification

Run the main backend test suite:

```bash
.venv/bin/python -m pytest -q
```

Run the frontend production build check:

```bash
cd apps/web
npm run build
```

Additional convenience targets from `Makefile`:

```bash
make test
make smoke-api
make smoke-morph
make smoke-gnn
make smoke-seed
make e2e-smoke
```

## Development Notes

### Design generation
The model does **not** directly emit the full internal design schema anymore. Provider-facing output is compact, then expanded deterministically to avoid Gemini structured-output schema-state failures.

### Motion ingest
The ingest path is YouTube-first. If YouTube fails due to timeout/auth/quota/weak retrieval, the backend can fall back to DROID-style structured trajectory retrieval.

### Rendering
The app defaults to the backend-generated engineering render path. The frontend consumes `render_glb` and `ui_scene` from the backend rather than inventing geometry locally.

### HITL
Checkpoint decisions, revision updates, and task/event streams are backend-backed. Photon/Spectrum support exists, but live outbound texting still depends on valid project credentials and recipient setup.

## Key Documents

- Implementation roadmap: [plans/2026-04-18-agentic-simulator-roadmap.md](plans/2026-04-18-agentic-simulator-roadmap.md)
- Recursive component IR note: [docs/architecture/recursive-component-ir.md](docs/architecture/recursive-component-ir.md)
- Phase 21 geometry note: [research/2026-04-19-phase-21-geometry-practices.md](research/2026-04-19-phase-21-geometry-practices.md)
- Systematic debugging follow-ups: [research/2026-04-19-systematic-debugging-followups.md](research/2026-04-19-systematic-debugging-followups.md)

## Current Constraints

The current strongest limitations are architectural, not UI-only:
- engineering geometry is richer, but still not full CAD-grade authored geometry
- recursive component generation is still shallower than a real assembly tree
- live external integrations depend on real credentials and provider setup
- simulation/export paths are present, but not every target is production-complete

If you are extending this repo, the next serious fidelity step is a recursive component IR plus CAD/mesh-backed geometry generation rather than more prompt-only tuning.
