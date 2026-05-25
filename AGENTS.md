# IL_ideation — Architecture Guide for AI Agents

## The Two Layers

This codebase has two independent layers that share a common pipeline library but serve different purposes and must not be confused. The one approved cross-layer bridge is the app-compatible research agent-loop registry used by the product backend for robot generation.

### Layer 1: Product Engineering (`apps/` + `packages/pipeline/`)

The user-facing product. A FastAPI backend + Next.js frontend that lets users type a natural-language robot description, generates candidate robot designs, and (eventually) runs autoresearch on them.

**Scope:** web UX, API routes, Supabase persistence, frontend components, deployment.

```
apps/
├── api/                          # FastAPI backend
│   ├── app.py                    # ASGI app, mounts routers
│   ├── routes/
│   │   ├── designs.py            # POST /designs — selects a registered research agent loop
│   │   ├── ingest.py             # POST /ingest  — video/motion ingestion
│   │   ├── exports.py            # GET  /exports — MJCF/URDF download
│   │   └── evolutions.py         # Evolution tracking
│   ├── services/                 # Business logic (orchestrator, ingest, evolution)
│   ├── supabase_client.py        # Supabase connection
│   └── store.py, workspace_store.py
├── web/                          # Next.js frontend
│   ├── app/                      # Pages: capture flow, design review, ingest viewer
│   ├── components/               # DesignSelector, MorphologyViewer, VideoGrid, etc.
│   └── lib/                      # API client, types, Supabase client
```

**Key characteristic:** the backend now treats generation as a registered loop call. `designs.py` selects an app-compatible agent loop by name, receives the same grammar HITL payload shape, creates flat candidate bundles, and feeds them to the frontend.

**When working in this layer:** you are doing product engineering. Changes should maintain API contracts, frontend compatibility, and Supabase schema. The only intended `packages/research/` import from product code is `packages.research.agent_loops`.

---

### Layer 2: Research Experimentation (`packages/research/`)

A self-contained Python package for experimenting with robot generation methods. CLI + notebook interface. No web server, no Supabase, no frontend dependency.

**Scope:** trying different generation strategies, agent loops, LLM prompts, inference-time methods — and benchmarking quality/diversity differences.

```
packages/research/
├── agent_loops/
│   ├── protocol.py               # AgentLoopConfig, AgentLoopResult, AgentLoopRunner
│   ├── registry.py               # register_agent_loop(), run_agent_loop(), list_agent_loops()
│   └── grammar_loop.py           # Built-in RoboGrammar LangGraph loop
├── local_chat_models.py           # Local Claude Code/Codex chat-model adapter
├── strategy/
│   ├── protocol.py               # GenerationStrategy protocol, StrategyConfig, IRMaterializer
│   ├── registry.py               # register_strategy(), get_strategy(), list_strategies()
│   ├── grammar_strategy.py       # GrammarStrategy — wraps grammar_loop + LLM materializer
│   ├── llm_materializer.py       # grammar nodes → RobotDesignIR via LLM (with deterministic fallback)
│   └── prompt_agents.py          # Agent adapters that inject registry prompts into grammar_loop
├── experiment/
│   ├── types.py                  # Experiment, ExperimentRun, ReproEnvelope (frozen dataclasses)
│   ├── runner.py                 # ExperimentRunner: strategy → benchmark → SQLite
│   └── comparison.py             # Cross-run comparison tables
├── benchmark/
│   ├── harness.py                # evaluate_single(), evaluate_designs() — strategy-agnostic
│   ├── metrics.py                # DesignMetrics, MetricsReport (frozen dataclasses)
│   └── diversity.py              # Shannon entropy, pairwise structural distance
├── prompts/
│   ├── registry.py               # PromptRegistry: load/version/hash YAML templates
│   └── templates/                # v1_normalizer.yaml, v1_rule_builder.yaml, v1_evaluator.yaml, v1_materializer.yaml
├── storage/
│   ├── store.py                  # RunStore protocol + SQLiteStore (local .runs/research.db)
│   └── schema.sql                # experiments, runs, designs, run_metrics tables
├── cli.py                        # Click CLI: run, strategies, show, compare, metrics, experiments
└── notebooks/
    └── quickstart.ipynb
```

