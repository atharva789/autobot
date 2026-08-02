# Data model 012

**Source spec:** [spec.md](spec.md) · **Status:** proposed, not implemented

All records are immutable. A revision never edits its predecessor; it references it.

---

## `TrainingScaffold`

The loop's only output. Never a policy, never Python.

```jsonc
{
  "scaffold_id": "sc_<ulid>",
  "schema_id": "dev-a",
  "schema_digest": "sha256:...",      // exact bytes the loop was given
  "task_text": "lift the payload to shelf height",
  "parent_scaffold_id": "sc_... | null",
  "motivating_batch_id": "rb_... | null",  // R2: null only for the first revision

  "reward_terms": [
    {
      "name": "grasp_hold",
      "weight": 0.45,
      "expression": "min(sensor.f_left, sensor.f_right) / const.f_target",
      "symbols": ["sensor.f_left", "sensor.f_right"],   // G1 resolves these
      "rationale": "episodes ended by payload_slip in batch rb_..."
    }
  ],

  "terminations": [
    {
      "name": "payload_slip",
      "predicate": "body.payload.pos.z - site.gripper.pos.z > 0.02",
      "symbols": ["body.payload", "site.gripper"],
      "cause_label": "slip"                 // R3: rollouts report this label back
    }
  ],

  "curriculum": [
    {
      "stage": 0,
      "parameter": "payload_mass",
      "range": [0.5, 1.0],
      "advance_when": "success_rate > 0.7 over 32 episodes"
    }
  ],

  "randomization": [
    {"parameter": "friction.tangential", "range": [0.6, 1.2], "distribution": "uniform"}
  ],

  "provenance": {
    "prompt_version": "v1",
    "model_id": "...",
    "model_tier": "cheap | frontier",
    "seed": 42,
    "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0
  }
}
```

**Symbol grammar.** `symbols` entries are dotted paths into the schema: `joint.<name>`,
`body.<name>`, `site.<name>`, `actuator.<name>`, `sensor.<name>`. `const.<name>` is a literal and
is explicitly **not** schema-resolvable — a scaffold made only of `const.*` fails G1 by construction.
That is the point: the type system makes the cheat visible.

## `RolloutBatch`

What the simulator returns. R3 forbids collapsing this to a scalar.

```jsonc
{
  "batch_id": "rb_<ulid>",
  "scaffold_id": "sc_...",
  "episodes": 64,
  "step_budget": 2000000,
  "success_rate": 0.94,
  "termination_histogram": {"slip": 2, "torso_z": 1, "timeout": 1, "success": 60},
  "contact_events": {"gripper_payload": 61, "payload_ground": 3},
  "joint_saturation": {"j_elbow": 0.31, "j_wrist": 0.02},   // fraction of steps at limit
  "trace_uri": "s3://artifacts/rb_.../trace.parquet",
  "seed": 42,
  "wall_clock_s": 0.0
}
```

`termination_histogram` keys are `cause_label`s from the scaffold. This is the coupling that lets
the loop reason about *why* episodes ended rather than *how well* they scored.

## `GateResult`

One per gate per run. Recorded on pass and on fail (R4).

```jsonc
{
  "gate": "G1 | G2 | G3 | G4",
  "scaffold_id": "sc_...",
  "passed": true,
  "score": 0.86,
  "threshold": 0.80,
  "detail": {
    // G1: {"resolved": 12, "total": 14, "unresolved": ["const.magic_offset"]}
    // G2: {"permutation": "dof_removed", "structural_diff": 0.41, "tau": 0.25}
    // G3: {"schema_a": "dev-a", "schema_b": "dev-b", "structural_diff": 0.55}
    // G4: {"holdout": "holdout-a", "vs_baseline": 0.12, "dev_gap": 0.08}
  },
  "rubric_version": "v1"
}
```

## `ExperimentRun`

The committed record. One directory per run under `.runs/loop_research/<run-id>/`, matching the
existing `.runs/agent_evals/` convention.

```jsonc
{
  "run_id": "2026-08-03T13-00-00Z_a1b2c3",
  "manifest_path": "experiments/queue/2026-08-03.yaml",
  "git_sha": "...",
  "trigger": "routine | manual",
  "status": "completed | aborted_cost | aborted_error",

  "scaffolds": ["sc_..."],
  "batches": ["rb_..."],
  "gates": [ /* GateResult */ ],

  "control": {                        // §5 negative control, every run
    "loop": "static_scaffold_loop",
    "gates": [ /* must show G1-G3 failing */ ]
  },

  "cost": {
    "usd_total": 0.0, "usd_ceiling": 5.0, "ceiling_hit": false,
    "tokens_by_tier": {"cheap": 0, "frontier": 0},
    "usd_per_gate_point": 0.0
  },

  "replay": {"schema_digest": "sha256:...", "prompt_version": "v1", "model_id": "...", "seed": 42}
}
```

### Files on disk

```text
.runs/loop_research/<run-id>/
├── run.json           ExperimentRun — the file the routine reads
├── scaffolds/         one JSON per revision, in order
├── batches/           RolloutBatch records (traces by reference)
└── gates.json         flattened GateResult list, for cheap diffing
```

`run.json` is the only file the daily routine is required to parse. Everything else is for humans
and for replay.

## Invariants

1. A `TrainingScaffold` with `parent_scaffold_id != null` and `motivating_batch_id == null` is
   rejected at write time (R2).
2. `schema_digest` must match the bytes actually passed to the loop. A mismatch invalidates the run.
3. `GateResult` rows are append-only. A rerun writes a new `run_id`; it never overwrites.
4. `control` is required on every run. A run without the negative control is incomplete (R7).
5. Any number appearing in the README `ROUTINE` block must be traceable to a `run.json` field.
6. **The core stays at four records.** Proposing a fifth record type requires folding or retiring
   one of these, argued in an increment. Sophistication belongs in the loop's reasoning, not in
   the data model (maintainer directive, 2026-08-02).
