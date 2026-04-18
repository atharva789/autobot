"""MuJoCo MJX lightweight screening for robot design candidates.

Generates MJCF from design candidates and runs quick simulation
to evaluate stability, motion tracking, and energy efficiency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from packages.pipeline.schemas import RobotDesignCandidate


@dataclass
class MJXScreeningResult:
    """Result of MJX simulation screening."""

    candidate_id: str
    stability_score: float
    tracking_score: float
    energy_efficiency: float
    combined_score: float
    simulation_steps: int
    fell_over: bool
    error_message: str | None


def generate_mjcf_from_candidate(candidate: RobotDesignCandidate) -> str:
    """Generate MJCF XML from a robot design candidate.

    Args:
        candidate: The robot design specification.

    Returns:
        MJCF XML string for MuJoCo simulation.
    """
    total_actuators = (
        candidate.num_legs * candidate.leg_dof
        + candidate.num_arms * candidate.arm_dof
        + candidate.spine_dof
    )

    actuators_xml = "\n".join(
        f'        <motor name="motor_{i}" joint="joint_{i}" gear="1" ctrllimited="true" ctrlrange="-1 1"/>'
        for i in range(total_actuators)
    )

    joints_xml = "\n".join(
        f'            <joint name="joint_{i}" type="hinge" axis="0 1 0" range="-1.57 1.57" damping="{candidate.joint_damping}"/>'
        for i in range(total_actuators)
    )

    leg_bodies = []
    joint_idx = 0
    for leg_idx in range(candidate.num_legs):
        side = "left" if leg_idx % 2 == 0 else "right"
        x_offset = -0.1 if side == "left" else 0.1

        if candidate.embodiment_class == "quadruped":
            z_offset = 0.15 if leg_idx < 2 else -0.15
        else:
            z_offset = 0.0

        segment_length = candidate.leg_length_m / candidate.leg_dof

        leg_xml_parts = [f'        <body name="leg_{leg_idx}" pos="{x_offset} 0 {z_offset}">']

        for seg in range(candidate.leg_dof):
            y_pos = -segment_length * (seg + 1)
            leg_xml_parts.append(
                f'            <body name="leg_{leg_idx}_seg_{seg}" pos="0 {y_pos:.3f} 0">'
            )
            leg_xml_parts.append(
                f'                <joint name="joint_{joint_idx}" type="hinge" axis="1 0 0" range="-1.57 1.57" damping="{candidate.joint_damping}"/>'
            )
            leg_xml_parts.append(
                f'                <geom type="capsule" size="0.02" fromto="0 0 0 0 {-segment_length:.3f} 0" rgba="0.8 0.3 0.3 1"/>'
            )
            joint_idx += 1

        for _ in range(candidate.leg_dof):
            leg_xml_parts.append("            </body>")

        leg_xml_parts.append("        </body>")
        leg_bodies.append("\n".join(leg_xml_parts))

    spine_joints = []
    for i in range(candidate.spine_dof):
        spine_joints.append(
            f'            <joint name="joint_{joint_idx}" type="hinge" axis="0 1 0" range="-0.5 0.5" damping="{candidate.joint_damping}"/>'
        )
        joint_idx += 1

    mjcf = f'''<mujoco model="candidate_{candidate.candidate_id}">
    <compiler angle="radian"/>

    <option timestep="0.002" gravity="0 0 -9.81"/>

    <worldbody>
        <light diffuse=".5 .5 .5" pos="0 0 3" dir="0 0 -1"/>
        <geom type="plane" size="10 10 0.1" rgba="0.9 0.9 0.9 1"/>

        <body name="torso" pos="0 0 {candidate.torso_length_m + candidate.leg_length_m}">
            <freejoint name="root"/>
            <geom type="box" size="{candidate.torso_length_m/2} 0.1 0.05" rgba="0.3 0.3 0.8 1" mass="{candidate.total_mass_kg * 0.4}"/>
            <site name="imu" pos="0 0 0"/>
{chr(10).join(spine_joints)}
{chr(10).join(leg_bodies)}
        </body>
    </worldbody>

    <actuator>
{actuators_xml}
    </actuator>

    <sensor>
        <accelerometer name="accel" site="imu"/>
        <gyro name="gyro" site="imu"/>
    </sensor>
</mujoco>'''

    return mjcf


def compute_stability_score(com_trajectory: np.ndarray) -> float:
    """Compute stability score from center-of-mass trajectory.

    Args:
        com_trajectory: Nx3 array of COM positions over time.

    Returns:
        Score from 0 to 1, where 1 is perfectly stable.
    """
    if len(com_trajectory) < 2:
        return 0.0

    z_values = com_trajectory[:, 2]
    z_variance = np.var(z_values)

    xy_drift = np.linalg.norm(com_trajectory[-1, :2] - com_trajectory[0, :2])

    variance_penalty = min(z_variance * 10, 1.0)
    drift_penalty = min(xy_drift * 0.5, 1.0)

    score = max(0.0, 1.0 - variance_penalty - drift_penalty * 0.3)
    return float(score)


def compute_motion_tracking_score(
    simulated: np.ndarray, reference: np.ndarray
) -> float:
    """Compute motion tracking score against reference trajectory.

    Args:
        simulated: Nx3 array of simulated positions.
        reference: Nx3 array of reference positions.

    Returns:
        Score from 0 to 1, where 1 is perfect tracking.
    """
    if len(simulated) != len(reference):
        min_len = min(len(simulated), len(reference))
        simulated = simulated[:min_len]
        reference = reference[:min_len]

    if len(simulated) == 0:
        return 0.0

    errors = np.linalg.norm(simulated - reference, axis=1)
    mean_error = np.mean(errors)

    score = max(0.0, 1.0 - mean_error * 2)
    return float(score)


def _run_mjx_simulation(
    mjcf: str,
    steps: int = 1000,
    reference_trajectory: np.ndarray | None = None,
) -> dict[str, Any]:
    """Run MJX simulation (stub for actual MuJoCo MJX integration).

    In production, this would:
    1. Load MJCF into MuJoCo
    2. JIT-compile with MJX for GPU acceleration
    3. Run forward simulation with simple controller
    4. Return trajectory data

    Args:
        mjcf: MJCF XML string.
        steps: Number of simulation steps.
        reference_trajectory: Optional reference to track.

    Returns:
        Dict with simulation results.
    """
    com_trajectory = np.zeros((steps, 3))
    com_trajectory[:, 2] = 0.5

    return {
        "com_trajectory": com_trajectory,
        "joint_positions": np.zeros((steps, 10)),
        "energy_used": 50.0,
        "steps": steps,
        "fell": False,
    }


def screen_candidate(
    candidate: RobotDesignCandidate,
    reference_trajectory: np.ndarray | None = None,
    simulation_steps: int = 1000,
) -> MJXScreeningResult:
    """Screen a single design candidate with MJX simulation.

    Args:
        candidate: Robot design to evaluate.
        reference_trajectory: Optional reference motion to track.
        simulation_steps: Number of simulation steps.

    Returns:
        MJXScreeningResult with scores.
    """
    mjcf = generate_mjcf_from_candidate(candidate)

    sim_result = _run_mjx_simulation(
        mjcf, steps=simulation_steps, reference_trajectory=reference_trajectory
    )

    if sim_result["fell"]:
        return MJXScreeningResult(
            candidate_id=candidate.candidate_id,
            stability_score=0.0,
            tracking_score=0.0,
            energy_efficiency=0.0,
            combined_score=0.0,
            simulation_steps=sim_result["steps"],
            fell_over=True,
            error_message=f"Robot fell at step {sim_result['steps']}",
        )

    stability = compute_stability_score(sim_result["com_trajectory"])

    if reference_trajectory is not None:
        tracking = compute_motion_tracking_score(
            sim_result["com_trajectory"], reference_trajectory
        )
    else:
        tracking = stability

    max_energy = simulation_steps * 10.0
    energy_efficiency = max(0.0, 1.0 - sim_result["energy_used"] / max_energy)

    combined = stability * 0.4 + tracking * 0.4 + energy_efficiency * 0.2

    return MJXScreeningResult(
        candidate_id=candidate.candidate_id,
        stability_score=stability,
        tracking_score=tracking,
        energy_efficiency=energy_efficiency,
        combined_score=combined,
        simulation_steps=sim_result["steps"],
        fell_over=False,
        error_message=None,
    )


def screen_candidates(
    candidates: list[RobotDesignCandidate],
    reference_trajectory: np.ndarray | None = None,
    simulation_steps: int = 1000,
) -> list[MJXScreeningResult]:
    """Screen multiple candidates and return sorted results.

    Args:
        candidates: List of robot designs to evaluate.
        reference_trajectory: Optional reference motion to track.
        simulation_steps: Number of simulation steps per candidate.

    Returns:
        List of results sorted by combined_score descending.
    """
    results = [
        screen_candidate(c, reference_trajectory, simulation_steps)
        for c in candidates
    ]

    results.sort(key=lambda r: r.combined_score, reverse=True)
    return results
