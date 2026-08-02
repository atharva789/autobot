# SDD Checkpoint: Agentic Robot Design Evals

**Reached**: 2026-07-19
**Phase**: Deterministic root POC implemented; live and complete-substitute gates remain partial
**Spec Kit status**: `partial-with-explicit-unrun-gates`

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

## Implemented deterministic local build

1. Six protected tasks cover robot-description repair, constrained MJCF modification, and executed
   MuJoCo behavior.
2. All six references pass and all six seeded failures are caught.
3. Exact task/profile/grader/environment snapshots, transcript and grade hashes, frozen artifacts,
   replay, integrity-checked comparison inputs, and source revisions are implemented in ordinary files.
4. Structural, file-format, compile, simulator-load, static, and behavior grades remain distinct.
5. Twelve deterministic bundles replay identically three times.
6. A one-file 291-SLOC control matches all twelve evaluator grading decisions.
7. The real controlled Codex comparison remains `unrun`: the inner Codex sandbox cannot start inside
   the outer sandbox and global skills contaminate the empty profile.
8. The drift and kill report is in `poc-results.md`; mandatory spend remains zero.

The slice is a falsification test. It is not permission to build a hosted platform, public leaderboard, new simulator, new IR, distributed runner, or enterprise workflow.

## Specification package

- `spec.md`: direct product, buyer, use cases, first slice, five user stories, 22 requirements, 12 success criteria, and kill conditions.
- `research.md`: current agent, CAD, Isaac Sim, ROS, eval, robotics-CI, and morphology substitutes; surviving niche; market gates.
- `red-team/agentic-ai-audit.md`: one consolidated four-round debate and jury verdict.
- `checklists/requirements.md`: completed clarity, threat-model, robotics-validity, and readiness checks.

## Approval history

The user approved the evaluator concept on 2026-07-19 and explicitly requested a built POC,
implementation refinement, defensibility testing, and recursive exploration of adjacent concepts.

Generated implementation sources:

- `plan.md`: one-module, headless local architecture and falsification protocol;
- `data-model.md`: task, profile, trial, grade, artifact, bundle, and comparison records;
- `contracts/`: task, profile, evidence-bundle, and CLI contracts;
- `quickstart.md`: executable validation flow;
- `tasks.md`: 48 dependency-ordered test-first tasks;
- `implementation-goal.md`: local goal record because the prior thread goal remains externally blocked.

## Decision

The product decision is `refine`, not `continue`. The frozen-artifact grading/comparison layer is
open-source-style infrastructure because the small control reaches parity there. The control does not
reproduce agent execution, isolation, profile capture, or hash-checked evidence bundles, and the live
agent and engineer-plus-Codex comparisons are unrun. The protected robotics failure corpus is
technically useful but has no external-failure, buyer-recurrence, or physical-calibration evidence.

The next reviewed node is `Agentic Robot Model-Repair Evals`. It is not approved for implementation
until a disposable uncontaminated runner and externally sourced repair faults are available.

## Still intentionally out of scope

- Cloud deployment, paid compute, Isaac Sim provisioning, HIL, or physical tests.
- A frontend, API, new database, distributed runner, generalized registry, or new robot IR.
- Claude parity during the first controlled profile experiment.

## Validation completed

- The release selection passes 180 tests with one third-party deprecation warning; all quickstart
  commands and 18 local Markdown links pass.
- Spec Kit's artifact scanner reports `ready-to-implement` with `tasks_complete=false` because the
  live and full-substitute gates remain incomplete; all required source artifacts exist.
- The specification contains 22 sequential `FR` requirements and 12 sequential `SC` criteria.
- No unresolved clarification, TODO, TBD, or placeholder marker remains in the normative specification.
- Every local Markdown link in the README and specification package resolves.
- Whitespace validation passes for the README and every file in the specification package.
- `tests/test_agent_evals.py` covers task/profile contracts, real sandbox probes, raw capture,
  protected grading, comparison, byte-hashed evidence bundles, drift refusal, three-repeat replay,
  CLI behavior, and the one-file control.
- The evidence ledger under `.runs/agent_evals/` preserves oracle, deterministic, replay, live-unrun,
  and control results. Fixtures are never relabeled as live agent trials.
