# Feature Specification: Agentic Robot Design Evals

**Feature directory**: `011-b2b-feasibility-evidence`
**Created**: 2026-07-18
**Revised**: 2026-07-19
**Status**: Approved for local POC implementation on 2026-07-19
**Product decision**: Reject the standalone robot-body generation workbench. Test the evaluator described below before treating it as a company.

## Product in one paragraph

IL Ideation evaluates AI agents that create or modify robot designs. It gives Codex, Claude Code, or another agent a robotics task and a controlled set of tools. It records what the agent does, then independently checks the robot files and runs the resulting model in physics. The output shows which agent, model, skill set, or MCP setup passed, what failed, and the executed evidence behind the result.

The product does **not** generate the robot for the user. The agent being tested does that. IL Ideation is the test harness and grader.

## Why this product might still need to exist

A capable coding agent can already:

- write robot code;
- create or edit CAD with specialized skills and MCP servers;
- generate URDF, MJCF, SDF, and SRDF;
- control Isaac Sim through natural language;
- call ROS topics, services, and actions;
- run tests and produce a report.

That makes the old product replaceable. A separate workbench is not justified merely because it connects those steps.

The possible remaining problem is **independent evaluation**. The agent that created a robot artifact should not be trusted to declare that artifact correct. Teams changing models, prompts, skills, plugins, or MCP servers need repeatable robotics tasks, protected graders, multiple trials, real simulator output, and eventually physical results.

```text
robotics task + starter files + allowed tools
  -> agent works in an isolated workspace
  -> final CAD / robot description / code / policy artifacts
  -> protected structural and physics graders
  -> repeated trials and raw evidence
  -> comparison across model + agent harness + tool profile
```

If an ordinary test script reproduces all of the customer-valued result, this should be an open-source tool rather than a standalone product.

## The niche under test

### First buyer

The first buyer is a robotics platform, simulation, or AI-tooling team that already uses coding agents and repeatedly changes one of the following:

- the model behind its robotics agent;
- the agent harness;
- a CAD, URDF, simulation, or ROS skill;
- an MCP server or plugin;
- prompts or repository instructions; or
- robot-description and controller code produced by those agents.

These teams need to detect robotics regressions before an agent-produced change reaches a prototype, shared simulator asset, or physical robot.

### First recurring job

Run the same protected robotics tasks against the old and new agent configuration and answer:

1. Did the agent produce valid robot artifacts?
2. Did those artifacts satisfy the explicit physical constraints?
3. Did the robot exhibit the required behavior in the executed test?
4. Which failures appeared only after the model, skill, MCP, or prompt changed?
5. Can another engineer reproduce the result from the saved run?

### Why the niche is not already owned by a simulator

Isaac Sim, MuJoCo, Gazebo, and their validators test assets and simulations. Generic agent-evaluation frameworks run tasks and graders. Parametric CAD benchmarks test CAD agents. Robotics CI products run robot software in simulation.

The narrower gap is the intersection: **outcome-based evaluation of the complete agent configuration on robot-design and robot-description tasks**, with the model, harness, skills, MCPs, artifacts, simulator results, and later physical outcomes tied to the same trial.

This is a hypothesis, not a proven market.

## Main use cases

### Use case 1: Compare Codex and Claude Code on the same robotics task

A robotics tooling team gives both agents the same broken mobile-robot model and the same allowed CAD, URDF, and simulation tools. IL Ideation runs three trials per setup and reports whether each final robot loads, preserves required dimensions, avoids self-collision, and completes the executed motion test.

The comparison is between complete systems, not only language models:

```text
model + agent harness + instructions + skills + MCPs + tool versions
```

### Use case 2: Regression-test a robotics skill or MCP release

A skill author changes the URDF workflow or releases a new Isaac Sim MCP integration. They run the protected task suite before and after the change. The report identifies tasks that improved, tasks that regressed, and the exact executed assertion that changed.

### Use case 3: Check an agent-produced robot change before accepting it

An engineer asks an agent to add a depth camera and a larger payload to a robot. The agent edits the robot description and simulator setup. IL Ideation checks frame placement, mass and inertia, collision geometry, actuator limits, simulator load, and a bounded behavior test. A plausible-looking render does not pass the task.

