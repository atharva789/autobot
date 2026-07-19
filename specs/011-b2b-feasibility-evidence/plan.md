# Implementation Plan: Agentic Robot Design Evals POC

**Branch**: current worktree | **Date**: 2026-07-19 | **Spec**: [spec.md](spec.md)

**Input**: Approved feature specification from `specs/011-b2b-feasibility-evidence/spec.md`

## Summary

Build a local, headless evaluator that gives a coding agent an isolated robot-model repair or
modification task, preserves its final files and transcript, runs protected structural and MuJoCo
graders outside the agent process, and compares repeated trials across complete agent profiles.

The POC intentionally tests whether this is merely easy-to-copy orchestration. It ships both the
evaluation runner and a deliberately small strongest-substitute baseline, then records whether any
value remains beyond task corpus quality, protected failure cases, and longitudinal evidence.

## Technical Context

**Language/Version**: Python 3.13 in the repository `.venv`

**Primary Dependencies**: Python standard library, existing Click CLI, MuJoCo 3.7.0, and the existing
Codex CLI for live trials

**Storage**: Versioned JSON and ordinary files under `.runs/agent_evals/`; no database migration

**Testing**: pytest with red-green-refactor; real MuJoCo loads and steps in integration tests

**Target Platform**: macOS local POC; `sandbox-exec` is the required live-agent isolation backend

**Project Type**: Headless research library and CLI inside `packages/research/`

**Performance Goals**: Deterministic grading of one saved outcome in under 5 seconds; runner overhead
excluding agent time under 2 seconds; byte-identical deterministic grade payloads on three replays

**Constraints**: Zero mandatory cloud spend; no shell invocation; no secrets written to bundles; an
agent process cannot read the repository, protected graders, reference answers, prior results, or
another trial workspace; unsupported live isolation is `unrun`, never silently downgraded

**Scale/Scope**: Six task fixtures, two fixture profiles, two controlled Codex profiles, three trials
per live profile, one local comparison report, one minimal substitute runner

## Constitution Check

*GATE: Passed before design and re-checked after Phase 1.*

| Principle | Plan evidence | Status |
| --- | --- | --- |
| Specification Is the Source | All POC behavior traces to Spec 011 requirements and stories | Pass |
| Executed Evidence | Graders run after the agent and keep raw MuJoCo/compiler output separate | Pass |
| Test First | Every behavior task begins with a witnessed failing pytest test | Pass |
| Complexity Pays Rent | One package, filesystem bundles, no hosted services or schema migration | Pass |
| Architectural Boundaries | Implementation stays in one `packages/research/agent_evals.py` module; shared pipeline is consumed, not changed | Pass |
| Falsification Before Expansion | Strongest substitute, head-to-head metrics, and kill artifact are mandatory deliverables | Pass |
| Local and resource limits | Existing `.venv`, MuJoCo, Codex, and macOS sandbox; $0 required spend | Pass |

Post-design re-check: the data model and contracts introduce no network API, database, workflow
engine, frontend, new robot IR, or cross-layer import. The gate remains passed.

## Falsification and Complexity Design

**Riskiest assumption**: Robotics teams gain recurring value from a protected, reproducible agent
evaluation layer beyond what a competent engineer can assemble with a coding agent and scripts in one
day.

**Strongest substitute**: A short Python runner that copies a starter directory, invokes Codex, calls
task-specific checks, and prints pass/fail without the typed evidence model,
isolation assertions, revision fingerprints, repeatability, or comparison bundle.

**Head-to-head measurement**:

1. Run the same six tasks through reference, seeded-failure, Codex baseline, and Codex robotics-context
   profiles when available. Keep the model and executable fixed so public robotics context is the only
   intentional treatment difference.
2. Require the reference to pass and the seeded failure to fail the intended assertion.
3. Measure task pass rate, pass@1, pass^3, runtime, observable cost, escaped seeded failures, evidence
   completeness, replay determinism, and lines of implementation required by the substitute.
4. Record whether the evaluator catches consequential errors missed by MuJoCo load-only checks and by
   the agent's own final report.
5. Kill the engine-as-moat claim if the substitute reproduces the customer-valued result in one day.

**Complexity budget**: One new research module, one existing CLI extension, one focused test file, and
direct task-specific graders. No executor class hierarchy, registry, plugin framework, repository
layer, service layer, event bus, generalized grader DSL, or new database is allowed in the POC.

**Kill decision artifact**: `specs/011-b2b-feasibility-evidence/poc-results.md`, with the raw bundle
paths, substitute comparison, continue/refine/open-source/kill decision, and next concept-tree node.

