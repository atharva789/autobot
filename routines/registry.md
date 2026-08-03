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
| 2026-08-03 | implement (manual, human-directed session, not a routine firing) | First local smoke of the loop on a substitute provider: Haiku via the repo's `claude-code` adapter (subscription auth, $0 API spend). One evidence-dense call emitted a 5-term/4-termination scaffold for `dev-a`; G1 passed at 1.0. G1 resolver + records implemented with 6 passing tests, including proof G1 fails fabricated symbols. | `.runs/loop_research/2026-08-03T01-42-44Z_smoke_19ffde/run.json` | this branch |
| — | — | No routine firings yet. Routine created 2026-08-02 11:27 UTC. | — | — |

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
| `gh` availability in the routine sandbox is unverified | If absent, the routine pushes a branch but opens no PR. Prompt requires it to say so loudly. | Confirm on first firing |
| Model ids unverified against the live API | Both tiers now default to `gpt-4.1-mini` (cheap end-to-end is the project's point; escalation only via manifest override citing a run log). Id still not confirmed to resolve billing-side. | Confirm before first compute run |
| Workflow preflight read the secret inside a `run:` block | Reworked: the presence check is computed in the expression layer (`env: OPENAI_KEY_SET`) so no secret text enters the shell. | **Resolved 2026-08-02** |
