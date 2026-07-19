# SDD Checkpoint: Agentic Robot Design Evals

**Reached**: 2026-07-19
**Phase**: Product reset and specification revised; awaiting approval before planning
**Spec Kit status**: `needs-plan`

## Product decision

The task-to-robot-body workbench has been rejected as the main product. Codex and Claude Code can use CAD, robot-description, simulator, and ROS skills or MCP servers to assemble most of that workflow.

The proposed replacement evaluates those agentic systems:

```text
protected robotics task
  -> Codex / Claude Code / another agent works with allowed tools
  -> independent graders inspect the final robot artifacts
  -> real compilation and physics execute
  -> repeated results compare model + harness + skills + MCPs
```

IL Ideation does not design the robot for the user. It tests whether the agent produced a correct robot outcome.

## First 12-hour build

1. Create six protected tasks across robot-description repair, constrained robot modification, and executed MuJoCo behavior.
2. Give every task a passing reference solution and a seeded failure.
3. Isolate the agent from graders and answers.
4. Record the complete model, harness, instructions, skills, MCPs, tools, budget, transcript, runtime, cost, and final artifacts.
5. Run real structural, compiler, simulator, and behavior graders.
6. Compare two complete system profiles at the task and trial level.
7. Preserve a reproducible evidence bundle.
8. Produce a drift report and a product kill report.
9. Use existing local dependencies with zero mandatory cloud spend.

The slice is a falsification test. It is not permission to build a hosted platform, public leaderboard, new simulator, new IR, distributed runner, or enterprise workflow.

## Specification package

- `spec.md`: direct product, buyer, use cases, first slice, five user stories, 22 requirements, 12 success criteria, and kill conditions.
- `research.md`: current agent, CAD, Isaac Sim, ROS, eval, robotics-CI, and morphology substitutes; surviving niche; market gates.
- `red-team/agentic-ai-audit.md`: one consolidated four-round debate and jury verdict.
- `checklists/requirements.md`: completed clarity, threat-model, robotics-validity, and readiness checks.

## Decision requested

Choose one:

- `approve`: continue to the Spec Kit plan, data model, contracts, 12-hour tasks, and implementation;
- `revise`: change the product or specification again before planning; or
- `deny`: stop and preserve the research and specification.

## Intentionally not run

- Implementation plan, data model, contracts, and tasks.
- Source code, API, schema, or architecture changes.
- Cloud deployment, paid compute, Isaac Sim provisioning, HIL, or physical tests.

These phases remain held at the Spec Kit approval checkpoint.

## Validation completed

- Spec Kit reports `needs-plan`; no plan, data model, contracts, tasks, or implementation goal exists for Spec 011.
- The specification contains 22 sequential `FR` requirements and 12 sequential `SC` criteria.
- No unresolved clarification, TODO, TBD, or placeholder marker remains in the normative specification.
- Every local Markdown link in the README and specification package resolves.
- Whitespace validation passes for the README and every file in the specification package.
