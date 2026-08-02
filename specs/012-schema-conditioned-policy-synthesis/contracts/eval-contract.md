# Contract — gates and rubrics

**Source spec:** [spec.md](spec.md) §4–§5 · **Status:** proposed, not implemented
**Rubric version:** v1. Changing any threshold or formula here requires a new version and human
review; historical runs keep their original version so comparisons stay valid.

---

## Structural diff `D(a, b)`

Used by G2 and G3. Compares two scaffolds on structure, not on wording — an LLM rephrasing a
rationale must not register as a change, and adding a load-bearing term must.

```
D(a, b) = 0.40 · jaccard_distance(term_names(a),        term_names(b))
        + 0.25 · jaccard_distance(symbol_set(a),        symbol_set(b))
        + 0.20 · jaccard_distance(termination_causes(a), termination_causes(b))
        + 0.15 · normalized_weight_distance(a, b)
```

`normalized_weight_distance` is L1 over weights of terms present in both, scaled to [0, 1].
Rationale strings, term ordering, and formatting are excluded by construction.

`D ∈ [0, 1]`. `D = 0` means structurally identical.

## G1 — Schema-reference resolution

Static. No model calls. Runs on every scaffold ever written.

**Procedure.** Parse the schema into an entity table (`joint`, `body`, `site`, `actuator`,
`sensor`). For each `symbols` entry in every reward term and termination predicate, attempt
resolution against that table. `const.*` never resolves — by design.

**Pass:** `resolved_terms / total_terms ≥ 0.80` **and** `resolved_terminations == total_terminations`.

Terminations are held to 100% because an unresolvable termination predicate cannot compile against
the robot at all; it is a correctness bug, not a style issue.

**Fails when:** the loop emits a generic scaffold decorated with plausible-sounding names that do
not exist in *this* robot.

## G2 — Ablation

Causal. The most expensive gate and the one that matters most.

**Permutation classes** — each applied to a dev schema to produce a mutant:

| Class | Mutation | Expected response |
| --- | --- | --- |
| `link_scaled` | Scale link lengths 0.5×–2.0× | Reach/height terms and curriculum bounds shift |
| `limits_altered` | Tighten joint limits 40% | Effort/saturation terms shift |
| `dof_removed` | Delete one actuated joint | Terms referencing it must disappear |
| `topology_swapped` | Reparent a subtree | Body-relative predicates must change |

**Pass:** `D(original, mutant) > τ` for **every** class.

`dof_removed` additionally requires a hard check: no surviving symbol may reference the deleted
joint. A scaffold citing a joint that no longer exists fails G2 outright regardless of `D`.

## G3 — Cross-body divergence

Same `task_text`, two structurally different schemas, independent loop runs.

**Pass:** `D(scaffold_dev_a, scaffold_dev_b) > τ`.

Cheapest gate to fail, and the fastest signal that the loop is reading the task string instead of
the robot.

## G4 — Held-out

Runs **once**, after G1–G3 are frozen (plan.md §7 step 8).

**Pass:** for each held-out schema, `success_rate(generated) > success_rate(baseline)` under an
identical step budget, **and** `dev_mean − holdout_mean ≤ 0.15`.

The second condition is the real test. Beating baseline only on schemas the prompts were developed
against is prompt overfitting — the subtle version of the cheat G1–G3 catch crudely.

## τ — calibration, not choice

τ is **derived**, never hand-picked. From the negative control (spec §5):

```
τ = D_control_max + 0.5 · (D_handwritten_min − D_control_max)
```

where `D_control_max` is the largest structural diff the static control produces across all G2/G3
comparisons, and `D_handwritten_min` is the smallest diff between per-schema hand-written scaffolds.

Midpoint between "a loop that definitely cheats" and "scaffolds a careful human wrote per robot."

**If `D_handwritten_min ≤ D_control_max`, τ does not exist and the diff function is broken.** That
outcome halts the spec until `D` is redesigned — it means the metric cannot distinguish cheating
from genuine per-robot work, and no result gathered with it would mean anything.

## Negative control

`static_scaffold_loop` ignores the schema and returns a fixed scaffold hand-tuned for `dev-a`.

**Required outcome — the control must FAIL:**

| Gate | Expected | Reasoning |
| --- | --- | --- |
| G1 | Fail on every schema except `dev-a` | Its symbols only exist in `dev-a` |
| G2 | Fail on all four permutation classes | `D = 0` by construction; it cannot respond |
| G3 | Fail | `D = 0` across bodies |
| G4 | Not run | Never reaches it |

**If the control passes any of G1–G3, the gates are broken and every result from the real loop is
inadmissible until they are fixed.** This is the check on the checker, and it runs every single run
(R7) rather than once at setup — a gate that silently degrades is worse than no gate.

## Rubric — proposed loop changes

The daily routine scores its own proposal before writing it. A proposal below 3/5 on any dimension
is not queued.

| Dimension | 1 | 3 | 5 |
| --- | --- | --- | --- |
| Falsifiability | No stated failure mode | Vague failure mode | Names the gate it moves and the observation that would refute it |
| Grounding | Speculative | Cites a run log | Cites a specific gate failure in a specific committed run |
| Scope | Rewrites the loop | Several coupled edits | One isolated change |
| Cost awareness | Unbounded | Rough estimate | Bounded, with expected cost per gate-point |
| Cheat resistance | Could pass by memorizing | Neutral | Makes cheating *harder* to hide |

The last dimension is the one that keeps this project honest as it accretes changes: a proposal that
would improve the headline number while weakening the gates scores 1 and is rejected.
