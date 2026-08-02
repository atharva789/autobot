---
description: Product route map and the files that implement each route family.
---

# Route Index

## App root

| Path | File | Notes |
| --- | --- | --- |
| `/health` | `apps/api/app.py` | Health check |
| `/clips` | `apps/api/app.py` | Demo clip listing |
| `/runs` | `apps/api/app.py` | Demo run creation/listing |
| `/runs/{id}` | `apps/api/app.py` | Demo run detail |
| `/runs/{id}/approve` | `apps/api/app.py` | Demo approval |
| `/runs/{id}/export` | `apps/api/app.py` | Demo export |

## Ingest

| Path | File | Notes |
| --- | --- | --- |
| `POST /ingest` | `apps/api/routes/ingest.py` | Analyze prompt and create ingest job |
| `GET /ingest/{job_id}` | `apps/api/routes/ingest.py` | Fetch ingest job |

## Designs

| Path | File | Notes |
| --- | --- | --- |
| `POST /designs/generate` | `apps/api/routes/designs.py` | Generate candidates from ingest job |
| `GET /designs/agent-loops` | `apps/api/routes/designs.py` | List app-compatible loops |

## Exports

| Path | File | Notes |
| --- | --- | --- |
| `POST /designs/{design_id}/compile` | `apps/api/routes/exports.py` | Compile stored design |
| `GET /designs/{design_id}/artifacts` | `apps/api/routes/exports.py` | Return artifacts |
| `POST /designs/{design_id}/export/mujoco` | `apps/api/routes/exports.py` | Export MJCF |
| `POST /designs/{design_id}/export/print` | `apps/api/routes/exports.py` | Export print files |
| `GET /designs/{design_id}/procurement` | `apps/api/routes/exports.py` | Procurement report |

## Evolutions

| Path | File | Notes |
| --- | --- | --- |
| `POST /evolutions` | `apps/api/routes/evolutions.py` | Create evolution |
| `POST /evolutions/{id}/approve-program` | `apps/api/routes/evolutions.py` | Approve generated program |
| `POST /evolutions/{id}/stop` | `apps/api/routes/evolutions.py` | Stop evolution |
| `POST /evolutions/{id}/mark-best` | `apps/api/routes/evolutions.py` | Mark best candidate |
| `GET /evolutions/{id}` | `apps/api/routes/evolutions.py` | Fetch evolution |
| `GET /evolutions/{id}/iterations` | `apps/api/routes/evolutions.py` | List iterations |

## Workspace

Workspace routes live in `apps/api/routes/workspace.py` and delegate to `RobotWorkspaceSDK`.

Common route families:

- projects,
- threads,
- messages,
- generation,
- selected design,
- simulation specs,
- policy specs,
- context summaries.

