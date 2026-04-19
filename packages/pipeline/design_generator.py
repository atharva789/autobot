"""Gemini-driven robot design generation.

Replaces VAE sampling with task-conditioned structured output from Gemini 2.5 Pro.
"""
from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from packages.pipeline.mjx_screener import generate_mjcf_from_candidate
from packages.pipeline.schemas import (
    DesignCandidatesResponse,
    RobotDesignCandidate,
    TaskSpec,
)

_DESIGN_SYSTEM_PROMPT = """You are an expert robotics engineer designing robots for specific tasks.
Your designs must be physically realizable, use standard components, and be appropriate for the task.

Design principles:
- Match embodiment to task (bipeds for human-like tasks, quadrupeds for stability, arms for manipulation)
- Balance complexity vs. reliability (simpler is often better)
- Consider actuator torque requirements for payload and limb lengths
- Ensure joint DOF is sufficient for the motion requirements
- Account for center of mass and stability

You will generate exactly 3 meaningfully different robot designs:
- Candidate A: Most conventional/proven approach for this task
- Candidate B: More novel/experimental approach with potential advantages
- Candidate C: Simplest feasible approach (minimize complexity while meeting requirements)

Each candidate must be genuinely different in embodiment, DOF, or approach - not cosmetic variants."""

_DESIGN_USER_PROMPT = """Design robots for this task:

Task Specification:
{task_spec_json}

Generate exactly 3 robot design candidates following the schema.
Select which candidate you recommend as model_preferred_id and explain why."""

_FEW_SHOT_WALKING_BIPED = {
    "task_spec": {
        "task_goal": "walk forward at 1 m/s on flat ground",
        "environment": "indoor",
        "locomotion_type": "walking",
        "manipulation_required": False,
        "payload_kg": 0.0,
        "success_criteria": "maintain stable bipedal gait for 10 seconds",
        "search_queries": ["human walking side view", "person walking full body"],
    },
    "response": {
        "task_interpretation": "Bipedal locomotion on flat terrain, no manipulation needed",
        "candidates": [
            {
                "candidate_id": "A",
                "embodiment_class": "biped",
                "num_legs": 2,
                "num_arms": 0,
                "has_torso": True,
                "torso_length_m": 0.4,
                "arm_length_m": 0.0,
                "leg_length_m": 0.5,
                "arm_dof": 0,
                "leg_dof": 4,
                "spine_dof": 1,
                "actuator_class": "servo",
                "actuator_torque_nm": 12.0,
                "total_mass_kg": 8.0,
                "payload_capacity_kg": 0.0,
                "sensor_package": ["imu", "encoder"],
                "joint_damping": 0.5,
                "joint_stiffness": 100.0,
                "friction": 0.8,
                "rationale": "Classic humanoid leg design with hip, knee, ankle. Proven approach.",
                "confidence": 0.85,
            },
            {
                "candidate_id": "B",
                "embodiment_class": "biped",
                "num_legs": 2,
                "num_arms": 2,
                "has_torso": True,
                "torso_length_m": 0.5,
                "arm_length_m": 0.3,
                "leg_length_m": 0.6,
                "arm_dof": 3,
                "leg_dof": 5,
                "spine_dof": 2,
                "actuator_class": "bldc",
                "actuator_torque_nm": 18.0,
                "total_mass_kg": 15.0,
                "payload_capacity_kg": 2.0,
                "sensor_package": ["imu", "encoder", "force"],
                "joint_damping": 0.4,
                "joint_stiffness": 150.0,
                "friction": 0.9,
                "rationale": "Full humanoid with arms for balance. More complex but more capable.",
                "confidence": 0.75,
            },
            {
                "candidate_id": "C",
                "embodiment_class": "biped",
                "num_legs": 2,
                "num_arms": 0,
                "has_torso": True,
                "torso_length_m": 0.3,
                "arm_length_m": 0.0,
                "leg_length_m": 0.4,
                "arm_dof": 0,
                "leg_dof": 3,
                "spine_dof": 0,
                "actuator_class": "servo",
                "actuator_torque_nm": 8.0,
                "total_mass_kg": 4.0,
                "payload_capacity_kg": 0.0,
                "sensor_package": ["imu"],
                "joint_damping": 0.6,
                "joint_stiffness": 80.0,
                "friction": 0.7,
                "rationale": "Minimal biped - hip, knee, ankle only. Simplest stable walker.",
                "confidence": 0.80,
            },
        ],
        "model_preferred_id": "A",
        "selection_rationale": "Candidate A balances complexity and capability. 4-DOF legs provide good control without excessive complexity.",
    },
}


def _get_gemini_client():
    """Get Gemini client with lazy import."""
    try:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY must be set for design generation.")
        return genai.Client(api_key=api_key)
    except ImportError as exc:
        raise RuntimeError(
            "google-genai SDK not installed. Install with: pip install google-genai"
        ) from exc


