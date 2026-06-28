---
description: The practical map of the repository, with each major directory tied to the responsibility it owns.
---

# Repository Map

`IL_ideation` is organized around a strict separation of product engineering, research experimentation, and shared robotics infrastructure.

{% hint style="warning" %}
Do not treat `apps/`, `packages/research/`, and `packages/pipeline/` as interchangeable. Most mistakes in this repo come from putting product orchestration in research code, or putting experimental strategy logic in product routes.
{% endhint %}

## Product layer

| Path | Role |
| --- | --- |
| `apps/api/app.py` | FastAPI app factory and route mounting |
| `apps/api/routes/` | HTTP routes for ingest, designs, exports, evolutions, and workspace APIs |
| `apps/api/workspace_sdk.py` | Backend-owned workspace orchestration used by the frontend |
| `apps/api/workspace_store.py` | Local SQLite persistence for workspace, design, ingest, artifact, simulation, and policy state |
| `apps/web/app/page.tsx` | Main workspace UI |
| `apps/web/components/` | Viewer, controls, UI primitives, and workspace components |
| `apps/web/lib/workspace-api.ts` | TypeScript client for `/workspace/*` backend endpoints |
| `apps/web/lib/types.ts` | Frontend-facing contracts for candidates, HITL, artifacts, specs, and workspace state |

The product layer is responsible for user workflows: creating projects, sending prompts, saving generated designs, rendering candidates, approving checkpoints, compiling exports, and tracking workspaces.

## Research layer

| Path | Role |
| --- | --- |
| `packages/research/agent_loops/registry.py` | App-compatible loop registry and execution entrypoint |
| `packages/research/agent_loops/grammar_v2_loop.py` | Current derivation-first RoboGrammar loop |
| `packages/research/agent_loops/creative_qd_v2_loop.py` | Quality-diversity wrapper around grammar V2 |
| `packages/research/agent_loops/grammar_loop.py` | Legacy modular loop based on structural grammar rules |
| `packages/research/strategy/` | Experiment-facing generation strategies and materialization |
| `packages/research/prompts/` | Versioned prompt templates and prompt hashing |
| `packages/research/experiment/` | Experiment runner, run metadata, and reproducibility envelopes |
| `packages/research/benchmark/` | Validation, MJCF compilation, screening, metrics, and diversity |
| `packages/research/cli.py` | Command-line interface for research experiments |

The research layer is responsible for trying generation methods, measuring them, and storing reproducible experiment results. Product code may call its app-compatible agent-loop registry, but research code must not import product code.

## Shared pipeline

| Path | Role |
| --- | --- |
| `packages/pipeline/robot_program.py` | Robot Design Program V2 schema, deterministic expansion, validation, lowering, and HITL creation |
| `packages/pipeline/ir/design_ir.py` | Canonical robot IR dataclasses |
| `packages/pipeline/compilers/mjcf_compiler.py` | `RobotDesignIR` to MJCF compiler |
| `packages/pipeline/engineering_render.py` | Engineering render payload construction |
| `packages/pipeline/grammar_graph.py` | Legacy grammar catalog helpers and Supabase-backed grammar vocabulary |
| `packages/pipeline/simulation/` | Structural validation, MuJoCo screening, and simulation result types |
| `packages/pipeline/cad/` | CAD assembly and print export helpers |
| `packages/pipeline/components/` | Component slots, resolver logic, and bill-of-material concepts |
| `packages/pipeline/procurement/` | Procurement provider interfaces and reports |

The shared pipeline owns robot representations and deterministic transforms. It should remain independent of UI, FastAPI route concerns, and experiment orchestration.

## Specs and docs

| Path | Role |
| --- | --- |
| `specs/003-robot-rl-research-program/` | Current Spec Kit umbrella plan for robot RL research |
| `AGENTS.md` | Agent-facing architecture guide and workflow rules |
| `.codex` | Architecture handoff document required for architecture-sensitive commits |
| `docs/` | GitBook source for Robodex |

## Current body-generation code path

The practical source trail for robot body generation is:

```text
apps/web/app/page.tsx
  -> apps/web/lib/workspace-api.ts
  -> apps/api/routes/workspace.py
  -> apps/api/workspace_sdk.py
  -> apps/api/routes/designs.py
  -> packages/research/agent_loops/registry.py
  -> packages/research/agent_loops/creative_qd_v2_loop.py or grammar_v2_loop.py
  -> packages/pipeline/robot_program.py
  -> apps/api/routes/designs.py
  -> apps/api/workspace_store.py
  -> apps/web/components/MorphologyViewer.tsx
```

