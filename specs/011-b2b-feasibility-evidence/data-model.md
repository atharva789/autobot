# Data Model: Agentic Robot Design Evals POC

The POC uses frozen Python records in memory and canonical JSON on disk. IDs and fingerprints are
content-derived where possible. No entity silently mutates after a bundle is finalized.

## EvalTask

One protected robotics job given to an agent.

| Field | Type | Rules |
| --- | --- | --- |
| `task_id` | string | lowercase kebab-case, stable across revisions |
| `version` | integer | positive; changes whenever prompt, starter, or grader changes |
| `title` | string | short engineer-facing name |
| `family` | enum | `repair`, `constrained-modification`, `executed-behavior` |
| `prompt` | string | complete visible instructions and success contract |
| `starter_dir` | path | must stay inside the task directory |
| `required_outputs` | string array | paths relative to the trial workspace |
| `allowed_tools` | string array | visible tool names; empty means ordinary file and shell tools only |
| `time_limit_seconds` | integer | positive and bounded by the CLI maximum |
| `grader_entrypoint` | string | path under `protected/`; never copied to the workspace |
| `reference_dir` | path | protected known-passing outcome |
| `seeded_failure_dir` | path | protected known-failing outcome |
| `fingerprint` | SHA-256 | canonical manifest plus starter and protected-grader digests |

Validation requires the reference to pass all required grades and the seeded failure to fail the
named target assertion before a task is runnable with a live agent.

## SystemProfile

The complete agent configuration being compared.

| Field | Type | Rules |
| --- | --- | --- |
| `profile_id` | string | stable human-readable ID |
| `harness` | enum | `fixture-reference`, `fixture-seeded-failure`, `codex`, `claude-code`, `command` |
| `model_id` | string | exact model ID or `fixture` |
| `command` | string array | trusted argv template; never passed through a shell |
| `instructions` | string | profile-specific visible instructions |
| `skills` | versioned string array | empty allowed |
| `mcps` | versioned string array | empty allowed |
| `tools` | versioned string array | exact allowed tool surface |
| `environment_keys` | string array | names only; secret values are never persisted |
| `time_limit_seconds` | integer | may reduce but not exceed task and CLI limits |
| `observable_cost_usd` | number or null | nonnegative; null means unavailable, not zero |
| `fingerprint` | SHA-256 | canonical profile without secret values |

## TrialResult

One attempt by one profile on one task revision.

| Field | Type | Rules |
| --- | --- | --- |
| `trial_id` | UUID | unique |
| `task_id` / `task_fingerprint` | strings | exact task revision |
| `profile_id` / `profile_fingerprint` | strings | exact system revision |
| `attempt` | integer | one-based within task/profile |
| `state` | enum | `passed`, `failed`, `error`, `timeout`, `unrun` |
| `started_at` / `finished_at` | UTC timestamps | monotonic ordering required |
| `duration_seconds` | number | nonnegative |
| `exit_code` | integer or null | null for fixture or unstarted trials |
| `transcript_path` | relative path | raw stdout/stderr or structured event log |
| `artifact_manifest` | Artifact array | every final regular file |
| `grades` | GradeResult array | ordered by required grade sequence |
| `error` | object or null | typed category and exact message |
| `observable_cost_usd` | number or null | unavailable remains null |

State transition: `created -> running -> passed|failed|error|timeout`. A dependency or isolation
preflight may transition `created -> unrun`. Final states are immutable.

## Artifact

| Field | Type | Rules |
| --- | --- | --- |
| `path` | string | workspace-relative POSIX path; no traversal |
| `sha256` | string | lowercase full digest |
| `size_bytes` | integer | nonnegative |
| `media_type` | string | inferred only for display; does not affect grading |

## GradeResult

| Field | Type | Rules |
| --- | --- | --- |
| `grade_id` | string | unique within the task |
| `category` | enum | `structural`, `file-format`, `compile`, `simulator-load`, `static`, `behavior` |
| `status` | enum | `pass`, `fail`, `error`, `unrun` |
| `assertion` | string | exact machine-checkable claim |
| `artifact_digests` | string array | artifacts actually inspected |
| `parameters` | object | canonical grader inputs and thresholds |
| `observed` | object | measured values, not conclusions alone |
| `raw_output` | string | bounded raw diagnostic text |
| `duration_seconds` | number | nonnegative |
| `grader_fingerprint` | SHA-256 | grader source plus protected configuration |

A required `fail` makes the trial `failed`; `error` makes it `error`; an executed grade cannot be
satisfied by a profile transcript or stored flag.

## EvidenceBundle

A directory containing `manifest.json`, normalized task/profile snapshots, trial subdirectories,
transcripts, final artifacts, grade payloads, and raw simulator output.

The bundle fingerprint covers every manifest entry. Replay runs deterministic graders against the
saved outcome and writes a separate replay record; it never overwrites the original result.

## Comparison

| Field | Type | Rules |
| --- | --- | --- |
| `comparison_id` | UUID | unique |
| `left_profile` / `right_profile` | fingerprints | complete system profiles |
| `task_fingerprints` | string array | exact shared task set |
| `trial_rows` | object array | every task and attempt before aggregates |
| `pass_rate` | per-profile number | passed / executed trials; unrun reported separately |
| `pass_at_1` | per-profile number | tasks with at least one pass on first attempt |
| `pass_power_3` | per-profile number | tasks passing all first three attempts |
| `regressions` / `improvements` | task ID arrays | hard task transitions only |
| `runtime` / `cost` | per-profile values | null cost remains unavailable |

No composite score is part of the POC.
