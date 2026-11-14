"""Symbol grammar for TrainingScaffold expressions.

Spec: specs/012-schema-conditioned-policy-synthesis/data-model.md, "Symbol grammar".
A symbol is a dotted path `<kind>.<entity>[.<attr>...]` where `<kind>` is one of
joint, body, site, actuator, sensor, or the non-schema-resolvable `const`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SymbolKind = Literal["joint", "body", "site", "actuator", "sensor", "const"]

_ENTITY_KINDS: tuple[SymbolKind, ...] = ("joint", "body", "site", "actuator", "sensor", "const")
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_SYMBOL_RE = re.compile(rf"^({'|'.join(_ENTITY_KINDS)})\.({_IDENTIFIER})((?:\.{_IDENTIFIER})*)$")


class SymbolSyntaxError(ValueError):
    """Raised when a string is not a well-formed schema symbol."""


@dataclass(frozen=True)
class Symbol:
    text: str
    kind: SymbolKind
    entity: str
    attr_path: tuple[str, ...]


def parse_symbol(text: str) -> Symbol:
    match = _SYMBOL_RE.match(text)
    if not match:
        raise SymbolSyntaxError(f"Not a valid schema symbol: {text!r}")
    kind, entity, rest = match.groups()
    attr_path = tuple(part for part in rest.split(".") if part)
    return Symbol(text=text, kind=kind, entity=entity, attr_path=attr_path)  # type: ignore[arg-type]


def is_schema_resolvable(symbol: Symbol) -> bool:
    """const.* is a literal by design (data-model.md) and never schema-resolvable."""

    return symbol.kind != "const"


__all__ = ["Symbol", "SymbolKind", "SymbolSyntaxError", "parse_symbol", "is_schema_resolvable"]
