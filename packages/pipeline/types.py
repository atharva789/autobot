from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class MorphologyParams:
    num_arms:        int
    num_legs:        int
    has_torso:       bool
    torso_length:    float   # meters, 0.2..0.6
    arm_length:      float   # meters, 0.3..0.8
    leg_length:      float   # meters, 0.4..1.0
    arm_dof:         int     # 3..7
    leg_dof:         int     # 3..6
    spine_dof:       int     # 0..3
    joint_damping:   float   # 0.01..1.0
    joint_stiffness: float   # 1..100
    friction:        float   # 0.3..1.2


@dataclass(frozen=True)
class TrialResult:
    tracking_error:      float
    er16_success_prob:   float
    fitness_score:       float
    replay_mp4_url:      str
    controller_ckpt_url: str
    trajectory_npz_url:  str
    reasoning_md:        str


@dataclass(frozen=True)
class EvolutionConfig:
    max_iters:            int                 = 20
    max_hours:            float               = 2.0
    cost_alarm_usd:       float               = 50.0
    fitness_weights:      tuple[float, float] = (0.6, 0.4)
    keep_best_threshold:  float               = 0.01
