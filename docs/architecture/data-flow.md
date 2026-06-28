---
description: The complete flow from prompt to generated robot body, saved artifact, rendered viewer, and export path.
---

# End To End Data Flow

## Prompt to body

```mermaid
sequenceDiagram
    participant User
    participant Web as Workspace UI
    participant WS as Workspace route
    participant SDK as RobotWorkspaceSDK
    participant Designs as /designs/generate
    participant Registry as Agent loop registry
    participant Loop as Agent loop
    participant Program as Robot program compiler
    participant Store as WorkspaceStore

    User->>Web: Describe a robot task
    Web->>WS: POST /workspace/threads/{id}/generate
    WS->>SDK: generate_for_thread()
    SDK->>Designs: generate_designs()
    Designs->>Registry: run_agent_loop()
    Registry->>Loop: grammar_v2 or creative_qd_v2
    Loop->>Program: compile_robot_design_program()
    Program-->>Loop: graph, component program, HITL
    Loop-->>Registry: AgentLoopResult
    Registry-->>Designs: state + hitl
    Designs->>Store: save designs, revisions, checkpoints
    Store-->>SDK: persisted candidates
    SDK-->>Web: assistant message + robot artifact
```

## Generated data shapes

| Shape | Owner | Description |
| --- | --- | --- |
| Prompt | Frontend and workspace SDK | Natural-language task request from the user |
| `AgentLoopConfig` | Research protocol | Population, attempts, confirmation, agents, and extra options |
| `RobotDesignProgram` | Pipeline | Derivation-first grammar program |
| `ExpandedRobotGraph` | Pipeline | Expanded graph of nodes, edges, symbols, and metadata |
| `ComponentProgram` | Pipeline | Lowered component-level body description |
| `RobotDesignHitlV2` | Pipeline | Reviewable payload with summary, validity, graph, components, and program |
| Product candidate | API route | Flat frontend-facing candidate bundle |
| Thread artifact | Workspace SDK | Saved artifact attached to a chat thread |
| Concept geometry | Frontend viewer | Three.js primitives derived from flat candidate fields |

## Ingest to generation

The ingest route can enrich a task before generation:

1. `POST /ingest` records the raw prompt.
2. `DemoService.analyze_prompt()` asks the configured model to produce a plan and search queries.
3. The route may select a YouTube reference, skip search via `SKIP_YOUTUBE_SEARCH=1`, or fall back to a DROID-style reference.
4. The ingest job is persisted in `workspace_store`.
5. `POST /designs/generate` loads the ingest job and uses `plan.task_goal` or `selected_query` as the generation prompt.

Workspace generation can also create a synthetic ingest job directly from a chat prompt. That keeps the design route reusable without requiring the user to pass through a video-ingest flow.

## Body to render

The current frontend viewer does not require a complete MJCF file to show a candidate. It can build a concept model from flat fields such as:

- embodiment,
- torso dimensions,
- leg count,
- arm count,
- limb degrees of freedom,
- actuator class,
- sensor list,
- compile-safe flag.

`MorphologyViewer.tsx` uses those fields to construct Three.js primitives for a quick visual inspection. Engineering exports remain separate.

## Body to export

Export endpoints use stored design data:

1. A design is converted to `RobotDesignIR` by `_design_to_ir()`.
2. `compile_to_mjcf()` emits MJCF XML.
3. engineering render helpers can produce UI scene data.
4. CAD and print export helpers can produce print-oriented files.
5. artifacts are saved back to `workspace_store`.

Some generated candidates are still concept-first. A compile-safe grammar program does not automatically mean the product has a final printable mechanical design.

