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
| 2026-08-02 | `implement` | First firing. Build order (plan.md §7) was 0/8 — nothing under `packages/research/loop_research/` existed and `.runs/loop_research/` was empty. Took step 1: `TrainingScaffold`/`RolloutBatch` records, symbol-grammar parser, a whitelisted-AST expression compiler (rejects `__import__`, attribute escapes, comprehensions, lambdas — scaffold expressions are agent-authored, so treated as untrusted input), an entity-table reader that parses schemas via MuJoCo's own parser (no hardcoded joint/body names, per loop-contract.md C2), and the scaffold-to-MuJoCo compiler + rollout runner. Added one hand-written scaffold against a fixture schema (explicitly not one of the four locked dev/holdout schemas — those are step 2) to exercise the "a hand-written scaffold trains" gate: compiles without error, and termination causes track real physics (generous step budget → `success` every episode; starved budget → `timeout` every episode). Did not touch steps 2-8, gate thresholds, τ, or any `holdout-*` path. No compute-plane run exists yet, so no gate/cost numbers are reported. | `tests/test_loop_research_scaffold.py` (19/19 passing, run locally against `packages/research/loop_research/`); `specs/012-schema-conditioned-policy-synthesis/plan.md` §7 for build-order position; `routines/prompts/daily-loop-research.v1.md` for the run's own instructions. | [PR pending — see next commit] |

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

## Known issues

| Issue | Impact | Status |
| --- | --- | --- |
| Spec 012 lived only on `codex/agentic-robot-evals-poc` | Routine clones the default branch; prompt carries a `git fetch && checkout` fallback. | **Resolved 2026-08-02** — PR #3 merged to master |
| `gh` availability in the routine sandbox is unverified | If absent, the routine pushes a branch but opens no PR. Prompt requires it to say so loudly. | Confirm on first firing |
| Model ids unverified against the live API | Both tiers now default to `gpt-4.1-mini` (cheap end-to-end is the project's point; escalation only via manifest override citing a run log). Id still not confirmed to resolve billing-side. | Confirm before first compute run |
| Workflow preflight read the secret inside a `run:` block | Reworked: the presence check is computed in the expression layer (`env: OPENAI_KEY_SET`) so no secret text enters the shell. | **Resolved 2026-08-02** |
