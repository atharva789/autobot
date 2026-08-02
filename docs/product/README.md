---
description: FastAPI product surface, route ownership, and how the workspace API coordinates generation without owning research internals.
---

# API Overview

The product API is a FastAPI app rooted at `apps/api/app.py`.

It mounts routers for:

- ingest,
- design generation,
- exports,
- evolutions,
- workspace projects and threads.

The API owns user workflow orchestration. It does not own the research logic that invents robot bodies, and it does not own the canonical robot IR.

## App factory

`create_app()` in `apps/api/app.py`:

- creates the FastAPI app,
- configures CORS for local and hosted frontend origins,
- initializes demo services,
- mounts product routers,
- exposes health and demo endpoints.

The route layer intentionally composes services rather than embedding all workflow state in the app factory.

## Main route groups

| Route group | File | Responsibility |
| --- | --- | --- |
| `/ingest` | `apps/api/routes/ingest.py` | Analyze task prompts and select motion/video references |
| `/designs` | `apps/api/routes/designs.py` | Generate robot candidates from an ingest job |
| `/exports` and design artifact routes | `apps/api/routes/exports.py` | Compile, export, and retrieve design artifacts |
| `/evolutions` | `apps/api/routes/evolutions.py` | Create and run evolution jobs |
| `/workspace` | `apps/api/routes/workspace.py` | Project/thread/chat workspace API |

## Product candidate model

The API adapts generated robot data into product candidates with fields the frontend can render and discuss:

- candidate id,
- title and rationale,
- embodiment,
- morphology summary,
- torso dimensions,
- limb counts,
- degrees of freedom,
- actuator class,
- sensor list,
- payload and mass estimates,
- confidence,
- compile-safety metadata,
- render payloads,
- grammar HITL payload.

That candidate bundle is not the same as canonical `RobotDesignIR`. It is a product-facing view over generated body information.

## Workspace-first path

The most important user path is:

```text
POST /workspace/projects
POST /workspace/projects/{project_id}/threads
POST /workspace/threads/{thread_id}/generate
```

The generation endpoint delegates to `RobotWorkspaceSDK.generate_for_thread()`, which chooses an agent loop, creates a synthetic ingest job, calls the design route, stores artifacts, and appends assistant messages.

