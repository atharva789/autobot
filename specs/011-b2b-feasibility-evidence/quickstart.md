# Quickstart: Agentic Robot Design Evals POC

This guide is executable after `tasks.md` is implemented. Use the repository `.venv`; `uv run`
currently fails dependency resolution because the unconstrained Python compatibility range makes its
solver consider an unsupported future Pink combination.

## 1. Preflight

```bash
.venv/bin/python -c "import mujoco; print(mujoco.__version__)"
command -v sandbox-exec
command -v codex
```

Python, MuJoCo, and `sandbox-exec` are required. Codex is the optional live executor; absence must be
reported as `unrun`, not replaced with a fixture.

## 2. List and validate protected tasks

```bash
.venv/bin/python -m packages.research.cli eval-tasks-list --suite evals/robot_design
.venv/bin/python -m packages.research.cli eval-verify-suite --suite evals/robot_design
```

Expected result: six tasks. Every reference passes. Every seeded failure fails its declared target
grade. No protected path is printed.

## 3. Prove the isolation boundary

```bash
.venv/bin/python -m pytest tests/test_agent_evals.py -k isolation -v
```

Expected result: a child command reads and writes its temporary workspace but receives a permission
error when attempting to read a sentinel under the repository root.

## 4. Run deterministic profiles

```bash
.venv/bin/python -m packages.research.cli eval-run-suite \
  --suite evals/robot_design \
  --profile reference \
  --profile seeded-failure \
  --output .runs/agent_evals/deterministic
```

Expected result: reference passes 6/6. Seeded failure fails 6/6 at the declared target assertions.
Each trial includes final artifacts, digests, raw grades, MuJoCo output where applicable, and a
manifest.

## 5. Replay deterministic evidence

```bash
.venv/bin/python -m packages.research.cli eval-replay \
  --run-root .runs/agent_evals/deterministic \
  --repeat 3 \
  --assert-identical
```

Normalized grade payloads must be identical and original evidence must remain unchanged.

## 6. Run controlled live-agent profiles

```bash
.venv/bin/python -m packages.research.cli eval-run-suite \
  --suite evals/robot_design \
  --profile codex-baseline \
  --profile codex-robotics-context \
  --trials 3 \
  --output .runs/agent_evals/live
```

The exact Codex executable and model stay fixed; only the public robotics instructions differ.
Authentication, executable, or isolation failures remain explicit.

## 7. Compare complete profiles

```bash
.venv/bin/python -m packages.research.cli eval-compare \
  --run-root .runs/agent_evals/live \
  --profiles codex-baseline,codex-robotics-context \
  --output .runs/agent_evals/live/comparison.json
```

Inspect task and trial rows before aggregates. A failed hard constraint remains failed.

## 8. Run the strongest substitute

```bash
.venv/bin/python evals/robot_design/control.py --help
```

Use the same public tasks and frozen outcomes. Record implementation size, setup effort, caught
failures, missing evidence, and reproduction effort in `poc-results.md`. The engine is not defensible
merely because the full runner has more features.

## 9. Focused verification

```bash
.venv/bin/python -m pytest tests/test_agent_evals.py -v
```
