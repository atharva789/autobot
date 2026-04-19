"""Gemini-driven robot design generation.

Replaces VAE sampling with task-conditioned structured output from Gemini 2.5 Pro.

Important implementation note:
- The provider-facing schema is intentionally smaller than the internal
  `DesignCandidatesResponse`.
- Gemini structured outputs can reject large, highly constrained schemas with
  "too many states for serving". Internal/post-processed fields are therefore
  derived deterministically after generation rather than emitted by the model.
"""
from __future__ import annotations

import json
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from packages.pipeline.design_prompts import build_candidate_prompt_family
from packages.pipeline.engineering_render import build_engineering_render
from packages.pipeline.mjx_screener import generate_mjcf_from_candidate
from packages.pipeline.schemas import (
    DesignCandidatesResponse,
    RobotDesignCandidate,
    TaskSpec,
)
from packages.pipeline.task_conditioning import (
    apply_task_conditioning,
    build_task_capability_graph,
)

_DESIGN_SYSTEM_PROMPT = """You are an expert robotics engineer designing diverse robots for specific tasks.
Your designs must be physically realizable, use standard components, and be appropriate for the task.

CRITICAL: Generate THREE FUNDAMENTALLY DIFFERENT embodiment approaches. Not variations of the same design.

Available embodiment classes (USE VARIETY):
- Legged: biped, quadruped, hexapod, tripod
- Wheeled: wheeled, tracked, omnidirectional
- Hybrid: wheeled_manipulator, legged_wheeled, climbing_hybrid
- Specialized: snake, inchworm, spherical, tensegrity
- Manipulation: fixed_arm, mobile_arm, dual_arm
- Novel: modular, soft_continuum

Design principles:
- Each candidate MUST use a DIFFERENT embodiment_class - no repeats allowed
- Match embodiment to task affordances (climbing needs adhesion/gripping, payload needs stability)
- Consider unconventional solutions: snake for confined spaces, tensegrity for rough terrain, spherical for exploration
- Balance complexity vs. reliability (simpler is often better)
- Consider actuator torque requirements for payload and limb lengths
- Account for center of mass and stability

CONTRASTIVE GENERATION RULES:
- Candidate A: CONVENTIONAL - Use the most proven approach for this task family
- Candidate B: UNCONVENTIONAL - Use a DIFFERENT embodiment class that challenges assumptions. Explore hybrid, specialized, or novel morphologies that could offer unexpected advantages.
- Candidate C: MINIMAL - Use the SIMPLEST possible approach with the fewest actuated joints. Could be single manipulator, wheeled base, or underactuated design.

HARD CONSTRAINT: If candidates share the same embodiment_class, regenerate until they differ."""

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


_EMBODIMENT_ENUM = [
    "biped", "quadruped", "hexapod", "tripod",
    "wheeled", "tracked", "omnidirectional",
    "wheeled_manipulator", "legged_wheeled", "climbing_hybrid",
    "snake", "inchworm", "spherical", "tensegrity",
    "fixed_arm", "mobile_arm", "dual_arm",
    "modular", "soft_continuum",
    "arm", "hybrid",
]


class _CompactCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    i: Literal["A", "B", "C"]
    e: str  # Validated post-hoc against _EMBODIMENT_ENUM
    nl: int
    na: int
    t: bool
    tl: float
    al: float
    ll: float
    ad: int
    ld: int
    sd: int
    ac: Literal["servo", "bldc", "stepper", "hydraulic"]
    tq: float
    tm: float
    pl: float
    sp: list[Literal["imu", "camera", "lidar", "force", "encoder"]]
    ra: str
    cf: float


class _CompactDesignResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ti: str
    c: list[_CompactCandidate]
    mp: Literal["A", "B", "C"]
    sr: str