**Key abstractions:**
- `GenerationStrategy` protocol — any generation method implements `generate(prompt, config) → list[RobotDesignIR]`. The agent loop lives INSIDE the strategy.
- `AgentLoopRunner` protocol — any app-testable LangGraph loop implements `loop(prompt, initial_state=None, *, config=None) → AgentLoopResult`.
- `AgentLoopResult` — returns both full research/debug `state` and backend-facing `hitl`; preserve the existing grammar HITL shape unless the frontend contract changes.
- `PromptRegistry` — loads versioned YAML templates, computes SHA-256 hashes, renders with variables. Prompts are swappable without touching code.
- `local_chat_models` — ChatOpenAI-compatible local model factory for research loops. Use `make_chat_model()` / `make_structured_llm()` instead of direct `ChatOpenAI` imports. Set `RESEARCH_LLM_PROVIDER=codex` for an isolated persistent local `codex mcp-server` thread, `RESEARCH_LLM_PROVIDER=claude-code` for persistent Claude Code with Sonnet 4.5, or `RESEARCH_LLM_PROVIDER=openai` only when an explicit OpenAI fallback is desired.
- `ExperimentRunner` — orchestrates: strategy.generate() → benchmark harness → SQLite persistence. One call, full reproducibility envelope.
- `ReproEnvelope` — captures seed, model_id, prompt hashes, strategy version, git SHA for exact reproducibility.

**When working in this layer:** you are doing research engineering. Changes should maintain the Strategy protocol, keep tests passing (`pytest tests/test_research_core.py`), and avoid importing from `apps/`. New strategies are added by implementing `GenerationStrategy` and calling `register_strategy()`. New app-testable loops are added under `packages/research/agent_loops/` and registered with `register_agent_loop()`.

---

### Shared Library (`packages/pipeline/`)

Both layers depend on this but neither should modify it lightly. It contains the canonical IR types, compilers, and simulation modules.

```
packages/pipeline/
├── ir/design_ir.py               # RobotDesignIR, LinkIR, JointIR — frozen dataclasses, canonical output
├── grammar_graph.py              # Grammar catalog/tool helpers plus compatibility shim
├── schemas.py                    # NormalizedRobotQuery, RobotDesignCandidate
├── compilers/mjcf_compiler.py    # compile_to_mjcf(ir) → MJCF XML string
├── simulation/
│   ├── validator.py              # validate_design(), validate_compiles(), validate_full()
│   └── mujoco_screening.py       # screen_design(ir) → ScreeningResult (stability, reachability, task_sanity)
├── mjcf_factory.py               # Legacy flat-param path: MorphologyParams → MJCF
├── types.py                      # MorphologyParams, TrialResult, EvolutionConfig
└── ...                           # CAD, components, procurement, UI scene compiler
```

**Dependency direction:**
- `apps/api/` → `packages/pipeline/` (compiler, schemas, shared helpers)
- `apps/api/` → `packages/research/agent_loops/` (narrow loop registry only)
- `packages/research/` → `packages/pipeline/` (uses IR types, compiler, validator, screening — never modifies)
- `packages/research/` ✗ `apps/` (no dependency from research into product code)

---

## Decision Rules for Agents

| If the task involves... | Work in | Do NOT touch |
|---|---|---|
| API routes, frontend pages, Supabase schema, UX | `apps/` | `packages/research/` except `agent_loops` registry imports |
| Generation strategies, prompt templates, benchmarks, experiment tracking | `packages/research/` | `apps/` |
| IR types, MJCF compiler, simulation/validator | `packages/pipeline/` | Coordinate with both layers |
| Adding a new generation method | `packages/research/strategy/` | `apps/api/routes/designs.py` |
| Adding or changing a backend-selectable LangGraph loop | `packages/research/agent_loops/` | `apps/api/routes/designs.py` unless request/response contract changes |
| Changing how the grammar loop's prompts work | `packages/research/prompts/templates/` | `apps/api/routes/designs.py` |
| Deploying the web app | `apps/` | `packages/research/` |

## Running Research Experiments

```bash
# List available strategies
python -m packages.research.cli strategies

# Run an experiment
python -m packages.research.cli run "quadruped that climbs stairs" -s grammar --seed 42 -e stair-v1

# View results
python -m packages.research.cli show stair-v1
python -m packages.research.cli metrics <run-id>

# Compare runs
python -m packages.research.cli compare <run-id-1> <run-id-2>
```

## Running Tests

```bash
# Research layer tests (38 tests, no external deps required)
pytest tests/test_research_core.py -v

# Product layer tests
pytest tests/ -v --ignore=tests/test_research_core.py

# Full suite
pytest tests/ -v
```
