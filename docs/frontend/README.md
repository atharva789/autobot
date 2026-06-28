---
description: The Next.js and Electron workspace UI, its backend client, and its generated robot rendering responsibilities.
---

# Frontend Overview

The frontend lives in `apps/web/`.

It is a Next.js app with an Electron shell for desktop use. Its job is to present the workspace, send user prompts to the backend, display generated robot candidates, and expose simulation and policy panels.

## Main files

| Path | Responsibility |
| --- | --- |
| `apps/web/app/page.tsx` | Main workspace page |
| `apps/web/lib/workspace-api.ts` | HTTP client for workspace endpoints |
| `apps/web/lib/types.ts` | Shared frontend TypeScript contracts |
| `apps/web/components/MorphologyViewer.tsx` | Three.js robot concept and engineering viewer |
| `apps/web/components/workspace/` | Workspace-specific UI components |
| `apps/web/electron/` | Desktop shell code |

## Design principle

The frontend should render and operate on backend-owned state. It should not decide which research loop to run, how to compile robot programs, or how to evaluate designs.

Good frontend responsibilities:

- collect the prompt,
- show messages,
- call workspace APIs,
- render candidates,
- let users select designs,
- show simulation/policy status,
- expose controls.

Backend responsibilities:

- choose agent loops,
- create ingest jobs,
- generate candidates,
- persist workspace state,
- create simulation and policy records,
- compile/export artifacts.

## API base URL

`workspace-api.ts` uses:

```text
NEXT_PUBLIC_API_URL
```

when set, otherwise it defaults to:

```text
http://127.0.0.1:8000
```

## Data freshness

The UI should treat workspace API responses as source of truth. Thread artifacts and selected-design state are persisted in the backend store, not in local-only component state.