## POC Task Suite

The suite contains two tasks in each required family. Every task has a visible prompt and starter,
plus a protected reference, seeded failure, and Python grader.

| Task | Family | Consequential evidence beyond parsing |
| --- | --- | --- |
| `ir-missing-parent` | Description repair | Existing IR validation, MJCF compilation, and load all execute after the typo is repaired |
| `ir-orphan-payload` | Description repair | Every IR link remains reachable and appears in the compiled MuJoCo model |
| `mjcf-payload-inertia` | Constrained modification | Physical mass, inertia, collision geometry, and dimensions satisfy constraints |
| `mjcf-actuator-contract` | Constrained modification | Joint axis, range, force, and executed direction agree with the contract |
| `arm-reach-target` | Executed behavior | A protected 1,000-step rollout reaches the end-effector target within 2 cm |
| `payload-vertical-lift` | Executed behavior | A protected rollout lifts 0.20 m and settles within force and velocity limits |

The tests are intentionally small. They measure evaluation correctness, not general robot-design
coverage.

## Project Structure

### Documentation

```text
specs/011-b2b-feasibility-evidence/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── implementation-goal.md
├── concept-tree.md
├── poc-results.md
├── contracts/
│   ├── cli.md
│   ├── eval-task.schema.json
│   ├── system-profile.schema.json
│   └── evidence-bundle.schema.json
└── tasks.md
```

### Source Code

```text
packages/research/
├── agent_evals.py        # records, tasks, isolation, execution, grading, bundles, comparison
└── cli.py                # existing CLI extended with eval commands

evals/robot_design/
├── tasks/<task-id>/public/
│   ├── task.json
│   └── starter/
├── protected/<task-id>/
│   ├── reference/
│   ├── seeded_failure/
│   └── grader.py
├── profiles/
│   ├── reference.json
│   ├── seeded-failure.json
│   ├── codex-baseline.json
│   └── codex-robotics-context.json
└── control.py

tests/
└── test_agent_evals.py
```

**Structure Decision**: The evaluator belongs in the research layer because it runs controlled
experiments and benchmarks agent systems. The POC does not alter `apps/` or `packages/pipeline/`.
Task assets remain under `evals/`, while the smallest reusable runner lives in one research module.
The module is split only if implementation pain demonstrates a second stable responsibility.

## Components and Data Flow

```text
task.json + starter/ + system profile
              |
              v
       validate and fingerprint
              |
              v
 copy starter into unique temporary workspace
              |
              v
 run fixture or sandboxed agent command
              |
              v
 snapshot final files + transcript + exit state
              |
              v
 load protected grader outside agent process
              |
              v
 structural -> compile/load -> static -> behavior grades
              |
              v
 immutable evidence bundle -> replay -> profile comparison
```

The agent command receives the visible prompt on stdin and a workspace as its current directory.
Commands are argument arrays and run with `shell=False`. The outer macOS sandbox denies reads to the
repository root and all result roots. The runner rejects execution when it cannot prove that the
workspace is outside every denied root.

## Error Handling

- Missing task/profile fields fail validation before a trial starts.
- Missing `sandbox-exec`, Codex, MuJoCo, or requested tools produce `unrun` with the exact
  dependency reason.
- Agent timeout produces `timeout`; nonzero exit produces `error`; neither is converted to `failed`.
- Grader exceptions produce a grade-level `error` with captured traceback and raw-output digest.
- Missing required artifacts produce an explicit failed grade.
- Bundle write failure leaves the temporary trial intact and reports its recovery path.
- Comparisons never average `error`, `timeout`, or `unrun` into a passing result.

## Testing Strategy

1. Focused tests prove canonical serialization, fingerprints, state constraints, and digest stability.
2. The isolation test executes a real child process that can read its workspace but cannot read a sentinel
   under the repository root.
3. Every task runs its reference and seeded failure; the expected grade must pass and fail respectively.
4. Runner tests verify clean workspaces, transcript capture, output digests, timeout/error separation,
   and protected grader execution.
5. Comparison tests verify per-trial display, pass@1, pass^3, regression classification, and hard-fail
   preservation.
6. CLI tests exercise list, validate, fixture run, replay, and compare from ordinary subprocesses.
7. The quickstart runs the full deterministic suite three times and compares normalized grade payloads.

## Complexity Tracking

No constitution violation is requested. Direct functions and frozen records are sufficient at this
scale. Filesystem evidence replaces a new database because six tasks and two profiles do not justify a
schema or indexing layer. Claude parity is deferred because it adds invocation and treatment variance
without changing the first product decision.
