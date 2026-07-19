# Tasks: Agentic Robot Design Evals POC

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`

**Tests**: Mandatory. Every behavioral implementation task follows red-green-refactor. The test task
immediately before it must be run and observed failing for the stated reason.

## Format

- `[P]` means the task touches distinct files and can run after its phase prerequisites.
- `[US1]` through `[US5]` map directly to the approved user stories in `spec.md`.

## Phase 1: Setup and frozen experiment definition

**Purpose**: Record the experiment before implementation so the result cannot be redefined after it
is seen.

- [X] T001 Record environment versions, six task IDs, two controlled Codex profiles, metrics, gates, zero-dollar starting spend, and an empty raw-evidence table in `specs/011-b2b-feasibility-evidence/poc-results.md`
- [X] T002 Update the approval and phase history in `specs/011-b2b-feasibility-evidence/sdd-checkpoint.md` without changing the approved requirements
- [X] T003 Add the Agentic Robot Design Evals plan pointer between the existing Spec Kit markers in `AGENTS.md`

---

## Phase 2: Foundational evidence contracts

**Purpose**: Establish canonical records, hashes, path safety, and state semantics used by every story.

- [X] T004 Add failing canonical-record tests for task/profile fingerprints, artifact manifests, grade states, trial states, and secret-value omission in `tests/test_agent_evals.py`; run them and confirm failure because `packages.research.agent_evals` is absent
- [X] T005 Implement the minimum frozen task, profile, artifact, grade, trial, bundle, and comparison records plus canonical JSON/SHA-256 helpers in `packages/research/agent_evals.py` to pass T004
- [X] T006 Add failing path-safety tests for traversal, external symlinks, output mutation after snapshot, and workspace overlap with denied roots in `tests/test_agent_evals.py`; run and confirm the safety functions are missing
- [X] T007 Implement path containment, symlink rejection, immutable artifact copying, before/after digests, and atomic manifest writes in `packages/research/agent_evals.py` to pass T006

**Checkpoint**: Evidence records and artifact snapshots are independently testable.

---

## Phase 3: User Story 1 - Define a robotics eval task (Priority: P1)

**Goal**: Six visible task contracts each prove a protected reference passes and a seeded failure is
caught.

**Independent Test**: `eval-verify-suite` reports six valid tasks, six passing references, and six
seeded failures at their declared grade IDs without printing protected paths.

### Tests first

- [X] T008 [US1] Add failing task-discovery and manifest-validation tests for all required fields, units, path containment, reference directories, seeded-failure directories, and duplicate IDs in `tests/test_agent_evals.py`; run and confirm failure because the loader and suite do not exist
- [X] T009 [US1] Add failing parametrized oracle tests requiring six references to pass and six seeded failures to fail their declared target grade in `tests/test_agent_evals.py`; run and confirm failure because the task assets do not exist

### Task assets

- [X] T010 [P] [US1] Create public starter, protected reference, seeded failure, and direct protected grader for `ir-missing-parent` under `evals/robot_design/tasks/ir-missing-parent/` and `evals/robot_design/protected/ir-missing-parent/`
- [X] T011 [P] [US1] Create public starter, protected reference, seeded failure, and direct protected grader for `ir-orphan-payload` under `evals/robot_design/tasks/ir-orphan-payload/` and `evals/robot_design/protected/ir-orphan-payload/`
- [X] T012 [P] [US1] Create public starter, protected reference, seeded failure, and direct MuJoCo grader for `mjcf-payload-inertia` under `evals/robot_design/tasks/mjcf-payload-inertia/` and `evals/robot_design/protected/mjcf-payload-inertia/`
- [X] T013 [P] [US1] Create public starter, protected reference, seeded failure, and direct MuJoCo grader for `mjcf-actuator-contract` under `evals/robot_design/tasks/mjcf-actuator-contract/` and `evals/robot_design/protected/mjcf-actuator-contract/`
- [X] T014 [P] [US1] Create public starter, protected reference, seeded failure, controls, and 1,000-step MuJoCo grader for `arm-reach-target` under `evals/robot_design/tasks/arm-reach-target/` and `evals/robot_design/protected/arm-reach-target/`
- [X] T015 [P] [US1] Create public starter, protected reference, seeded failure, controls, and MuJoCo lift/settling grader for `payload-vertical-lift` under `evals/robot_design/tasks/payload-vertical-lift/` and `evals/robot_design/protected/payload-vertical-lift/`

### Implementation

- [X] T016 [US1] Implement task discovery, JSON contract validation, task fingerprinting, protected grader loading, and reference/seeded validation in `packages/research/agent_evals.py` to pass T008 and T009; profile discovery remains covered by T017 and the Phase 4 profile tasks
- [X] T017 [US1] Add `eval-tasks-list`, `eval-profiles-list`, and `eval-verify-suite` commands to `packages/research/cli.py` and cover their JSON and human output in `tests/test_agent_evals.py`
- [X] T018 [US1] Run `.venv/bin/python -m packages.research.cli eval-verify-suite --suite evals/robot_design` and save the raw deterministic validation output under `.runs/agent_evals/oracle/`

**Checkpoint**: Task publication and oracle validation work without any live agent.

---

## Phase 4: User Story 2 - Run an agent in isolation (Priority: P1)

**Goal**: Run fixture or Codex profiles in clean workspaces without protected-data or cross-trial
access.

**Independent Test**: A real sandboxed child reads and writes its starter workspace but cannot read the
repository sentinel, protected grader, reference, prior result, or another workspace.

### Tests first

- [X] T019 [US2] Add failing isolation tests for allowed workspace access and denied repository, protected, previous-trial, and result-root reads in `tests/test_agent_evals.py`; run and confirm protected reads currently succeed or the sandbox function is absent
- [X] T020 [US2] Add failing runner-state tests for clean copies, exact command capture, stdout/stderr transcript, timeout, dependency error, permission error, nonzero exit, and fixture/live distinction in `tests/test_agent_evals.py`; run and confirm the runner is absent

### Implementation

- [X] T021 [US2] Implement the macOS `sandbox-exec` profile, shell-free subprocess launcher, timeout handling, dependency checks, and denied-root preflight in `packages/research/agent_evals.py` to pass T019
- [X] T022 [US2] Implement clean trial workspaces, fixture copying, Codex JSONL invocation, transcript capture, final artifact freezing, exact error categories, and cleanup/recovery behavior in `packages/research/agent_evals.py` to pass T020
- [X] T023 [P] [US2] Add `reference` and `seeded-failure` fixture profiles under `evals/robot_design/profiles/`
- [X] T024 [P] [US2] Add controlled `codex-baseline` and `codex-robotics-context` profiles with the same executable/model and one documented instruction difference under `evals/robot_design/profiles/`
- [X] T025 [US2] Add `eval-run` and serial `eval-run-suite` commands to `packages/research/cli.py` and cover fixture, live, timeout, error, and unrun output in `tests/test_agent_evals.py`

**Checkpoint**: The runner produces frozen outcomes; it does not yet claim grading or comparison.

---

## Phase 5: User Story 3 - Grade robot artifacts and behavior (Priority: P1)

**Goal**: Grade frozen final artifacts outside the agent process with separate structural, compile,
load, static, and behavior evidence.

**Independent Test**: A result that loads in MuJoCo but violates actuator direction or protected motion
fails the exact behavior assertion, while agent prose and generated grade files are ignored.

### Tests first

- [X] T026 [US3] Add failing grading tests for required artifact absence, protected grader execution after snapshot, category separation, raw MuJoCo output, grader/artifact digests, grader error, and agent-authored `grades.json` rejection in `tests/test_agent_evals.py`; run and confirm normalized grading is absent
- [X] T027 [US3] Add a test requiring at least one seeded artifact to pass XML/MuJoCo load but fail a robotics-semantic or executed-behavior grade in `tests/test_agent_evals.py`; the test passed immediately for two behavior fixtures created in T013 through T015

### Implementation

- [X] T028 [US3] Implement normalized protected grading, direct MuJoCo version/parameter capture, raw output retention, required-grade state reduction, and post-grade artifact rehashing in `packages/research/agent_evals.py` to pass T026
- [X] T029 [US3] Correct the minimum task fixture or grader needed to satisfy the beyond-load negative control in T027 without weakening visible constraints in `evals/robot_design/`
- [X] T030 [US3] Implement the frozen hash-checked evidence-bundle layout and manifest emission in `packages/research/agent_evals.py`, then assert conformance with `contracts/evidence-bundle.schema.json` in `tests/test_agent_evals.py`
- [X] T031 [US3] Run deterministic reference and seeded-failure suites through the complete runner and save bundles under `.runs/agent_evals/deterministic/`

**Checkpoint**: Every shown grade is tied to executed code, exact artifacts, and raw evidence.

---

## Phase 6: User Story 4 - Compare complete agent configurations (Priority: P1)

**Goal**: Compare every task and trial before aggregates and expose exact regressions.

**Independent Test**: Known synthetic trial rows produce correct pass rate, empirical pass@1, strict
pass^3, runtime/cost availability, improvements, regressions, and explicit unrun/error states.

### Tests first

- [X] T032 [US4] Add failing comparison tests for task/trial rows, hard-failure preservation, pass rate, empirical pass@1, strict pass^3, runtime, nullable cost, improvements, regressions, incompatible task revisions, and insufficient samples in `tests/test_agent_evals.py`; run and confirm comparison is absent

### Implementation

- [X] T033 [US4] Implement two-profile comparison and canonical comparison JSON in `packages/research/agent_evals.py` to pass T032
- [X] T034 [US4] Add `eval-compare` to `packages/research/cli.py` and cover human/JSON ordering plus exit states in `tests/test_agent_evals.py`
- [X] T035 [US4] Run three real trials for each available controlled Codex profile across the six tasks, or record the exact unrun blocker without fixture substitution, under `.runs/agent_evals/live/`; local nested-sandbox and profile-contamination blockers are frozen in `unrun.json`
- [ ] T036 [US4] Compare the two complete controlled profiles and save task/trial rows plus aggregates under `.runs/agent_evals/live/comparison.json`; `unrun` because nested Codex isolation failed and global skills contaminated the frozen profiles, with exact evidence in `.runs/agent_evals/live/unrun.json`

**Checkpoint**: The POC can detect a profile regression without producing a composite score.

---

## Phase 7: User Story 5 - Reproduce a result (Priority: P2)

**Goal**: Replay deterministic graders from ordinary saved files and detect every input drift.

**Independent Test**: Three replays of one unchanged bundle produce identical canonical evidence
digests; any task, grader, artifact, simulator, or profile change refuses replay as drift.

### Tests first

- [X] T037 [US5] Add failing replay tests for identical normalized digests, immutable originals, task/grader/artifact/simulator/profile drift, and missing raw files in `tests/test_agent_evals.py`; run and confirm replay is absent

### Implementation

- [X] T038 [US5] Implement deterministic replay with timestamp exclusion and explicit drift reports in `packages/research/agent_evals.py` to pass T037
- [X] T039 [US5] Add `eval-replay` to `packages/research/cli.py` with `--repeat` and `--assert-identical`, then cover exit semantics in `tests/test_agent_evals.py`
- [X] T040 [US5] Replay the deterministic suite three times and save the canonical digest comparison under `.runs/agent_evals/replay/`

**Checkpoint**: Another engineer can reproduce grading without the original UI or agent process.

---

## Phase 8: Strongest-substitute and product decision

**Purpose**: Determine whether the POC is useful, merely vibe-codeable infrastructure, or defensible
enough to justify the next experiment.

- [X] T041 Add a failing subprocess test for the control's validate, grade, compare, and replay outputs in `tests/test_agent_evals.py`; run and confirm `evals/robot_design/control.py` is absent
- [ ] T042 Implement the smallest honest one-file agent-plus-scripts control in `evals/robot_design/control.py` to pass T041 without importing private evaluator orchestration; partial: the 291-SLOC control covers frozen-artifact grading/comparison/replay but does not execute an agent
- [X] T043 Freeze shared outcomes and run evaluator and control against identical artifact digests; save raw control output under `.runs/agent_evals/control/`
- [ ] T044 Measure evaluator/control known-bad recall, reference acceptance, beyond-load catches, hard false passes, localization, replay determinism, isolation violations, task-specific grader lines, total implementation lines, and manual reconciliation time in `specs/011-b2b-feasibility-evidence/poc-results.md`; partial: all automated measures are frozen, but manual reconciliation and engineer-plus-Codex effort are unrun
- [X] T045 Run the Spec 011 drift audit and complexity audit, mapping every `FR` and `SC` to code, tests, evidence, unrun state, or failure in `specs/011-b2b-feasibility-evidence/poc-results.md`
- [X] T046 Record `continue`, `refine`, `open-source`, or `kill`, name the exact evidence, and select the next reviewed concept-tree node in `specs/011-b2b-feasibility-evidence/poc-results.md` and `specs/011-b2b-feasibility-evidence/concept-tree.md`
- [X] T047 Update `README.md`, `.codex`, `AGENTS.md`, and `specs/011-b2b-feasibility-evidence/sdd-checkpoint.md` with only executed POC results and current architecture
- [X] T048 Run `.venv/bin/python -m pytest tests/test_agent_evals.py tests/test_research_core.py tests/test_simulation_loop.py -q`, all quickstart commands, `git diff --check`, local Markdown-link validation, and `python3 .agents/skills/speckit-sdd/scripts/sdd_status.py --json`; 180 tests passed with one dependency warning, all quickstart commands and 18 local links passed, and Spec Kit correctly reports incomplete tasks because T036, T042, and T044 remain unrun or partial

---

## Phase 9: Independent red-team hardening

**Purpose**: Close comparison-integrity defects reproduced by the independent NVIDIA-style code audit.

- [X] T049 [US4] Add failing tests proving comparison accepted corrupted artifacts, missing raw evidence, forged trial/profile/attempt metadata, a missing bundle ID, and legitimate source-revision collisions; run each and observe the expected red failure before implementation
- [X] T050 [US4] Factor byte and cross-link verification from replay into the saved-bundle loader, separate malformed-manifest exit 2 from drift exit 7, expose validated profile/bundle/environment source revisions, and include them in `comparison_id`

---

## Dependencies and execution order

```text
Setup
  -> foundational records and path safety
  -> US1 task definitions and oracle validation
  -> US2 isolated outcome generation
  -> US3 protected grading and evidence bundles
  -> US4 profile comparison
  -> US5 deterministic replay
  -> strongest substitute and product decision
```

- T010 through T015 may run in parallel after T008 and T009 fail as expected.
- T023 and T024 may run in parallel after runner contracts exist.
- Live trials do not begin until oracle, isolation, grading, and bundle tests pass.
- US4 depends on US2 and US3 because comparison inputs must be frozen, graded trial bundles.
- US5 depends on US3 because replay consumes authoritative bundles.
- The product decision depends on shared frozen outcomes; evaluator and control may not grade different
  stochastic agent runs.

## User-story task counts

| Story | Tasks | Independent result |
| --- | ---: | --- |
| US1 | 11 | Valid six-task oracle suite |
| US2 | 7 | Isolated fixture/live trial outcome |
| US3 | 6 | Executed protected evidence bundle |
| US4 | 7 | Complete-profile regression comparison with validated source revisions |
| US5 | 4 | Deterministic replay and drift detection |

## Implementation strategy

The minimum technical POC is Phase 1 through US3: it proves task validity, isolation, and consequential
grading. US4 and US5 make the result useful for recurring profile changes. Phase 8 decides whether that
usefulness survives the one-file substitute.

No task authorizes a frontend, API, cloud deployment, database, generalized registry, Claude parity,
Isaac Sim, new robot IR, URDF claim, controller training, HIL, or physical claim.
