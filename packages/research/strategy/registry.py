"""Strategy discovery and registration."""

from __future__ import annotations

from typing import Any

from packages.research.strategy.protocol import GenerationStrategy


_BUILTIN: dict[str, type] = {}


def _load_builtins() -> None:
    if _BUILTIN:
        return
    from packages.research.strategy.grammar_strategy import GrammarStrategy
    _BUILTIN["grammar"] = GrammarStrategy


def register_strategy(name: str, cls: type) -> None:
    _BUILTIN[name] = cls


def get_strategy(name: str, **kwargs: Any) -> GenerationStrategy:
    _load_builtins()
    cls = _BUILTIN.get(name)
    if cls is None:
        available = ", ".join(sorted(_BUILTIN.keys()))
        raise ValueError(
            f"Unknown strategy: {name!r}. Available: {available}"
        )
    return cls(**kwargs)


def list_strategies() -> list[str]:
    _load_builtins()
    return sorted(_BUILTIN.keys())
