---
description: A complete field guide to the IL_ideation robot design workspace, from prompt ingestion to grammar loops, generated bodies, renders, exports, and research experiments.
---

# Robodex

Robodex is the operating manual for `IL_ideation`: a local-first robot design workspace that turns natural-language tasks into candidate robot bodies, reviewable engineering artifacts, and research-grade experiment records.

The system has two product surfaces and one shared robotics core:

{% hint style="info" %}
Product code lives in `apps/`. Research code lives in `packages/research/`. Shared robot representations, compilers, render helpers, CAD helpers, and validators live in `packages/pipeline/`.
{% endhint %}

## Start here

{% cards %}
{% card title="Architecture" icon="sitemap" %}
Understand the product layer, research layer, shared pipeline, and the one approved bridge between them.
{% endcard %}

{% card title="Robot body generation" icon="bot" %}
Trace how a user prompt becomes a grammar-derived robot body, component program, flat candidate bundle, and interactive Three.js concept model.
{% endcard %}

{% card title="Agent loops" icon="repeat" %}
Read how `grammar_v2`, `creative_qd_v2`, and the legacy grammar loop are registered, selected, run, traced, and tested.
{% endcard %}

{% card title="Production details" icon="server" %}
Operate the API, workspace SDK, SQLite state, frontend contracts, exports, tests, and documentation publishing workflow.
{% endcard %}
{% endcards %}

## The shortest accurate answer

Robot-body generation is owned by the research and pipeline layers, then adapted into product-friendly candidates by the API:

1. The frontend calls the workspace API with a prompt.
2. `RobotWorkspaceSDK` chooses an agent loop, preferring `creative_qd_v2` when available and falling back to `grammar_v2`.
3. The selected loop produces a derivation-first `RobotDesignProgram`.
4. `packages/pipeline/robot_program.py` deterministically expands that program into a robot graph, validates it, lowers it into a component program, and builds the HITL payload.
5. `apps/api/routes/designs.py` converts the HITL payload into flat candidates for the frontend and stores the results.
6. `apps/web/components/MorphologyViewer.tsx` renders a concept body from those candidate fields, while export endpoints can compile stored designs into MJCF or print-oriented assets.

## Repository map

| Area | Code | Purpose |
| --- | --- | --- |
| Product API | `apps/api/` | FastAPI app, routes, workspace SDK, local persistence, exports, evolutions |
| Product web | `apps/web/` | Next.js and Electron workspace UI, chat, robot viewer, simulation/policy panels |
| Research loops | `packages/research/agent_loops/` | App-compatible agent loops and the loop registry |
| Research strategy | `packages/research/strategy/` | Experiment-facing generation strategies and LLM materialization |
| Shared pipeline | `packages/pipeline/` | Canonical IR, robot grammar program compiler, render, MJCF, CAD, validation |
| Tests | `tests/` | Unit and contract tests across product, research, frontend, and pipeline |
| Specs | `specs/` | Spec Kit plans for the robot RL research program |

## What this documentation is for

This site is written for engineers and agents who need to change the repo without breaking its layer boundaries. It emphasizes:

- where code lives,
- what owns each responsibility,
- what data shapes cross module boundaries,
- how robot bodies are generated,
- what is production-ready versus scaffolded,
- how to validate changes before shipping.

