"""Strategy-agnostic design evaluation harness."""

from __future__ import annotations

import statistics

from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf
from packages.pipeline.ir.design_ir import RobotDesignIR
from packages.pipeline.simulation.mujoco_screening import screen_design
from packages.pipeline.simulation.validator import (
    validate_actuator_coverage,
    validate_design,
    validate_no_self_collision,
    validate_zero_control_stability,
)

from packages.research.benchmark.diversity import (
    joint_count_entropy,
    link_count_entropy,
)
from packages.research.benchmark.metrics import DesignMetrics, MetricsReport


def evaluate_single(ir: RobotDesignIR) -> DesignMetrics:
    """Evaluate a single design through the full MuJoCo pipeline.

    Degrades gracefully when MuJoCo is not installed — still reports
    IR validity and structural metrics.
    """
    validation = validate_design(ir)
    ir_errors = tuple(validation.errors)
    actuated = sum(1 for j in ir.joints if j.actuator is not None)
    total_joints = len(ir.joints)

    base = dict(
        design_name=ir.name,
        ir_valid=validation.is_valid,
        ir_errors=ir_errors,
        link_count=len(ir.links),
        joint_count=total_joints,
        actuated_joint_count=actuated,
        actuated_joint_ratio=actuated / total_joints if total_joints > 0 else 0.0,
    )

    if not validation.is_valid:
        return DesignMetrics(**base)

    try:
        mjcf_xml = compile_to_mjcf(ir)
    except (ValueError, Exception):
        return DesignMetrics(**base)

    try:
        screening = screen_design(ir)
        ok_actuator, _ = validate_actuator_coverage(mjcf_xml)
        ok_collision, _ = validate_no_self_collision(mjcf_xml)
        ok_stability, _ = validate_zero_control_stability(mjcf_xml)
    except (ImportError, ModuleNotFoundError):
        return DesignMetrics(**base, mjcf_compiles=True)

    return DesignMetrics(
        **base,
        mjcf_compiles=screening.mjcf_compiled,
        zero_ctrl_stable=ok_stability,
        actuator_coverage=ok_actuator,
        no_self_collision=ok_collision,
        screening_score=screening.overall_score,
        stability_score=screening.stability_score,
        reachability_score=screening.reachability_score,
        task_sanity_score=screening.task_sanity_score,
    )


def evaluate_designs(
    designs: list[RobotDesignIR],
    wall_time_seconds: float = 0.0,
    llm_calls: int = 0,
    estimated_cost_usd: float = 0.0,
) -> MetricsReport:
    """Evaluate a batch of designs and produce aggregate metrics."""
    per_design = tuple(evaluate_single(ir) for ir in designs)
    total = len(per_design)

    if total == 0:
        return MetricsReport()

    compiled = [d for d in per_design if d.mjcf_compiles]
    stable = [d for d in per_design if d.zero_ctrl_stable]
    scores = [d.screening_score for d in per_design]

    return MetricsReport(
        per_design=per_design,
        total_designs=total,
        compile_rate=len(compiled) / total,
        stability_rate=len(stable) / total,
        mean_screening_score=statistics.mean(scores),
        median_screening_score=statistics.median(scores),
        link_count_entropy=link_count_entropy(designs),
        joint_count_entropy=joint_count_entropy(designs),
        morphology_families=_count_families(designs),
        wall_time_seconds=wall_time_seconds,
        llm_calls=llm_calls,
        estimated_cost_usd=estimated_cost_usd,
    )


def _count_families(designs: list[RobotDesignIR]) -> dict[str, int]:
    """Heuristic morphology classification based on link structure."""
    families: dict[str, int] = {}
    for ir in designs:
        family = _classify_morphology(ir)
        families[family] = families.get(family, 0) + 1
    return families


def _classify_morphology(ir: RobotDesignIR) -> str:
    """Simple heuristic classification by joint/link count ratios."""
    n_links = len(ir.links)
    n_joints = len(ir.joints)

    if n_links <= 1:
        return "minimal"
    if n_joints == 0:
        return "rigid"

    name_lower = ir.name.lower()
    for family in ("humanoid", "quadruped", "biped", "snake", "centipede", "bird", "hexapod"):
        if family in name_lower:
            return family

    ratio = n_joints / n_links
    if ratio > 1.5:
        return "articulated"
    if n_links > 10:
        return "complex"
    return "standard"
