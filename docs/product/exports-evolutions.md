---
description: Artifact compilation, MJCF export, print export, procurement reports, and evolution jobs.
---

# Exports And Evolutions

## Exports route

Export behavior lives in `apps/api/routes/exports.py`.

The route group handles:

- compiling a stored design,
- returning stored artifacts,
- exporting MJCF,
- exporting print-oriented files,
- returning procurement reports.

## Compile design

`POST /designs/{design_id}/compile`:

1. loads the stored design,
2. converts it to `RobotDesignIR` through `_design_to_ir()`,
3. calls `compile_to_mjcf(ir)`,
4. builds UI scene data,
5. saves artifacts back to `workspace_store`.

Current conversion can use defaults if detailed morphology data is missing. That makes it useful for smoke testing, but not a substitute for a complete mechanical design pipeline.

## Retrieve artifacts

`GET /designs/{design_id}/artifacts` returns saved artifact payloads such as:

- MJCF XML,
- UI scene data,
- export metadata.

## MuJoCo export

`POST /designs/{design_id}/export/mujoco` ensures the design has been compiled and returns an artifact path like:

```text
artifacts/{design_id}/robot.mjcf
```

## Print export

`POST /designs/{design_id}/export/print` uses CAD helpers to write print-oriented files under:

```text
data/exports/{design_id}
```

## Procurement

`GET /designs/{design_id}/procurement` resolves components and returns a procurement report. This connects generated robot concepts to component-slot planning.

## Evolutions route

Evolution behavior lives in `apps/api/routes/evolutions.py`.

The route can:

- create an evolution job,
- draft a `program.md`,
- approve the program,
- run a background evolution loop,
- stop an evolution,
- mark the best result,
- list iteration history.

## Evolution work directories

Evolution artifacts are written under `EVOLUTION_ARTIFACTS_DIR` when set, or a local default under `/tmp/il_ideation/evolutions`.

## Background loop

The evolution loop uses:

- `EvolutionConfig`,
- a CLI/Gemini orchestrator,
- optional legacy clip lookup,
- Modal dispatch for trials,
- iteration persistence.

It is separate from the immediate prompt-to-body agent loop path. Treat it as a longer-running product workflow.

