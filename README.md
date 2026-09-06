# AutoBot

**Robot schema in. Task-specific RL policy out.**

AutoBot takes a robot description and one task, and returns a policy trained for that task on that
body — together with the reward specification it wrote to get there, and the rollout evidence
behind every revision of that specification.

The bet is narrow and mechanical: **the model is the policy designer, not the policy.** Reward
shaping, curriculum design, and termination conditions are the human bottleneck in robot RL, and
they are re-derived by hand for every new body. AutoBot generates that scaffold from the schema,
trains against MuJoCo, reads why the episodes actually ended, and rewrites the scaffold until the
task holds.

```text
robot.urdf | robot.xml  +  one task description
  -> reward terms, termination conditions, curriculum, domain randomization
  -> compiled MuJoCo environment
  -> training run + rollout batch
  -> structured failure trace (termination cause, contact events, joint saturation)
  -> revised scaffold                          <-- loop until the task holds
  -> policy checkpoint + reward spec + eval report + replayable rollouts
```

The loop closes on physics, not on a self-reported score. The model never sees a scalar reward in
isolation; it sees the episode that produced it. Every reward term in the final specification is
traceable to the rollout batch that caused it to be added.

## Status: this is a pivot in progress

Read this before any capability claim further down.

The repository as committed implements the **previous** thesis — task-conditioned robot *body*
generation, plus a protected falsification harness that independently grades agent-produced robot
artifacts. That code is real, tested, and described accurately in the sections below. The
policy-generation direction above is being built now, on top of it.

| | |
| --- | --- |
| Direction | Robot schema → task-specific RL policy |
| Implemented today | Robot IR, MJCF compiler, agent-loop registry, protected graders, hash-checked eval bundles |
| Being built | Reward and curriculum synthesis, training loop, critic memory, rollout-driven revision |
| Specified, not implemented | `specs/003`–`specs/010`, listed in the spec table below |

Nothing in this repository yet produces a trained policy end to end. Do not read the sections below
as a claim that it does.

### Daily research log

Regenerated each morning by a scheduled routine ([`routines/registry.md`](routines/registry.md)).
Every number in this block traces to a committed run log under `.runs/loop_research/`; the routine
is not permitted to state a figure it did not read from a file. Everything outside the markers is
hand-authored.

<!-- ROUTINE:BEGIN -->
**2026-09-06** · build order: still 7/8 · no new evidence since 2026-08-25 · today was a near-miss

