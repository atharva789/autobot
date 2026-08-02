"""CLI entry point for the research experimentation layer."""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import click

from packages.research.experiment.comparison import (
    compare_runs,
    compare_runs_by_prompt_label,
    format_comparison_table,
    format_grouped_comparison_tables,
)
from packages.research.experiment.runner import ExperimentRunner
from packages.research.agent_evals import (
    atomic_write_json,
    capture_profile_execution,
    compare_profile_trials,
    EvidenceManifestError,
    finalize_evidence_bundle,
    load_profiles,
    load_suite,
    load_verified_evidence_manifest,
    profile_availability,
    replay_evidence_bundle,
    validate_task_oracles,
)
from packages.research.storage.store import SQLiteStore
from packages.research.strategy.registry import list_strategies


def _default_store() -> SQLiteStore:
    return SQLiteStore()


@click.group()
def cli() -> None:
    """Research experimentation CLI for robot generation strategies."""


@cli.command()
@click.argument("prompt")
@click.option("--strategy", "-s", required=True, help="Strategy name")
@click.option("--seed", type=int, default=42, help="Random seed")
@click.option("--model", default="gpt-4.1-mini", help="LLM model ID")
@click.option("--max-candidates", "-n", type=int, default=6, help="Designs to generate")
@click.option("--experiment", "-e", required=True, help="Experiment name")
@click.option("--max-attempts", type=int, default=2, help="Grammar loop max attempts")
def run(
    prompt: str,
    strategy: str,
    seed: int,
    model: str,
    max_candidates: int,
    experiment: str,
    max_attempts: int,
) -> None:
    """Run a generation strategy on a prompt."""
    runner = ExperimentRunner()
    click.echo(f"Running strategy={strategy} seed={seed} model={model} n={max_candidates}")
    click.echo(f"Prompt: {prompt[:80]}...")

    result = runner.run(
        prompt=prompt,
        strategy_name=strategy,
        experiment_name=experiment,
        seed=seed,
        model_id=model,
        max_candidates=max_candidates,
        extra={"max_attempts": max_attempts},
    )

    if result.error:
        click.secho(f"Error: {result.error}", fg="red")
    else:
        m = result.metrics_report
        click.secho(f"Run {result.run_id} complete", fg="green")
        if m:
            click.echo(f"  Designs: {m.total_designs}")
            click.echo(f"  Compile rate: {m.compile_rate:.0%}")
            click.echo(f"  Stability rate: {m.stability_rate:.0%}")
            click.echo(f"  Mean score: {m.mean_screening_score:.3f}")
            click.echo(f"  Wall time: {m.wall_time_seconds:.1f}s")


@cli.command("strategies")
def list_strategies_cmd() -> None:
    """List available generation strategies."""
    for name in list_strategies():
        click.echo(f"  - {name}")


@cli.command()
@click.argument("experiment_name")
@click.option("--group-by-label", is_flag=True, help="Group runs by TestPrompt label")
def show(experiment_name: str, group_by_label: bool) -> None:
    """Show runs and metrics for an experiment."""
    store = _default_store()
    exp = store.find_experiment_by_name(experiment_name)
    if exp is None:
        click.secho(f"Experiment not found: {experiment_name}", fg="red")
        return

    click.echo(f"Experiment: {exp.name} ({exp.experiment_id})")
    click.echo(f"Created: {exp.created_at.isoformat()}")

    runs = store.list_runs(exp.experiment_id)
    if not runs:
        click.echo("  No runs yet.")
        return

    click.echo(f"  {len(runs)} run(s):\n")
    if group_by_label:
        table = format_grouped_comparison_tables(compare_runs_by_prompt_label(runs, store))
    else:
        table = format_comparison_table(compare_runs(runs, store), include_label=True)
    click.echo(table)


@cli.command()
@click.argument("run_ids", nargs=-1, required=True)
def compare(run_ids: tuple[str, ...]) -> None:
    """Compare metrics across runs."""
    store = _default_store()
    runs = []
    for rid in run_ids:
        r = store.load_run(rid)
        if r is None:
            click.secho(f"Run not found: {rid}", fg="red")
            return
        runs.append(r)

    table = format_comparison_table(compare_runs(runs, store))
    click.echo(table)


