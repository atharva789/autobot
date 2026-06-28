---
description: The frontend TypeScript types that define product-visible generated design data.
---

# Frontend Contracts

Frontend contracts live in `apps/web/lib/types.ts`.

These types are the product-visible shape of generated robot data. They do not need to expose every internal research or pipeline field.

## Important contracts

| Type | Purpose |
| --- | --- |
| `RobotDesignCandidate` | Product-facing generated candidate |
| `TaskIntent` | Normalized task description |
| `RobotDesignProgram` | Program data when surfaced to the frontend |
| `GrammarHitl` | Grammar-loop review payload |
| `GenerateDesignsResponse` | Response from design generation |
| `DesignSpecResponse` | Design specification response |
| `WorkspaceProject` | Project metadata |
| `WorkspaceThread` | Thread metadata |
| `ThreadMessage` | User/assistant chat messages |
| `ThreadArtifact` | Generated artifacts attached to a thread |
| `SimulationSpec` | Simulation-check request and result |
| `PolicySpec` | Policy/training request and result |

## Contract discipline

When changing a generated-design field, update all relevant places together:

- `apps/api/routes/designs.py`,
- `apps/api/workspace_sdk.py`,
- `apps/api/workspace_store.py` if persisted,
- `apps/web/lib/types.ts`,
- `apps/web/components/MorphologyViewer.tsx`,
- route or frontend contract tests.

## Candidate versus IR

`RobotDesignCandidate` is a product view. It is optimized for:

- display,
- review,
- selection,
- simple rendering,
- user explanation.

`RobotDesignIR` is a canonical robotics representation. It is optimized for:

- compilation,
- validation,
- simulation,
- deterministic downstream processing.

Do not collapse them unless the product and pipeline requirements truly become identical.

## Grammar HITL payload

The HITL payload is the safest place to expose structured generation context to the frontend. It can include:

- summary,
- compile-safe status,
- graph information,
- component program,
- selected program,
- validation messages,
- candidate metadata.

The frontend should display or inspect this data, not mutate it into a new source of truth.