### Use case 4: Measure whether simulation predicts hardware

Later, a team attaches physical test results to the exact robot, controller, task, and calibration revision. The system measures whether simulator pass/fail decisions and rankings predicted physical outcomes. This is required for a defensible data moat but is outside the first 12-hour slice.

## What the user sees

The first product surface has five parts:

1. **Task**: prompt, starter workspace, allowed tools, budget, required outputs, and visible success contract.
2. **Trial**: model, agent harness, instructions, skills, MCPs, versions, transcript, runtime, and cost.
3. **Outcome**: final files and their immutable digests.
4. **Grades**: protected structural, compiler, simulator, and behavior checks with raw output.
5. **Comparison**: task-level pass rates, repeatability, time, cost, and regressions between two complete agent configurations.

There is no automatic "best robot" label and no overall score that hides failed hard constraints.

## How the current repository helps

The repository already contains useful pieces:

- local Codex and Claude Code model adapters;
- registered robotics agent loops;
- an experiment runner, run storage, prompt versions, and reproducibility metadata;
- a robot grammar and construction program;
- a canonical robot IR;
- an MJCF compiler and MuJoCo-oriented validators; and
- a local workspace and review UI.

Those pieces become eval subjects, fixtures, graders, or evidence viewers. They are not the product moat.

### Current behavior that cannot be used as evaluation evidence

1. The product API can turn one selected robot graph into several numeric variants and present them as a population.
2. Candidate A is preferred by default and receives an order-based synthetic score.
3. The render payload can contain placeholder MJCF.
4. The workspace "simulation check" reads stored flags and scores instead of running physics.
5. `urdf_factory.py` currently aliases `build_urdf` to an MJCF builder; the repository does not have a trustworthy URDF compiler on that path.
6. The IR-to-MJCF compiler does not yet preserve every geometry origin or create all sensor sites it references.
7. Existing screens label actuator coverage as "task sanity" and rest-pose self-collision as "reachability."
8. The current ranking has no task controller, controller-training budget, perturbation suite, cross-simulator check, or physical outcome.

The evaluator must expose these as failures or unsupported claims, not silently reuse them.

## First build: one 12-hour falsification slice

The first slice tests whether this repo can become a credible robotics-agent evaluator without new cloud infrastructure.

1. Create six robotics eval tasks across three families:
   - repair a malformed robot graph or description;
   - modify a robot under explicit geometry, payload, sensor, or actuator constraints;
   - make a supported robot model pass a bounded executed MuJoCo behavior test.
2. Give every task a starter workspace, task prompt, allowed-tool profile, required outputs, protected graders, a known passing reference solution, and at least one seeded failure.
3. Run every trial in an isolated task workspace that cannot read or edit protected graders or reference answers.
4. Record the complete system profile: model, agent harness, instructions, skills, MCPs, tool versions, budget, seed where available, transcript, runtime, and cost.
5. Grade final outcomes with deterministic checks first: graph/schema validity, real compilation and simulator load, physical constraints, and task behavior.
6. Keep compile, load, structural, physics, and task behavior results separate.
7. Run three trials for every nondeterministic live agent profile. If no live Codex or Claude Code adapter is available, mark that comparison unrun rather than substituting fixtures.
8. Compare two system profiles at the task level using pass rate, pass@1, pass^3, time, and cost. Do not hide hard failures inside one composite score.
9. Preserve final artifacts, digests, grader output, simulator output, and failure category in a reproducible run bundle.
10. Demonstrate that changing one model, skill, prompt, or tool-profile version creates a new comparison and does not overwrite the prior evidence.
11. Run locally with MuJoCo and existing repository dependencies. Do not add Isaac Sim, a distributed runner, a cloud database, a new robot IR, or an enterprise control plane in this slice.
12. Produce a spec-drift report and a product kill report with the validation results below.

## User Scenarios and Acceptance Tests

### User Story 1: Define a robotics eval task (Priority: P1)

A robotics engineer can define one concrete task that an agent must complete and that software can grade without judging prose quality.

**Acceptance tests**:

