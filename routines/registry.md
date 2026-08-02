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
| — | — | No firings yet. Routine created 2026-08-02 11:27 UTC; first run 2026-08-02 13:00 UTC. | — | — |

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
