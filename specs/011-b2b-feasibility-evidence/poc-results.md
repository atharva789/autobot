# POC Results: Agentic Robot Design Evals

**Experiment frozen**: 2026-07-19

**Starting Git SHA**: `eb9aa97`

**Mandatory spend**: `$0`

**Decision**: `refine` the product hypothesis; treat the frozen-artifact evaluator as open-source infrastructure

**Live causal comparison**: `unrun`, not failed and not substituted with fixtures

## Outcome

The executable robotics graders distinguished six references from six internally seeded failures;
four loadable models failed deeper static or behavior checks, and all twelve saved outcomes replayed
identically three times. Customer usefulness is not established.

It did not prove a defensible evaluator product. A 291-SLOC one-file control drove the same protected
graders over the same artifact bytes and matched the evaluator's state and failed-grade set on 12 of
12 outcomes. The evaluator plus its CLI is 2,701 SLOC after independent comparison-integrity
hardening. This proves that frozen-artifact grading and
basic comparison are easy to reproduce. The control does not run an agent, enforce isolation, capture
profiles, or measure an engineer using Codex, so it does not reproduce the full product. The 1,503
SLOC of protected robotics graders is the clearest technical asset.

The controlled Codex experiment produced zero valid trials. The real Codex process reached the model,
but its inner sandbox could not start inside the outer macOS sandbox, and global skill descriptions
contaminated the supposedly empty profile. Those runs are recorded as `unrun` for causal comparison.

## Environment

The Python, MuJoCo, platform, and sandbox values are frozen in the evidence bundles. Hardware, Codex,
Docker-daemon, and free-disk rows are local operator observations; no separate raw environment probe
was preserved for them.

| Component | Executed value |
| --- | --- |
| Platform | Apple M3 MacBook Air, 24 GB RAM, local worktree |
| Python | 3.13.7 from `.venv/bin/python` |
| MuJoCo | 3.7.0 |
| Codex CLI | 0.144.5 |
| Local isolation backend | `/usr/bin/sandbox-exec` |
| Docker | CLI present; daemon unavailable |
| Cloud | none |
| Remaining local disk observed during the POC | 66 GiB |

## Built slice

- Six tasks under `evals/robot_design/`, each with starter files, a reference, one seeded failure, and
  a protected grader.
- One evaluator module, `packages/research/agent_evals.py`, for profiles, isolation, frozen artifacts,
  grading, bundles, replay, and comparison.
- Seven CLI commands in `packages/research/cli.py` across five operation categories: list, verify,
  run, replay, and compare.
- Ordinary-file evidence bundles containing exact task, profile, grader, environment, transcript,
  grade, and artifact snapshots or hashes.
- One deliberately small control, `evals/robot_design/control.py`, which does not run or isolate
  agents and does not import evaluator orchestration.

## Executed measurements

| Measurement | Evaluator | One-file control |
| --- | ---: | ---: |
| Reference acceptance | 6 / 6 | 6 / 6 |
| Known-bad recall | 6 / 6 | 6 / 6 |
| Hard false passes | 0 | 0 |
| Exact declared-failure localization | 6 / 6 | 6 / 6 |
| Loadable failures caught by deeper static/behavior checks | 4 / 5 eligible | 4 / 5 eligible |
| Same-artifact state and failed-grade agreement | 12 / 12 | 12 / 12 |
| Three-repeat deterministic replay | 12 / 12 | 12 / 12 |
| Evidence fields present | 8 / 8 | 5 / 8 |
| Evaluator plus eval CLI SLOC | 2,701 | 291 |
| Shared task-grader SLOC | 1,503 | 1,503 |
| Warm median grade time, agent execution excluded; ad hoc | 2.04 ms | 2.23 ms |
| Warm p95 grade time, agent execution excluded; ad hoc | 4.51 ms | 4.42 ms |
| Isolation | enumerated local probes only | unsupported |

The grading times and automated twelve-outcome reconciliation time of 2.67 seconds are single local
ad hoc observations. The raw timing samples and benchmark driver were not preserved, so exact
reproduction is not claimed.
Manual reconciliation time and the
engineer-plus-Codex substitute were not measured, so the strongest-substitute gate is partial and no
workflow-effort advantage is claimed. Full definitions, file lists, and task rows are in
`.runs/agent_evals/control/metrics.json`.

## Raw evidence ledger

