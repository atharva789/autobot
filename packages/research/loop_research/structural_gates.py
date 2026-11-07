"""G2 (ablation) and G3 (divergence) — contracts/eval-contract.md, build-order step 5.

Both gates reduce to the same comparison: "did the scaffold change enough". G2 compares a
scaffold against itself re-run on a permuted schema (packages/research/loop_research/permutations.py's
four classes); G3 compares two scaffolds from structurally different schemas for the same task.
Neither gate does anything model-specific -- they take whatever scaffold a loop (real or the
static_scaffold_loop control) actually produced and score it.
"""

from __future__ import annotations

from packages.research.loop_research.scaffold import GateResult, TrainingScaffold
from packages.research.loop_research.structural_diff import structural_diff, symbol_set


def _dof_removed_hard_check(mutant: TrainingScaffold, deleted_joint: str) -> tuple[bool, list[str]]:
    """eval-contract.md G2: 'dof_removed additionally requires a hard check: no surviving symbol
    may reference the deleted joint. A scaffold citing a joint that no longer exists fails G2
    outright regardless of D.'"""

    prefix = f"joint.{deleted_joint}"
    offending = sorted(
        s for s in symbol_set(mutant) if s == prefix or s.startswith(prefix + ".")
    )
    return not offending, offending


def run_g2(
    original: TrainingScaffold,
    mutant: TrainingScaffold,
    *,
    permutation_class: str,
    tau: float,
    deleted_joint: str | None = None,
) -> GateResult:
    d = structural_diff(original, mutant)
    passed = d > tau

    detail = {
        "permutation": permutation_class,
        "structural_diff": round(d, 4),
        "tau": round(tau, 4),
        "original_scaffold_id": original.scaffold_id,
        "mutant_scaffold_id": mutant.scaffold_id,
    }

    if permutation_class == "dof_removed":
        if deleted_joint is None:
            raise ValueError("dof_removed's hard check needs deleted_joint")
        hard_check_passed, offending = _dof_removed_hard_check(mutant, deleted_joint)
        detail["dof_removed_hard_check"] = {
            "deleted_joint": deleted_joint,
            "offending_symbols": offending,
            "passed": hard_check_passed,
        }
        passed = passed and hard_check_passed

    return GateResult(
        gate="G2",
        scaffold_id=mutant.scaffold_id,
        passed=passed,
        score=round(d, 4),
        threshold=round(tau, 4),
        detail=detail,
    )


def run_g3(scaffold_a: TrainingScaffold, scaffold_b: TrainingScaffold, *, tau: float) -> GateResult:
    d = structural_diff(scaffold_a, scaffold_b)
    passed = d > tau

    return GateResult(
        gate="G3",
        scaffold_id=scaffold_a.scaffold_id,
        passed=passed,
        score=round(d, 4),
        threshold=round(tau, 4),
        detail={
            "schema_a": scaffold_a.schema_id,
            "schema_b": scaffold_b.schema_id,
            "structural_diff": round(d, 4),
            "tau": round(tau, 4),
            "scaffold_a_id": scaffold_a.scaffold_id,
            "scaffold_b_id": scaffold_b.scaffold_id,
        },
    )


__all__ = ["run_g2", "run_g3"]
