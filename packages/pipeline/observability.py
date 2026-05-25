"""Optional LangSmith observability helpers for pipeline code."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class _NoopObservation:
    trace_id: str | None = None
    id: str | None = None

    def update(self, **_kwargs: Any) -> None:
        return None

    def end(self) -> None:
        return None


class _LangSmithObservation:
    def __init__(self, run: Any) -> None:
        self._run = run
        self.trace_id = str(getattr(run, "trace_id", "") or "") or None
        self.id = str(getattr(run, "id", "") or "") or None

    def update(
        self,
        *,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        level: str | None = None,
        status_message: str | None = None,
        **_kwargs: Any,
    ) -> None:
        if output is not None:
            self._run.add_outputs(output if isinstance(output, dict) else {"output": output})
        merged_metadata = dict(metadata or {})
        if level is not None:
            merged_metadata["level"] = level
        if status_message is not None:
            merged_metadata["status_message"] = status_message
        if merged_metadata:
            self._run.add_metadata(merged_metadata)

    def end(self) -> None:
        return None


def _format_exception_status(name: str, exc: BaseException) -> str:
    message = str(exc).strip()
    if not message:
        message = repr(exc)
    return f"{name} failed with {exc.__class__.__name__}: {message}"


def _mark_observation_failed(
    observation: Any,
    name: str,
    exc: BaseException,
    metadata: dict[str, Any] | None,
) -> None:
    try:
        error_payload = {
            "error_type": exc.__class__.__name__,
            "error_message": str(exc) or repr(exc),
        }
        observation.update(
            level="ERROR",
            status_message=_format_exception_status(name, exc),
            output={"error": error_payload},
            metadata={
                **(metadata or {}),
                **error_payload,
            },
        )
    except Exception:
        logger.debug("Failed to mark LangSmith observation as failed.", exc_info=True)


def _langsmith_enabled() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    load_dotenv(override=False)
    if os.environ.get("LANGSMITH_ENABLED", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    return bool(os.environ.get("LANGSMITH_API_KEY"))


def langsmith_enabled() -> bool:
    return _langsmith_enabled()


@contextmanager
def langsmith_trace_context() -> Iterator[None]:
    if _langsmith_enabled():
        yield
        return
    try:
        from langsmith.run_helpers import tracing_context

        with tracing_context(enabled=False):
            yield
    except Exception:
        yield


def get_langsmith_trace_id() -> str | None:
    if not _langsmith_enabled():
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree

        run = get_current_run_tree()
        return str(run.trace_id) if run is not None and run.trace_id else None
    except Exception:
        return None


def _run_type(as_type: str) -> str:
    if as_type == "tool":
        return "tool"
    if as_type in {"llm", "retriever", "embedding", "prompt", "parser"}:
        return as_type
    return "chain"


@contextmanager
def langsmith_observation(
    name: str,
    *,
    as_type: str = "span",
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    if not _langsmith_enabled():
        yield _NoopObservation()
        return

    try:
        from langsmith.run_helpers import trace

        os.environ.setdefault("LANGSMITH_TRACING", "true")
        kwargs: dict[str, Any] = {
            "name": name,
            "run_type": _run_type(as_type),
        }
        if input is not None:
            kwargs["inputs"] = {"input": input}
        if metadata is not None:
            kwargs["metadata"] = metadata
        observation_context = trace(**kwargs)
        run = observation_context.__enter__()
        observation = _LangSmithObservation(run)
    except Exception:
        logger.debug("LangSmith observation disabled after instrumentation error.", exc_info=True)
        yield _NoopObservation()
        return

    exc_info = (None, None, None)
    try:
        try:
            yield observation
        except Exception as exc:
            exc_info = sys.exc_info()
            _mark_observation_failed(observation, name, exc, metadata)
            raise
    finally:
        try:
            observation_context.__exit__(*exc_info)
        except Exception:
            logger.debug("LangSmith observation finalization failed.", exc_info=True)
