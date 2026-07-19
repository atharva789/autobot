# Agentic Robot Design Evals POC Design

**Date**: 2026-07-19
**Approval**: The user approved the evaluator concept and explicitly requested a built POC,
implementation refinement, defensibility testing, and recursive adjacent-concept exploration.

## Goal

Determine whether an independent evaluator for agent-produced robot artifacts provides value beyond a
competent engineer, Codex, MuJoCo, and ordinary scripts. The POC must work locally and may conclude
that the engine is commodity or should remain open source.

## Approved approach

Build a headless research CLI with six protected robot-model tasks. A task copies only public starter
files into a temporary workspace. A sandboxed Codex process edits those files. After it exits, the
runner freezes and hashes the outcome, executes protected structural and MuJoCo graders, and writes an
ordinary-files evidence bundle. Two controlled Codex profiles differ only in public robotics context.

A separate, intentionally small control script receives the same public task contracts and frozen
outcomes. Defensibility is measured by consequential failure detection, leakage resistance,
reproducibility, task-authoring effort, and comparison effort, not by code volume or presentation.

## Scope

- Six tasks: two robot-description repairs, two constrained modifications, and two executed behaviors.
- Reference and seeded-failure fixtures for every task.
- Real MuJoCo loads and time-stepped behavior grades.
- macOS protected-path sandboxing for live Codex trials.
- Immutable artifacts, transcripts, hashes, grades, raw output, environment, and comparison results.
- Three trials per nondeterministic profile.
- One strongest-substitute control and one written kill decision.

## Non-goals

- A frontend, API, hosted service, queue, new database, or new robot IR.
- Claude parity in the first controlled experiment.
- Isaac Sim, URDF, sensor/mesh fidelity, RL training, HIL, or physical validation.
- An overall score, automatic best-robot label, or safety/manufacturing claim.
- Treating protected tests or orchestration code as a moat without customer and physical evidence.

## Architecture

```text
public task + starter + controlled system profile
  -> temporary workspace
  -> outer protected-path sandbox + Codex workspace sandbox
  -> frozen final artifact snapshot
  -> protected task-specific grader
  -> direct IR/MJCF/MuJoCo evidence
  -> immutable filesystem bundle
  -> replay and profile comparison
```

The implementation is one new research module plus additions to the existing research CLI and one
focused test file. Direct functions and frozen records are preferred. Splitting modules requires
observed implementation pain, not predicted scale.

## Components

1. Canonical records for task, profile, artifact, grade, trial, bundle, and comparison.
2. Task/profile loading with path containment and content fingerprints.
3. Starter copying, symlink rejection, artifact freezing, and SHA-256 manifests.
4. A shell-free subprocess launcher wrapped by `sandbox-exec`.
5. Protected grader loading after the agent process terminates.
6. Direct MuJoCo model inspection and fixed-control rollouts.
7. JSON evidence bundles, deterministic replay, and task-level comparison.
8. A small control script that exposes how much of the runner is easy to reproduce.

## Error handling

Invalid manifests stop before execution. Missing dependencies and isolation are `unrun`; timeouts are
`timeout`; agent and grader failures are `error`; contract failures are `failed`. None are silently
coerced into another state. Bundle writes are atomic at manifest level, and an incomplete bundle is
never reported as a completed result.

## Testing

Every behavior follows red-green-refactor. Reference fixtures must pass, seeded failures must fail the
intended assertion, and at least one seeded failure must load successfully in MuJoCo before failing a
robotics-semantic or behavior grade. A live isolation probe must prove workspace access and repository
denial. Three deterministic replays must produce the same canonical evidence digest.

## Rollout

1. Implement and validate deterministic fixtures and graders.
2. Prove isolation and bundle replay.
3. Freeze two controlled Codex profiles and run three trials per task/profile.
4. Freeze outcomes and run both evaluator and control against identical artifacts.
5. Publish the evidence-backed continue, refine, open-source, or kill decision locally.
6. Select the next concept-tree node only after reviewing that decision.

## Open questions resolved by the POC

- Can protected robotics graders catch errors beyond XML parsing and MuJoCo loading?
- Can one engineer reproduce the customer-valued result with a small script in one day?
- Does robotics context change Codex task outcomes under a controlled model/harness comparison?
- Is task authoring cheap enough to support a growing corpus?
- Does reproducibility and isolation create meaningful value, or only more ceremony?

The normative implementation sources remain
[`spec.md`](../../specs/011-b2b-feasibility-evidence/spec.md),
[`plan.md`](../../specs/011-b2b-feasibility-evidence/plan.md), and the generated `tasks.md`.
