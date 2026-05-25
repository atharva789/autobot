"""Diversity metrics for robot design batches."""

from __future__ import annotations

import math
from collections import Counter

from packages.pipeline.ir.design_ir import RobotDesignIR


def shannon_entropy(counts: Counter[int]) -> float:
    """Compute Shannon entropy from a Counter of integer values."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def link_count_entropy(designs: list[RobotDesignIR]) -> float:
    counts = Counter(len(d.links) for d in designs)
    return shannon_entropy(counts)


def joint_count_entropy(designs: list[RobotDesignIR]) -> float:
    counts = Counter(len(d.joints) for d in designs)
    return shannon_entropy(counts)


def pairwise_structural_distance(
    a: RobotDesignIR,
    b: RobotDesignIR,
) -> float:
    """Simple structural distance based on link/joint count differences
    and name overlap. Returns 0.0 for identical structures, higher for more different."""
    link_names_a = {link.name for link in a.links}
    link_names_b = {link.name for link in b.links}

    if not link_names_a and not link_names_b:
        return 0.0

    union = link_names_a | link_names_b
    intersection = link_names_a & link_names_b
    jaccard = 1.0 - (len(intersection) / len(union)) if union else 0.0

    count_diff = abs(len(a.links) - len(b.links)) + abs(
        len(a.joints) - len(b.joints)
    )
    count_norm = count_diff / max(
        len(a.links) + len(a.joints),
        len(b.links) + len(b.joints),
        1,
    )

    return (jaccard + count_norm) / 2.0


def mean_pairwise_distance(designs: list[RobotDesignIR]) -> float:
    """Average pairwise structural distance across all design pairs."""
    n = len(designs)
    if n < 2:
        return 0.0

    total = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += pairwise_structural_distance(designs[i], designs[j])
            pairs += 1

    return total / pairs if pairs > 0 else 0.0