| Stage | Evidence | Status | File SHA-256 or exact result |
| --- | --- | --- | --- |
| Oracle validation | `.runs/agent_evals/oracle/verify-suite.json` | passed | `2d396280abf14813d788af464e823e2d824adc632db24e6c24436f78478fbc0c` |
| Isolation and execution tests | `tests/test_agent_evals.py` | passed locally | enumerated boundary only; not a production-isolation claim |
| Deterministic bundles | `.runs/agent_evals/deterministic-v2/` | passed | six references passed; six seeded outcomes failed |
| Deterministic comparison | `.runs/agent_evals/deterministic-v2/comparison.json` | passed but sample incomplete | `05d9b8eab5caf8a8e414391b5306c74b83332746027e1144f0911b6507c8e61e` |
| Three-repeat replay | `.runs/agent_evals/replay/deterministic-v2.json` | passed | file `ed93d1372530ec41264d5c0229f34a64a8be78a1ba0834918e982c63a765fee1`; canonical result `00fa7e1646bb2f55ae630dc175b57bcaee5f6760b279cfd05d518f0633681ac5` |
| Controlled Codex trials | `.runs/agent_evals/live/unrun.json` | unrun | `1e798b82c0141eb0f368093a9fbc5b1ca6d85d16ab7ca9975fd70827e633d4a2` |
| Control raw outputs | `.runs/agent_evals/control/index.json` | passed | `625ef8d907d975233aac34626b8f145d42dce4ccbd4dc80f883056547c7a1f37` |
| Control metrics | `.runs/agent_evals/control/metrics.json` | partial | `7a1295c00c23245e80fe3dbb9072501325c12db6884f1880493b46ddb68fb6a7`; grading parity measured, engineer-plus-agent effort unrun |

## Independent code red team

The first implementation was not accepted. An independent code-path audit reproduced three material
comparison failures:

1. `eval-compare` trusted saved manifest rows after an artifact was corrupted.
2. Two legitimate profile/bundle revisions with identical aggregate outcomes could receive the same
   `comparison_id`.
3. Editing only a saved attempt number changed pass@1 without invalidating the comparison.

Failing tests were added before each fix. Saved comparison now validates snapshot, transcript, grade,
artifact, state, attempt, and trial-ID cross-links; requires canonical bundle identity; exposes both
sides' profile/bundle/environment revisions; and hashes those revisions into `comparison_id`.
Malformed manifests exit 2, drift or incompatible revisions exit 7, and replay drift exits 6. The
final direct audit found no remaining P0/P1 in this path. This establishes internal consistency, not
authenticity: a coordinated rewrite of the unsigned manifest and every referenced hash still lacks an
external trust root.

## Exact live blocker

The actual Codex smoke reached the model and returned exit code 0, but every inner tool launch failed
with:

```text
sandbox-exec: sandbox_apply: Operation not permitted
```

The transcript also reported injected global skill descriptions even though the frozen profile
declared no skills, MCPs, or plugins. Running the remaining 35 trials would have measured a broken
nested sandbox and a contaminated treatment, not agent quality. Disabling Codex's inner sandbox under
the permissive compatibility profile would expose the host and was not attempted.

The minimum valid next runtime is a disposable worker or VM, a disposable Codex credential, an empty
Codex home, and no global skills/plugins. On this machine the smallest local route is a Linux VM or
container runtime; only the Docker CLI is installed and no daemon is available.

### Minimum resource request

- Permission to install and start Colima locally. It is free; allocate about 4 CPU, 8 GB RAM, and
  20 GB disk. Mount only each copied starter workspace into the disposable worker.
- One disposable OpenAI project API key delivered through a secure environment mechanism, not chat,
  with a `$100` hard project cap.
- First run only 2 profiles × 1 task × 3 trials = 6 trials. Stop the pilot at `$20` or on any leakage,
  contamination, or isolation failure. Run the full 36 trials only if the pilot is clean.

Do not copy the current long-lived Codex login into the worker. No paid compute is requested.

## Requirement drift audit

| Requirement | Status | Executed evidence or gap |
| --- | --- | --- |
| FR-001 | pass | Six exact-field task manifests include prompt, starter, constraints, tools, budget, outputs, grader, and reference. |
| FR-002 | pass | Oracle evidence is 6 / 6 reference acceptance and 6 / 6 seeded-failure recall. |
| FR-003 | partial | Generic and compatibility-boundary probes pass; the real Codex profile is invalid under nested sandboxing and cannot support a live-isolation claim. |
| FR-004 | partial | Frozen profiles record harness, model, command, instructions, skills, MCPs, tools, environment names, budget, runtime, and nullable cost. Seed and complete tool-version manifests remain absent where unavailable. |
| FR-005 | pass | Bundle trials include raw transcript and grade paths plus byte hashes, exit state, final artifacts, and artifact hashes. |
| FR-006 | pass | Timeout, dependency, permission/nonzero execution, error, and unrun paths have separate states and tests. |
| FR-007 | pass | Protected graders inspect frozen files; agent-authored `grades.json` is ignored. |
| FR-008 | pass | IR compilation, MuJoCo model loading, 1,000-step reach, 250-step actuator direction, and 1,500-step lift checks executed. |
| FR-009 | pass | Structural, file-format, compile, simulator-load, static, and behavior categories remain separate. |
| FR-010 | pass | Missing artifact and agent-score tests fail; fixtures are labeled fixtures and never agent results. |
| FR-011 | pass | Each grade carries task/trial revision context, grader hash, artifact hashes, parameters, observations, raw output, status, and duration. |
| FR-012 | pass | Six tasks cover IR repair, constrained MJCF modification, and executed behavior. |
| FR-013 | pass as incomplete | Both live profiles are explicitly `unrun`; no one-trial result is presented as a three-trial profile. |
| FR-014 | partial | Complete profile fingerprints and changed-component comparison exist; no valid live two-profile comparison exists. |
| FR-015 | pass | Tests and deterministic evidence show task/attempt rows before aggregates. |
| FR-016 | pass | Any required failure makes the trial fail; no composite score exists. |
| FR-017 | pass | Replay refuses task, grader, profile, artifact, simulator, transcript, and grade-file drift. Comparison validates every referenced bundle before use, refuses metadata/state/attempt/raw/artifact drift, and hashes profile, bundle, and environment source revisions into its ID. |
| FR-018 | pass | This report is human-readable; manifests and replay/control ledgers are machine-readable JSON. |
| FR-019 | pass | All completed POC work ran locally at zero mandatory spend. |
| FR-020 | pass | The slice reused local adapters, IR/compiler, and MuJoCo where truthful; unsupported live isolation remained visible instead of entering old run storage as success. |
| FR-021 | pass | Claims are limited to the executed invariant; no manufacturability, safety, controller, or hardware claim is made. |
| FR-022 | pass | This section and the product verdict provide the required drift and kill reports. |

