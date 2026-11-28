# Increment 2026-11-09 — self-check field on the initial-generation prompt

**Status:** proposed, not implemented. Scored against `contracts/eval-contract.md`'s rubric
below; queued for the compute plane as `experiments/queue/2026-11-09.yaml`. Not applied to
`scaffold_loop.py` by this firing — per the routine's own authority (spec.md §9), a research-day
proposal is written and queued, not merged into the loop unilaterally.

**Why today is a research day, not an implementation day.** Build order (plan.md §7) is 7/8:
steps 1–7 are implemented and evidenced (`packages/research/loop_research/` carries
`scaffold.py`/`symbols.py`/`expr.py`/`entity_table.py`/`mujoco_compiler.py`/`rollout.py`/
`scaffold_loop.py`/`static_scaffold_loop.py`/`structural_diff.py`/`structural_gates.py`/`tau.py`/
`permutations.py`/`orchestrator.py`/`sim_worker.py`/`gates.py`/`baselines.py`, 97/97
`tests/test_loop_research_*.py` passing, reconfirmed live by this firing). Step 8 (held-out
evaluation) is externally blocked: it requires schemas under `evals/policy_synthesis/holdout/`
that spec.md §2/§9 bar this routine from authoring, and that directory still holds only its
placeholder `README.md`. No firing has produced a research-day proposal since the build order
reached this state around 2026-08-11 — every firing since has been consumed by re-verifying the
same standing facts (trigger still bootstraps from the `v1` prompt, PR #6 still open/draft/
unreviewed) rather than doing the work spec.md's research-day path actually asks for. This firing
does both: re-verifies the standing facts (see `routines/registry.md`'s new row) **and** produces
the first research-day proposal.

## 1. The narrowest margin in the most recent run

[`run.json`](../../../.runs/loop_research/2026-08-11T13-56-25Z_step7_9fc352/run.json) (step 7, the
real loop, dev-a/dev-b, task "lift the payload to shelf height") — all gates pass, but G2's four
permutation classes do not pass with equal margin:

| Permutation | Structural diff `D` | τ | Margin (`D` − τ) |
| --- | --- | --- | --- |
| `limits_altered` | 0.9432 | 0.0278 | 0.9154 |
| `topology_swapped` | 0.9432 | 0.0278 | 0.9154 |
| `link_scaled` | 0.9079 | 0.0278 | 0.8801 |
| **`dof_removed`** | **0.6357** | 0.0278 | **0.6079** |

Every class passes comfortably in absolute terms — this is not a failing gate. But `dof_removed`
is the narrowest of the four by a wide margin (0.27–0.31 lower than the other three), and
`routines/registry.md`'s Known Issues table already flagged this exact permutation as "a candidate
research-day topic once build order is complete," after a 2026-08-09 run showed it as the one arm
that needed the 2026-08-10 compile-repair-loop fix to even produce a scored result. That loop-side
gap is closed (the repair loop exists), but *why this specific class scores lower*, structurally,
has not been investigated. This increment is that investigation's first proposal.

## 2. The change

Add a `self_check` field to `scaffold_loop.py`'s `_INITIAL_PROMPT` (the one-shot, zero-revision
call every G2/G3 arm actually makes — confirmed by reading `step7_dof_removed_recheck.py`:
`ScaffoldLoopConfig(max_revisions=0, ...)`, so G2/G3 arms never reach `_REVISION_PROMPT` at all).

Today, `self_check` exists **only** in `_REVISION_PROMPT`:

```
"self_check": one sentence confirming every symbol referenced below appears in the entity table
above.
```

`_INITIAL_PROMPT` — the only prompt a G2/G3 arm ever sees — has no equivalent field. The proposed
field, added to `_INITIAL_PROMPT`'s required JSON keys:

```
"self_check": one sentence naming any actuated joint, site, or sensor in the entity table above
that this scaffold's reward_terms and terminations do NOT reference, and why leaving it out is
correct for this task. If every entity is referenced, say so explicitly.
```