1. The task identifies its starter files, prompt, visible constraints, allowed tools, time or token budget, required outputs, and protected graders.
2. A known reference solution passes every required grader.
3. A seeded bad solution fails the intended assertion with a specific robotics failure.
4. Missing units, ambiguous thresholds, or an unsolved reference task prevent the task from being published.

### User Story 2: Run an agent in isolation (Priority: P1)

The engineer can run a complete agent configuration without allowing it to inspect or change the answer key.

**Acceptance tests**:

1. Each trial starts from a clean copy of the task workspace.
2. The trial records the model, harness, instructions, skills, MCPs, tool versions, budget, and final state.
3. The agent cannot read or edit protected graders, reference solutions, or results from another trial.
4. A timeout, tool failure, agent refusal, or missing dependency is recorded as its real state.

### User Story 3: Grade robot artifacts and behavior (Priority: P1)

The engineer receives executed robotics evidence rather than the agent's opinion of its own work.

**Acceptance tests**:

1. Robot graph and file-format checks run against the final artifacts.
2. A simulator result requires a real compile/load and executed physics process.
3. Structural validity, simulator validity, static diagnostics, and task behavior are reported separately.
4. Agent prose, stored flags, placeholder files, and fabricated scores cannot satisfy an executed grader.
5. Every failure includes the assertion, raw output, affected artifact digest, and task revision.

### User Story 4: Compare complete agent configurations (Priority: P1)

The engineer can determine whether a model, harness, skill, MCP, or prompt change caused a robotics regression.

**Acceptance tests**:

1. The comparison names every changed system component.
2. It shows pass/fail/error/unrun per task and trial before any aggregate.
3. It reports repeatability across trials, runtime, and cost.
4. A hard-constraint failure remains a failure regardless of performance on other tasks.
5. The report can say there is no meaningful difference when the sample is insufficient.

### User Story 5: Reproduce a result (Priority: P2)

Another engineer can rerun or audit a saved evaluation without the original UI session.

**Acceptance tests**:

1. The run bundle contains the task revision, system profile, starter-state digest, final artifacts, transcripts, grader versions, simulator version, raw results, and environment manifest.
2. Replaying deterministic graders on the same outcome reproduces the same result.
3. Changing a task, grader, artifact, simulator, or system profile creates a new evidence revision and invalidates dependent comparisons.
4. The bundle remains inspectable from ordinary files and command-line tools.

## Functional Requirements

- **FR-001**: The system MUST define each eval task with starter files, a prompt, visible constraints, allowed tools, a resource budget, required outputs, protected graders, and a reference solution.
- **FR-002**: Every published task MUST prove that its reference solution passes and its seeded failure is caught.
- **FR-003**: Every trial MUST run in a clean, isolated workspace that cannot access protected graders, reference answers, or other trial results.
- **FR-004**: Every trial MUST record the model, agent harness, instructions, skill set, MCP/plugin set, tool versions, budget, seed when available, runtime, and cost when observable.
- **FR-005**: The system MUST preserve the trial transcript, tool calls, exit state, final files, and immutable artifact digests.
- **FR-006**: Timeouts, dependency failures, permission failures, refusals, and unrun trials MUST remain distinct states.
- **FR-007**: Grading MUST inspect the final environment and robot artifacts, not only the agent's final message.
- **FR-008**: Simulator claims MUST come from a real compiler/load attempt and executed physics process.
- **FR-009**: Structural, file-format, compile, simulator-load, static-diagnostic, and task-behavior grades MUST remain separate.
- **FR-010**: Placeholder files, stored flags, generated prose, fixtures, and unexplained scores MUST NOT satisfy executed graders.
- **FR-011**: Every grade MUST identify the task revision, grader version, artifact digest, parameters, raw output, and error state.
- **FR-012**: The first suite MUST contain six tasks across graph/description repair, constrained robot modification, and executed behavior testing.
- **FR-013**: Every nondeterministic live system profile MUST run three trials per task or be clearly marked incomplete.
- **FR-014**: Comparisons MUST treat the model, agent harness, instructions, skills, MCPs/plugins, and tool versions as one complete system profile.
- **FR-015**: Comparisons MUST show task- and trial-level results before aggregate pass rate, pass@1, pass^3, runtime, or cost.
- **FR-016**: Hard-constraint failures MUST NOT be averaged away by success on other checks.
- **FR-017**: A changed task, grader, artifact, simulator, or system profile MUST create a new revision and invalidate dependent comparisons.
- **FR-018**: The system MUST export a human-readable report and a machine-readable reproducibility bundle.
- **FR-019**: The first slice MUST run locally without a hosted database, distributed queue, paid compute service, or new simulator platform.
- **FR-020**: The first slice MUST reuse the existing research runner, local agent adapters, robot IR, compiler, MuJoCo checks, and run storage where they are truthful; unsupported paths MUST fail visibly.
- **FR-021**: The product MUST NOT claim manufacturability, safety, controller quality, task suitability, or real-world performance unless a grader executed evidence that directly supports the scoped claim.
- **FR-022**: The delivery MUST include a drift report and a kill report that evaluates the slice against this specification and the business gates below.

