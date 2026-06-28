---
description: Where to add loops, strategies, prompts, routes, render data, exports, and tests without crossing architectural boundaries.
---

# Extension Points

## Add a backend-selectable loop

Add the loop under:

```text
packages/research/agent_loops/
```

Then register it through `packages/research/agent_loops/registry.py`.

Required behavior:

- implement the `AgentLoopRunner` protocol,
- return `AgentLoopResult(state=..., hitl=...)`,
- preserve the backend-facing HITL shape,
- add tests in `tests/test_agent_loop_registry.py` or a focused loop test.

Only change `apps/api/routes/designs.py` if the product request or response contract must change.

## Add an experiment-only generation method

Use:

```text
packages/research/strategy/
```

Implement `GenerationStrategy.generate(prompt, config) -> list[RobotDesignIR]` and register it with the strategy registry.

Do not make product routes import the strategy directly. If the method should be app-selectable, wrap the needed behavior in an app-compatible agent loop.

## Add a prompt template

Use:

```text
packages/research/prompts/templates/
```

Prompt templates are loaded, rendered, versioned, and hashed by `PromptRegistry`. If a prompt affects reproducibility, include it in the reproducibility envelope or run metadata.

## Add a robot representation field

Changes to canonical robot fields usually belong in:

```text
packages/pipeline/ir/design_ir.py
packages/pipeline/robot_program.py
apps/web/lib/types.ts
```

Also check:

- product candidate conversion in `apps/api/routes/designs.py`,
- frontend rendering in `apps/web/components/MorphologyViewer.tsx`,
- export conversion in `apps/api/routes/exports.py`,
- tests that assert frontend/backend contract compatibility.

## Add a route

Use `apps/api/routes/` and mount the router in `apps/api/app.py`.

Routes should stay thin. Put reusable workflow logic in a service or SDK module, especially if the frontend and Electron workspace both need it.

## Add export behavior

Start in:

```text
apps/api/routes/exports.py
packages/pipeline/compilers/
packages/pipeline/cad/
packages/pipeline/procurement/
```

Export code should accept stored design data or canonical IR. It should not call research loops.

## Add viewer behavior

Start in:

```text
apps/web/components/MorphologyViewer.tsx
apps/web/lib/types.ts
```

If the viewer needs a new field, update the backend candidate payload and the frontend contract together.