@cli.command()
@click.argument("run_id")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def metrics(run_id: str, fmt: str) -> None:
    """Show detailed metrics for a run."""
    store = _default_store()
    report = store.load_run_metrics(run_id)
    if report is None:
        click.secho(f"No metrics found for run: {run_id}", fg="red")
        return

    if fmt == "json":
        click.echo(json.dumps(dataclasses.asdict(report), indent=2, default=str))
        return

    click.echo(f"Run: {run_id}")
    click.echo(f"Total designs: {report.total_designs}")
    click.echo(f"Compile rate: {report.compile_rate:.0%}")
    click.echo(f"Stability rate: {report.stability_rate:.0%}")
    click.echo(f"Mean screening score: {report.mean_screening_score:.3f}")
    click.echo(f"Median screening score: {report.median_screening_score:.3f}")
    click.echo(f"Link count entropy: {report.link_count_entropy:.2f}")
    click.echo(f"Joint count entropy: {report.joint_count_entropy:.2f}")
    click.echo(f"Wall time: {report.wall_time_seconds:.1f}s")
    click.echo(f"Morphology families: {report.morphology_families}")
    click.echo()

    for dm in report.per_design:
        status = "OK" if dm.mjcf_compiles else "FAIL"
        click.echo(
            f"  [{status}] {dm.design_name}: "
            f"score={dm.screening_score:.3f} "
            f"links={dm.link_count} joints={dm.joint_count} "
            f"stable={dm.zero_ctrl_stable}"
        )


@cli.command()
def experiments() -> None:
    """List all experiments."""
    store = _default_store()
    exps = store.list_experiments()
    if not exps:
        click.echo("No experiments yet.")
        return
    for exp in exps:
        n_runs = len(store.list_runs(exp.experiment_id))
        click.echo(f"  {exp.name} ({exp.experiment_id}) — {n_runs} run(s)")


