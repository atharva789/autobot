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
    """Return three prompt variants that bias Gemini toward feasible designs."""
    task_text = _task_text(task)
    return [
        _join_lines(
            [
                f"Conventional, physically plausible robot concept for: {task_text}",
                "Prefer a proven topology, a low center of mass, and standard joint counts.",
                "Do not invent gratuitous extra limbs or cartoonish mechanisms.",
                "Keep the design manufacturable, inspectable, and easy to simulate.",
            ]
        ),
        _join_lines(
            [
                f"Stability-first robot concept for: {task_text}",
                "Bias toward a low-slung, contact-stable platform with clear support geometry.",
                "If the terrain is difficult, prefer a realistic wide-base or hybrid design over an over-limbed creature.",
                "Reason about torque, reach, and slip resistance explicitly.",
            ]
        ),
        _join_lines(
            [
                f"Simplest feasible robot concept for: {task_text}",
                "Use the fewest limbs, joints, and custom parts that still satisfy the task.",
                "Optimize for buildability, procurement simplicity, and simulator reliability.",
                "Reject speculative anatomy that would be hard to control or manufacture.",
            ]
        ),
    ]

