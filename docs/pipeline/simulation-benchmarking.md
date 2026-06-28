---
description: Simulation validation, MuJoCo screening, benchmark metrics, and research evaluation.
---

# Simulation And Benchmarking

Simulation helpers live in:

```text
packages/pipeline/simulation/
```

Research benchmark code lives in:

```text
packages/research/benchmark/
```

## Pipeline validation

Pipeline validators check whether a design is structurally valid and whether it can be compiled or screened.

Useful concepts include:

- `validate_design()`,
- `validate_compiles()`,
- `validate_full()`,
- `screen_design(ir)`.

## MuJoCo screening

`mujoco_screening.py` provides a screening layer for properties such as:

- stability,
- reachability,
- task sanity,
- zero-control behavior where applicable.

The code should gracefully report missing MuJoCo or unavailable screening rather than pretending evidence exists.

## Research benchmark harness

`packages/research/benchmark/harness.py` can:

- evaluate a single `RobotDesignIR`,
- evaluate a population of designs,
- compile MJCF,
- run screening,
- aggregate metrics.

## Metrics

The benchmark layer tracks metrics such as:

- compile success,
- stability,
- actuator coverage,
- diversity,
- structural distance,
- candidate-level screening results.

## Product simulation checks

Workspace simulation checks are lighter. `RobotWorkspaceSDK.run_simulation_checks()` records whether a generated artifact has enough compile/render evidence and whether screening metadata clears a threshold when present.

It does not run full RL training.

## Research roadmap

The current Spec Kit research program under `specs/003-robot-rl-research-program/` plans a graph-general RL stack:

- goal generation,
- state/action spaces,
- dynamics,
- policies,
- rewards,
- critics,
- PPO training.

Treat those specs as implementation planning unless the corresponding code and tests exist.

