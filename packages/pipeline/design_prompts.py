"""Task-conditioned prompt families for robot concept generation."""

from __future__ import annotations

from collections.abc import Iterable

from packages.pipeline.schemas import TaskSpec


def _task_text(task: str | TaskSpec) -> str:
    if isinstance(task, TaskSpec):
        payload = ", ".join(task.search_queries)
        return (
            f"{task.task_goal}. Environment: {task.environment}. "
            f"Locomotion: {task.locomotion_type}. "
            f"Manipulation required: {task.manipulation_required}. "
            f"Payload: {task.payload_kg} kg. "
            f"Success criteria: {task.success_criteria}. "
            f"Reference search terms: {payload}"
        )
    return str(task).strip()


def _join_lines(lines: Iterable[str]) -> str:
    return "\n".join(line.strip() for line in lines if line.strip())


def build_candidate_prompt_family(task: str | TaskSpec) -> list[str]:
    """Return three CONTRASTIVE prompt variants forcing embodiment diversity.

    Each prompt explicitly requires a DIFFERENT embodiment class:
    - Candidate A: CONVENTIONAL (proven topology like quadruped, wheeled, biped)
    - Candidate B: UNCONVENTIONAL (different class - snake, tensegrity, hexapod, etc.)
    - Candidate C: MINIMAL (simplest - often wheeled, fixed_arm, or tracked)
    """
    task_text = _task_text(task)
    return [
        # Candidate A: CONVENTIONAL - proven, well-understood approach
        _join_lines(
            [
                f"CANDIDATE A (CONVENTIONAL): Design a robot for: {task_text}",
                "",
                "EMBODIMENT CONSTRAINT: Use a PROVEN, well-understood topology.",
                "Choose from: biped, quadruped, wheeled, tracked, mobile_arm, dual_arm.",
                "",
                "Design principles:",
                "- Low center of mass for stability",
                "- Standard joint configurations (3-6 DOF per limb)",
                "- Manufacturable with off-the-shelf actuators",
                "- Easy to simulate in MuJoCo/Isaac",
                "",
                "This is the SAFE, reliable choice that a robotics lab would build first.",
            ]
        ),
        # Candidate B: UNCONVENTIONAL - explore different morphology
        _join_lines(
            [
                f"CANDIDATE B (UNCONVENTIONAL): Design a robot for: {task_text}",
                "",
                "EMBODIMENT CONSTRAINT: Use a DIFFERENT embodiment class than typical.",
                "MUST choose from: hexapod, snake, inchworm, tensegrity, spherical,",
                "climbing_hybrid, soft_continuum, legged_wheeled, omnidirectional, tripod.",
                "",
                "Design principles:",
                "- Challenge conventional assumptions about locomotion",
                "- Exploit unique advantages of non-standard morphology",
                "- Consider bio-inspired or novel kinematic chains",
                "- Still physically realizable and simulatable",
                "",
                "This design should make reviewers say 'I wouldn't have thought of that'.",
            ]
        ),
        # Candidate C: MINIMAL - simplest possible solution
        _join_lines(
            [
                f"CANDIDATE C (MINIMAL): Design a robot for: {task_text}",
                "",
                "EMBODIMENT CONSTRAINT: Use the SIMPLEST possible approach.",
                "Prefer: wheeled, tracked, fixed_arm, or underactuated designs.",
                "",
                "Design principles:",
                "- Fewest actuated joints that still accomplish the task",
                "- Minimize DOF while maintaining capability",
                "- Optimize for procurement simplicity and fast build",
                "- Reject complexity unless absolutely necessary",
                "",
                "Ask: 'Can this be done with fewer joints? Simpler kinematics?'",
                "A wheeled base with a 3-DOF arm often beats a 24-DOF humanoid.",
            ]
        ),
    ]