Bootstrap message again named `daily-loop-research.v1.md` by filename with no step 0 (the live
trigger's stored prompt is still v1, unchanged). This time it was **not** caught before building:
read `plan.md` §7 against a bare `master` checkout, concluded step 1 (compiler-to-MuJoCo) was the
lowest incomplete step, and wrote a full duplicate implementation — `expr.py` (whitelisted-`ast`
expression evaluator, no `eval`/`exec`), `compiler.py` (`TrainingScaffold` → steppable MuJoCo env,
compiled eagerly), `rollout.py` (structured `RolloutBatch` collection), `trainer.py` (a local
cross-entropy-method search over a linear policy), a hand-written `dev-a` baseline scaffold, and 18
new tests — committed to a local branch and pushed once (rejected, non-fast-forward) before running
`git fetch origin routine/experiments` + `git log --oneline --not origin/master` and finding that
branch 42 commits ahead of `master`, carrying steps 1–7 already under a different, canonical module
layout (`scaffold.py`/`symbols.py`/`entity_table.py`/`mujoco_compiler.py`/`rollout.py`/…), in open PR
#6. Caught by the push rejection: re-checked out `routine/experiments` from `origin`, discarding
every file from the duplicate build, matching the discard procedure v2's step 0 specifies. This is
the **eleventh** confirmed near-miss of this kind overall, and the fourth in a row — see "Known
issues" below. No repo-state cost: the rejected push never reached `origin`, and nothing from the
duplicate build was ever merged into it.

Having discarded that, re-verified every standing blocker fresh from `routine/experiments` (tip
`4c77f23`) rather than trusting 2026-09-05's entry: PR #6 — open, draft, head unchanged at
`4c77f23`, `get_reviews` → `[]`, `get_status` → 0 statuses (`pending`), newest comments (through
2026-09-05) all routine self-reports, no distinct human review or reply since 2026-08-03, now
**35 days**. `actions_list list_workflow_runs` on `loop-research.yml` — still 1 total run, from
2026-08-08, none since. `evals/policy_synthesis/holdout/` (directory listing only) still holds only
`README.md` — step 8 still structurally blocked (needs a human to drop `holdout-a.xml`/
`holdout-b.xml` in; not this routine's to author, per spec.md §2/§9). No
`experiments/credits-ready.flag`; `routines/budget-log.md` unchanged since its single 2026-08-03
row — the maintainer's local crontab job has now evidently not run for ~35 days. `origin/master`
unchanged at `d2e853c`. The live trigger's stored prompt was independently re-checked
(`list_triggers`) and confirmed still v1 verbatim; a second, separate trigger ("PR #6 check-in",
hourly, bound to its own persistent session) now also exists, created minutes before this firing —
new since yesterday, not something this firing created or controls. Installed this sandbox's
missing test deps and ran the full `loop_research` suite fresh: **97/97 pass**, unchanged since
2026-08-24 (latest run log still
[`9fc352`](.runs/loop_research/2026-08-11T13-56-25Z_step7_9fc352/run.json), 2026-08-11).

No push notification sent — the near-miss cost session tokens only, and every standing fact above
(trigger stuck on v1, PR unreviewed 35 days, no OpenAI credits, no holdout schemas) is already
flagged in prior entries and the "Known issues" table; today added no new fact requiring a human's
attention right now beyond one more data point on an already-escalated pattern.
<!-- ROUTINE:END -->

### Why the direction changed

Two theses have been rejected on evidence, and the reasoning is kept here on purpose.

**Task-to-robot-body workbench.** Rejected. Coding agents can already drive CAD, URDF, SDF, Isaac
Sim, and ROS through skills, plugins, MCP servers, and ordinary scripts. Wrapping those steps in a
separate UI is not a durable product.

**Agentic robotics outcome evaluation.** Refined, not adopted. The deterministic six-task slice is
implemented: all six references pass, all six seeded failures are caught, and twelve saved outcomes
replay identically three times. But a 291-SLOC one-file control matched the full evaluator's grading
decisions on all twelve frozen outcomes, so frozen-artifact grading is reproducible infrastructure
rather than a moat. The live two-profile Codex experiment remains `unrun`: Codex's inner sandbox
cannot start inside the outer macOS sandbox, and global skill descriptions contaminate the frozen
empty profile. See the executed
[POC results](specs/011-b2b-feasibility-evidence/poc-results.md).

What survived both rejections is the part worth keeping: a robot IR that compiles to real physics,
executable graders that run actual MuJoCo checks, and an evidence format that refuses drifted
inputs. Policy generation is the thing that needs exactly that substrate — an LLM rewriting reward
functions is only useful if something independent and physical decides whether the rewrite worked.

Several existing product paths are still not trustworthy evidence: the design route can project one
selected graph into several candidates, Candidate A is preferred by default, some scores are
deterministic formulas, render payloads can contain placeholder MJCF, and the workspace "simulation
check" reads stored flags instead of executing physics.

The current product and architecture docs are also published in the [Robodex GitBook](https://robodex.gitbook.io/robodex-docs/).

## Product overview

### The problem

Getting a robot to do one specific thing in simulation is rarely blocked on the RL algorithm. PPO,
SAC, and their implementations are commodities. The work is upstream of them: deciding what to
reward, how much, when to terminate an episode, and in what order to make the task harder. That
work is done by hand, it is specific to the body, and it does not transfer — a reward function
tuned for one arm's link lengths and actuator limits is close to worthless on the next one.

So the same engineer re-derives the same class of scaffolding for every new robot, and the feedback
loop is slow: change a weight, train, watch the rollouts, guess which term was wrong, repeat.

### Current direction

The target output is a **task-conditioned policy bundle**: the trained checkpoint, the reward
specification that produced it, every prior revision of that specification with the rollout batch
that motivated the change, an evaluation report with failure modes and randomization coverage, and
seeds that re-run the episodes behind each number.

Two properties are non-negotiable, both inherited from the rejected evaluation thesis:

- **The model does not grade its own work.** A plausible reward function, a rising return curve, or
  a self-authored summary is not evidence. Only executed simulator output counts.
- **No claim outlives its artifact.** A stored `policy_spec` or a UI badge is not a training run.
  Execution evidence must carry the actual simulator output and reproducibility metadata.

The first buyer hypothesis is a robotics or simulation team that needs a working policy for a
specific body and task, and currently pays an engineer weeks of reward-tuning to get it. That
hypothesis is not yet validated, and no revenue or design-partner evidence supports it today.

### What the repository can do now

- Create local projects and branch work into context-carrying threads.
- Describe a robot or task in natural language, with or without a prior ingest job.
- Generate candidate populations through a named, registered agent loop.
- Use `grammar_v2` for derivation-first generation or `creative_qd_v2` for a quality-diversity proposal layer around the grammar kernel.
- Inspect candidates, telemetry, render payloads, derivation/HITL data, BOM estimates, checkpoints, and revision history.
- Select a design and attach it to the current thread as a durable artifact.
- Compile or export MJCF-, print-, UI-scene-, and procurement-oriented artifacts where the underlying candidate supports them; the current legacy URDF path is not a trustworthy URDF compiler.
- Create simulation and policy specifications without pretending that a long-running training job has occurred.
- Run research strategies under seeds and prompt versions, store runs in SQLite, and compare compile, stability, score, and diversity metrics.

### The implemented local demo

A credible local demo evaluates saved outcomes rather than advertising a generated robot:

1. Create a protected task containing a broken robot description and explicit physical constraints.
2. Validate the passing reference and intended seeded failure.
3. Freeze the final files and raw transcript before protected grading.
4. Compile the produced robot and execute the task's real MuJoCo checks.
5. Show every task and trial before any aggregate.
6. Replay the same grader three times and refuse changed task, profile, grader, simulator, transcript,
   grade, or artifact bytes.
7. Verify every saved bundle before comparison and expose the exact profile, bundle, and environment
   revisions used on both sides.
8. Compare the full evaluator with the one-file control on identical artifact manifests.

The first six-task falsification slice is specified in
[spec.md](specs/011-b2b-feasibility-evidence/spec.md) and audited in
[poc-results.md](specs/011-b2b-feasibility-evidence/poc-results.md). A valid live-agent demo now needs
a disposable worker, disposable credential, empty Codex home, and no global skills or plugins.

### Product maturity and honest boundaries

| Area | Current state |
| --- | --- |
| Agent adapters | Local Codex, Claude Code, and OpenAI-compatible research adapters exist |
| Experiment infrastructure | Strategies, runs, prompt hashes, metrics, and SQLite storage exist |
| Robotics baselines | Registered `grammar`, `grammar_v2`, and `creative_qd_v2` loops exist |
| Robot representation | Canonical graph/IR plus a V2 derivation program exists, with limited validation |
| MJCF compilation | IR-to-MJCF compiler exists but is not yet qualification-grade |
| URDF compilation | Legacy `build_urdf` currently aliases the MJCF builder and must not be claimed as URDF output |
| Physics validation | MuJoCo-oriented checks exist; the workspace check does not execute them |
| Protected eval tasks | Six implemented with passing references and caught seeded failures |
| Isolated agent trials | Generic local probes pass; real Codex profile is `unrun` because nested isolation fails |
| Hidden outcome graders | Six implemented across structural, compile/load, static, and behavior checks |
| Model/harness/tool comparisons | Saved inputs are integrity-checked and source-revisioned; valid controlled live comparison is `unrun` |
| Evidence replay | Task/profile/grader/environment/raw/artifact drift checks and three-repeat replay implemented |
| Strongest substitute | 291-SLOC control reaches frozen-artifact grading parity; full agent workflow remains unrun |
| Reward/curriculum synthesis | Specified in `specs/008` and `specs/004`; not implemented |
| Training loop | Specified in `specs/010`; no PPO run exists, and `policy_spec` records are specifications, not runs |
| Rollout-driven revision | Specified in `specs/009`; the critic/memory loop is not implemented |
| End-to-end schema-to-policy | Not implemented. No trained policy has been produced by this repository |
| Hardware-grounded calibration | Not implemented |
| Multi-user B2B product | Not implemented and not yet justified |

### Current evaluation path

The interactive product path is still the pre-pivot robot-generation workbench. Separately, the
research layer now owns the headless evaluator POC. No eval code or protected task assets are imported
into the web product.

The implemented POC path is deliberately thin:

```text
protected task + copied starter workspace
  -> fixture validation or attempted isolated agent run
  -> final environment and robot artifacts
  -> real structural, compiler, simulator, and behavior graders
  -> repeated trial comparison
  -> hash-checked eval bundle with explicit drift refusal
```

The first slice reuses current adapters, robot IR, compiler, and MuJoCo checks only where their
outputs are truthful. Its evidence is ordinary files under `.runs/agent_evals/`; it does not use a
new database or product UI. The POC result does not justify a new simulator, robot IR, workflow
engine, graph database, distributed queue, cloud database, CAD kernel, public leaderboard, or
enterprise control plane.

## Technical overview

### Architectural rule: two layers, one deterministic seam

The repository has two independent layers that share the pipeline library. The product layer optimizes for interactive decisions. The research layer optimizes for controlled experiments. Product code may call the narrow agent-loop registry, but it must not absorb experiment runners, notebooks, or training internals.

```text
                          HTTP
apps/web  ---------------------------------------->  apps/api
Next.js + optional Electron shell                    FastAPI + RobotWorkspaceSDK
                                                           |
                                          +----------------+----------------+
                                          |                                 |
                                          v                                 v
                               packages/pipeline                 packages/research/agent_loops
                               canonical IR, compilers,          app-compatible loop registry
                               validation, simulation                       |
                                          ^                                 |
                                          |                                 |
                                          +-------------+-------------------+
                                                        |
                                             packages/research
                                             strategies, prompts,
                                             experiments, metrics, storage,
                                             loop_research (spec 012 — schema-conditioned
                                             policy synthesis, self-contained)
```

Allowed dependency directions:

- `apps/web` calls `apps/api` over HTTP.
- `apps/api` imports `packages/pipeline`.
- `apps/api` imports only the app-compatible `packages.research.agent_loops` surface from research.
- `packages/research` imports `packages/pipeline`.
- `packages/pipeline` does not import product or research orchestration code.
- `packages/research` does not import from `apps/`.

### Product layer

`apps/api/` is the product control plane. `RobotWorkspaceSDK` owns project/thread behavior and orchestration; FastAPI routes should remain thin transport adapters. `WorkspaceStore` persists product state in local SQLite by default.

`apps/web/` is a Next.js/React client with a project/thread workspace, candidate inspection, and a Three.js-based morphology viewer. The optional Electron shell is deliberately renderer-only. It loads the same web app and does not own, spawn, or supervise the Python backend.

The primary product flow is:

```text
project + thread
  -> prompt or ingest job
  -> selected registered agent loop
  -> AgentLoopResult(state, hitl)
  -> flat candidate records + render/telemetry payloads
  -> design revisions, checkpoints, and thread artifacts
  -> user selection
  -> compile/export or simulation/policy specification
```

### Shared pipeline

`packages/pipeline/` contains deterministic contracts and transforms used by both layers:

- `ir/design_ir.py`: `RobotDesignIR`, links, joints, actuators, sensors, geometry, and metadata.
- `robot_program.py`: the V2 derivation-program representation used before graph expansion.
- `grammar_graph.py`: grammar catalogs, structural-rule helpers, expansion, and compatibility paths.
- `compilers/mjcf_compiler.py`: MJCF compilation. The current `urdf_factory.py` path is a legacy MJCF alias and is not a valid URDF export contract.
- `simulation/`: validation, candidate screening, ranking, and orchestration helpers.
- `cad/`, `components/`, and `procurement/`: parts, assembly, print, and supplier-oriented paths.
- `engineering_render.py` and `ui/scene_compiler.py`: backend-owned render and scene artifacts.

The pipeline is the most sensitive seam in the repo. A change to its shared IR, compiler contracts, or validation semantics can affect both the product and research layers and must update the architecture handoff document.

### Research layer

`packages/research/` is a self-contained experiment package. It owns:

- app-compatible agent loops;
- experiment-facing generation strategies;
- versioned prompt templates and hashes;
- local/remote chat-model adapters;
- benchmark metrics and morphology-diversity calculations;
- reproducibility envelopes;
- SQLite research-run storage;
- the research CLI, notebooks, and evaluation helpers.

There are intentionally two generation interfaces:

| Interface | Consumer | Contract |
| --- | --- | --- |
| `AgentLoopRunner` | Product API and loop tests | `loop(prompt, initial_state, config) -> AgentLoopResult(state, hitl)` |
| `GenerationStrategy` | Research runner and CLI | `generate(prompt, config) -> list[RobotDesignIR]` |

The agent-loop HITL payload is stable enough for the product. A strategy may carry experiment-only configuration, prompts, seeds, and metrics that should never leak into the frontend contract.

### Persistence and evidence

Product and research records are intentionally separate:

- Product workflow state defaults to `/tmp/il_ideation/workspace.sqlite3`; override with `WORKSPACE_DB_PATH`.
- Research experiments default to `.runs/research.db`.
- Generated evolution artifacts default under `/tmp/il_ideation/evolutions`; override with `EVOLUTION_ARTIFACTS_DIR`.
- Supabase clients and migrations remain for hosted/legacy paths, grammar catalogs, and optional prompt persistence. The current workspace does not require Supabase.
- LangSmith and Langfuse integration points exist for trace/evaluation workflows but are not required for deterministic local tests.

Do not infer a completed simulation or training run from a stored `simulation_spec`, `policy_spec`, task record, or UI badge. Execution evidence must include the actual compiler/simulator/training output and reproducibility metadata.

## Repository map

```text
apps/
├── api/                         FastAPI product backend
│   ├── app.py                   app factory and router mounting
│   ├── routes/                  ingest, designs, exports, evolutions, workspace
│   ├── services/                product orchestration and external integrations
│   ├── workspace_sdk.py         backend-owned workspace behavior
│   └── workspace_store.py       local SQLite product persistence
└── web/                         Next.js product client
    ├── app/                     workspace and capture routes
    ├── components/              workspace UI and morphology viewer
    ├── lib/                     typed API clients and contracts
    └── electron/                optional thin desktop shell

packages/
├── pipeline/                    shared deterministic robotics kernel
└── research/                    loops, strategies, experiments, metrics, prompts, agent eval POC
    └── loop_research/           spec 012 — TrainingScaffold, MuJoCo compiler, G1-G4 gates

specs/                           Spec Kit feature directories and acceptance contracts
tests/                           backend, pipeline, research, and frontend-contract tests
evals/                           protected robot-design tasks plus trace/loop evaluation tooling
├── policy_synthesis/dev/        spec 012 development schemas (dev-a; dev-b not yet added)
└── policy_synthesis/holdout/    spec 012 held-out schemas — generalization test, untouched by design
supabase/migrations/             hosted schema history and grammar catalog migrations
docs/                            detailed GitBook-compatible documentation
```

## Spec-as-source development

The source of intent is `specs/`, not issue titles, screenshots, or whatever the current code happens to do. Each approved feature should progress through:

```text
spec.md -> research.md -> plan.md + data-model.md + contracts/ -> tasks.md -> implementation -> verification
```

Specs `003` through `010` are the schema-to-policy direction. They were written before the pivot and
are now the active roadmap rather than a side research program. Specs `001`, `002`, and `011` are
the implemented substrate the direction builds on.

Current Spec Kit state at the time of this README rewrite:

| Spec | Scope | State |
| --- | --- | --- |
| `001-creative-qd-v2` | Compile-safe quality-diversity morphology loop | Implemented; task list complete |
| `002-macos-electron-dev-ui` | API/SDK-first local workspace and thin Electron shell | Implemented; task list complete |
| `003-robot-rl-research-program` | Umbrella graph-to-control research program | **Active roadmap**; task breakdown not created |
| `004-task-goal-generation` | Task prompt to measurable goal contract | **Active roadmap**; task breakdown not created |
| `005-state-action-formalization` | Robot graph to control-problem contract | **Active roadmap**; task breakdown not created |
| `006-physics-dynamics-rules` | Physics and dynamics contract | **Active roadmap**; task breakdown not created |
| `007-policy-generation` | Graph-compatible policy proposal | **Active roadmap**; task breakdown not created |
| `008-reward-generation` | Goal-grounded reward contract | **Active roadmap**; task breakdown not created |
| `009-llm-critic-memory` | Bounded critic evaluation and memory | **Active roadmap**; task breakdown not created |
| `010-ppo-training-loop` | PPO evidence and loss accounting | **Active roadmap**; task breakdown not created |
| `011-b2b-feasibility-evidence` | Protected evaluation of agent-produced robot artifacts and behavior | Root POC decision is refine; frozen-artifact control matches grading, live and full substitute gates unrun |

"Active roadmap" means selected and prioritized, not started. None of `003`–`010` has an
implementation or a task breakdown yet.

Run the local status helper instead of trusting this snapshot:

```bash
python3 /Users/thorbthorb/.agents/skills/speckit-sdd/scripts/sdd_status.py --json
```

### Drift policy

Spec/code drift is a release signal, not documentation cleanup. Every implementation slice should check:

1. Are implemented behaviors covered by a requirement and acceptance scenario?
2. Do route, schema, IR, and UI types still match their contracts?
3. Do `tasks.md` completion marks correspond to code and test evidence?
4. Are README maturity claims supported by a runnable local path?
5. Did an architecture-sensitive change update and stage `.codex`?

No new abstraction earns permanence merely by passing tests. Its plan must explain the complexity it introduces, the simpler alternative, the measurable payoff, and the deletion boundary if the bet fails.

## API surfaces

The FastAPI app mounts five route families:

- `/workspace`: projects, threads, context, messages, generation, simulation specs, and policy specs.
- `/ingest`: task/video intake and retrieval status.
- `/designs`: generation, loop discovery, revisions, checkpoints, tasks, selection, events, compilation, exports, and procurement.
- `/evolutions`: evolution creation, approval, stop, iteration, and best-candidate state.
- `/health`, `/clips`, and `/runs`: the smaller prompt-to-policy demo workflow retained by the app factory.

Use the generated OpenAPI document at `http://127.0.0.1:8000/docs` for the exact current request and response schemas.

## Local setup

### Requirements

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- A C/C++ toolchain suitable for the declared robotics packages

The default Python dependency set includes PyTorch, PyTorch Geometric, MuJoCo, Pinocchio, Pink, LangGraph, and model/provider clients. It is a large install. A future packaging pass should split product, simulation, and research extras; that split does not exist yet.

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

cd apps/web
npm install
cd ../..
```

Copy the environment template if you need provider-backed features:

```bash
cp .env.example .env
```

The deterministic test suite and most local workspace operations do not require every external credential. Common configuration groups are:

- `WORKSPACE_DB_PATH`, `NEXT_PUBLIC_API_URL`, `EVOLUTION_ARTIFACTS_DIR`: local product paths.
- `RESEARCH_LLM_PROVIDER`, `RESEARCH_LLM_MODEL`, `RESEARCH_LLM_BASE_URL`: research model adapter.
- `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, `MODAL_*`: optional ingest/provider flows.
- `SUPABASE_*`, `GRAMMAR_*`, `PROMPT_*`: hosted catalogs and persistence paths.
- `LANGSMITH_*`, `LANGFUSE_*`: optional experiment observability.
- `PHOTON_*`: optional messaging integration.

Do not commit `.env` or provider credentials.

## Run locally

Backend:

```bash
source .venv/bin/activate
uvicorn apps.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Web client, in a second terminal:

```bash
cd apps/web
npm run dev
```

Open:

- Web workspace: `http://localhost:3000`
- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`

The convenience target `make dev` starts both processes. Separate terminals are easier to debug.

Optional Electron shell, after the web app and API are already running:

```bash
cd apps/web
npm run desktop:dev
```

The Electron process must remain a client. Backend ownership stays in `RobotWorkspaceSDK` and FastAPI.

## Research CLI

```bash
# Discover experiment strategies
python -m packages.research.cli strategies

# Run a reproducible morphology experiment
python -m packages.research.cli run \
  "quadruped that climbs stairs" \
  --strategy grammar \
  --seed 42 \
  --experiment stair-v1

# Inspect and compare stored runs
python -m packages.research.cli show stair-v1
python -m packages.research.cli metrics <run-id>
python -m packages.research.cli compare <run-id-1> <run-id-2>
```

App-compatible loop names and experiment strategy names are different registries. Use `GET /designs/agent-loops` for product loop discovery and the CLI `strategies` command for experiment strategy discovery.

## Verification

Focused gates:

```bash
# Research core
pytest tests/test_research_core.py -v

# Product and pipeline tests
pytest tests/ -v --ignore=tests/test_research_core.py

# Full Python suite
pytest tests/ -v

# Frontend production contract/build
cd apps/web
npm run build

# Optional Electron contract smoke
npm run electron:smoke
```

Some legacy Makefile smoke targets reference narrower test selections. Prefer direct, existing test paths when a target and the repository diverge.

## Current architecture versus future deployment

### What exists now

The current system is intentionally local-first:

- one Next.js client;
- one FastAPI process;
- local SQLite product and research stores;
- in-process generation orchestration;
- local compiler/screening work;
- optional calls to model, video, Supabase, Modal, and observability providers;
- no production queue, scheduler, GPU worker pool, organization model, or artifact object store.

That topology is appropriate for proving the workflow and collecting evidence. Splitting it into more services now would add operational cost without fixing the main product risk: whether the design-to-evidence workflow solves a painful, repeatable customer job.

The agent-eval POC adds one local Python module, CLI commands, six protected task folders, and
ordinary-file evidence bundles. It deliberately does not add an API route, UI, database table, queue,
or hosted worker.

### What a real B2B deployment is likely to need

This is a direction, not an implemented architecture. The market/niche specification must decide which pieces are justified.

```text
browser
  -> authenticated web application
  -> API/workspace control plane
       -> durable relational database
       -> object storage for graphs, renders, simulator files, videos, and run evidence
       -> bounded job queue
            -> CPU compiler/validation workers
            -> GPU simulation/training workers only when demanded
       -> trace, cost, audit, and failure telemetry
```

Possible hosted-product additions are tenant/project access control, queued run state, resumable artifacts, budget enforcement, and provider isolation. None are justified by the POC: the one-file control reached grading parity, the live causal run is unrun, and no external failure corpus or recurring buyer use has been established.

The initial infrastructure budget is capped at **$200**. Local MuJoCo and local model/simulation options should be exhausted first. Any cloud request should name the exact experiment, runtime, expected spend, stop condition, and artifact that cannot be produced locally.

## Key documents

- [Architecture boundaries](docs/architecture/layers-and-boundaries.md)
- [Architecture data flow](docs/architecture/data-flow.md)
- [Local persistence](docs/architecture/local-first-persistence.md)
- [Workspace SDK](docs/product/workspace-sdk.md)
- [Agent-loop registry](docs/research/agent-loop-registry.md)
- [Strategies and experiments](docs/research/strategies-experiments.md)
- [Canonical IR](docs/pipeline/canonical-ir.md)
- [Simulation and benchmarking](docs/pipeline/simulation-benchmarking.md)
- [Operations limits and roadmap](docs/operations/limits-and-roadmap.md)
- [Robot RL research program](specs/003-robot-rl-research-program/plan.md)
- [Task-to-robot design specification](specs/011-b2b-feasibility-evidence/spec.md)
- [Product and market research](specs/011-b2b-feasibility-evidence/research.md)
- [Executed POC results and drift audit](specs/011-b2b-feasibility-evidence/poc-results.md)

## Change discipline

Major or new API, schema, abstraction, registry, shared-pipeline, or dependency changes must update the architecture handoff document in the same change. The default handoff is `.codex`; a repository may override it with `git config codex.archDocPath <path>`.

The global pre-commit hook enforces that rule for staged architecture-sensitive changes. If the repo uses a local `core.hooksPath`, its pre-commit wrapper must delegate to `/Users/thorbthorb/.codex/git-hooks/pre-commit`.

The engineering standard is simple: readable contracts, explicit evidence, bounded complexity, and no claim stronger than the artifact that supports it.
