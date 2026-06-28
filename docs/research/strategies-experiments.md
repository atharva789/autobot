---
description: Research strategies, materialization, experiment runs, benchmark harnesses, and reproducibility metadata.
---

# Strategies And Experiments

Research strategies live in:

```text
packages/research/strategy/
```

Experiments live in:

```text
packages/research/experiment/
```

Benchmarks live in:

```text
packages/research/benchmark/
```

## Strategy protocol

The `GenerationStrategy` protocol is:

```python
generate(prompt, config) -> list[RobotDesignIR]
```

Strategies produce canonical IR designs for research benchmarking. They are not the same as app-compatible loops.

## Grammar strategy

`packages/research/strategy/grammar_strategy.py` wraps grammar-loop behavior for experiments.

It can:

- build V2 registry agents from prompt templates,
- run `run_grammar_v2_agent_loop`,
- pass program, graph, component program, spec, compile-safety, and HITL data to the materializer,
- create variants when fewer designs than the requested population are produced.

## LLM materializer

`packages/research/strategy/llm_materializer.py` converts graph or component data into `RobotDesignIR`.

It:

- extracts node contexts,
- requests physical attributes from an LLM when configured,
- uses deterministic fallback attributes when needed,
- builds links, joints, sensors, and actuators,
- validates and repairs dangling references.

## Experiment runner

`ExperimentRunner` orchestrates:

```text
strategy.generate() -> benchmark harness -> SQLite store
```

It captures a `ReproEnvelope` with:

- seed,
- model id,
- prompt hashes,
- strategy version,
- git SHA.

## Benchmark harness

The benchmark harness can:

- validate the IR,
- compile MJCF,
- run MuJoCo screening when available,
- measure stability and actuator coverage,
- compute diversity metrics,
- aggregate compile and screening results.

If MuJoCo or a heavier dependency is unavailable, the harness should degrade clearly rather than hiding the missing evidence.

## Research CLI

Common commands:

```bash
python3 -m packages.research.cli strategies
python3 -m packages.research.cli run "quadruped that climbs stairs" -s grammar --seed 42 -e stair-v1
python3 -m packages.research.cli show stair-v1
python3 -m packages.research.cli metrics <run-id>
python3 -m packages.research.cli compare <run-id-1> <run-id-2>
```

Use the CLI for reproducible research runs, not the product workspace route.

