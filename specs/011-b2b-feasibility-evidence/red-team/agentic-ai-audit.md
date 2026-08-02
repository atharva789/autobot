# Agentic-AI Product Red Team

**Date**: 2026-07-19
**Proposition**: A standalone product built from this repository should exist even when robotics engineers can use Codex or Claude Code with CAD, Isaac Sim, ROS, MCPs, plugins, skills, and ordinary scripts.
**Verdict**: The current workbench loses. A protected robotics evaluator survives only as a falsifiable hypothesis.

## Panel method

The audit used three independent panels:

- robotics-focused venture investors attacked buyer frequency, budget, distribution, moat, and venture scale;
- senior NVIDIA-style robotics engineers attacked simulation, asset, controller, production, and qualification claims;
- CMU-style robotics researchers attacked novelty, experimental validity, control coupling, reproducibility, and sim-to-real evidence.

The panels were grounded in current products, official documentation, source code, and research. They were not asked to imitate named personalities. All three were allowed to recommend killing the product.

The jury prior was simple:

- agents make orchestration and glue cheaper;
- existing CAD and simulator vendors own strong distribution;
- a new layer must improve a physical decision, not merely organize files;
- executable outcomes beat generated explanations;
- a simulator result is not a physical result; and
- complexity must pay for itself in fewer failures, less engineer time, or better decisions.

## Round 1: Can agents replace the robot-body workbench?

### Attack

Yes, for most of the claimed value.

Codex and Claude Code can edit repositories, run programs, test results, and use domain skills. Zoo exposes parametric CAD through an MCP server. Isaac Sim 6.0 gives agents a live simulator interface plus skills for robot import, physics, navigation, sensors, ROS 2, validation, and headless execution. ROS MCP connects agents to robot middleware. Research systems already combine language models, morphology search, reward generation, controller learning, and reusable design memory.

The former product offered:

```text
task -> generated topology -> MJCF/URDF -> screens -> report
```

A capable engineer can now ask an agent to assemble that workflow inside the existing CAD and simulation stack. A dedicated UI is convenience, not a durable product boundary.

### Blue-team defense

The repository provides a constrained grammar, canonical IR, compilers, experiment storage, and a local review surface. A preassembled workflow may save time for smaller teams.

### Jury ruling

**Skeptic wins. Kill the standalone generation workbench.**

The defense describes a useful open-source project or service engagement, not a moat. The product also stops before controller, manufacturing, safety, and physical validation, so its selected robot is supported mainly by proxies.

## Round 2: Is an agentic robotics evaluator already commodity?

### Proposed pivot

Evaluate the complete robotics agent configuration on protected tasks:

```text
model + harness + instructions + skills + MCPs + tool versions
```

Grade the final robot artifacts and executed behavior instead of trusting the agent's report.

### Attack

This layer is also crowded:

- Isaac Sim has asset rules, robot and physics tests, CI, and headless workflows.
- MuJoCo, Gazebo, URDF, SDF, and CAD tools expose their own validators.
- Artefacts, RoSi, MoveIt Pro, Intrinsic, and other products provide robotics simulation and testing workflows.
- Parametric CAD Bench evaluates CAD agents in isolated environments.
- generic eval frameworks already provide tasks, trials, protected graders, traces, pass@k, and regression reports.

A thin adapter over these tools is still replaceable by an agent and scripts.

### Blue-team defense

Existing validators test one artifact or simulator. Generic eval systems do not understand robot frames, inertias, collision models, body-controller coupling, or physical task outcomes. The remaining opportunity is to evaluate a complete agent configuration across robotics-specific outcomes and track regressions as models and tool profiles change.

### Jury ruling

**Conditional survival.**

The evaluator is differentiated only if its task corpus and graders catch consequential robotics failures that existing validators and agent self-reports miss. The first product must be CLI/API/MCP/CI-native. The dashboard is only an evidence browser.

## Round 3: Can the evaluator make scientifically valid robot claims?

### Attack

The current repository cannot.