This does **not** show the mutant arm the original (pre-permutation) schema or scaffold — it
operates entirely within the single independent call each arm already makes, so it does not
touch loop-contract.md C6's independence boundary ("Independent gate arms ... must never share a
prompt context"). It is a one-line addition to an existing prompt template; nothing else in
`scaffold_loop.py` changes, and the field is not read or branched on by the harness (consistent
with `restructure_required` being the only field the loop currently acts on) — it changes only
what the model is asked to produce, not what the code does with the reply.

## 3. Hypothesis and what would refute it

**Hypothesis.** `dof_removed` shrinks the entity table by exactly one joint (and its actuator)
while leaving everything else unchanged. A one-shot generation with no explicit prompt pressure to
engage with the *current* entity table's exact membership can satisfy "ground every choice in
THIS robot" (the existing closing line of both prompts) by habit — reusing term names and
structure that would also fit the five unaffected joints — without the model ever having to
notice, inside its own output, that one entity is gone. Forcing an explicit "what's not used, and
why" sentence is cheap, bounded pressure toward actually engaging with the schema's exact current
membership on every independent call, which should show up most on the permutation class where
habit and correctness are easiest to conflate.

**Observation that would confirm it.** Re-running the `dof_removed` arm (same method as
`step7_dof_removed_recheck.py`: single arm, `seed=11`, reused `dev-a-g2-baseline` scaffold, τ from
the same `step5` run) with the modified `_INITIAL_PROMPT` produces `structural_diff` materially
above 0.6357, without moving it closer to or past the other three classes' ~0.94 in a way that
suggests the model is now inferring cross-arm information it shouldn't have access to (it has
none to infer from — the mutant call never sees the original schema).

**Observation that would refute it.** The re-run's `structural_diff` is at or below 0.6357, or any
permutation arm's G1/G2 result changes in a way not attributable to this one field (e.g. a new
compile failure) — meaning the field added prompt length without changing behavior, and should be
reverted rather than kept on the strength of this hypothesis alone. One re-run is not a reliability
claim either way (the existing Known Issues entry's own caution); this is step one of
characterizing `dof_removed`, not a closing one.

## 4. Rubric score (`contracts/eval-contract.md`)

| Dimension | Score | Why |
| --- | --- | --- |
| Falsifiability | 5 | Names the gate (G2, `dof_removed`) and the exact observation (`structural_diff` vs. the committed 0.6357) that would confirm or refute it. |
| Grounding | 5 | Cites the specific gate result in the specific committed run (`2026-08-11T13-56-25Z_step7_9fc352/gates.json`), not a general impression. |
| Scope | 5 | One field, one prompt template, no gate/contract/threshold code touched, no other prompt changed. |
| Cost awareness | 5 | Zero new model calls; bounded output-token cost (one sentence); no tier escalation implied; validation is one single-arm re-run, same shape as the existing `step7_dof_removed_recheck.py`. |
| Cheat resistance | 4 | Does not reveal cross-arm information (independence preserved); makes template-reuse *harder* to pass unnoticed since the model must explicitly account for the exact entity table it was given. Not a 5 only because the field's honesty is self-reported by the same model being asked to improve on it — the hard, structural check is still G1/G2 themselves, not this field. |

All five dimensions clear the ≥3 bar — queued, not discarded.

## 5. What this is not

- Not a change to any gate, to τ, or to the diff formula — nothing in `structural_gates.py`,
  `structural_diff.py`, or `tau.py` is touched.
- Not a hand-written reward function or policy for the lift task — the field asks the model to
  audit its own output against the schema; it does not supply, suggest, or bias toward any
  specific reward term, weight, or expression.
- Not validated yet. No compute-plane run exists to test it (`OPENAI_API_KEY` is still unset,
  per `routines/budget-log.md`'s single 2026-08-03 row); the queue manifest
  (`experiments/queue/2026-11-09.yaml`) is what lets either the compute plane or a future local
  substitute run pick it up and produce that evidence.