def _compact_generation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ti": {"type": "string"},
            "c": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "string", "enum": ["A", "B", "C"]},
                        "e": {"type": "string", "enum": _EMBODIMENT_ENUM},
                        "nl": {"type": "integer"},
                        "na": {"type": "integer"},
                        "t": {"type": "boolean"},
                        "tl": {"type": "number"},
                        "al": {"type": "number"},
                        "ll": {"type": "number"},
                        "ad": {"type": "integer"},
                        "ld": {"type": "integer"},
                        "sd": {"type": "integer"},
                        "ac": {"type": "string", "enum": ["servo", "bldc", "stepper", "hydraulic"]},
                        "tq": {"type": "number"},
                        "tm": {"type": "number"},
                        "pl": {"type": "number"},
                        "sp": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["imu", "camera", "lidar", "force", "encoder"]},
                        },
                        "ra": {"type": "string"},
                        "cf": {"type": "number"},
                    },
                    "required": ["i", "e", "nl", "na", "t", "tl", "al", "ll", "ad", "ld", "sd", "ac", "tq", "tm", "pl", "sp", "ra", "cf"],
                    "additionalProperties": False,
                },
            },
            "mp": {"type": "string", "enum": ["A", "B", "C"]},
            "sr": {"type": "string"},
        },
        "required": ["ti", "c", "mp", "sr"],
        "additionalProperties": False,
    }


def _normalize_actuator_defaults(actuator_class: str) -> tuple[float, float, float]:
    if actuator_class == "bldc":
        return 0.42, 170.0, 0.92
    if actuator_class == "hydraulic":
        return 0.35, 240.0, 1.05
    if actuator_class == "stepper":
        return 0.58, 120.0, 0.76
    return 0.5, 100.0, 0.82


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _coerce_candidate_lengths(count: int, length: float) -> float:
    return 0.0 if count <= 0 else max(length, 0.0)


