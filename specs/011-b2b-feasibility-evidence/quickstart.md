# Quickstart: Agentic Robot Design Evals POC

This guide exercises the deterministic local POC and generic isolation probes. Use the repository `.venv`; `uv run`
currently fails dependency resolution because the unconstrained Python compatibility range makes its
solver consider an unsupported future Pink combination.

## 1. Preflight

```bash
.venv/bin/python -c "import mujoco; print(mujoco.__version__)"
command -v sandbox-exec
command -v codex
```

Python and MuJoCo are required. `sandbox-exec` is required for the generic local boundary probes, but
it is not a valid live Codex backend on this machine because nested sandboxing failed. Live trials
require a disposable VM or container; absence must be reported as `unrun`, not replaced with a fixture.

## 2. List and validate protected tasks

```bash
.venv/bin/python -m packages.research.cli eval-tasks-list --suite evals/robot_design
.venv/bin/python -m packages.research.cli eval-verify-suite --suite evals/robot_design
```

Expected result: six tasks. Every reference passes. Every seeded failure fails its declared target
grade. No protected path is printed.

## 3. Prove the isolation boundary

```bash
.venv/bin/python -m pytest tests/test_agent_evals.py -k "sandbox or isolation" -v
```

Expected result: a child command reads and writes its temporary workspace but receives a permission
error when attempting to read a sentinel under the repository root.

## 4. Run deterministic profiles

```bash
EVAL_QUICKSTART_ROOT="$(mktemp -d)"
.venv/bin/python -m packages.research.cli eval-run-suite \
  --suite evals/robot_design \
  --profile reference \
  --profile seeded-failure \
  --output "$EVAL_QUICKSTART_ROOT"
```

Expected result: reference passes 6/6. Seeded failure fails 6/6 at the declared target assertions.
Each trial includes final artifacts, digests, raw grades, MuJoCo output where applicable, and a
manifest.

## 5. Replay deterministic evidence

```bash
.venv/bin/python -m packages.research.cli eval-replay \
  --run-root "$EVAL_QUICKSTART_ROOT/reference/arm-reach-target" \
  --repeat 3 \
  --assert-identical
```

Normalized grade payloads must be identical and original evidence must remain unchanged.

## 6. Inspect the live-agent gate

```bash
.venv/bin/python -m json.tool .runs/agent_evals/live/unrun.json
```

The local live experiment is intentionally `unrun`: nested sandboxing fails and global skills
contaminate the empty profile. Run the 36-trial command only on a disposable worker with a disposable
credential and empty Codex home. Never substitute deterministic fixtures for this gate.

## 7. Compare complete profiles

```bash
.venv/bin/python -m packages.research.cli eval-compare \
  --run-root "$EVAL_QUICKSTART_ROOT" \
  --profiles reference,seeded-failure \
  --output "$EVAL_QUICKSTART_ROOT/comparison.json"
```

The command verifies every referenced snapshot, transcript, grade file, and artifact before loading
trial rows. Inspect task and trial rows plus their source revisions before aggregates. A failed hard
constraint remains failed.

## 8. Run the partial frozen-artifact control

```bash
.venv/bin/python evals/robot_design/control.py validate --suite evals/robot_design
.venv/bin/python evals/robot_design/control.py grade \
  --suite evals/robot_design \
  --task arm-reach-target \
  --artifacts evals/robot_design/protected/arm-reach-target/reference \
  > "$EVAL_QUICKSTART_ROOT/control-reference.json"
.venv/bin/python evals/robot_design/control.py replay \
  --record "$EVAL_QUICKSTART_ROOT/control-reference.json" \
  --repeat 3
```

Use the same public tasks and frozen outcomes. Record implementation size, setup effort, caught
failures, missing evidence, and reproduction effort in `poc-results.md`. The engine is not defensible
merely because the full runner has more features.

## 9. Focused verification

```bash
.venv/bin/python -m pytest tests/test_agent_evals.py -v
```
