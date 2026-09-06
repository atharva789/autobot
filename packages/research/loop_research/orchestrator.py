"""Compute-plane entrypoint — spec-012 build order step 6 (plan.md §7): "Actions workflow +
Compose stack, running steps 1-5 in CI. Gate: green run, logs committed."

This is the process the `orchestrator` Compose service (infra/loop-research/docker-compose.yml)
runs (`command: ["python", "-m", "packages.research.loop_research.orchestrator"]`), and what
`python -m packages.research.loop_research.orchestrator` runs directly for local/CI-less
verification. Its job today is exactly what step 6 asks for and no more: run everything build
order steps 1-5 already produced (`step2_run`, `step4_run`, `step5_run` — each already the
routine's own tested, committed evidence for its step) back to back in one process, and fail
loudly if any of them regresses.

It does not run the real loop. Step 7 (`scaffold_loop.py`/`step7_run.py`) exists now, but it runs
against the local `claude-code` CLI substitute provider (routines/registry.md "Local substitute
mode") -- there is no `claude` binary and no `OPENAI_API_KEY` inside this compute-plane container,
so nothing here could drive it yet. This module is where that call goes once a compute-plane-usable
provider exists (the pending `OPENAI_API_KEY` secret, plan.md §8); today it stays honest about not
making one rather than silently no-op-ing on a provider that was never configured for it.

`LOOP_RUN_ID` (env, or `--run-id`) is used verbatim as this run's directory name when supplied —
the workflow's "Commit the run log" step looks for `.runs/loop_research/$LOOP_RUN_ID` exactly, so
this must not append a suffix to a caller-supplied id the way a self-generated one does.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
import uuid
from pathlib import Path

from packages.research.loop_research import step2_run, step4_run, step5_run
from packages.research.loop_research.scaffold import ExperimentRun

_RUNS_ROOT = Path(".runs/loop_research")

_STEPS = (
    ("step2", step2_run.main),
    ("step4", step4_run.main),
    ("step5", step5_run.main),
)


def _git_sha() -> str:
    # Dockerfile.orchestrator copies only packages/research/loop_research and the dev schemas
    # into the image -- no .git directory -- so `git rev-parse HEAD` always fails inside the
    # container (verified by actually running this image). GIT_SHA, set from `github.sha` by the
    # workflow, is how the real sha reaches a containerized run instead of every run silently
    # recording "unknown".
    from_env = os.environ.get("GIT_SHA")
    if from_env:
        return from_env
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _existing_run_dirs() -> set[str]:
    if not _RUNS_ROOT.exists():
        return set()
    return {p.name for p in _RUNS_ROOT.iterdir() if p.is_dir()}


def run_pipeline() -> list[dict]:
    """Runs steps 1-5's committed evidence generators in sequence.

    Every step runs even if an earlier one fails or raises — mirrors the workflow's own
    `if: always()` gates step, so one broken step doesn't hide evidence about the others.
    Returns one result dict per step; nothing here raises.
    """

    results = []
    for name, step_main in _STEPS:
        before = _existing_run_dirs()
        try:
            exit_code = step_main()
            error = None
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            exit_code = 1
            error = repr(exc)
        new_dirs = sorted(_existing_run_dirs() - before)
        results.append(
            {
                "step": name,
                "exit_code": exit_code,
                "passed": exit_code == 0,
                "error": error,
                "run_dir": new_dirs[0] if new_dirs else None,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=os.environ.get("LOOP_RUN_ID"))
    args = parser.parse_args()

    manifest = os.environ.get("LOOP_MANIFEST")
    started = time.time()
    step_results = run_pipeline()
    wall_s = round(time.time() - started, 2)
    all_passed = all(r["passed"] for r in step_results)

    run_id = args.run_id or (
        time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime()) + f"_orchestrator_{uuid.uuid4().hex[:6]}"
    )
    run = ExperimentRun(
        run_id=run_id,
        git_sha=_git_sha(),
        trigger="routine",
        status="completed" if all_passed else "aborted_error",
        scaffolds=(),
        batches=(),
        gates=(),
        cost={
            "usd_total": 0.0,
            "usd_ceiling": 0.0,
            "ceiling_hit": False,
            "note": "orchestrator re-runs steps 1-5's own no-model-call generators; no OpenAI spend",
        },
        replay={"prompt_version": "n/a", "model_id": "n/a", "seed": 0},
        manifest_path=manifest,
        control={
            "orchestrator": {
                "wall_clock_s": wall_s,
                "all_passed": all_passed,
                "steps": step_results,
                "note": (
                    "step 7 (the real loop) is not implemented; this run exercises steps 1-5 only, "
                    "per build order step 6's own scope."
                ),
            }
        },
    )
    run_path = run.write(_RUNS_ROOT, [])

    print(f"run: {run_path}")
    for r in step_results:
        status = "PASS" if r["passed"] else "FAIL"
        detail = f" error={r['error']}" if r["error"] else ""
        print(f"{r['step']}: {status} (run_dir={r['run_dir']}){detail}")
    print(f"orchestrator: {'PASS' if all_passed else 'FAIL'} ({wall_s}s)")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
