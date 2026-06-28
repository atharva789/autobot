---
description: How the API calls app-compatible research loops and adapts grammar HITL into product candidates.
---

# Design Generation Route

The design generation route lives in `apps/api/routes/designs.py`.

It is the product adapter between workspace or ingest state and research loop output.

## Default loop

The route default is:

```python
DEFAULT_AGENT_LOOP = "grammar_v2"
```

Workspace generation may request another loop, and the SDK normally prefers `creative_qd_v2` when it is registered.

## `POST /designs/generate`

The route:

1. loads the ingest job,
2. derives a prompt from `plan.task_goal`, selected query, or raw prompt,
3. determines population size,
4. calls `run_agent_loop(...)`,
5. reads the returned HITL payload,
6. converts grammar candidates into product candidates,
7. stores design records and revisions,
8. creates review checkpoints,
9. returns candidates, render payloads, rankings, telemetry, and grammar HITL.

## Agent loop call

Conceptually:

```python
run_agent_loop(
    agent_loop,
    prompt,
    {"prompt": prompt, "candidates": [], "population": population},
    config=AgentLoopConfig(population=population),
)
```

The route expects the loop to return `AgentLoopResult(state=..., hitl=...)`.

## Candidate adaptation

`_candidate_from_grammar()` turns the HITL payload into a flat product candidate.

It pulls or infers:

- candidate name and summary,
- embodiment,
- morphology family,
- graph node and edge counts,
- compile-safe flag,
- number of legs,
- number of arms,
- torso dimensions,
- limb degrees of freedom,
- actuator class and torque,
- mass estimate,
- payload estimate,
- sensors,
- rationale,
- confidence.

## Embodiment inference

`_embodiment_from_hitl()` uses a layered fallback:

1. explicit program metadata,
2. symbol counts from the expanded graph,
3. inferred morphology names,
4. default quadruped.

The base morphology table covers common forms such as humanoid, biped, snake, worm chain, centipede, bird, and quadruped.

## Render payloads

The route currently emits conceptual render payloads and simple MJCF placeholders for product display. Full engineering compilation is handled by export routes and pipeline compilers.

## Loop discovery

`GET /designs/agent-loops` returns:

- the default loop,
- registered loop names from `list_agent_loops()`.

Use this endpoint when a frontend or automation needs to know whether `creative_qd_v2`, `grammar_v2`, or another loop is available.

## Important production boundary

This route should not contain the grammar algorithm. It should adapt loop output into product state. The generation algorithm lives in `packages/research/agent_loops/` and deterministic robot transforms live in `packages/pipeline/`.

