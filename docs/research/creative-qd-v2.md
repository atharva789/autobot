---
description: The quality-diversity loop that proposes multiple prompt variants and selects a strong generated body.
---

# Creative QD V2 Loop

`creative_qd_v2` lives in:

```text
packages/research/agent_loops/creative_qd_v2_loop.py
```

It wraps `grammar_v2` with a lightweight quality-diversity search.

## Purpose

The loop tries to avoid returning only the most obvious morphology. It explores candidate variations, measures their structural differences, and selects a useful candidate while preserving the same app-compatible HITL shape.

## Proposal modes

The loop can propose variants using modes such as:

- analogy,
- mutation,
- novelty,
- constraint inversion,
- exploit.

These modes alter the prompt or candidate framing before calling `grammar_v2`.

## Seed ideas

The current loop includes seed concepts such as:

- goat-like,
- inchworm-like,
- tank-tread-like,
- rock-climber brace.

Those seeds provide diversity pressure before the grammar compiler validates and lowers the final result.

## Archive behavior

The loop computes structural features for candidates and inserts them into a quality-diversity archive. It tracks morphology identity and physics-inspired features so candidates are not treated as interchangeable if their bodies differ meaningfully.

## Relationship to grammar V2

`creative_qd_v2` does not replace the grammar compiler. It calls `grammar_v2` for each candidate proposal and then chooses among the resulting HITL payloads.

That means the selected candidate still follows the same derivation-first body-generation path:

```text
proposal prompt -> grammar_v2 -> RobotDesignProgram -> expanded graph -> component program -> HITL
```

## Product behavior

The workspace SDK prefers `creative_qd_v2` when it is registered. If it is unavailable, product generation falls back to `grammar_v2`.

The selected HITL payload can include a `creative_qd` block with archive and selection metadata.

