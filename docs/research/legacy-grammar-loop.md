---
description: The older modular grammar loop, its node graph, and how it differs from derivation-first grammar V2.
---

# Legacy Grammar Loop

The legacy loop lives in:

```text
packages/research/agent_loops/grammar_loop.py
```

It is registered as:

```text
grammar
```

## What it is

The legacy loop is a modular agent loop that builds and evaluates structural grammar rules. It predates the V2 `RobotDesignProgram` path.

## Modular loop API

The loop uses local primitives such as:

- `ModularAgentLoop`,
- `Node`,
- `add_edge`,
- `add_router`,
- node insertions.

These make the loop app-testable and configurable without requiring the product API to know its internal graph.

## Typical nodes

The loop can include nodes for:

- query normalization,
- state or checklist construction,
- structural rule generation,
- node-name resolution,
- structural rule compilation,
- evaluation,
- HITL summarization.

## LangGraph behavior

The loop can run without automatic LangGraph invocation unless the relevant environment flag enables it. This keeps unit tests from requiring every LangGraph runtime path.

## Difference from grammar V2

| Area | Legacy `grammar` | `grammar_v2` |
| --- | --- | --- |
| Body representation | Structural rules | `RobotDesignProgram` derivation |
| Compiler | Grammar graph helpers | `robot_program.py` compiler |
| App path | Still registered | Current baseline is V2 |
| Determinism | More agent-rule dependent | Deterministic expansion and lowering after program selection |

Use `grammar_v2` or `creative_qd_v2` for new product-facing generation unless there is a specific reason to test the legacy path.

