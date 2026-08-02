---
description: Install, configure, and run the local API, frontend, research CLI, and documentation source.
---

# Local Setup

## Python environment

The repo is packaged as `autoresearch-robotics` and expects Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Prefer `python3` in shell commands. Some local environments do not provide a reliable bare `python` executable.

## Backend API

Run the FastAPI app from the repository root:

```bash
uvicorn apps.api.app:app --host 127.0.0.1 --port 8000
```

The app factory in `apps/api/app.py` mounts the ingest, design, export, evolution, and workspace routers. The default workspace database is local SQLite at `/tmp/il_ideation/workspace.sqlite3` unless `WORKSPACE_DB_PATH` is set.

## Frontend

Install frontend dependencies and start the Next.js app:

```bash
cd apps/web
npm install
npm run dev
```

The frontend uses `NEXT_PUBLIC_API_URL` when set. Otherwise `apps/web/lib/workspace-api.ts` defaults to `http://127.0.0.1:8000`.

## Electron workspace

The web app includes Electron scripts for the desktop workspace shell:

```bash
cd apps/web
npm run desktop:dev
```

The Electron shell is intended to stay thin. Workspace orchestration belongs in the backend SDK, not in renderer-only logic.

## Research CLI

The package exposes a `research` console script and also supports module execution:

```bash
python3 -m packages.research.cli strategies
python3 -m packages.research.cli run "quadruped that climbs stairs" -s grammar --seed 42 -e stair-v1
python3 -m packages.research.cli show stair-v1
```

Research runs persist to the configured research store, normally a local SQLite database under the research run directory.

## Local model provider

Research loops should use `packages/research/local_chat_models.py` rather than importing a remote chat model directly.

Common provider choices:

| Provider | Environment |
| --- | --- |
| Codex local thread | `RESEARCH_LLM_PROVIDER=codex` |
| Claude Code | `RESEARCH_LLM_PROVIDER=claude-code` |
| Explicit OpenAI fallback | `RESEARCH_LLM_PROVIDER=openai` |

If no live model is configured, several paths intentionally use deterministic fallback generation so tests and local development can still run.

## Documentation source

Robodex lives in `docs/` and is configured by the root `.gitbook.yaml`.

```bash
gitbook dev
```

This installed GitBook CLI is the current integration-oriented CLI. It does not expose the legacy `gitbook build` command. Use the validation workflow in [Run And Verify](verification.md) to check links and navigation locally.