## Success-criterion audit

| Criterion | Status | Evidence or gap |
| --- | --- | --- |
| SC-001 | pass | Six passing references and six caught seeded failures. |
| SC-002 | pass | Four loadable artifacts fail inertia, actuator direction, reach, or lift semantics. |
| SC-003 | partial | Local probes report zero enumerated protected-path violations; the real Codex boundary is unrun, so zero live-agent leakage is not claimed. |
| SC-004 | pass | Simulator and behavior grades carry final artifact hashes and MuJoCo 3.7.0 evidence. |
| SC-005 | pass | No placeholder, flag, formula score, or agent assertion establishes a pass. |
| SC-006 | pass | Twelve bundles each produced one digest across three replays. |
| SC-007 | partial | Exact fixture task changes are reported; the intended live profile comparison is unrun. |
| SC-008 | pass | Failed grade IDs and hard failure states remain visible before aggregates. |
| SC-009 | partial | CLI replay needs no UI, but two IR graders still import live repository pipeline code that is not copied into the bundle. |
| SC-010 | pass | Zero mandatory cloud spend. |
| SC-011 | partial | All declared fields are represented, but the bundle manifest is unsigned, `bundle_id` is not a hash of every raw byte, and imported pipeline/NumPy dependencies are not snapshotted. |
| SC-012 | pass | The report does not return `continue`; the control reached full grading parity. |

## Field and export drift

- Task fields are exact-validated and the full task JSON is byte-hashed in each bundle.
- Profile fields are exact-validated and the public profile JSON is byte-hashed. Secret values are
  never persisted.
- Trial state, command, timing, transcript, grades, artifacts, error, and observable cost are recorded.
- Grade category, status, assertion, hashes, parameters, observations, raw output, duration, and grader
  fingerprint are recorded.
- Comparison rows preserve task, attempt, profile, bundle, and environment revision identity before
  aggregates; derived snapshot hashes remain separate from treatment-change reporting.
- Exported task, profile, grader, environment, transcript, grade, and artifact bytes are checked on
  replay. The top-level manifest itself has no external signature or content-addressed trust root.
- The copied grader is replayed from a temporary directory so Python cache files and faulty graders
  cannot mutate the original bundle. Imported local pipeline modules remain an unsnapshotted input.

## Complexity and defensibility decision

The frozen-artifact grading and comparison layer is straightforward to vibe-code. The 291-SLOC
control matched every frozen grading decision; implementation time was not measured. Its single
local ad hoc grading timings were in the same millisecond range, but the raw samples were not
preserved. Adding a database, web UI, distributed queue, registry hierarchy, or cloud control plane
would increase code without changing that result.

The full evaluator was not reproduced by the control: isolated agent execution, profile capture,
transcripts, hash-checked bundles, and drift refusal remain evaluator-only. Their customer value also
remains unproven because the live profile experiment and engineer-plus-Codex substitute are unrun.

The protected graders are different: they encode graph connectivity, compiled-body coverage, inertial
contracts, actuator semantics, reach behavior, and loaded-payload behavior. They are also bespoke and
currently all authored inside this repository. There is no evidence yet that they generalize, recur for
buyers, or compound into a proprietary corpus.

Therefore:

1. Return `refine`, not `continue`: product defensibility is unresolved.
2. Do not position frozen-artifact grading, JSON evidence, or comparison as the moat; keep that layer
   as open-source-style local infrastructure.
3. Do not build hosted B2B UX until valid live trials, external faults, and recurring buyer use exist.
4. Treat the current local isolation as a narrow test boundary, never production host isolation.

## Next concept node

`Agentic Robot Model-Repair Evals` is selected for design review, not implementation. It is the closest
child to the only surviving asset: executable repair invariants and failure cases.

Its next POC must use at least twelve held-out repair faults, include at least three externally sourced
failures from at least two teams, run a static-lint baseline, and run uncontaminated live agents. Kill it
if static lint catches 90% or more, live agents saturate the suite, or teams do not perform repairs
repeatedly. Until the disposable runtime and external-failure inputs exist, branching further would be
speculation rather than the requested build-test-refine loop.
