# Routine registry

Every scheduled Claude Code routine attached to this repository, and a journal of what each firing
did. Maintained by the routines themselves, reviewed by a human.

---

## Active routines

| Routine | ID | Schedule (UTC) | Local | Prompt | Model | Branch |
| --- | --- | --- | --- | --- | --- | --- |
| `daily-loop-research` | `trig_012k5hZBEfTpeyTjTaJ2aGcb` | `0 13 * * *` | 06:00 PT | [`daily-loop-research.v1.md`](prompts/daily-loop-research.v1.md) | claude-sonnet-5 | `routine/experiments` |

Created 2026-08-02. Run history: <https://claude.ai/code/routines/trig_012k5hZBEfTpeyTjTaJ2aGcb>

Routines cannot be deleted from here; disable or delete at <https://claude.ai/code/routines>.

### `daily-loop-research`

**Purpose.** Control plane for [spec 012](../specs/012-schema-conditioned-policy-synthesis/spec.md).
Advances the build order while it is incomplete; afterwards proposes one loop/graph change per day,
queues it for the compute plane, and reports what came back.

**Authority.** May propose, implement build-order steps, queue experiments, regenerate the delimited
README block, and open PRs. May **not** edit gate thresholds or τ, touch held-out schemas, rewrite
run history, or report a number it did not read from a committed file. Rationale in
[spec.md §9](../specs/012-schema-conditioned-policy-synthesis/spec.md).

**Cost.** Session tokens only. It makes no OpenAI calls and holds no secrets — the compute plane
(GitHub Actions) does both.

---

## Prompt versions

| Version | Date | Change | Reason |
| --- | --- | --- | --- |
| v1 | 2026-08-02 | Initial | — |

Prompts are never edited in place. The version is recorded in every run log; editing a prompt
without bumping it silently invalidates every comparison across that boundary.

---

## Run journal

Newest first. One row per firing, including no-ops and failures — a journal that records only
successes cannot tell the human whether the routine is worth its tokens.