def _expand_compact_response(compact: _CompactDesignResponse) -> DesignCandidatesResponse:
    candidates: list[RobotDesignCandidate] = []
    for item in compact.c:
        joint_damping, joint_stiffness, friction = _normalize_actuator_defaults(item.ac)
        num_arms = max(0, int(item.na))
        num_legs = max(0, int(item.nl))
        arm_dof = 0 if num_arms == 0 else max(0, int(item.ad))
        leg_dof = 0 if num_legs == 0 else max(0, int(item.ld))
        candidate = RobotDesignCandidate(
            candidate_id=item.i,
            embodiment_class=item.e,
            num_legs=num_legs,
            num_arms=num_arms,
            has_torso=bool(item.t),
            torso_length_m=_clamp(float(item.tl), 0.05, 2.0),
            arm_length_m=_clamp(_coerce_candidate_lengths(num_arms, float(item.al)), 0.0, 1.5),
            leg_length_m=_clamp(_coerce_candidate_lengths(num_legs, float(item.ll)), 0.0, 1.5),
            arm_dof=min(7, arm_dof),
            leg_dof=min(6, leg_dof),
            spine_dof=min(4, max(0, int(item.sd))),
            actuator_class=item.ac,
            actuator_torque_nm=_clamp(float(item.tq), 0.1, 500.0),
            total_mass_kg=_clamp(float(item.tm), 0.1, 500.0),
            payload_capacity_kg=_clamp(float(item.pl), 0.0, 200.0),
            sensor_package=list(dict.fromkeys(item.sp)),
            joint_damping=joint_damping,
            joint_stiffness=joint_stiffness,
            friction=friction,
            rationale=item.ra,
            confidence=_clamp(float(item.cf), 0.0, 1.0),
        )
        candidates.append(candidate)

    return DesignCandidatesResponse(
        task_interpretation=compact.ti,
        candidates=candidates,
        model_preferred_id=compact.mp,
        selection_rationale=compact.sr,
    )


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
    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if isinstance(text, str):
            texts.append(text)
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
    prompt_family = "\n\n".join(build_candidate_prompt_family(task_spec))
    task_capability_graph = build_task_capability_graph(task_spec).model_dump_json(indent=2)

    prompt = f"""{_DESIGN_SYSTEM_PROMPT}

Task-specific prompt family:
{prompt_family}

Task capability graph:
{task_capability_graph}

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
                        "response_json_schema": _compact_generation_schema(),
                    },
                )
                text = _extract_response_text(response)
                if not isinstance(text, str):
                    raise RuntimeError(
                        f"Gemini returned non-text response on attempt {attempt + 1}"
                    )
                text = _coerce_json_text(text)
                try:
                    compact = _CompactDesignResponse.model_validate_json(text)
                    result = _expand_compact_response(compact)
                except ValidationError:
                    result = DesignCandidatesResponse.model_validate_json(text)
                _validate_candidates(result)
                return apply_task_conditioning(result, task_spec)
            except (ValidationError, json.JSONDecodeError, RuntimeError, Exception) as exc:
                last_error = exc
                if attempt < max_retries:
                    continue

    return apply_task_conditioning(_fallback_design_candidates(task_spec, last_error), task_spec)


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
    capability_graph = build_task_capability_graph(task_spec)
    payload = _infer_payload(task_spec)
    needs_stairs = any(keyword in task_text for keyword in ("stairs", "stair", "upstairs", "steps"))
    needs_manipulation = task_spec.manipulation_required or any(
        keyword in task_text for keyword in ("carry", "pick", "place", "lift", "hold", "grasp")
    )
    outdoor_bias = task_spec.environment in {"outdoor", "mixed"}

    if capability_graph.task_family == "climbing":
        candidate_a = RobotDesignCandidate(
            candidate_id="A",
            embodiment_class="hybrid",
            num_legs=2,
            num_arms=2,
            has_torso=True,
            torso_length_m=0.46,
            arm_length_m=0.58,
            leg_length_m=0.62,
            arm_dof=5,
            leg_dof=4,
            spine_dof=2,
            actuator_class="bldc",
            actuator_torque_nm=28.0,
            total_mass_kg=17.0,
            payload_capacity_kg=max(payload, 3.0),
            sensor_package=["imu", "camera", "force", "encoder"],
            joint_damping=0.48,
            joint_stiffness=190.0,
            friction=1.05,
            rationale="Lean climbing hybrid with dual grasping limbs, explicit surface attachment strategy, and centered payload support.",
            confidence=0.86,
        )
        candidate_b = RobotDesignCandidate(
            candidate_id="B",
            embodiment_class="biped",
            num_legs=2,
            num_arms=2,
            has_torso=True,
            torso_length_m=0.5,
            arm_length_m=0.52,
            leg_length_m=0.66,
            arm_dof=4,
            leg_dof=4,
            spine_dof=2,
            actuator_class="bldc",
            actuator_torque_nm=24.0,
            total_mass_kg=18.5,
            payload_capacity_kg=max(payload * 0.85, 2.5),
            sensor_package=["imu", "camera", "encoder", "force"],
            joint_damping=0.5,
            joint_stiffness=175.0,
            friction=0.98,
            rationale="Humanoid-style wall climber with dual-arm grasping and vertical support strategy for rough surfaces.",
            confidence=0.8,
        )
        candidate_c = RobotDesignCandidate(
            candidate_id="C",
            embodiment_class="quadruped",
            num_legs=4,
            num_arms=0,
            has_torso=True,
            torso_length_m=0.54,
            arm_length_m=0.0,
            leg_length_m=0.42,
            arm_dof=0,
            leg_dof=4,
            spine_dof=1,
            actuator_class="bldc",
            actuator_torque_nm=22.0,
            total_mass_kg=20.0,
            payload_capacity_kg=max(payload * 0.9, 2.0),
            sensor_package=["imu", "camera", "encoder"],
            joint_damping=0.46,
            joint_stiffness=165.0,
            friction=0.96,
            rationale="Conservative rough-terrain climber using hooked feet for surface attachment and distributed load support.",
            confidence=0.74,
        )

        reason = "Fallback selection was used because Gemini design generation was unavailable."
        if last_error is not None:
            reason += f" Last error: {last_error}"
        return DesignCandidatesResponse(
            task_interpretation=f"Offline fallback generated climbing-aware candidates for task: {task_spec.task_goal}",
            candidates=[candidate_a, candidate_b, candidate_c],
            model_preferred_id="A",
            selection_rationale=reason,
        )

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

def build_render_payload(
    candidate: RobotDesignCandidate,
    task_spec: TaskSpec | None = None,
) -> dict[str, Any]:
    engineering_render = build_engineering_render(candidate, task_spec)
    return {
        "candidate_id": candidate.candidate_id,
        "topology_label": f"{candidate.embodiment_class}:{candidate.num_legs}L/{candidate.num_arms}A",
        "view_modes": ["concept", "engineering", "joints", "components"],
        "engineering_ready": engineering_render["engineering_ready"],
        "render_glb": engineering_render["render_glb"],
        "ui_scene": engineering_render["ui_scene"],
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
