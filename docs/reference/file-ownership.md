---
description: Ownership table for common changes, with the right files and tests to inspect.
---

# File Ownership

## Change routing

| Task | Start here | Also inspect | Tests |
| --- | --- | --- | --- |
| Add a new app-selectable loop | `packages/research/agent_loops/` | `registry.py`, `tests/test_agent_loop_registry.py` | loop registry tests |
| Change body grammar | `packages/pipeline/robot_program.py` | `grammar_v2_loop.py`, `tests/test_robot_program_v2.py` | robot program tests |
| Change default generation behavior | `workspace_sdk.py` or `designs.py` | registry tests, frontend contracts | workspace/design route tests |
| Change candidate fields | `apps/api/routes/designs.py` | `apps/web/lib/types.ts`, `MorphologyViewer.tsx` | design and frontend contract tests |
| Change canonical robot fields | `packages/pipeline/ir/design_ir.py` | compiler, benchmark, materializer | pipeline/research tests |
| Change prompt templates | `packages/research/prompts/templates/` | prompt registry, strategy tests | research core tests |
| Change export behavior | `apps/api/routes/exports.py` | compilers, CAD, procurement | export or route tests |
| Change workspace state | `apps/api/workspace_store.py` | routes, SDK, frontend client | workspace store/route tests |
| Change main UI | `apps/web/app/page.tsx` | workspace API client, types | frontend build and contract tests |
| Change docs | `docs/` and `docs/SUMMARY.md` | `.gitbook.yaml`, README link | docs navigation validation |

## Architecture-sensitive files

Treat these as architecture-sensitive:

- `apps/api/routes/*.py`,
- `apps/api/workspace_sdk.py`,
- `apps/api/workspace_store.py`,
- `apps/web/lib/types.ts`,
- `packages/research/agent_loops/protocol.py`,
- `packages/research/agent_loops/registry.py`,
- `packages/research/strategy/protocol.py`,
- `packages/pipeline/robot_program.py`,
- `packages/pipeline/ir/design_ir.py`,
- migrations and schema files,
- dependency and build config.

If changing these, update the architecture handoff document required by the repo hook.

## Generated-body debugging checklist

When a generated body looks wrong:

1. Check which loop was selected in workspace or design response.
2. Inspect the returned grammar HITL payload.
3. Check `RobotDesignProgram` metadata and derivation steps.
4. Run or inspect `compile_robot_design_program()` in `robot_program.py`.
5. Compare graph symbol counts to candidate fields in `designs.py`.
6. Check frontend candidate types and `MorphologyViewer.tsx` rendering assumptions.
7. If export fails, inspect `_design_to_ir()` and `compile_to_mjcf()`.

