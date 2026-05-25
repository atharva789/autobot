"""SQLite-backed registry for reusable synthetic test prompts."""

from __future__ import annotations

from collections.abc import Sequence

from packages.research.experiment.types import TestPrompt, TestPromptLabel
from packages.research.experiment.prompt_oracle import infer_expected_robo_grammar
from packages.research.storage.store import SQLiteStore


class TaskRegistry:
    """Tiny API for registering reusable prompt suites in the research DB."""

    def __init__(self, store: SQLiteStore | None = None) -> None:
        self._store = store or SQLiteStore()
        self._ensure_oracles()

    @property
    def store(self) -> SQLiteStore:
        return self._store

    def register(self, prompt: str, label: TestPromptLabel) -> TestPrompt:
        test_prompt: TestPrompt = {
            "prompt": prompt,
            "label": label,
            "expected_robo_grammar": infer_expected_robo_grammar(prompt, label),
        }
        return self._store.save_test_prompt(test_prompt)

    def register_many(self, prompts: Sequence[TestPrompt]) -> list[TestPrompt]:
        registered: list[TestPrompt] = []
        for test_prompt in prompts:
            registered.append(
                self.register(test_prompt["prompt"], test_prompt["label"])
            )
        return registered

    def list(self, label: TestPromptLabel | None = None) -> list[TestPrompt]:
        return self._store.list_test_prompts(label=label)

    def _ensure_oracles(self) -> None:
        for test_prompt in self._store.list_test_prompts():
            if test_prompt.get("expected_robo_grammar"):
                continue
            self._store.save_test_prompt(
                {
                    "prompt": test_prompt["prompt"],
                    "label": test_prompt["label"],
                    "expected_robo_grammar": infer_expected_robo_grammar(
                        test_prompt["prompt"],
                        test_prompt["label"],
                    ),
                }
            )
