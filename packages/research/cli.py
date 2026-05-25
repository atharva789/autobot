"""CLI entry point for the research experimentation layer."""

from __future__ import annotations

import dataclasses
import json

import click

from packages.research.experiment.comparison import (
    compare_runs,
    compare_runs_by_prompt_label,
    format_comparison_table,
    format_grouped_comparison_tables,
)
from packages.research.experiment.runner import ExperimentRunner
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


if __name__ == "__main__":
    cli()
