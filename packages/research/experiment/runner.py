"""Experiment runner: orchestrates strategy, benchmark, and storage."""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Any

from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.research.benchmark.harness import evaluate_designs
from packages.research.benchmark.metrics import MetricsReport
from packages.research.experiment.types import (
    Experiment,
    ExperimentRun,
    ReproEnvelope,
    TestPrompt,
    TestPromptLabel,
)
from packages.research.prompts.registry import PromptRegistry
from packages.research.storage.store import SQLiteStore
from packages.research.strategy.protocol import StrategyConfig
from packages.research.strategy.registry import get_strategy


class ExperimentRunner:
    """Runs a strategy, benchmarks results, and persists everything."""

    def __init__(self, store: SQLiteStore | None = None) -> None:
        self._store = store or SQLiteStore()

    @property
    def store(self) -> SQLiteStore:
        return self._store

    def run(
        self,
        prompt: str,
        strategy_name: str,
        experiment_name: str,
        seed: int = 42,
        model_id: str = "gpt-4.1-mini",
        max_candidates: int = 6,
        extra: dict[str, Any] | None = None,
        prompt_label: TestPromptLabel | None = None,
    ) -> ExperimentRun:
        strategy = get_strategy(strategy_name)
        prompts = PromptRegistry()

        config = StrategyConfig(
            seed=seed,
            model_id=model_id,
            max_candidates=max_candidates,
            prompt_registry=prompts,
            extra=extra or {},
        )

        experiment = self._ensure_experiment(experiment_name)
        run_id = str(uuid.uuid4())[:8]
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        repro = ReproEnvelope(
            seed=seed,
            model_id=model_id,
            prompt_hash=prompt_hash,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            prompt_template_hashes=prompts.all_hashes(),
        )

        started_at = datetime.now(timezone.utc)
        error: str | None = None
        langsmith_trace_id: str | None = None
        designs: list[RobotDesignIR] = []
        metrics: MetricsReport | None = None

        start_wall = time.monotonic()
        try:
            designs = strategy.generate(prompt, config)
            last_state = getattr(strategy, "last_state", None)
            if isinstance(last_state, dict):
                trace_id = last_state.get("langsmith_trace_id")
                if isinstance(trace_id, str):
                    langsmith_trace_id = trace_id
        except Exception as exc:
            error = str(exc)

        wall_time = time.monotonic() - start_wall

        if designs and error is None:
            metrics = evaluate_designs(
                designs, wall_time_seconds=wall_time
            )

        finished_at = datetime.now(timezone.utc)

        run = ExperimentRun(
            run_id=run_id,
            experiment_id=experiment.experiment_id,
            strategy_name=strategy.name,
            prompt=prompt,
            config=config,
            repro=repro,
            started_at=started_at,
            finished_at=finished_at,
            designs=tuple(designs),
            metrics_report=metrics,
            error=error,
            prompt_label=prompt_label,
            langsmith_trace_id=langsmith_trace_id,
        )

        self._store.save_run(run)
        if designs:
            self._store.save_designs(run_id, designs)
        if metrics:
            self._store.save_metrics(run_id, metrics)

        return run

    def run_test_prompt(
        self,
        test_prompt: TestPrompt,
        *,
        strategy_name: str,
        experiment_name: str,
        seed: int = 42,
        model_id: str = "gpt-4.1-mini",
        max_candidates: int = 6,
        extra: dict[str, Any] | None = None,
    ) -> ExperimentRun:
        return self.run(
            prompt=test_prompt["prompt"],
            strategy_name=strategy_name,
            experiment_name=experiment_name,
            seed=seed,
            model_id=model_id,
            max_candidates=max_candidates,
            extra=extra,
            prompt_label=test_prompt["label"],
        )

    def run_suite(
        self,
        *,
        test_prompts: Sequence[TestPrompt],
        strategy_names: Sequence[str],
        experiment_name: str,
        seed: int = 42,
        model_id: str = "gpt-4.1-mini",
        max_candidates: int = 6,
        extra: dict[str, Any] | None = None,
    ) -> list[ExperimentRun]:
        runs: list[ExperimentRun] = []
        for test_prompt in test_prompts:
            self._store.save_test_prompt(test_prompt)
            for strategy_name in strategy_names:
                runs.append(
                    self.run_test_prompt(
                        test_prompt,
                        strategy_name=strategy_name,
                        experiment_name=experiment_name,
                        seed=seed,
                        model_id=model_id,
                        max_candidates=max_candidates,
                        extra=extra,
                    )
                )
        return runs

    def _ensure_experiment(self, name: str) -> Experiment:
        existing = self._store.find_experiment_by_name(name)
        if existing is not None:
            return existing

        experiment = Experiment(
            experiment_id=str(uuid.uuid4())[:8],
            name=name,
        )
        self._store.save_experiment(experiment)
        return experiment
