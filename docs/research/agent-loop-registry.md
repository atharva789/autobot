---
description: How app-compatible loops are registered, discovered, run, and traced.
---

# Agent Loop Registry

The registry lives in:

```text
packages/research/agent_loops/registry.py
```

It is the approved product-to-research bridge.

## Public functions

| Function | Purpose |
| --- | --- |
| `register_agent_loop(name, runner)` | Register a loop implementation |
| `get_agent_loop(name)` | Retrieve a registered runner |
| `list_agent_loops()` | Return available loop names |
| `run_agent_loop(name, prompt, initial_state=None, config=None)` | Execute a loop by name |

## Built-in loop loading

The registry loads built-ins lazily so import-time failures do not break the entire app. Current built-ins include:

- `creative_qd_v2`,
- `grammar_v2`,
- `grammar`.

This lazy loading is important because some research dependencies may be heavier than product startup should require.

## Runner contract

Loops follow the `AgentLoopRunner` protocol from `packages/research/agent_loops/protocol.py`:

```python
loop(prompt, initial_state=None, *, config=None) -> AgentLoopResult
```

`AgentLoopResult` contains:

- `state`: full debug or research state,
- `hitl`: backend-facing payload.

## Configuration

`AgentLoopConfig` includes:

- population,
- max attempts,
- confirmed specification,
- normalizer agent,
- rule builder agent,
- evaluator agent,
- human confirmation flag,
- extra options.

## Trace metadata

`run_agent_loop()` normalizes LangSmith or tracing metadata into returned state and HITL when available. That lets product and tests inspect trace ids without knowing how the loop was instrumented.

## Product use

Product code should use:

```python
run_agent_loop(...)
list_agent_loops()
```

It should not import `grammar_v2_loop.py` or `creative_qd_v2_loop.py` directly unless there is a narrow test or development reason.