def _extract_response_text(response: Any) -> str | None:
    """Extract text from Gemini response."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return None
    first_candidate = candidates[0]
    content = getattr(first_candidate, "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        return None
    texts = [
        getattr(part, "text", None)
        for part in parts
        if isinstance(getattr(part, "text", None), str)
    ]
    return "".join(texts).strip() or None


def _coerce_json_text(text: str) -> str:
    """Strip markdown code fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def generate_design_candidates(
    task_spec: TaskSpec,
    *,
    model: str = "gemini-2.5-pro",
    max_retries: int = 2,
) -> DesignCandidatesResponse:
    """Generate 3 robot design candidates using Gemini structured output.

    Args:
        task_spec: The extracted task specification.
        model: Gemini model to use (default: gemini-2.5-pro).
        max_retries: Number of retries on validation failure.

    Returns:
        DesignCandidatesResponse with 3 candidates and model-preferred selection.

    Raises:
        RuntimeError: If Gemini call fails or returns invalid response.
    """
    few_shot_example = json.dumps(_FEW_SHOT_WALKING_BIPED, indent=2)
    task_spec_json = task_spec.model_dump_json(indent=2)

    prompt = f"""{_DESIGN_SYSTEM_PROMPT}

Example (for reference):
{few_shot_example}

Now generate designs for this task:

{_DESIGN_USER_PROMPT.format(task_spec_json=task_spec_json)}"""

    last_error: Exception | None = None
    try:
        client = _get_gemini_client()
    except RuntimeError as exc:
        client = None
        last_error = exc

    if client is not None:
        for attempt in range(max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_json_schema": DesignCandidatesResponse.model_json_schema(),
                    },
                )
                text = _extract_response_text(response)
                if not isinstance(text, str):
                    raise RuntimeError(
                        f"Gemini returned non-text response on attempt {attempt + 1}"
                    )
                text = _coerce_json_text(text)
                result = DesignCandidatesResponse.model_validate_json(text)
                _validate_candidates(result)
                return result
            except (ValidationError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                if attempt < max_retries:
                    continue

    return _fallback_design_candidates(task_spec, last_error)


def _validate_candidates(response: DesignCandidatesResponse) -> None:
    """Additional validation beyond schema."""
    ids = {c.candidate_id for c in response.candidates}
    if ids != {"A", "B", "C"}:
        raise ValidationError(f"Expected candidates A, B, C but got {ids}")

    if response.model_preferred_id not in ids:
        raise ValidationError(
            f"model_preferred_id {response.model_preferred_id} not in candidates"
        )

    for candidate in response.candidates:
        if candidate.num_legs == 0 and candidate.leg_length_m > 0:
            raise ValidationError(
                f"Candidate {candidate.candidate_id}: has leg_length but num_legs=0"
            )
        if candidate.num_arms == 0 and candidate.arm_length_m > 0:
            raise ValidationError(
                f"Candidate {candidate.candidate_id}: has arm_length but num_arms=0"
            )


def _infer_payload(task_spec: TaskSpec) -> float:
    payload = max(task_spec.payload_kg, 0.0)
    task_text = f"{task_spec.task_goal} {' '.join(task_spec.search_queries)}".lower()
    if payload > 0:
        return payload
    if any(keyword in task_text for keyword in ("carry", "box", "crate", "bin", "bag")):
        return 4.0
    if any(keyword in task_text for keyword in ("lift", "stack", "shelf")):
        return 2.0
    return 0.5


def _fallback_design_candidates(
    task_spec: TaskSpec,
    last_error: Exception | None,
) -> DesignCandidatesResponse:
    task_text = f"{task_spec.task_goal} {' '.join(task_spec.search_queries)}".lower()
    payload = _infer_payload(task_spec)
    needs_stairs = any(keyword in task_text for keyword in ("stairs", "stair", "upstairs", "steps"))
    needs_manipulation = task_spec.manipulation_required or any(
        keyword in task_text for keyword in ("carry", "pick", "place", "lift", "hold", "grasp")
    )
    outdoor_bias = task_spec.environment in {"outdoor", "mixed"}

    candidate_a = RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="biped" if needs_stairs else "wheeled",
        num_legs=2 if needs_stairs else 0,
        num_arms=2 if needs_manipulation else 0,
        has_torso=True,
        torso_length_m=0.52 if needs_manipulation else 0.38,
        arm_length_m=0.44 if needs_manipulation else 0.0,
        leg_length_m=0.72 if needs_stairs else 0.0,
        arm_dof=4 if needs_manipulation else 0,
        leg_dof=5 if needs_stairs else 0,
        spine_dof=2 if needs_manipulation else 1,
        actuator_class="bldc" if payload >= 3 else "servo",
        actuator_torque_nm=28.0 if payload >= 3 else 12.0,
        total_mass_kg=26.0 if needs_stairs else 18.0,
        payload_capacity_kg=max(payload, 2.0 if needs_manipulation else 0.0),
        sensor_package=["imu", "encoder", "camera"],
        joint_damping=0.55,
        joint_stiffness=180.0,
        friction=0.95 if needs_stairs else 0.8,
        rationale="Fallback candidate tuned for direct task coverage with balanced manipulation and locomotion.",
        confidence=0.84,
    )

    candidate_b = RobotDesignCandidate(
        candidate_id="B",
        embodiment_class="quadruped" if outdoor_bias or needs_stairs else "hybrid",
        num_legs=4 if (outdoor_bias or needs_stairs) else 2,
        num_arms=1 if needs_manipulation else 0,
        has_torso=True,
        torso_length_m=0.58,
        arm_length_m=0.38 if needs_manipulation else 0.0,
        leg_length_m=0.48 if (outdoor_bias or needs_stairs) else 0.35,
        arm_dof=4 if needs_manipulation else 0,
        leg_dof=3,
        spine_dof=1,
        actuator_class="bldc" if payload >= 2 else "servo",
        actuator_torque_nm=18.0 if payload >= 2 else 10.0,
        total_mass_kg=22.0,
        payload_capacity_kg=max(payload * 0.8, 1.0 if needs_manipulation else 0.0),
        sensor_package=["imu", "encoder", "camera"],
        joint_damping=0.45,
        joint_stiffness=150.0,
        friction=1.0 if outdoor_bias or needs_stairs else 0.82,
        rationale="Fallback candidate emphasizes stability and terrain robustness while keeping a simpler manipulator package.",
        confidence=0.78,
    )

    candidate_c = RobotDesignCandidate(
        candidate_id="C",
        embodiment_class="arm" if not needs_stairs and needs_manipulation else "biped",
        num_legs=0 if (not needs_stairs and needs_manipulation) else 2,
        num_arms=1 if (not needs_stairs and needs_manipulation) else 0,
        has_torso=not (not needs_stairs and needs_manipulation),
        torso_length_m=0.24 if (not needs_stairs and needs_manipulation) else 0.34,
        arm_length_m=0.65 if (not needs_stairs and needs_manipulation) else 0.0,
        leg_length_m=0.0 if (not needs_stairs and needs_manipulation) else 0.52,
        arm_dof=6 if (not needs_stairs and needs_manipulation) else 0,
        leg_dof=3 if needs_stairs else 4,
        spine_dof=0 if (not needs_stairs and needs_manipulation) else 1,
        actuator_class="servo",
        actuator_torque_nm=9.0 if (not needs_stairs and needs_manipulation) else 11.0,
        total_mass_kg=9.0 if (not needs_stairs and needs_manipulation) else 12.0,
        payload_capacity_kg=max(payload * 0.6, 0.5),
        sensor_package=["imu", "encoder"],
        joint_damping=0.62,
        joint_stiffness=110.0,
        friction=0.78,
        rationale="Fallback candidate minimizes complexity for rapid prototyping and easier procurement.",
        confidence=0.72,
    )

    preferred = "A" if needs_stairs or needs_manipulation else "B"
    reason = "Fallback selection was used because Gemini design generation was unavailable."
    if last_error is not None:
        reason += f" Last error: {last_error}"

    return DesignCandidatesResponse(
        task_interpretation=f"Offline fallback generated candidates for task: {task_spec.task_goal}",
        candidates=[candidate_a, candidate_b, candidate_c],
        model_preferred_id=preferred,
        selection_rationale=reason,
    )


def build_render_payload(candidate: RobotDesignCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "topology_label": f"{candidate.embodiment_class}:{candidate.num_legs}L/{candidate.num_arms}A",
        "view_modes": ["concept", "wireframe", "joints", "components"],
        "mjcf": generate_mjcf_from_candidate(candidate),
        "joint_count": candidate.num_legs * candidate.leg_dof
        + candidate.num_arms * candidate.arm_dof
        + candidate.spine_dof,
    }


def candidate_to_morphology_params(candidate: RobotDesignCandidate) -> dict[str, Any]:
    """Convert RobotDesignCandidate to MorphologyParams-compatible dict.

    This bridges the new schema to the existing URDF generator.
    """
    return {
        "num_arms": candidate.num_arms,
        "num_legs": candidate.num_legs,
        "has_torso": candidate.has_torso,
        "torso_length": candidate.torso_length_m,
        "arm_length": candidate.arm_length_m,
        "leg_length": candidate.leg_length_m,
        "arm_dof": candidate.arm_dof,
        "leg_dof": candidate.leg_dof,
        "spine_dof": candidate.spine_dof,
        "joint_damping": candidate.joint_damping,
        "joint_stiffness": candidate.joint_stiffness,
        "friction": candidate.friction,
    }
