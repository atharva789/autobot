"""τ — calibration, not choice (eval-contract.md).

    τ = D_control_max + 0.5 * (D_handwritten_min - D_control_max)

`D_control_max` is the largest structural diff the negative control produces across all G2/G3
comparisons; `D_handwritten_min` is the smallest diff between per-schema hand-written baselines.
τ is the midpoint between "a loop that definitely cheats" and "scaffolds a careful human wrote per
robot" -- derived from measured diffs, never hand-picked, and never edited here without a
human-reviewed contract version bump (routines/registry.md's hard limits).
"""

from __future__ import annotations


class TauUndefinedError(ValueError):
    """eval-contract.md: 'If D_handwritten_min <= D_control_max, tau does not exist and the diff
    function is broken.' That outcome halts the spec until D is redesigned -- it means the metric
    cannot distinguish cheating from genuine per-robot work, so no result gathered with it would
    mean anything. Raised, not silently clamped, so a caller cannot accidentally proceed past it.
    """


def derive_tau(d_control_max: float, d_handwritten_min: float) -> float:
    if d_handwritten_min <= d_control_max:
        raise TauUndefinedError(
            f"D_handwritten_min ({d_handwritten_min}) <= D_control_max ({d_control_max}): "
            "tau does not exist. The structural diff cannot separate the negative control from "
            "hand-written per-robot scaffolds, which means it cannot mean anything for a real "
            "loop's output either (eval-contract.md 'tau — calibration, not choice')."
        )
    return d_control_max + 0.5 * (d_handwritten_min - d_control_max)


__all__ = ["TauUndefinedError", "derive_tau"]