- Compilation proves that a file loads, not that the robot can perform the task.
- Zero-control stability can favor inert shapes and reject dynamically stabilized designs.
- Topology fingerprints measure structure, not useful behavior.
- Equal static screens do not create a fair body comparison.
- Body quality depends on controller, observation/action space, training budget, task distribution, simulator parameters, and perturbations.
- A reproducible simulation can reproduce the wrong conclusion.
- Physical parameters such as friction, backlash, compliance, thermal behavior, and sensor noise must be measured or sourced.

The current product route makes the problem concrete: it can show placeholder MJCF, copied flags, synthetic scores, and order-based preferences as though they were evidence.

### Blue-team defense

An evaluation ladder can keep claims scoped:

1. graph and schema validity;
2. compiler and simulator loadability;
3. static diagnostics;
4. controlled task execution under equal budgets;
5. perturbation and parameter sweeps;
6. cross-simulator consistency;
7. HIL and physical outcomes;
8. calibrated prediction intervals.

### Jury ruling

**The pivot survives only as a falsification system.**

The product may report exactly what a grader executed. It may not call static checks "task suitability," rank morphologies without control, or imply sim-to-real validity until paired evidence supports that claim.

The strongest research question is:

> Which cheap robot-design checks, if any, predict equal-budget controlled performance and physical outcomes across tasks and embodiments?

## Round 4: Can this become a business rather than a benchmark project?

### Attack

The buyer and frequency are uncertain.

Many robotics companies choose an embodiment early, then spend years on control, reliability, manufacturing, integration, and deployment. Academic morphology researchers have limited software budgets. Large companies already own simulation, CAD, test infrastructure, and internal failure data. Local-first software does not automatically accumulate a cross-customer moat.

A public benchmark can also saturate, leak into model training, or be copied. A generated report has no pricing power.

### Blue-team defense

Agent models, prompts, skills, MCPs, and plugins change frequently. Teams integrating them need repeated regression tests even when the physical robot does not change. Agents therefore create a new recurring evaluation job.

The compounding asset could be a permissioned corpus linking:

- protected tasks and failure cases;
- complete agent configurations;
- final robot artifacts and controller revisions;
- simulator conditions and negative results;
- hardware parameters and physical outcomes; and
- which cheap tests predicted expensive failures.

### Jury ruling

**Conditional pivot, not company approval.**

Begin as an open local evaluator. Hosted B2B software is justified only after repeated customer use, paid pilots, and predictive evidence. If teams want generation but will not pay for recurring evaluation, keep the project open source.

## Final jury verdict

### Winner

The skeptic wins on the current product.

**Kill**:

- the robot-body idea generator as the main product;
- the standalone design-workbench moat claim;
- automatic "best robot" selection;
- static or zero-control scores presented as task evidence;
- a broad B2B workflow, approval, or report system; and
- architecture expansion before the evaluator passes its gates.

### Surviving hypothesis

Build **Agentic Robot Design Evals**:

- agents create or modify the robot artifacts;
- protected graders independently inspect the final state;
- real compilers and simulators execute tests;
- trials compare complete model-plus-harness-plus-tool profiles;
- failures and negative results remain first-class;
- later physical data calibrates which simulated claims are trustworthy.

The repository's grammar, loops, IR, compilers, and workspace become baselines and test infrastructure rather than the moat.

### Strongest argument from the losing side

A preassembled task-to-robot workbench could still help education, research, and small teams explore morphology faster. That is worth preserving as open-source functionality. It does not justify the commercial thesis unless the strongest-substitute test proves that it improves consequential decisions beyond what an engineer and agent can assemble.

## Decision gates

1. **Local technical gate**: six protected tasks, valid reference solutions, seeded failures, real MuJoCo execution, zero fake evidence, and at least one consequential failure missed by the current screens.
2. **Agent substitution gate**: compare against an engineer using Codex or Claude Code plus available robotics tools. Continue only if the evaluator reduces effort or catches material misses.
3. **Scientific gate**: show that cheap graders predict equal-budget controlled performance better than mass-only, complexity-only, random, and shuffled-task controls.
4. **Customer gate**: 20 interviews, five teams with recurring eval work, three real contributed failures, and three paid pilots that rerun after a real revision.
5. **Moat gate**: held-out evidence that the accumulated failure and physical-outcome corpus improves predictions beyond static validators and expert scripts.

If these gates fail, the correct outcome is a useful open-source robotics evaluation project, not a forced startup narrative.
