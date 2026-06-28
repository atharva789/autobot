---
description: Shared robot representations, deterministic transforms, compilers, validation, rendering, CAD, and procurement.
---

# Pipeline Overview

The shared pipeline lives in:

```text
packages/pipeline/
```

It is used by both product and research code.

## What the pipeline owns

The pipeline owns:

- robot grammar program schemas,
- expanded robot graphs,
- component programs,
- canonical robot IR,
- MJCF compilation,
- UI scene and engineering render data,
- simulation validation and screening,
- CAD and print export helpers,
- component resolution and procurement reports.

## What the pipeline should not own

The pipeline should not own:

- FastAPI routes,
- React components,
- workspace persistence,
- research experiment scheduling,
- prompt orchestration,
- user chat history.

## Major modules

| Module | Purpose |
| --- | --- |
| `robot_program.py` | Derivation-first robot program compiler |
| `ir/design_ir.py` | Canonical robot design dataclasses |
| `schemas.py` | Shared product/task schema helpers |
| `compilers/mjcf_compiler.py` | MJCF compiler |
| `engineering_render.py` | Engineering render payload builder |
| `grammar_graph.py` | Legacy grammar vocabulary helpers |
| `simulation/` | Validation and MuJoCo screening |
| `cad/` | CAD assembly and print export |
| `components/` | Component slots and resolver |
| `procurement/` | Procurement provider/report abstraction |

## Design rule

If a transform should be deterministic, reusable, and independent of a UI or experiment runner, it probably belongs in `packages/pipeline/`.

