"""
Candidate ranking for simulation results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.pipeline.simulation.candidate import DesignCandidate


def rank_candidates(candidates: list["DesignCandidate"]) -> list["DesignCandidate"]:
    """
    Rank candidates by their screening scores.

    Args:
        candidates: List of design candidates with screening results

    Returns:
        Sorted list with highest scores first, ranks assigned
    """
    # Sort by score descending
    sorted_candidates = sorted(
        candidates,
        key=lambda c: c.score,
        reverse=True,
    )

    # Assign ranks
    for i, candidate in enumerate(sorted_candidates):
        candidate.rank = i + 1

    return sorted_candidates
