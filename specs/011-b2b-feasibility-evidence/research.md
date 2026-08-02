# Product Research: What Survives Agentic AI?

**Research date**: 2026-07-19
**Decision**: Kill the standalone task-to-robot-body workbench. Test an agent-native robotics evaluation product instead.

## Direct conclusion

The former thesis was:

> An engineer describes a task; the product generates robot topologies, compiles them, runs screens, and helps choose a body.

That thesis no longer survives the available toolchain. A competent engineer can give Codex or Claude Code access to CAD, robot-description, simulation, and ROS tools through skills, plugins, MCP servers, and ordinary command-line programs. The resulting agent can assemble most of the proposed workflow on demand.

The narrow thesis that remains is:

> Robotics teams need independent, protected, repeatable tests for the complete AI system that produces robot artifacts: model, agent harness, instructions, skills, MCPs, plugins, and tool versions.

The agent creates or edits the robot. IL Ideation grades the outcome.

This is still an unvalidated product hypothesis. It should begin as an open, local evaluator and earn the right to become hosted B2B software.

## Why the old product is now commodity

### General agents already execute long engineering workflows

[Claude Code](https://www.anthropic.com/product/claude-code) reads repositories, edits files, runs commands, and tests its work. Anthropic's [Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) package procedural knowledge, scripts, and resources into portable domain capabilities, and [MCP](https://docs.anthropic.com/en/docs/mcp) connects the agent to external tools.

[Codex](https://openai.com/codex/) is positioned as an end-to-end engineering agent. OpenAI's current [skills and plugin model](https://openai.com/index/codex-for-every-role-tool-workflow/) packages workflows and tool connections instead of requiring a new application for each domain.

In the exact Codex environment used for this repository, installed skills already cover parametric STEP CAD, URDF, SRDF, SDF, G-code, CAD inspection, viewer handoff, and local 3D-printer handoff. This is direct evidence that robot-artifact generation can arrive as reusable agent capabilities rather than a standalone product.

### CAD generation is agent-accessible

[Zoo's Zookeeper](https://zoo.dev/press/zoo-introduces-zookeeper) creates and edits parametric CAD through conversation and exposes the same tools through Zoo-MCP so teams can use their preferred agent. [Onshape AI Advisor](https://www.onshape.com/en/resource-center/videos/instant-expertise-ai-advisor) is embedded in an established CAD workspace. Autodesk is researching [Neural CAD](https://www.research.autodesk.com/blog/neural-cad-how-ai-can-reason-in-design-and-engineering/) that reasons over professional geometric representations.

[Parametric CAD Bench](https://cadbench.ai/) now evaluates coding agents on editable FreeCAD parts and assemblies. Its May 2026 results show that the agent harness materially changes performance even when the model is held constant. This supports evaluating the complete model-plus-harness-plus-tools system, but it also proves that agentic CAD is already benchmarkable and improving.

### NVIDIA now makes its robotics simulator agent-native

[Isaac Sim 6.0](https://github.com/isaac-sim/IsaacSim/discussions/655) ships an MCP server plus agent skills. NVIDIA states that Claude Code can connect to a running Isaac Sim instance, execute code, modify the USD stage, run simulations, interact with the UI, and build new natural-language skills.

The official [Isaac Sim skills inventory](https://github.com/isaac-sim/IsaacSim/blob/main/skills/SKILLS.md) covers:

- natural-language requests to runnable simulations;
- URDF/MJCF/CAD to sim-ready USD;
- articulation and joint validation;
- PhysX and Newton physics;
- navigation, manipulation, sensors, rendering, and ROS 2;
- headless execution, CI, profiling, and final QA.

The [Isaac Sim MCP server](https://docs.isaacsim.omniverse.nvidia.com/latest/development_tools/isaac_sim_mcp.html) gives coding assistants direct access to extensions, APIs, examples, settings, and documentation. The [Isaac Sim test collection](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.test.collection/docs/index.html) already provides integration, robot, physics, and rendering tests.

Therefore, "we connect natural language, robot files, and simulation" is explicitly not a niche.

### Robot access is also available through MCP

The open-source [ROS MCP server](https://github.com/robotmcp/ros-mcp-server) connects models such as Claude and GPT to ROS topics, services, actions, sensors, debugging, and robot control. An agent can increasingly span repository, simulator, and robot interfaces without a new general-purpose workbench.

## Robotics-generation prior art

The generation mechanism is also crowded:

- [RoboGrammar](https://people.csail.mit.edu/jiex/papers/robogrammar/index.html) generates robot graphs from a grammar and optimizes them for terrain.
- [RoboMorph](https://arxiv.org/abs/2407.08626) combines LLM proposals, robot grammars, evolution, and controller learning.
- [LASeR](https://proceedings.iclr.cc/paper_files/paper/2025/hash/934eb45b99eff8f16b5cb8e4d3cb5641-Abstract-Conference.html) studies LLM-guided robot-design search and generalization.
- [RoboMoRe](https://arxiv.org/abs/2506.00276) jointly optimizes morphology and reward rather than judging bodies independently of control.
- [Auto-Robotist](https://arxiv.org/abs/2605.25832) turns morphology-search results into a reusable natural-language skill library with evidence-backed positive and negative design rules.
- [RoboGen](https://arxiv.org/abs/2311.01455), [Eureka](https://proceedings.iclr.cc/paper_files/paper/2024/hash/70c26937fbf3d4600b69a129031b66ec-Abstract-Conference.html), and [DrEureka](https://arxiv.org/abs/2406.01967) automate task, scene, reward, policy, and sim-to-real portions of robot learning.

Natural-language morphology generation, quality-diversity search, simulator compilation, and reusable design skills are not unique contributions by themselves.

## Why the evaluator is not automatically a product either

The proposed pivot is also surrounded by incumbents:

- Isaac Sim already imports, validates, simulates, and tests robot assets. Its [asset validation rules](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.asset.validation/docs/index.html) check robot schemas, joints, drives, materials, collisions, and file structure.
- [Artefacts](https://artefacts.com/) sells continuous simulation and testing for robotics applications.
- [RoSi](https://rosi-docs.robotec.ai/docs/intro) runs scenario-based SIL and HIL validation with CI/CD hooks and metrics.
- [MoveIt Pro](https://docs.picknik.ai/software_installation/) builds, simulates, tests, and deploys robot applications.
- [Intrinsic Flowstate](https://www.intrinsic.ai/flowstate) moves robot solutions between digital-twin simulation and physical workcells.
- Generic agent-eval platforms already provide isolation, trials, traces, and graders. Anthropic's [agent-eval guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) explicitly recommends grading the final environment, running multiple trials, protecting against task leakage, and tracking pass@k and pass^k.

So the evaluator cannot win by wrapping a simulator, storing reports, or adding a dashboard.

## The niche that survived four audit rounds

### Category

**Agentic robotics outcome evaluation.**

### What is evaluated

The subject under test is a complete system profile:

```text
model
+ agent harness
+ repository instructions
+ skills
+ MCPs and plugins
+ CAD / simulator / ROS tool versions
```

### What makes the task robotics-specific

The graders inspect and execute robot outcomes that generic coding tests cannot establish:

- kinematic graph and frame correctness;
- dimensions, mass, inertia, collision geometry, and joint limits;
- robot-description and simulator compatibility;
- executed physical behavior under an explicit task and perturbations;
- coupling between body, controller, observations, actions, and training budget;
- agreement or disagreement across simulators; and
- later, correlation with physical tests.

### Initial buyer

The most plausible first buyer is not a researcher looking for robot-shape ideas. It is the platform or evaluation lead at:

- a company building robotics coding agents, skills, or MCP products;
- a robotics company deploying internal coding agents;
- a simulator or CAD vendor evaluating agent integrations; or
- a foundation-model lab measuring physical-engineering capabilities.

These buyers ship model and tool updates repeatedly. That creates a more frequent job than choosing a new robot morphology once.

### Initial output

The first output is a reproducible comparison:

```text
same protected robotics tasks
  -> old agent configuration
  -> new agent configuration
  -> repeated isolated trials
  -> executed robot graders
  -> regressions, improvements, cost, and raw evidence
```

## What could become defensible

The code is not the moat. Agents can recreate runners and dashboards.

A defensible asset would require all of the following:

1. A continuously refreshed set of protected robotics tasks that do not leak into training data.
2. Failure cases contributed by real engineering teams, including negative outcomes.
3. Graders that measure physical and behavioral outcomes rather than file syntax or visual similarity.
4. Paired simulator and hardware results tied to exact robot, controller, task, and calibration revisions.
5. Evidence that the evaluator predicts costly failures better than static validators, simple heuristics, and engineer-plus-agent scripts.

[SIMPLER](https://proceedings.mlr.press/v270/li25c.html) is a useful standard: its claims about simulation evaluation were supported by more than 1,500 paired simulated and real evaluations. A new evaluator cannot assume sim-to-real validity from a few attractive rollouts.

## Current repository audit

The repository is not yet credible as its own evaluator:

- `apps/api/routes/designs.py` can generate route-level variants from one loop result, prefer Candidate A, assign order-based scores, and return placeholder MJCF.
- `apps/api/workspace_sdk.py::run_simulation_checks()` reads stored payloads and scores instead of executing physics.
- `packages/pipeline/urdf_factory.py` aliases URDF functions to an MJCF builder.
- `packages/pipeline/compilers/mjcf_compiler.py` calls itself full-fidelity but omits or mishandles some geometry and sensor semantics.
- `packages/pipeline/ir/design_ir.py::validate()` primarily checks that referenced links exist.
- `packages/pipeline/simulation/mujoco_screening.py` renames actuator coverage and rest-pose collision checks as task and reachability scores without a controller or task environment.

These defects are useful first eval cases. They are also proof that an agent-generated report can look more authoritative than its executed evidence.

## Market verdict

### Current workbench

**Kill as a standalone venture product.** It is substitutable, used infrequently, weakly connected to physical outcomes, and has no data moat.

It can remain useful as open-source research infrastructure and as a set of baselines for the new evaluator.

### Agentic robotics evaluator

**Conditional test only.** Do not build enterprise SaaS yet.

The evaluator earns continued investment only if it:

- catches consequential robotics failures existing validators and agent self-reports miss;
- is used repeatedly when agent or robot configurations change;
- reduces decision error or engineering time versus engineer-plus-agent scripts;
- receives real customer failure cases and outcome data; and
- eventually demonstrates simulator-to-physical predictive value.

## Required falsification gates

### Technical gate

Run the six-task local slice. Continue only if it catches at least one consequential frame, inertia, collision, actuator, or behavior failure that the current repository screens miss, with zero fake execution claims.

### Strongest-substitute gate

Give a robotics engineer with Codex or Claude Code, the available CAD/simulation skills, and ordinary scripts the same task. Continue only if the evaluator reduces median evaluation effort or catches material failures the control misses.

### Recurrence gate

Interview 20 qualified robotics and AI-tooling teams. Continue the B2B thesis only if at least five already run repeated agent or simulator regressions and at least three provide real failed tasks or artifacts.

### Paid-use gate

Before building enterprise administration, require at least three paid pilots using customer-owned tasks and a second evaluation run after a real model, skill, MCP, or robot revision.

### Moat gate

Do not claim a data moat until held-out results show that the accumulated failure and physical-outcome corpus predicts regressions or physical ranking better than static validators, simple heuristics, and expert scripts.

## Resource posture

The first 12-hour slice requires no paid cloud resources. It should use the current local agent adapters, experiment storage, robot IR, MuJoCo compiler, and deterministic graders.

Cross-simulator, controller-training, HIL, and physical tests are later resource requests. Each request must name the task, hardware or compute, expected artifact, time limit, spend limit, stop condition, and the decision the result changes. The current total budget ceiling remains $200.

## POC implementation decisions

### Decision: start with robot-model repair and constrained MJCF changes

**Rationale**: These tasks produce executable pass/fail evidence with the current local MuJoCo stack,
can be seeded with known failures, and directly test whether protected robotics graders separate agent
configurations. They require no new simulator, controller-training stack, or cloud service.

**Alternatives considered**: Broad morphology generation was rejected because the old product thesis
already failed. Controller training, cross-simulator evaluation, and physical trials remain stronger
scientific evidence but are slower and do not test the runner's first product assumption.

### Decision: use filesystem evidence bundles rather than extending research SQLite

**Rationale**: Existing `ExperimentRun` records describe generation strategies returning
`RobotDesignIR`. Agent trials have workspaces, commands, transcripts, arbitrary final files, protected
grades, and error states. Forcing both into one schema would create a false abstraction. Ordinary files
are inspectable, hashable, and sufficient for six tasks.

**Alternative considered**: A database migration was rejected until query volume or concurrent writers
demonstrate the need.

### Decision: keep macOS protected-path probes, but require an external boundary for live agents

**Executed correction**: `/usr/bin/sandbox-exec` denied the enumerated protected roots for generic
child-process probes. A real Codex process reached the model but could not start its inner sandbox
inside the outer sandbox, and global skill descriptions contaminated the empty profile. Therefore the
macOS boundary is not a valid live Codex backend. Those trials remain `unrun`.

**Next valid boundary**: Use a disposable Linux VM or container, mount only the copied starter
workspace, use an empty Codex home and disposable project credential, and then let Codex disable its
inner sandbox only inside that external boundary. Starting Colima locally is the smallest no-compute-
spend option on this machine; a remote runner is unnecessary until local disposable execution fails.
Trusting instructions or disabling the inner sandbox directly on the host remains prohibited.

### Decision: compare two controlled Codex profiles before adding Claude parity

**Rationale**: Holding the model and executable fixed while changing only the public robotics context
creates a cleaner first experiment. It also avoids building and debugging a second transcript protocol
before the evaluator itself is validated.

**Alternative considered**: Codex-versus-Claude is commercially legible but confounds model, harness,
tool behavior, output protocol, and instructions. It is deferred to the next experiment, not claimed as
complete by fixture substitution.

### Decision: keep graders task-specific

**Rationale**: Six direct Python graders are clearer than inventing a grader DSL. They can use MuJoCo,
XML inspection, and task-specific physics while returning one normalized grade contract.

**Alternative considered**: A declarative grader registry was rejected because its generality is not
required by the POC and would duplicate ordinary Python.

### Decision: build the strongest substitute alongside the evaluator

**Rationale**: Implementation difficulty is part of the product test. A short baseline runner makes it
possible to show that orchestration is commodity and isolate any remaining value in task quality,
failure corpus, leakage controls, reproducibility, and longitudinal comparisons.

**Alternative considered**: Arguing defensibility from architecture or code volume was rejected as
non-evidence.
