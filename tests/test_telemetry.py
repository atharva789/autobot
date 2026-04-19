from __future__ import annotations

from packages.pipeline.design_prompts import build_candidate_prompt_family
from packages.pipeline.schemas import BOMOutput, BOMItem, RobotDesignCandidate
from packages.pipeline.telemetry import build_candidate_telemetry


def _sample_candidate() -> RobotDesignCandidate:
    return RobotDesignCandidate(
        candidate_id="A",
        embodiment_class="quadruped",
        num_legs=4,
        num_arms=0,
        has_torso=True,
        torso_length_m=0.55,
        arm_length_m=0.0,
        leg_length_m=0.42,
        arm_dof=0,
        leg_dof=3,
        spine_dof=1,
        actuator_class="bldc",
        actuator_torque_nm=18.0,
        total_mass_kg=19.0,
        payload_capacity_kg=3.5,
        sensor_package=["imu", "encoder"],
        rationale="Stable, low-slung platform for carrying and traversal.",
        confidence=0.86,
    )


def test_build_candidate_prompt_family_is_task_distinct():
    prompts = build_candidate_prompt_family("carry a box down a slippery slope")

    assert len(prompts) == 3
    assert any("conventional" in prompt.lower() for prompt in prompts)
    assert any("stability" in prompt.lower() for prompt in prompts)
    assert any("simplest" in prompt.lower() for prompt in prompts)
    assert len(set(prompts)) == 3


def test_build_candidate_telemetry_includes_price_and_attributes():
    candidate = _sample_candidate()
    bom = BOMOutput(
        candidate_id="A",
        actuator_items=[
            BOMItem(
                part_name="Dynamixel XM540-W270",
                quantity=8,
                vendor="Robotis",
                sku="XM540-W270-R",
                unit_price_usd=359.9,
                availability="in_stock",
            )
        ],
        structural_items=[
            BOMItem(
                part_name="Aluminum extrusion",
                quantity=6,
                vendor="McMaster-Carr",
                sku="47065T107",
                unit_price_usd=18.0,
                availability="in_stock",
            )
        ],
        total_cost_usd=3071.2,
        procurement_confidence=0.92,
        missing_items=[],
    )

    telemetry = build_candidate_telemetry(candidate, bom)

    assert telemetry.candidate_id == "A"
    assert telemetry.estimated_total_cost_usd == 3071.2
    assert telemetry.estimated_mass_kg == 19.0
    assert telemetry.payload_capacity_kg == 3.5
    assert telemetry.estimated_reach_m > 0.4
    assert telemetry.estimated_backlash_deg > 0
    assert telemetry.estimated_bandwidth_hz > 0
    assert telemetry.procurement_confidence == 0.92
    assert telemetry.design_quality_score >= 0
    assert "cost" in telemetry.summary.lower()