## Success Criteria

- **SC-001**: Six eval tasks ship, each with a passing reference solution and a seeded failure that the intended grader catches.
- **SC-002**: At least two tasks catch a robotics error that XML/schema validation alone would miss, such as a wrong axis, unit, inertia, sensor frame, collision shape, or behavior threshold.
- **SC-003**: Zero protected graders or reference answers are readable or writable from the agent workspace.
- **SC-004**: Every simulator result shown to the user comes from a real executed run tied to the final artifact digest.
- **SC-005**: Zero placeholder files, stored flags, formula scores, or agent assertions pass an executed grader.
- **SC-006**: Replaying deterministic graders three times on the same saved outcome produces identical grades and required evidence fields.
- **SC-007**: A comparison identifies the exact tasks and trials that changed between two complete system profiles.
- **SC-008**: A hard-constraint failure remains visible and cannot be hidden by an aggregate score.
- **SC-009**: A second engineer can reproduce one saved evaluation from the exported bundle without the original UI session.
- **SC-010**: The local test harness and deterministic suite require zero mandatory cloud spend.
- **SC-011**: The drift report accounts for every task field, trial field, grade, comparison, and exported artifact in this specification.
- **SC-012**: The kill report returns "continue" only if the evaluator catches at least one consequential failure missed by the current repo screens and does so more reliably than an agent-generated self-report.

## Explicit Non-Goals

- Building another general coding agent.
- Building a robot-body generation product or morphology idea gallery.
- Replacing CAD, Isaac Sim, MuJoCo, Gazebo, ROS, OSMO, or generic CI.
- Claiming that graph diversity, compilation, or zero-control stability identifies the best robot.
- Creating a new robot IR, simulator, workflow engine, distributed runner, cloud platform, or enterprise approval system in the first slice.
- Manufacturing a robot, producing certified CAD, or making a safety decision.
- Publishing a public leaderboard before tasks, graders, and leakage controls are credible.
- Treating a web dashboard as the moat; CLI, API, MCP, and CI use are primary.

## Business and Research Kill Conditions

Stop treating this as a standalone product if any of the following occurs:

1. An engineer with Codex or Claude Code and ordinary robotics scripts reproduces the customer-valued result in one day.
2. The protected evaluator catches no consequential failure beyond existing Isaac, MuJoCo, CAD, or format validators.
3. Teams do not run these evaluations repeatedly when a model, skill, MCP, controller, or robot revision changes.
4. Simulator judgments do not predict controlled or physical outcomes better than simple heuristics.
5. Customers will not provide real failure cases, hardware parameters, or outcome data.
6. The only advantage is a generated report or a more convenient UI.

## Assumptions

- The first tasks use robot structures and MuJoCo behaviors the current repository can express and execute locally.
- Deterministic graders are preferred over model judges for physical correctness.
- The first slice evaluates artifacts and bounded behavior; controller-training and sim-to-real calibration require later specs and explicit resources.
- The existing generation loops remain valuable research baselines even though they are no longer the proposed end-user product.
- Commercial value depends on repeated regressions and accumulated real failure evidence, neither of which has been validated yet.
