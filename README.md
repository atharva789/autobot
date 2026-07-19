# IL Ideation

IL Ideation is a local-first test harness for AI agents that create or modify robot designs. Give Codex, Claude Code, or another agent a protected robotics task and an allowed tool set; IL Ideation records the run, independently checks the final robot files, executes physics tests, and reports what passed or failed.

The agent designs or edits the robot. IL Ideation grades the outcome.

The previous product thesis was a task-to-robot-body workbench. That thesis has been rejected. Coding agents can now use CAD, URDF, SDF, Isaac Sim, ROS, and other robotics capabilities through skills, plugins, MCP servers, and ordinary scripts. Connecting those steps in a separate UI is not a durable product.

The surviving hypothesis is narrower:

```text
protected robotics task + starter files + allowed tools
  -> model + agent harness + instructions + skills + MCPs
  -> final robot artifacts and transcript
  -> protected structural and physics graders
  -> repeated trials and raw evidence
  -> regression comparison between two complete agent configurations
```

Today, the repository contains useful evaluation building blocks: local Codex and Claude Code adapters, registered morphology-generation loops, an experiment runner, run storage, a robot grammar, a canonical IR, an MJCF compiler, MuJoCo-oriented validators, and a local review workspace. It does **not** yet implement the protected agent-eval harness described above.

Several current product paths are also not trustworthy evaluation evidence: the design route can project one selected graph into several candidates, Candidate A is preferred by default, some scores are deterministic formulas, render payloads can contain placeholder MJCF, and the workspace “simulation check” reads stored flags instead of executing physics.

The current product and architecture docs are also published in the [Robodex GitBook](https://robodex.gitbook.io/robodex-docs/).

## Product overview

### The problem

Robotics engineers can increasingly ask a coding agent to write robot code, generate CAD, edit URDF or MJCF, run a simulator, and prepare a report. The difficult question shifts from “can the agent create something?” to “did the complete agent configuration produce a physically correct outcome, and did a new model, skill, MCP, or prompt introduce a regression?”

The agent should not grade its own work. A plausible render, successful XML parse, generated confidence score, or self-authored report is not independent evidence.

### Current product wedge

The proposed product is **agentic robotics outcome evaluation**.

The first buyer is a robotics platform, simulation, or AI-tooling team that repeatedly changes a model, agent harness, robotics skill, MCP server, plugin, prompt, or robot-description workflow. The job is to run the same protected robotics tasks before and after the change and identify real regressions in final artifacts and executed behavior.

The useful output is an **Agentic Robotics Eval Run**: the task revision, starter state, complete model/harness/tool profile, transcript, final robot artifacts, immutable digests, protected grader versions, executed simulator output, trial-level results, cost, runtime, and regression comparison. The [product research](specs/011-b2b-feasibility-evidence/research.md) and [four-round red team](specs/011-b2b-feasibility-evidence/red-team/agentic-ai-audit.md) explain why the former generation workbench was killed and what this evaluator must prove.

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

### The next truthful demo story

A credible local demo evaluates the agent rather than advertising the generated robot:

1. Create a protected task containing a broken robot description and explicit physical constraints.
2. Give two complete agent configurations the same starter files, time budget, and allowed robotics tools.
3. Run three isolated trials per configuration without exposing graders or reference answers.
4. Inspect the final environment, compile the produced robot, and execute the same MuJoCo behavior checks.
5. Show every task and trial result before pass rate, repeatability, runtime, and cost.
6. Change one model, skill, MCP, prompt, or tool version and report the exact regression.
7. Export the task, system profile, transcript, artifacts, digests, grader versions, raw simulator output, and comparison.

The first six-task falsification slice is specified in [spec.md](specs/011-b2b-feasibility-evidence/spec.md). It is not implemented yet.

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
| Protected eval tasks | Not implemented |
| Isolated agent trials | Not implemented |
| Hidden outcome graders | Not implemented |
| Model/harness/tool comparisons | Research comparison pieces exist; agentic robotics comparison is not implemented |
| Hardware-grounded calibration | Not implemented |
| Multi-user B2B product | Not implemented and not yet justified |

### Current and target evaluation path

The current product path is still the pre-pivot robot-generation workbench. It calls one selected loop, may project that result into route-level variants, stores render and telemetry payloads, and lets the workspace inspect stored values. No source architecture has been changed at this specification checkpoint.

The proposed target is deliberately thin:

```text
protected task + isolated starter workspace
  -> complete agent configuration runs
  -> final environment and robot artifacts
  -> real structural, compiler, simulator, and behavior graders
  -> repeated trial comparison
  -> reproducible eval bundle
```

The first slice reuses the current adapters, experiment storage, robot IR, compiler, MuJoCo checks, and workspace only where their outputs are truthful. It does not justify a new simulator, robot IR, workflow engine, graph database, distributed queue, cloud database, CAD kernel, public leaderboard, or enterprise control plane.

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
                                             experiments, metrics, storage
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
└── research/                    loops, strategies, experiments, metrics, prompts

specs/                           Spec Kit feature directories and acceptance contracts
tests/                           backend, pipeline, research, and frontend-contract tests
evals/                           LangSmith/Langfuse and loop-comparison tooling
supabase/migrations/             hosted schema history and grammar catalog migrations
docs/                            detailed GitBook-compatible documentation
```

## Spec-as-source development

The source of intent is `specs/`, not issue titles, screenshots, or whatever the current code happens to do. Each approved feature should progress through:

```text
spec.md -> research.md -> plan.md + data-model.md + contracts/ -> tasks.md -> implementation -> verification
```

Current Spec Kit state at the time of this README rewrite:

| Spec | Scope | State |
| --- | --- | --- |
| `001-creative-qd-v2` | Compile-safe quality-diversity morphology loop | Implemented; task list complete |
| `002-macos-electron-dev-ui` | API/SDK-first local workspace and thin Electron shell | Implemented; task list complete |
| `003-robot-rl-research-program` | Umbrella graph-to-control research program | Planned; task breakdown not created |
| `004-task-goal-generation` | Task prompt to measurable goal contract | Planned; task breakdown not created |
| `005-state-action-formalization` | Robot graph to control-problem contract | Planned; task breakdown not created |
| `006-physics-dynamics-rules` | Physics and dynamics contract | Planned; task breakdown not created |
| `007-policy-generation` | Graph-compatible policy proposal | Planned; task breakdown not created |
| `008-reward-generation` | Goal-grounded reward contract | Planned; task breakdown not created |
| `009-llm-critic-memory` | Bounded critic evaluation and memory | Planned; task breakdown not created |
| `010-ppo-training-loop` | PPO evidence and loss accounting | Planned; task breakdown not created |
| `011-b2b-feasibility-evidence` | Protected evaluation of agent-produced robot artifacts and behavior | Revised specification; awaiting approval checkpoint |

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

Possible hosted-product additions are tenant/project access control, queued run state, resumable artifacts, budget enforcement, and provider isolation. None are justified until the local robot-design loop proves useful to engineers.

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

## Change discipline

Major or new API, schema, abstraction, registry, shared-pipeline, or dependency changes must update the architecture handoff document in the same change. The default handoff is `.codex`; a repository may override it with `git config codex.archDocPath <path>`.

The global pre-commit hook enforces that rule for staged architecture-sensitive changes. If the repo uses a local `core.hooksPath`, its pre-commit wrapper must delegate to `/Users/thorbthorb/.codex/git-hooks/pre-commit`.

The engineering standard is simple: readable contracts, explicit evidence, bounded complexity, and no claim stronger than the artifact that supports it.
