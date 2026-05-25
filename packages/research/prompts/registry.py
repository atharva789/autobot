"""Versioned prompt template loading and rendering."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PromptTemplate:
    """An immutable, content-hashed prompt template."""

    name: str
    version: str
    template: str
    variables: tuple[str, ...]
    sha256: str


_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptRegistry:
    """Load, hash, and render YAML prompt templates."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._dir = templates_dir or _DEFAULT_TEMPLATES_DIR
        self._cache: dict[str, PromptTemplate] = {}

    @property
    def templates_dir(self) -> Path:
        return self._dir

    def load(self, name: str) -> PromptTemplate:
        cached = self._cache.get(name)
        if cached is not None:
            return cached

        path = self._dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")

        raw = yaml.safe_load(path.read_text())
        content = str(raw["template"])
        tpl = PromptTemplate(
            name=name,
            version=str(raw.get("version", "0.1.0")),
            template=content,
            variables=tuple(raw.get("variables", [])),
            sha256=hashlib.sha256(content.encode()).hexdigest(),
        )
        self._cache[name] = tpl
        return tpl

    def render(self, name: str, **kwargs: str) -> str:
        tpl = self.load(name)
        return tpl.template.format(**kwargs)

    def all_hashes(self) -> dict[str, str]:
        return {k: v.sha256 for k, v in self._cache.items()}

    def list_templates(self) -> list[str]:
        return sorted(
            p.stem for p in self._dir.glob("*.yaml") if p.is_file()
        )
