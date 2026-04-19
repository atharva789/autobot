from __future__ import annotations

from packages.pipeline.schemas import RobotDesignCandidate, TaskSpec


def derive_revised_task_spec(task_spec: TaskSpec, instruction: str) -> TaskSpec:
    text = instruction.strip() or task_spec.task_goal
    lowered = text.lower()
    locomotion = task_spec.locomotion_type
    if any(keyword in lowered for keyword in ("climb", "wall", "vertical", "rock")):
        locomotion = "climbing"
    elif any(keyword in lowered for keyword in ("crawl", "tunnel", "duct", "low-clearance")):
        locomotion = "crawling"
    elif any(keyword in lowered for keyword in ("slippery", "slope", "descent", "downhill")):
        locomotion = "walking"

    manipulation = task_spec.manipulation_required or any(
        keyword in lowered for keyword in ("grip", "gripper", "hand", "carry", "hold", "pack", "rope")
    )
    payload = task_spec.payload_kg
    if any(keyword in lowered for keyword in ("carry", "pack", "backpack", "payload", "back")):
        payload = max(payload, 2.5)

    return task_spec.model_copy(
        update={
            "task_goal": text,
            "locomotion_type": locomotion,
            "manipulation_required": manipulation,
            "payload_kg": payload,
            "search_queries": [text, *task_spec.search_queries[:2]],
        }
    )


def revise_candidate_for_instruction(
    candidate: RobotDesignCandidate,
    revised_task_spec: TaskSpec,
    instruction: str,
) -> tuple[RobotDesignCandidate, dict]:
    text = instruction.lower()
    updated = candidate.model_dump()
    changes: dict[str, object] = {}

    if any(keyword in text for keyword in ("climb", "wall", "vertical", "rock")):
        updated["embodiment_class"] = "hybrid"
        updated["num_arms"] = max(2, candidate.num_arms)
        updated["num_legs"] = 2
        updated["arm_length_m"] = max(candidate.arm_length_m, 0.58)
        updated["leg_length_m"] = max(candidate.leg_length_m, 0.62)
        updated["arm_dof"] = max(candidate.arm_dof, 5)
        updated["leg_dof"] = max(candidate.leg_dof, 4)
        updated["spine_dof"] = max(candidate.spine_dof, 2)
        updated["total_mass_kg"] = min(candidate.total_mass_kg, 19.0)
        updated["actuator_class"] = "bldc"
        updated["sensor_package"] = sorted(set(candidate.sensor_package) | {"camera", "force", "encoder"})
        changes["embodiment"] = "lean climbing hybrid"

    if any(keyword in text for keyword in ("crawl", "duct", "tunnel", "low-clearance")):
        updated["embodiment_class"] = "hybrid"
        updated["num_legs"] = max(4, candidate.num_legs)
        updated["num_arms"] = 0
        updated["torso_length_m"] = min(candidate.torso_length_m, 0.36)
        updated["leg_length_m"] = min(max(candidate.leg_length_m, 0.32), 0.48)
        updated["spine_dof"] = max(candidate.spine_dof, 1)
        updated["total_mass_kg"] = min(candidate.total_mass_kg, 16.0)
        changes["clearance_profile"] = "crawler"

    if any(keyword in text for keyword in ("slippery", "slope", "descent", "downhill")):
        updated["embodiment_class"] = "quadruped" if revised_task_spec.payload_kg < 3 else "hybrid"
        updated["num_legs"] = max(4, candidate.num_legs)
        updated["num_arms"] = max(candidate.num_arms, 0 if revised_task_spec.payload_kg < 3 else 2)
        updated["torso_length_m"] = max(candidate.torso_length_m, 0.46)
        updated["actuator_class"] = "bldc"
        updated["joint_damping"] = max(candidate.joint_damping, 0.55)
        updated["friction"] = max(candidate.friction, 1.0)
        changes["terrain_strategy"] = "traction-biased low-slung stance"

    if any(keyword in text for keyword in ("hand", "hands", "gripper", "grip")):
        updated["num_arms"] = max(2, updated["num_arms"])
        updated["arm_length_m"] = max(updated["arm_length_m"], 0.54)
        updated["arm_dof"] = max(updated["arm_dof"], 5)
        changes["end_effector"] = "dual grippers"

    if any(keyword in text for keyword in ("carry", "pack", "backpack", "back")):
        updated["payload_capacity_kg"] = max(candidate.payload_capacity_kg, revised_task_spec.payload_kg, 3.0)
        changes["payload"] = updated["payload_capacity_kg"]

    updated["rationale"] = (
        f"{candidate.rationale.rstrip('.')} Revised for: {revised_task_spec.task_goal}."
    )
    revised = RobotDesignCandidate.model_validate(updated)
    return revised, {
        "source": "user_revision",
        "instruction": instruction,
        "revised_task_spec": revised_task_spec.model_dump(),
        "changes": changes,
    }
