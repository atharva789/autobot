"""Structural diff `D(a, b)` — contracts/eval-contract.md, used by G2 and G3.

Implements the formula exactly:

    D(a, b) = 0.40 * jaccard_distance(term_names(a),        term_names(b))
            + 0.25 * jaccard_distance(symbol_set(a),        symbol_set(b))
            + 0.20 * jaccard_distance(termination_causes(a), termination_causes(b))
            + 0.15 * normalized_weight_distance(a, b)

The coefficients (0.40/0.25/0.20/0.15) and the four component names are the contract's numbers,
not a local choice -- do not change them without a human-reviewed contract version bump (the same
rule g1.py follows for its 0.80 threshold).

Two points the contract states the *name* of but not a formula for; both are implementation
decisions made here, and called out so a human reviewing this can see exactly what was decided:

- `jaccard_distance` on two empty sets is defined as 0.0 (two scaffolds with no reward terms at
  all are not "maximally different" from each other; they are identical in that respect, and
  TrainingScaffold's own invariant already forbids zero reward terms/terminations in practice --
  see scaffold.py -- so this only matters for symbol_set(), which can still be legitimately empty
  in isolation e.g. a scaffold whose only symbols are unresolvable consts filtered elsewhere).
- `normalized_weight_distance` compares weights of reward terms with the same `name` present in
  both scaffolds (the contract's own words: "weights of terms present in both"). When there are no
  common term names, there is nothing to compare -- this returns 1.0 (maximal), not 0.0, because
  "no comparable terms" is itself evidence of structural divergence, not similarity, and D must
  not silently score a fully-disjoint scaffold pair as agreeing on weights it doesn't share.
"""

from __future__ import annotations

from packages.research.loop_research.scaffold import TrainingScaffold

# eval-contract.md's coefficients. Do not change without a contract version bump + human review.
_W_TERM_NAMES = 0.40
_W_SYMBOL_SET = 0.25
_W_TERMINATION_CAUSES = 0.20
_W_WEIGHT_DISTANCE = 0.15


def term_names(scaffold: TrainingScaffold) -> frozenset[str]:
    return frozenset(t.name for t in scaffold.reward_terms)


def symbol_set(scaffold: TrainingScaffold) -> frozenset[str]:
    """Union of every symbol referenced by any reward term or termination.

    Both contribute: a scaffold that keeps the same reward terms but rewires its terminations to
    different schema entities has changed structurally, and D must see that.
    """

    reward_symbols = {s for term in scaffold.reward_terms for s in term.symbols}
    termination_symbols = {s for term in scaffold.terminations for s in term.symbols}
    return frozenset(reward_symbols | termination_symbols)


def termination_causes(scaffold: TrainingScaffold) -> frozenset[str]:
    return frozenset(t.cause_label for t in scaffold.terminations)


def jaccard_distance(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)


def normalized_weight_distance(a: TrainingScaffold, b: TrainingScaffold) -> float:
    weights_a = {t.name: t.weight for t in a.reward_terms}
    weights_b = {t.name: t.weight for t in b.reward_terms}
    common = set(weights_a) & set(weights_b)
    if not common:
        return 1.0
    total_abs_diff = sum(abs(weights_a[name] - weights_b[name]) for name in common)
    return min(1.0, total_abs_diff / len(common))


def structural_diff(a: TrainingScaffold, b: TrainingScaffold) -> float:
    """`D(a, b)` per eval-contract.md. Symmetric; `D(a, a) == 0.0`; `D(a, b) in [0, 1]`."""

    d = (
        _W_TERM_NAMES * jaccard_distance(term_names(a), term_names(b))
        + _W_SYMBOL_SET * jaccard_distance(symbol_set(a), symbol_set(b))
        + _W_TERMINATION_CAUSES * jaccard_distance(termination_causes(a), termination_causes(b))
        + _W_WEIGHT_DISTANCE * normalized_weight_distance(a, b)
    )
    # Each component is already in [0, 1] and the coefficients sum to 1.0, so this can never
    # exceed 1 -- the clamp is a defensive assertion of that invariant, not a correction.
    return max(0.0, min(1.0, d))


__all__ = [
    "term_names",
    "symbol_set",
    "termination_causes",
    "jaccard_distance",
    "normalized_weight_distance",
    "structural_diff",
]
