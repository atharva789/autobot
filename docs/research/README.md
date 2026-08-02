---
description: The research package, including app-compatible agent loops, experiment strategies, prompt registries, benchmark harnesses, and local model adapters.
---

# Research Overview

Research code lives in `packages/research/`.

It is a Python package for experimenting with robot generation methods and evaluating the quality, diversity, and reproducibility of generated designs.

## Main responsibilities

The research layer owns:

- app-compatible agent loops,
- experiment-only generation strategies,
- prompt templates,
- local model adapters,
- benchmark harnesses,
- metrics,
- SQLite experiment storage,
- research CLI commands,
- notebooks and evaluation scripts.

It does not own product routes, frontend rendering, or workspace persistence.

## Package map

| Path | Purpose |
| --- | --- |
| `agent_loops/` | App-callable loops that return `AgentLoopResult` |
| `strategy/` | Experiment-facing generation strategies |
| `prompts/` | Versioned YAML prompt templates and hashing |
| `experiment/` | Runner, run types, reproducibility envelopes |
| `benchmark/` | Validation, screening, metrics, diversity |
| `storage/` | Research run persistence |
| `local_chat_models.py` | Local and remote chat-model adapters |
| `cli.py` | Research command-line interface |
| `notebooks/` | Interactive research notebooks |

## Two generation surfaces

| Surface | Used by | Returns |
| --- | --- | --- |
| Agent loop | Product API and loop tests | `AgentLoopResult(state, hitl)` |
| Generation strategy | Research CLI and experiment runner | `list[RobotDesignIR]` |

The app-compatible loop can be used by product code. The experiment strategy is for research benchmarking.

## Why both exist

The product needs a stable, reviewable payload. The research package needs flexible experiments and exact run comparisons. Splitting loops from strategies lets product use the best current loop without inheriting every experiment harness detail.

## Current headline loops

| Loop | File | Summary |
| --- | --- | --- |
| `grammar_v2` | `agent_loops/grammar_v2_loop.py` | Derivation-first RoboGrammar loop |
| `creative_qd_v2` | `agent_loops/creative_qd_v2_loop.py` | Quality-diversity proposal loop that wraps grammar V2 |
| `grammar` | `agent_loops/grammar_loop.py` | Legacy modular structural-rule loop |

