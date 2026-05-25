from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from packages.pipeline import observability


def test_langsmith_observation_marks_application_exceptions(monkeypatch: pytest.MonkeyPatch):
    updates: list[dict[str, object]] = []
    exit_exception_types: list[type[BaseException] | None] = []

    class FakeObservation:
        trace_id = "trace-1"
        id = "run-1"

        def update(self, **kwargs: object) -> None:
            updates.append(kwargs)

        def add_outputs(self, outputs: dict[str, object]) -> None:
            updates.append({"output": outputs})

        def add_metadata(self, metadata: dict[str, object]) -> None:
            updates.append({"metadata": metadata})

    class FakeObservationContext:
        def __enter__(self) -> FakeObservation:
            return FakeObservation()

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            *_args: object,
        ) -> bool:
            exit_exception_types.append(exc_type)
            return False

    def fake_trace(**_kwargs: object) -> FakeObservationContext:
        return FakeObservationContext()

    monkeypatch.setattr(observability, "_langsmith_enabled", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "langsmith.run_helpers",
        SimpleNamespace(trace=fake_trace),
    )

    with pytest.raises(ValueError, match="missing structural_rules payload"):
        with observability.langsmith_observation(
            "resolve_grammar_node_names",
            metadata={"langgraph_node": "resolve_grammar_node_names"},
        ):
            raise ValueError("missing structural_rules payload")

    assert updates == [
        {
            "output": {
                "error": {
                    "error_type": "ValueError",
                    "error_message": "missing structural_rules payload",
                },
            },
        },
        {
            "metadata": {
                "langgraph_node": "resolve_grammar_node_names",
                "error_type": "ValueError",
                "error_message": "missing structural_rules payload",
                "level": "ERROR",
                "status_message": (
                    "resolve_grammar_node_names failed with ValueError: "
                    "missing structural_rules payload"
                ),
            },
        },
    ]
    assert exit_exception_types == [ValueError]