@cli.command("eval-tasks-list")
@click.option("--suite", "suite_path", type=click.Path(path_type=str), required=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_tasks_list(suite_path: str, as_json: bool) -> None:
    """List public agentic-robotics task metadata."""

    try:
        suite = load_suite(Path(suite_path))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    rows = [
        {
            "task_id": task.manifest.task_id,
            "version": task.manifest.version,
            "family": task.manifest.family,
            "title": task.manifest.title,
            "fingerprint": task.fingerprint,
        }
        for task in suite.tasks
    ]
    if as_json:
        click.echo(json.dumps({"tasks": rows}, indent=2, sort_keys=True))
        return
    for row in rows:
        click.echo(
            f"{row['task_id']} v{row['version']} [{row['family']}] "
            f"{row['title']} {row['fingerprint'][:12]}"
        )


@cli.command("eval-profiles-list")
@click.option("--suite", "suite_path", type=click.Path(path_type=str), required=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_profiles_list(suite_path: str, as_json: bool) -> None:
    """List public system profiles and locally provable availability."""

    try:
        profiles = load_profiles(Path(suite_path))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    rows = []
    for profile in profiles:
        available, reason = profile_availability(profile)
        rows.append(
            {
                "profile_id": profile.profile_id,
                "harness": profile.harness,
                "model_id": profile.model_id,
                "skills": list(profile.skills),
                "mcps": list(profile.mcps),
                "tools": list(profile.tools),
                "fingerprint": profile.fingerprint,
                "available": available,
                "availability_reason": reason,
            }
        )
    if as_json:
        click.echo(json.dumps({"profiles": rows}, indent=2, sort_keys=True))
        return
    for row in rows:
        status = "available" if row["available"] else f"unavailable: {row['availability_reason']}"
        click.echo(
            f"{row['profile_id']} [{row['harness']}] {row['model_id']} {status} "
            f"{row['fingerprint'][:12]}"
        )


@cli.command("eval-verify-suite")
@click.option("--suite", "suite_path", type=click.Path(path_type=str), required=True)
@click.option("--task", "task_ids", multiple=True, help="Limit validation to task IDs")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_verify_suite(suite_path: str, task_ids: tuple[str, ...], as_json: bool) -> None:
    """Execute protected reference and seeded-failure oracle checks."""

    try:
        suite = load_suite(Path(suite_path))
        selected = [suite.task(task_id) for task_id in task_ids] if task_ids else list(suite.tasks)
        validations = [validate_task_oracles(task) for task in selected]
    except (KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    payload = {
        "task_count": len(validations),
        "reference_passes": sum(row.reference_state == "passed" for row in validations),
        "seeded_failures_caught": sum(
            row.seeded_failure_state == "failed" for row in validations
        ),
        "tasks": [
            {
                "task_id": row.task_id,
                "reference_state": row.reference_state,
                "seeded_failure_state": row.seeded_failure_state,
                "failed_grade_ids": list(row.failed_grade_ids),
            }
            for row in validations
        ],
    }
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    click.echo(
        f"Validated {payload['task_count']} tasks: "
        f"references={payload['reference_passes']} "
        f"seeded_failures={payload['seeded_failures_caught']}"
    )
    for row in payload["tasks"]:
        click.echo(
            f"  {row['task_id']}: reference={row['reference_state']} "
            f"seeded={row['seeded_failure_state']} "
            f"failed={','.join(row['failed_grade_ids'])}"
        )


def _profile_by_id(profiles, profile_id: str):
    for profile in profiles:
        if profile.profile_id == profile_id:
            return profile
    raise KeyError(f"unknown profile_id: {profile_id}")


def _execute_eval_outcomes(
    *,
    suite_path: Path,
    task_ids: tuple[str, ...],
    profile_ids: tuple[str, ...],
    trials: int | None,
    output: Path,
) -> list[dict[str, object]]:
    suite = load_suite(suite_path)
    profiles = load_profiles(suite_path)
    tasks = [suite.task(task_id) for task_id in task_ids] if task_ids else list(suite.tasks)
    selected_profiles = [_profile_by_id(profiles, profile_id) for profile_id in profile_ids]
    for task in tasks:
        validate_task_oracles(task)
    output.mkdir(parents=True, exist_ok=True)
    workspace_parent = Path(tempfile.gettempdir()) / "il-ideation-agent-eval-workspaces"
    workspace_parent.mkdir(parents=True, exist_ok=True)
    repository_root = Path(__file__).resolve().parents[2]
    rows: list[dict[str, object]] = []
    for profile in selected_profiles:
        attempt_count = trials if trials is not None else (
            1 if profile.harness.startswith("fixture-") else 3
        )
        for task in tasks:
            if profile.harness == "fixture-reference":
                source_dir = task.reference_dir
            elif profile.harness == "fixture-seeded-failure":
                source_dir = task.seeded_failure_dir
            else:
                source_dir = task.starter_dir
            captures = []
            for attempt in range(1, attempt_count + 1):
                evidence_dir = (
                    output
                    / profile.profile_id
                    / task.manifest.task_id
                    / f"attempt-{attempt:03d}"
                )
                prior_workspaces = tuple(path for path in workspace_parent.iterdir() if path.is_dir())
                capture = capture_profile_execution(
                    profile,
                    source_dir,
                    prompt=task.manifest.prompt,
                    workspace_parent=workspace_parent,
                    evidence_dir=evidence_dir,
                    denied_roots=(
                        repository_root,
                        suite.root / "protected",
                        output.resolve(),
                        *prior_workspaces,
                    ),
                )
                captures.append(capture)
            bundle_dir = output / profile.profile_id / task.manifest.task_id
            bundle = finalize_evidence_bundle(
                task,
                profile,
                tuple(captures),
                bundle_dir,
            )
            for capture, trial in zip(captures, bundle.trials, strict=True):
                rows.append(
                    {
                        "task_id": task.manifest.task_id,
                        "task_fingerprint": task.fingerprint,
                        "profile_id": profile.profile_id,
                        "profile_fingerprint": profile.fingerprint,
                        "attempt": trial.attempt,
                        "mode": capture.execution.mode,
                        "execution_state": capture.execution.state,
                        "state": trial.state,
                        "command": list(capture.execution.command),
                        "exit_code": trial.exit_code,
                        "duration_seconds": trial.duration_seconds,
                        "error": trial.error,
                        "evidence_dir": str(capture.evidence_dir),
                        "bundle_id": bundle.bundle_id,
                        "artifacts": [dataclasses.asdict(artifact) for artifact in trial.artifacts],
                        "grades": [dataclasses.asdict(grade) for grade in trial.grades],
                        "recovery_workspace_path": (
                            str(capture.recovery_workspace_path)
                            if capture.recovery_workspace_path is not None
                            else None
                        ),
                    }
                )
    return rows


def _emit_eval_outcomes(rows: list[dict[str, object]], *, as_json: bool) -> None:
    payload = {"execution_count": len(rows), "executions": rows}
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for row in rows:
        click.echo(
            f"{row['profile_id']} {row['task_id']} attempt={row['attempt']} "
            f"mode={row['mode']} state={row['state']}"
        )


def _eval_outcome_exit_code(rows: list[dict[str, object]], *, allow_unrun: bool) -> int:
    states = {str(row["state"]) for row in rows}
    if states & {"error", "timeout"}:
        return 5
    if "unrun" in states and not allow_unrun:
        return 4
    return 0


@cli.command("eval-run")
@click.option("--suite", "suite_path", type=click.Path(path_type=str), required=True)
@click.option("--task", "task_id", required=True)
@click.option("--profile", "profile_id", required=True)
@click.option("--trials", type=click.IntRange(min=1), default=None)
@click.option("--output", type=click.Path(path_type=str), required=True)
@click.option("--allow-unrun", is_flag=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_run(
    suite_path: str,
    task_id: str,
    profile_id: str,
    trials: int | None,
    output: str,
    allow_unrun: bool,
    as_json: bool,
) -> None:
    """Run isolated attempts for one task and complete system profile."""

    try:
        rows = _execute_eval_outcomes(
            suite_path=Path(suite_path),
            task_ids=(task_id,),
            profile_ids=(profile_id,),
            trials=trials,
            output=Path(output),
        )
    except (KeyError, OSError, ValueError) as exc:
        raise click.UsageError(str(exc)) from exc
    _emit_eval_outcomes(rows, as_json=as_json)
    exit_code = _eval_outcome_exit_code(rows, allow_unrun=allow_unrun)
    if exit_code:
        raise click.exceptions.Exit(exit_code)


@cli.command("eval-run-suite")
@click.option("--suite", "suite_path", type=click.Path(path_type=str), required=True)
@click.option("--profile", "profile_ids", multiple=True, required=True)
@click.option("--trials", type=click.IntRange(min=1), default=None)
@click.option("--output", type=click.Path(path_type=str), required=True)
@click.option("--allow-unrun", is_flag=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_run_suite(
    suite_path: str,
    profile_ids: tuple[str, ...],
    trials: int | None,
    output: str,
    allow_unrun: bool,
    as_json: bool,
) -> None:
    """Run every validated task serially for one or more profiles."""

    try:
        rows = _execute_eval_outcomes(
            suite_path=Path(suite_path),
            task_ids=(),
            profile_ids=profile_ids,
            trials=trials,
            output=Path(output),
        )
    except (KeyError, OSError, ValueError) as exc:
        raise click.UsageError(str(exc)) from exc
    _emit_eval_outcomes(rows, as_json=as_json)
    exit_code = _eval_outcome_exit_code(rows, allow_unrun=allow_unrun)
    if exit_code:
        raise click.exceptions.Exit(exit_code)


@cli.command("eval-replay")
@click.option("--run-root", type=click.Path(path_type=str), required=True)
@click.option("--repeat", type=click.IntRange(min=1), default=1, show_default=True)
@click.option("--assert-identical", is_flag=True)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_replay(
    run_root: str,
    repeat: int,
    assert_identical: bool,
    as_json: bool,
) -> None:
    """Replay protected graders against one immutable saved bundle."""

    try:
        replay = replay_evidence_bundle(Path(run_root), repeat=repeat)
    except (OSError, ValueError) as exc:
        raise click.UsageError(str(exc)) from exc
    payload = dataclasses.asdict(replay)
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        click.echo(
            f"Replay {replay.bundle_id}: state={replay.state} "
            f"identical={replay.identical} repeats={len(replay.repeat_digests)}"
        )
        for row in replay.drift:
            click.echo(
                f"  drift={row.get('category', 'unknown')} "
                f"message={row.get('message', '')}"
            )
    if replay.state != "passed" or (assert_identical and not replay.identical):
        raise click.exceptions.Exit(6)


def _load_saved_profile_trials(
    run_root: Path,
    profile_id: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    profile_root = run_root.resolve() / profile_id
    manifest_paths = sorted(profile_root.glob("*/manifest.json"))
    if not manifest_paths:
        raise ValueError(f"no saved bundles for profile: {profile_id}")
    profile_snapshot: dict[str, object] | None = None
    trials: list[dict[str, object]] = []
    for manifest_path in manifest_paths:
        try:
            manifest = load_verified_evidence_manifest(manifest_path.parent)
        except EvidenceManifestError:
            raise
        except (OSError, ValueError) as exc:
            raise ValueError(f"invalid saved bundle {manifest_path.parent}: {exc}") from exc
        candidate_profile = manifest.get("profile")
        if not isinstance(candidate_profile, dict):
            raise ValueError(f"bundle profile snapshot missing: {manifest_path}")
        if candidate_profile.get("profile_id") != profile_id:
            raise ValueError(f"bundle profile mismatch: {manifest_path}")
        if profile_snapshot is None:
            profile_snapshot = dict(candidate_profile)
        elif profile_snapshot != candidate_profile:
            raise ValueError(f"profile revision drift within saved bundles: {profile_id}")
        candidate_trials = manifest.get("trials")
        if not isinstance(candidate_trials, list):
            raise ValueError(f"bundle trials missing: {manifest_path}")
        environment_snapshot = manifest.get("environment")
        assert isinstance(environment_snapshot, dict)
        for trial in candidate_trials:
            if not isinstance(trial, dict):
                raise ValueError(f"bundle trial must be an object: {manifest_path}")
            saved_trial = dict(trial)
            saved_trial["bundle_id"] = manifest.get("bundle_id")
            saved_trial["environment_sha256"] = environment_snapshot.get("snapshot_sha256")
            trials.append(saved_trial)
    assert profile_snapshot is not None
    return profile_snapshot, trials


@cli.command("eval-compare")
@click.option("--run-root", type=click.Path(path_type=str), required=True)
@click.option("--profiles", required=True, help="Exactly two comma-separated profile IDs")
@click.option("--output", type=click.Path(path_type=str), default=None)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def eval_compare(
    run_root: str,
    profiles: str,
    output: str | None,
    as_json: bool,
) -> None:
    """Compare saved complete profiles with task/trial rows first."""

    profile_ids = tuple(part.strip() for part in profiles.split(",") if part.strip())
    if len(profile_ids) != 2 or profile_ids[0] == profile_ids[1]:
        raise click.UsageError("--profiles requires two distinct comma-separated IDs")
    try:
        left_profile, left_trials = _load_saved_profile_trials(
            Path(run_root), profile_ids[0]
        )
        right_profile, right_trials = _load_saved_profile_trials(
            Path(run_root), profile_ids[1]
        )
        comparison = compare_profile_trials(
            profile_ids[0],
            profile_ids[1],
            left_trials,
            right_trials,
            left_profile=left_profile,
            right_profile=right_profile,
        )
    except EvidenceManifestError as exc:
        raise click.UsageError(str(exc)) from exc
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise click.exceptions.Exit(7) from exc
    payload = dataclasses.asdict(comparison)
    if output is not None:
        atomic_write_json(Path(output), payload)
    if as_json:
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    click.echo(
        f"Comparison: {comparison.left_profile} -> {comparison.right_profile}"
    )
    for row in comparison.trial_rows:
        click.echo(
            f"{row['task_id']} attempt={row['attempt']} "
            f"left={row['left_state']} right={row['right_state']} "
            f"classification={row['classification']}"
        )
    click.echo("Aggregates:")
    click.echo(
        f"  left pass_rate={comparison.aggregates['left']['pass_rate']} "
        f"pass@1={comparison.aggregates['left']['pass_at_1']} "
        f"pass^3={comparison.aggregates['left']['pass_power_3']}"
    )
    click.echo(
        f"  right pass_rate={comparison.aggregates['right']['pass_rate']} "
        f"pass@1={comparison.aggregates['right']['pass_at_1']} "
        f"pass^3={comparison.aggregates['right']['pass_power_3']}"
    )
    click.echo(
        f"  improvements={','.join(comparison.aggregates['improvements']) or 'none'} "
        f"regressions={','.join(comparison.aggregates['regressions']) or 'none'} "
        f"sample_complete={comparison.aggregates['sample_complete']}"
    )


if __name__ == "__main__":
    cli()
