---
description: What is implemented today, what is scaffolded, and what the current robot RL research program intends to add.
---

# Limits And Roadmap

## Implemented today

The repo currently supports:

- local workspace projects and threads,
- prompt-driven generation through app-compatible agent loops,
- deterministic grammar V2 fallback generation,
- creative QD wrapper selection when registered,
- product candidate persistence,
- concept robot rendering in the frontend,
- MJCF export scaffolding through canonical IR conversion,
- print/procurement route scaffolding,
- research strategies and benchmark harnesses,
- prompt templates and prompt hashing,
- local SQLite experiment storage.

## Scaffolded or partial

Treat these as partial unless verified in the specific environment:

- full mechanical CAD fidelity for every generated candidate,
- full MuJoCo screening for every body,
- long-running evolution jobs,
- YouTube/GVHMR ingestion enrichment,
- Supabase-backed production persistence,
- complete PPO training loop from product UI,
- GitBook remote deployment state.

## Research roadmap

The current Spec Kit plan at:

```text
specs/003-robot-rl-research-program/plan.md
```

describes a program for turning compile-safe robot graphs into validated control artifacts.

Planned task areas:

- goal generation,
- state and action space derivation,
- dynamics setup,
- policy architecture,
- reward design,
- critic/value learning,
- PPO training.

## Rule for roadmap docs

Do not describe planned research as shipped behavior. Keep the distinction clear:

- code that exists,
- tests that pass,
- local smoke evidence,
- research plan,
- production-ready workflow.

