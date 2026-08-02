# Spec 012 — Schema-Conditioned Policy Synthesis

**Status:** proposed, not implemented
**Author:** Claude (agent-authored, pending human review)
**Created:** 2026-08-02
**Supersedes scope of:** none. Narrows `specs/003-robot-rl-research-program` to one falsifiable slice.
**Depends on:** `packages/pipeline` IR + MJCF compiler, `evals/robot_design/protected/` graders.

---

## 1. The claim under test

> An agent loop, given a robot schema and one task, can emit an RL training scaffold whose
> content is **causally dependent on that schema** — and this dependence can be measured, not asserted.

The failure mode this spec exists to catch is the obvious one: a loop that ignores the schema,
pattern-matches the task string, and emits a plausible reward function that happens to work on the
robot it was tuned against. Such a loop demos well and is worthless. Every requirement below is
built to make that outcome *fail visibly* rather than pass quietly.

This is the same methodology `specs/011` used — seeded failures that the grader must catch — applied
to policy synthesis instead of body generation.

## 2. Scope

Deliberately one task class and four bodies. Not a general system.

| Axis | Locked value |
| --- | --- |
| Task class | Payload lift-and-place to a target height |
| Task variation | Payload mass, target height, initial payload pose |
| Development schemas | 2 (`dev-a`, `dev-b`) — structurally different |
| Held-out schemas | 2 (`holdout-a`, `holdout-b`) — never seen during loop development |
| Loop output | A `TrainingScaffold`, not a policy and not training code |
| Physics | MuJoCo, CPU, fixed step budget |
| Baseline | One hand-written scaffold per schema, authored once, frozen |

**Structural difference** is a requirement, not a preference. The four schemas must differ in DOF
count, kinematic topology, and actuator type. Four variations of the same arm would make the
divergence gate (§4, G3) unfalsifiable.

### Out of scope

Sim-to-real, hardware, multi-task transfer, learned reward models, policy distillation, any claim
about wall-clock training cost, and training a policy that is *good* rather than *better than the
baseline scaffold under a fixed budget*.

## 3. The artifact: `TrainingScaffold`

The loop emits a scaffold, never a policy and never Python. Four parts:

- **reward terms** — name, weight, and an expression over schema-resolvable symbols
- **termination predicates** — conditions ending an episode, with a labelled cause
- **curriculum stages** — an ordered progression with an advancement criterion
- **domain randomization ranges** — per-parameter bounds

A scaffold compiles to a MuJoCo environment or it is rejected. Compilation is a gate, not a score.

Full field-level definition: [data-model.md](data-model.md).
Interface the loop must satisfy: [contracts/loop-contract.md](contracts/loop-contract.md).

## 4. Anti-cheat gates

These four gates are the substance of this spec. A loop that improves the headline metric while
failing any gate is a **regression**, not progress.

### G1 — Schema-reference gate (static, zero model cost)

Every reward term and termination predicate must resolve at least one symbol to a named entity in
the supplied schema: a joint, body, site, actuator, or sensor that actually exists in that file.

A scaffold made entirely of free-floating literals (`torso_z < 0.4` where no `torso` exists in this
robot) fails. This runs as a parse-and-resolve check with no model calls, so it gates every run.

**Pass condition:** ≥ 80% of terms resolve, and 100% of termination predicates resolve.

### G2 — Ablation gate (causal)

Re-run the loop on a **permuted** schema: link lengths scaled, joint limits altered, one DOF removed.
The emitted scaffold must change by more than threshold τ under the structural diff in
[contracts/eval-contract.md](contracts/eval-contract.md).

A loop that emits the same scaffold for a mutilated robot is not reading the robot.

**Pass condition:** structural diff > τ for every permutation class. τ is calibrated against the
negative control in §5, not chosen by hand.

### G3 — Divergence gate (cross-body)

Same task text, two structurally different robots. Scaffolds must diverge.

Near-identical scaffolds across a quadruped and a 7-DOF arm mean the loop is conditioning on the
task string. This is the cheapest gate to fail and the most important to keep.

**Pass condition:** cross-body structural diff > τ, on the same scale as G2.

### G4 — Held-out gate (generalization)

Performance on `holdout-a` and `holdout-b`, which are not available during loop or prompt
development. Guards against overfitting the *prompt* to the dev cohort — the subtler version of the
same cheat.

**Pass condition:** held-out scaffolds beat their frozen baselines under a fixed step budget, and
the held-out/dev performance gap does not exceed the pre-registered margin.

## 5. Negative control (calibration)

A deliberately cheating loop ships alongside the real one: `static_scaffold_loop`. It ignores the
schema entirely and returns a fixed scaffold hand-tuned for `dev-a`.

It must **fail G1, G2, and G3**, and may well pass a naive headline metric on `dev-a`. If the gates
do not catch it, the gates are broken and no result from the real loop is admissible.

This inverts the usual demo incentive: the control existing and failing is the evidence that the
gates mean something. It also calibrates τ — τ is set from the separation between control and real
loop, not picked by hand.

## 6. Requirements

**R1** The loop accepts `(schema_path, task_description)` and returns a `TrainingScaffold`.
No task-specific branch may exist in loop code. A `if "lift" in task:` is a spec violation.

**R2** Every scaffold revision records the rollout batch that motivated it. A revision with no
antecedent evidence is rejected at write time.

**R3** The loop reads structured rollout outcomes — termination cause, contact events, joint
saturation — never a bare scalar return.

**R4** All four gates run on every experiment. Gate results are recorded even when they pass.

**R5** Every run records token count, model tier, and dollar cost per step, and aborts at a
pre-set ceiling.

**R6** Every run is replayable from `(schema, task, seed, prompt version, model id)`.

**R7** The negative control runs in the same harness on the same cadence as the real loop.

## 7. Exit criteria

This spec is answered — in either direction — when:

1. The negative control fails G1–G3 with a margin that sets τ.
2. The real loop passes G1–G3 on both dev schemas.
3. The real loop is evaluated on both held-out schemas, and the result is recorded **whatever it is**.
4. Cost per full experiment is measured and reported.

A negative result satisfies these criteria. "The loop does not condition on the schema, here is the
ablation evidence" is a valid and publishable outcome of this spec.

## 8. What would falsify the whole direction

Stated up front so it cannot be quietly avoided later:

- Scaffolds pass G1 (they cite real joint names) but fail G2 (citing them changes nothing) —
  the loop is decorating a fixed template with schema symbols.
- Real loop and negative control are statistically indistinguishable on held-out bodies.
- The hand-written baseline beats every generated scaffold on every schema, and the gap does not
  close across revisions.

Any of these means schema-conditioning is not happening, and the direction in the README is wrong.

## 9. Authority of the daily routine

The daily cloud routine (see `routines/registry.md`) is the **control plane**: it decides what
experiment to run next, dispatches it to GitHub Actions, and reports what came back. It does not
hold secrets and does not execute physics itself — that separation is deliberate, not a limitation.
See [plan.md](plan.md) §1–§3.

It **may**: propose changes to this spec and the loop design, queue an experiment, regenerate the
delimited README block, and open a PR.

It **may not**: edit gate thresholds or rubric criteria, modify the held-out schemas, or report a
number it did not read from a committed run log. A routine that can move τ can make its own work
look successful, so τ moves only through human review.
