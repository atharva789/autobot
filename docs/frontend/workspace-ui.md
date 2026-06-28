---
description: How the main workspace page uses projects, threads, chat prompts, generated robot artifacts, and simulation/policy panels.
---

# Workspace UI

The main UI lives in `apps/web/app/page.tsx`.

It presents:

- project and thread navigation,
- a chat-style prompt input,
- generated robot panels,
- selected robot details,
- simulation checks,
- policy spec creation,
- context summaries.

## Default project behavior

The page creates or loads projects and threads through `workspaceApi`.

When creating projects, the UI can pass a selected agent loop, commonly:

```text
creative_qd_v2
```

The backend still validates availability and chooses a fallback when needed.

## Sending a prompt

The prompt flow is:

1. user enters a robot task,
2. `sendPrompt()` calls `workspaceApi.generate(threadId, { prompt, population: 4 })`,
3. backend appends user and assistant messages,
4. backend attaches a `robot_design` thread artifact,
5. frontend reads and displays the generated artifact.

## Robot panel

The robot panel displays the selected generated design using:

- candidate fields,
- render payloads,
- grammar HITL summaries,
- generated artifacts.

It should avoid reconstructing research-loop internals. The backend returns the candidate and payload fields the UI needs.

## Simulation panel

The UI can create simulation specs and run lightweight checks. These are not full RL training runs. The backend records the result and explicitly marks whether full training started.

## Policy panel

The UI can create policy specs describing:

- observations,
- actions,
- reward terms,
- safety constraints.

This is planning/scaffolding for downstream training, not a hidden PPO launcher.

## Context summaries

Context summaries are saved on the thread to make a workspace resumable. They summarize recent prompt, generation, and selected-design state.

