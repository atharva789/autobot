"""Design quality and aggregate metrics types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DesignMetrics:
    """Metrics for a single RobotDesignIR."""

    design_name: str
    ir_valid: bool
    ir_errors: tuple[str, ...] = ()
    mjcf_compiles: bool = False
    zero_ctrl_stable: bool = False
    actuator_coverage: bool = False
    no_self_collision: bool = False
    screening_score: float = 0.0
    stability_score: float = 0.0
    reachability_score: float = 0.0
    task_sanity_score: float = 0.0
    link_count: int = 0
    joint_count: int = 0
    actuated_joint_count: int = 0
    actuated_joint_ratio: float = 0.0


@dataclass(frozen=True)
class MetricsReport:
    """Aggregate metrics across all designs in a run."""

    per_design: tuple[DesignMetrics, ...] = ()
    total_designs: int = 0
    compile_rate: float = 0.0
    stability_rate: float = 0.0
    mean_screening_score: float = 0.0
    median_screening_score: float = 0.0
    link_count_entropy: float = 0.0
    joint_count_entropy: float = 0.0
    morphology_families: dict[str, int] = field(default_factory=dict)
    wall_time_seconds: float = 0.0
    llm_calls: int = 0
    estimated_cost_usd: float = 0.0
