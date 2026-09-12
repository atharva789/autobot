"""Safe compiler for TrainingScaffold reward/termination expressions.

Expressions in a TrainingScaffold come from an agent loop, not a developer, so they are treated as
untrusted: this module parses with `ast`, walks the tree against a strict whitelist, and rejects
anything outside it — no `eval()` of arbitrary source, no attribute access beyond a schema symbol's
own dotted path, no calls except the small numeric whitelist. Compilation is rejected, not
sandboxed, for anything else.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable, Protocol

from packages.research.loop_research.symbols import SymbolSyntaxError, parse_symbol


class ExpressionError(ValueError):
    """Raised when a scaffold expression is malformed or uses a disallowed construct."""


class EvalContext(Protocol):
    def resolve(self, symbol: str) -> float: ...


_ALLOWED_FUNCS: dict[str, Callable[..., float]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "clamp": lambda x, lo, hi: min(max(x, lo), hi),
}

_BINOPS: dict[type, Callable[[float, float], float]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Mod: lambda a, b: a % b,
}

_UNARY: dict[type, Callable[[float], float]] = {
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: a,
    ast.Not: lambda a: not a,
}

_CMP: dict[type, Callable[[float, float], bool]] = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


@dataclass(frozen=True)
class CompiledExpression:
    source: str
    symbols: tuple[str, ...]
    _tree: ast.Expression

    def __call__(self, ctx: EvalContext) -> float:
        return _eval(self._tree.body, ctx)


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def compile_expression(source: str, *, declared_symbols: tuple[str, ...] = ()) -> CompiledExpression:
    """Parse and validate `source`; raises ExpressionError on anything not whitelisted."""

    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Could not parse expression {source!r}: {exc}") from exc

    found_symbols: set[str] = set()
    _validate(tree.body, found_symbols)

    if declared_symbols:
        undeclared = found_symbols - set(declared_symbols)
        if undeclared:
            raise ExpressionError(
                f"Expression {source!r} references symbols not declared in `symbols`: "
                f"{sorted(undeclared)}"
            )

    return CompiledExpression(source=source, symbols=tuple(sorted(found_symbols)), _tree=tree)


def _validate(node: ast.AST, found_symbols: set[str]) -> None:
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _validate(value, found_symbols)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise ExpressionError(f"Operator {type(node.op).__name__} is not allowed")
        _validate(node.left, found_symbols)
        _validate(node.right, found_symbols)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise ExpressionError(f"Unary operator {type(node.op).__name__} is not allowed")
        _validate(node.operand, found_symbols)
        return
    if isinstance(node, ast.Compare):
        _validate(node.left, found_symbols)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in _CMP:
                raise ExpressionError(f"Comparator {type(op).__name__} is not allowed")
            _validate(comparator, found_symbols)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            allowed = ", ".join(sorted(_ALLOWED_FUNCS))
            raise ExpressionError(f"Only whitelisted functions may be called: {allowed}")
        if node.keywords:
            raise ExpressionError("Keyword arguments are not allowed in scaffold expressions")
        for arg in node.args:
            _validate(arg, found_symbols)
        return
    if isinstance(node, (ast.Attribute, ast.Name)):
        dotted = _dotted_name(node)
        if dotted is None or any(part.startswith("_") for part in dotted.split(".")):
            raise ExpressionError("Malformed or disallowed symbol reference")
        try:
            parse_symbol(dotted)
        except SymbolSyntaxError as exc:
            raise ExpressionError(str(exc)) from exc
        found_symbols.add(dotted)
        return
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or isinstance(node.value, (int, float)):
            return
        raise ExpressionError("Only numeric constants are allowed in scaffold expressions")
    raise ExpressionError(f"{type(node).__name__} is not allowed in a scaffold expression")


def _eval(node: ast.AST, ctx: EvalContext):
    if isinstance(node, ast.BoolOp):
        values = [_eval(v, ctx) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.BinOp):
        return _BINOPS[type(node.op)](_eval(node.left, ctx), _eval(node.right, ctx))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, ctx))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, ctx)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        args = [_eval(a, ctx) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)  # type: ignore[union-attr]
    if isinstance(node, (ast.Attribute, ast.Name)):
        return ctx.resolve(_dotted_name(node))  # type: ignore[arg-type]
    if isinstance(node, ast.Constant):
        return node.value
    raise ExpressionError(f"{type(node).__name__} is not allowed in a scaffold expression")


__all__ = ["CompiledExpression", "EvalContext", "ExpressionError", "compile_expression"]
