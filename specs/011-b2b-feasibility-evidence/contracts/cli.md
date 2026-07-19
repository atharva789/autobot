# CLI Contract

The executable entry point is:

```bash
.venv/bin/python -m packages.research.cli <eval-command>
```

Every command supports `--json`. Human output goes to stdout, diagnostics to stderr, and a nonzero
exit code indicates invalid input or incomplete required execution.

## `eval-tasks-list --suite SUITE`

Lists task ID, version, family, title, and validation state. It does not expose protected paths,
reference files, seeded failures, or grader code.

## `eval-verify-suite --suite SUITE [--task TASK_ID]`

Runs the reference and seeded-failure outcomes through protected graders. Exit 0 requires every
reference to pass and every seeded failure to fail its declared target assertion.

## `eval-profiles-list --suite SUITE`

Lists profile ID, harness, model ID, skills, MCPs, tools, and availability. Secret environment values
are never printed.

## `eval-run --suite SUITE --task TASK_ID --profile PROFILE_ID [--trials N] [--output DIR]`

Runs clean isolated attempts. Live nondeterministic profiles default to three trials. Fixture profiles
default to one. An unavailable dependency or isolation backend produces an `unrun` result and nonzero
exit unless `--allow-unrun` is supplied.

## `eval-run-suite --suite SUITE --profile PROFILE_ID... [--trials N] [--output DIR]`

Runs all validated tasks for each profile. Tasks execute serially in the POC to avoid cross-trial
resource and evidence ambiguity.

## `eval-replay --run-root BUNDLE_DIR [--repeat N] [--assert-identical]`

Re-runs deterministic graders against saved final artifacts. It checks task, grader, and artifact
fingerprints before execution and reports drift rather than replaying under mismatched inputs.

## `eval-compare --run-root DIR --profiles LEFT,RIGHT [--output PATH]`

Prints task/trial rows before pass rate, pass@1, pass^3, runtime, cost, improvements, and regressions.
`error`, `timeout`, and `unrun` remain explicit.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | requested work completed and contract checks passed |
| 2 | invalid CLI arguments or manifest |
| 3 | task validation failure |
| 4 | dependency or isolation unavailable |
| 5 | agent timeout or execution error |
| 6 | grading or replay error |
| 7 | comparison inputs are incompatible |