| Date | Type | What happened | Evidence read | PR |
| --- | --- | --- | --- | --- |
| 2026-08-04 | `implement` (cron firing) | Checked `origin/routine/experiments` and PR #6 *before* building anything (the lesson recorded in the row below) — found steps 1-3 done, step 2 complete for the two dev schemas, step 4 (negative control) the lowest-numbered incomplete step. Implemented `static_scaffold_loop` (`static_scaffold_loop.py`): a fixed scaffold hand-tuned for `dev-a` that ignores `schema_path`/`task_text` entirely. Deliberately did **not** reuse `baselines.py`'s per-schema baseline — that scaffold reuses site names (`grip_center`/`payload_center`/`shelf_target`) shared across `dev-a` and `dev-b` by design (for G2/G3 comparability later), which would have let the control accidentally pass G1 on `dev-b` too. Built the control's fixed scaffold from `dev-a`-only joint/body/sensor names instead (`j_shoulder`, `j_elbow`, `wrist`, `finger_left`, `s_touch_left`) so it fails to resolve at all once the topology changes. Ran it (`step4_run.py`) against both dev schemas: **G1 passes 1.0 on dev-a, fails 0.0 on dev-b** — exactly eval-contract.md's required outcome ("Fail on every schema except dev-a"). Also corroborated at the compiler level: `compile_scaffold` succeeds against `dev-a`, raises `CompilationError` against `dev-b`. G2/G3 need the structural diff `D(a, b)` (step 5, not yet implemented) — did not compute or claim a numeric score for either; instead added a test proving the control returns an object-identical scaffold for different inputs, which makes every term of `D` zero by construction regardless of how `D` is later implemented. No gate threshold, τ, or rubric criterion touched; no `holdout-*` path read or written; no Compose service added. | [`run.json`](.runs/loop_research/2026-08-04T13-29-01Z_step4_423c5e/run.json), [`gates.json`](.runs/loop_research/2026-08-04T13-29-01Z_step4_423c5e/gates.json), `tests/test_loop_research_step4.py` (5 new tests) — 34/34 `loop_research` tests passing (29 prior + 5 new) | pushed to [#6](https://github.com/atharva789/autobot/pull/6) |
| 2026-08-03 | `implement` (first cron firing) | Started from a fresh `master` checkout per the routine's own instructions, read `plan.md` §7 against `master` alone, and initially rebuilt step 1 (`TrainingScaffold` → MuJoCo compiler) from scratch under different module names (`compiler.py`, `expr.py`, `rollout.py`, `records.py`) — duplicating, with a less mature design, the canonical step-1 work already sitting in **open draft PR #6** on `routine/experiments` (reconciled the day before). Caught this before pushing by checking `origin/routine/experiments` and `list_pull_requests`; discarded the duplicate entirely (`git reset --hard origin/routine/experiments`) rather than pushing a second, conflicting implementation. Lesson for future firings, recorded here rather than fixed silently: check this branch and its open PR *before* deciding what to build — `plan.md`'s "read `.runs/loop_research/` from day N-1" assumes prior work is visible, but unmerged PR work on `routine/experiments` is not visible from `master` alone. With the real state established (steps 1 and 3 done, step 2 partial — `dev-a.xml` existed, `dev-b`/`holdout-*` did not), did the actual lowest-numbered incomplete step: authored `evals/policy_synthesis/dev/dev-b.xml`, a 4-DOF Cartesian gantry with a single-jaw pinch gripper and position (servo) actuators, structurally different from `dev-a`'s 6-DOF serial revolute arm with motor (torque) actuators on all three of spec.md §2's required axes (DOF count, kinematic topology, actuator type — asserted directly in `tests/test_loop_research_step2.py` via `model.nu`, `jnt_type`, and `actuator_biastype`). Authored frozen per-schema baselines for both schemas (`baselines.py`, spec.md §2's "one hand-written scaffold per schema, authored once, frozen") and ran both: **G1 passes at 1.0 on both dev-a and dev-b**; both rollouts complete 8 episodes each with a valid `RolloutBatch` (all episodes ended `timeout` under simple, untuned probe policies — this gate is "baselines run", not "baselines succeed"; no success claim is made). 29/29 `loop_research` tests pass. | [`run.json`](.runs/loop_research/2026-08-03T13-39-19Z_step2_ce8fd4/run.json), `tests/test_loop_research_step2.py` (5 new tests), `tests/test_loop_research_scaffold.py` + `tests/test_loop_research_g1.py` (24, unchanged, still passing) | pushed to [#6](https://github.com/atharva789/autobot/pull/6) |
| 2026-08-03 | `implement` (reconciliation, human-directed, PR #6 continued) | `routine/experiments` (PR #6) and `master` (via PR #7, a separate human-directed session) had each built an incompatible implementation of the same spec-012 core: PR #6's `scaffold.py` used typed frozen dataclasses and a symbol grammar supporting multi-level dotted attribute paths (`body.payload.pos.z`, needed by `mujoco_compiler.py` to pull a runtime scalar out of physics state); master's `records.py` used plain dicts and a G1 resolver (`symbol.partition(".")`) that only understood single-level symbols. Flagged the conflict on PR #6 rather than resolving unilaterally (see PR #6 comment); maintainer chose PR #6's implementation as canonical. Reconciled: kept PR #6's `scaffold.py`/`symbols.py`/`expr.py`/`entity_table.py`/`mujoco_compiler.py`/`rollout.py` (step 1) as-is; ported the real `dev-a.xml` schema (4-DOF arm, from PR #7) forward unchanged; rewrote `g1.py` (step 3, the scored gate — 0.80/100% thresholds unchanged from `contracts/eval-contract.md`) against the canonical entity table and multi-level-safe symbol resolution; added the `GateResult`/`ExperimentRun` records to `scaffold.py`, completing data-model.md's four-record set; ported `smoke.py` (the local Haiku-backed loop entry point) onto the typed dataclasses and updated its prompt to describe the canonical symbol grammar. Left PR #7's first run log (`.runs/loop_research/2026-08-03T01-42-44Z_smoke_19ffde/`) untouched — it used the now-superseded dict-shaped scaffold, kept as historical evidence per the append-only rule on `.runs/`, not as a claim about the current G1 implementation. | `tests/test_loop_research_scaffold.py` (19/19), `tests/test_loop_research_g1.py` (7/7, rewritten against the real `dev-a.xml` schema and the canonical grammar) — 26/26 passing locally. | [#6](https://github.com/atharva789/autobot/pull/6) |
| 2026-08-02 | `implement` | First firing. Build order (plan.md §7) was 0/8 — nothing under `packages/research/loop_research/` existed and `.runs/loop_research/` was empty. Took step 1: `TrainingScaffold`/`RolloutBatch` records, symbol-grammar parser, a whitelisted-AST expression compiler (rejects `__import__`, attribute escapes, comprehensions, lambdas — scaffold expressions are agent-authored, so treated as untrusted input), an entity-table reader that parses schemas via MuJoCo's own parser (no hardcoded joint/body names, per loop-contract.md C2), and the scaffold-to-MuJoCo compiler + rollout runner. Added one hand-written scaffold against a fixture schema (explicitly not one of the four locked dev/holdout schemas — those are step 2) to exercise the "a hand-written scaffold trains" gate: compiles without error, and termination causes track real physics (generous step budget → `success` every episode; starved budget → `timeout` every episode). Did not touch steps 2-8, gate thresholds, τ, or any `holdout-*` path. No compute-plane run exists yet, so no gate/cost numbers are reported. | `tests/test_loop_research_scaffold.py` (19/19 passing, run locally against `packages/research/loop_research/`); `specs/012-schema-conditioned-policy-synthesis/plan.md` §7 for build-order position; `routines/prompts/daily-loop-research.v1.md` for the run's own instructions. | [#6](https://github.com/atharva789/autobot/pull/6) |
| 2026-08-03 | `implement` (manual, human-directed session, not a routine firing) | First local smoke of the loop on a substitute provider: Haiku via the repo's `claude-code` adapter (subscription auth, $0 API spend). One evidence-dense call emitted a 5-term/4-termination scaffold for `dev-a`; G1 passed at 1.0. G1 resolver + records implemented with 6 passing tests, including proof G1 fails fabricated symbols. Superseded 2026-08-03 by the reconciliation row above, which ports this schema and re-implements G1 against the canonical grammar — the run log stands as historical evidence, the code it exercised does not. | `.runs/loop_research/2026-08-03T01-42-44Z_smoke_19ffde/run.json` | merged to `master` via #7 |

### Column meanings

- **Type** — `implement` (advanced a build-order step), `research` (proposed a loop change),
  `no-op` (no new evidence), `failed` (the run errored).
- **Evidence read** — the run ids or files the entry's claims came from. An entry with claims and no
  evidence is a review finding, not a record.

---

## Review checklist

For the human, when reviewing a routine PR:

- [ ] Every number in the README block traces to a committed `run.json`.
- [ ] No gate threshold, τ, or rubric criterion changed.
- [ ] **Gate implementations match `contracts/eval-contract.md` exactly** — diff coefficients, G1
      cutoffs, τ derivation. A softened `D` weakens every future result without touching a
      documented constant, so diff the code against the contract, not against the previous commit.
- [ ] No file under a `holdout-*` path was read or written.
- [ ] The proposed change is one change, not several.
- [ ] The increment states what would refute it.
- [ ] The registry row matches what the diff actually does.

## Local substitute mode (active until OpenAI credits arrive)

No OpenAI credits exist yet (2026-08-03). Standing arrangement, maintainer-directed:

- The loop runs **locally** through `packages/research/local_chat_models.py` with
  `--provider claude-code --model haiku` (subscription auth, zero API spend) or `--provider codex`.
  Entry point: `python -m packages.research.loop_research.smoke`.
- A crontab job (`17 9 * * *`, this machine) runs `scripts/daily_budget_check.sh`: it appends to
  `routines/budget-log.md`, and when OpenAI credits exceed **$500** it drops
  `experiments/credits-ready.flag` and fires a desktop notification with the unlock command
  (`gh secret set OPENAI_API_KEY --repo atharva789/autobot`).
- The `credit_grants` endpoint is session-locked (403 with an API key), so the balance is
  `?` in the log until the user sets `OPENAI_BUDGET_USD` in `.env` from the dashboard figure.
  The key's liveness is verified daily via `/v1/models`.
- The compute plane (Actions workflow) stays parked; its preflight correctly reports not-ready
  until the secret exists.

## Known issues

| Issue | Impact | Status |
| --- | --- | --- |
| Spec 012 lived only on `codex/agentic-robot-evals-poc` | Routine clones the default branch; prompt carries a `git fetch && checkout` fallback. | **Resolved 2026-08-02** — PR #3 merged to master |
| `gh` CLI is not installed in the routine sandbox | No impact — the sandbox has the GitHub MCP server's tools instead (`create_pull_request`, `list_pull_requests`, etc.), which the first cron firing used to find and push to the already-open PR #6. | **Resolved 2026-08-03** — confirmed on first cron firing |
| Model ids unverified against the live API | Both tiers now default to `gpt-4.1-mini` (cheap end-to-end is the project's point; escalation only via manifest override citing a run log). Id still not confirmed to resolve billing-side. | Confirm before first compute run |
| Workflow preflight read the secret inside a `run:` block | Reworked: the presence check is computed in the expression layer (`env: OPENAI_KEY_SET`) so no secret text enters the shell. | **Resolved 2026-08-02** |
