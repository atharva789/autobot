"""BOM (Bill of Materials) generation from robot design candidates.

Maps RobotDesignCandidate -> ComponentizedMorphology -> BOMOutput.
Uses curated catalogs for servo/structural/electronics lookups.
"""
from __future__ import annotations

import math
from typing import Literal

from packages.pipeline.schemas import (
    ActuatorComponent,
    BOMItem,
    BOMOutput,
    ComponentizedMorphology,
    ElectronicsComponent,
    FastenerComponent,
    RobotDesignCandidate,
    StructuralComponent,
)

# Curated servo catalog (common hobby/research servos)
_SERVO_CATALOG: list[dict] = [
    {
        "model": "Dynamixel XM430-W350",
        "vendor": "robotis",
        "torque_nm": 4.1,
        "rpm": 46,
        "sku": "XM430-W350-R",
        "price_usd": 269.90,
    },
    {
        "model": "Dynamixel XM540-W270",
        "vendor": "robotis",
        "torque_nm": 10.6,
        "rpm": 30,
        "sku": "XM540-W270-R",
        "price_usd": 359.90,
    },
    {
        "model": "Dynamixel XH540-W270",
        "vendor": "robotis",
        "torque_nm": 9.2,
        "rpm": 36,
        "sku": "XH540-W270-R",
        "price_usd": 419.90,
    },
    {
        "model": "Feetech STS3215",
        "vendor": "feetech",
        "torque_nm": 1.5,
        "rpm": 60,
        "sku": "STS3215",
        "price_usd": 35.00,
    },
    {
        "model": "Feetech SCS0009",
        "vendor": "feetech",
        "torque_nm": 0.5,
        "rpm": 100,
        "sku": "SCS0009",
        "price_usd": 12.00,
    },
    {
        "model": "ODrive D6374-150KV",
        "vendor": "odrive",
        "torque_nm": 8.0,
        "rpm": 150,
        "sku": "ODR-D6374-150",
        "price_usd": 159.00,
    },
]

# Curated structural profiles (McMaster-Carr)
_STRUCTURAL_CATALOG: list[dict] = [
    {
        "type": "aluminum_extrusion_20x20",
        "material": "aluminum_6061",
        "mcmaster_pn": "47065T101",
        "price_per_m_usd": 8.50,
    },
    {
        "type": "aluminum_extrusion_40x40",
        "material": "aluminum_6061",
        "mcmaster_pn": "47065T107",
        "price_per_m_usd": 18.00,
    },
    {
        "type": "aluminum_tube_25mm",
        "material": "aluminum_6061",
        "mcmaster_pn": "9056K14",
        "price_per_m_usd": 12.00,
    },
    {
        "type": "carbon_fiber_tube_20mm",
        "material": "carbon_fiber",
        "mcmaster_pn": None,
        "price_per_m_usd": 45.00,
    },
]

# Electronics catalog
_ELECTRONICS_CATALOG: list[dict] = [
    {
        "part_name": "Raspberry Pi 5",
        "component_type": "mcu",
        "vendor": "Raspberry Pi Foundation",
        "sku": "RPI5-8GB",
        "price_usd": 80.00,
    },
    {
        "part_name": "U2D2 USB Communication Converter",
        "component_type": "driver",
        "vendor": "Robotis",
        "sku": "U2D2",
        "price_usd": 39.90,
    },
    {
        "part_name": "MPU-6050 IMU Module",
        "component_type": "sensor",
        "vendor": "InvenSense",
        "sku": "GY-521",
        "price_usd": 8.00,
    },
    {
        "part_name": "12V 10A Power Supply",
        "component_type": "power",
        "vendor": "Mean Well",
        "sku": "LRS-120-12",
        "price_usd": 25.00,
    },
]

# Standard fasteners
_FASTENER_CATALOG: list[dict] = [
    {"type": "bolt", "size": "M3x10", "mcmaster_pn": "91290A115", "price_per_100": 5.50},
    {"type": "bolt", "size": "M4x12", "mcmaster_pn": "91290A150", "price_per_100": 6.00},
    {"type": "bolt", "size": "M5x16", "mcmaster_pn": "91290A228", "price_per_100": 7.50},
    {"type": "nut", "size": "M3", "mcmaster_pn": "90591A250", "price_per_100": 3.00},
    {"type": "nut", "size": "M4", "mcmaster_pn": "90591A145", "price_per_100": 3.50},
    {"type": "nut", "size": "M5", "mcmaster_pn": "90591A146", "price_per_100": 4.00},
    {
        "type": "washer",
        "size": "M4",
        "mcmaster_pn": "91166A220",
        "price_per_100": 2.50,
    },
]


def _select_servo(torque_required: float) -> dict | None:
    """Select smallest servo that meets torque requirement."""
    candidates = [s for s in _SERVO_CATALOG if s["torque_nm"] >= torque_required]
    if not candidates:
        return None
    return min(candidates, key=lambda s: s["torque_nm"])


def _estimate_joint_torque(
    limb_length_m: float,
    mass_kg: float,
    num_joints: int,
) -> float:
    """Estimate required joint torque based on limb geometry."""
    if num_joints == 0:
        return 0.0
    gravity = 9.81
    lever_arm = limb_length_m / 2
    load_per_joint = mass_kg / max(num_joints, 1)
    torque = load_per_joint * gravity * lever_arm * 1.5
    return torque


def design_to_componentized_morphology(
    candidate: RobotDesignCandidate,
) -> ComponentizedMorphology:
    """Convert a design candidate to componentized morphology with parts."""
    structural: list[StructuralComponent] = []
    actuators: list[ActuatorComponent] = []
    electronics: list[ElectronicsComponent] = []
    fasteners: list[FastenerComponent] = []

    if candidate.has_torso:
        structural.append(
            StructuralComponent(
                part_name="torso_frame",
                material="aluminum_6061",
                length_mm=candidate.torso_length_m * 1000,
                width_mm=100.0,
                thickness_mm=40.0,
                mcmaster_pn="47065T107",
            )
        )

    leg_torque = _estimate_joint_torque(
        candidate.leg_length_m,
        candidate.total_mass_kg / max(candidate.num_legs, 1),
        candidate.leg_dof,
    )
    for leg_idx in range(candidate.num_legs):
        structural.append(
            StructuralComponent(
                part_name=f"leg_{leg_idx}_link",
                material="aluminum_6061",
                length_mm=candidate.leg_length_m * 1000,
                width_mm=30.0,
                thickness_mm=20.0,
                mcmaster_pn="47065T101",
            )
        )
        for joint_idx in range(candidate.leg_dof):
            servo = _select_servo(leg_torque)
            actuators.append(
                ActuatorComponent(
                    joint_name=f"leg_{leg_idx}_joint_{joint_idx}",
                    servo_model=servo["model"] if servo else "CUSTOM_REQUIRED",
                    torque_nm=servo["torque_nm"] if servo else leg_torque,
                    rpm=servo["rpm"] if servo else 30,
                    vendor=servo["vendor"] if servo else "custom",
                    sku=servo["sku"] if servo else None,
                    unit_price_usd=servo["price_usd"] if servo else None,
                )
            )

    arm_torque = _estimate_joint_torque(
        candidate.arm_length_m,
        candidate.payload_capacity_kg + 0.5,
        candidate.arm_dof,
    )
    for arm_idx in range(candidate.num_arms):
        structural.append(
            StructuralComponent(
                part_name=f"arm_{arm_idx}_link",
                material="aluminum_6061",
                length_mm=candidate.arm_length_m * 1000,
                width_mm=25.0,
                thickness_mm=15.0,
                mcmaster_pn="47065T101",
            )
        )
        for joint_idx in range(candidate.arm_dof):
            servo = _select_servo(arm_torque)
            actuators.append(
                ActuatorComponent(
                    joint_name=f"arm_{arm_idx}_joint_{joint_idx}",
                    servo_model=servo["model"] if servo else "CUSTOM_REQUIRED",
                    torque_nm=servo["torque_nm"] if servo else arm_torque,
                    rpm=servo["rpm"] if servo else 30,
                    vendor=servo["vendor"] if servo else "custom",
                    sku=servo["sku"] if servo else None,
                    unit_price_usd=servo["price_usd"] if servo else None,
                )
            )

    electronics.append(
        ElectronicsComponent(
            part_name="Raspberry Pi 5",
            component_type="mcu",
            vendor="Raspberry Pi Foundation",
            sku="RPI5-8GB",
            unit_price_usd=80.00,
        )
    )
    if any(s == "imu" for s in candidate.sensor_package):
        electronics.append(
            ElectronicsComponent(
                part_name="MPU-6050 IMU Module",
                component_type="sensor",
                vendor="InvenSense",
                sku="GY-521",
                unit_price_usd=8.00,
            )
        )
    if actuators and actuators[0].vendor == "robotis":
        electronics.append(
            ElectronicsComponent(
                part_name="U2D2 USB Communication Converter",
                component_type="driver",
                vendor="Robotis",
                sku="U2D2",
                unit_price_usd=39.90,
            )
        )
    electronics.append(
        ElectronicsComponent(
            part_name="12V 10A Power Supply",
            component_type="power",
            vendor="Mean Well",
            sku="LRS-120-12",
            unit_price_usd=25.00,
        )
    )

    total_joints = len(actuators)
    fasteners.append(
        FastenerComponent(
            fastener_type="bolt",
            size="M4x12",
            quantity=total_joints * 4 + 20,
            mcmaster_pn="91290A150",
        )
    )
    fasteners.append(
        FastenerComponent(
            fastener_type="nut",
            size="M4",
            quantity=total_joints * 4 + 20,
            mcmaster_pn="90591A145",
        )
    )

    return ComponentizedMorphology(
        design=candidate,
        structural_components=structural,
        actuators=actuators,
        electronics=electronics,
        fasteners=fasteners,
    )


def componentized_to_bom(morphology: ComponentizedMorphology) -> BOMOutput:
    """Convert componentized morphology to bill of materials."""
    structural_items: list[BOMItem] = []
    actuator_items: list[BOMItem] = []
    electronics_items: list[BOMItem] = []
    fastener_items: list[BOMItem] = []
    missing: list[str] = []
    total_cost = 0.0

    for comp in morphology.structural_components:
        price = None
        for cat in _STRUCTURAL_CATALOG:
            if cat["mcmaster_pn"] == comp.mcmaster_pn:
                length_m = comp.length_mm / 1000
                price = cat["price_per_m_usd"] * length_m
                break
        structural_items.append(
            BOMItem(
                part_name=comp.part_name,
                quantity=1,
                vendor="McMaster-Carr",
                sku=comp.mcmaster_pn,
                unit_price_usd=price,
                availability="in_stock" if comp.mcmaster_pn else "unknown",
                requires_review=comp.custom_cad_required,
            )
        )
        if price:
            total_cost += price
        if comp.custom_cad_required:
            missing.append(f"Custom CAD required: {comp.part_name}")

    servo_counts: dict[str, int] = {}
    for act in morphology.actuators:
        key = act.servo_model
        servo_counts[key] = servo_counts.get(key, 0) + 1

    for model, qty in servo_counts.items():
        act_example = next(a for a in morphology.actuators if a.servo_model == model)
        price = act_example.unit_price_usd
        actuator_items.append(
            BOMItem(
                part_name=model,
                quantity=qty,
                vendor=act_example.vendor,
                sku=act_example.sku,
                unit_price_usd=price,
                availability="in_stock" if act_example.sku else "unknown",
                requires_review=act_example.vendor == "custom",
            )
        )
        if price:
            total_cost += price * qty
        if act_example.vendor == "custom":
            missing.append(f"Custom actuator required: {model}")

    for elec in morphology.electronics:
        electronics_items.append(
            BOMItem(
                part_name=elec.part_name,
                quantity=1,
                vendor=elec.vendor,
                sku=elec.sku,
                unit_price_usd=elec.unit_price_usd,
                availability="in_stock" if elec.sku else "unknown",
            )
        )
        if elec.unit_price_usd:
            total_cost += elec.unit_price_usd

    for fast in morphology.fasteners:
        price_per_100 = None
        for cat in _FASTENER_CATALOG:
            if cat["mcmaster_pn"] == fast.mcmaster_pn:
                price_per_100 = cat["price_per_100"]
                break
        price = (
            (price_per_100 * math.ceil(fast.quantity / 100)) if price_per_100 else None
        )
        fastener_items.append(
            BOMItem(
                part_name=f"{fast.fastener_type} {fast.size}",
                quantity=fast.quantity,
                vendor="McMaster-Carr",
                sku=fast.mcmaster_pn,
                unit_price_usd=price,
                availability="in_stock" if fast.mcmaster_pn else "unknown",
            )
        )
        if price:
            total_cost += price

    items_with_sku = sum(
        1
        for items in [
            structural_items,
            actuator_items,
            electronics_items,
            fastener_items,
        ]
        for item in items
        if item.sku
    )
    total_items = sum(
        len(items)
        for items in [
            structural_items,
            actuator_items,
            electronics_items,
            fastener_items,
        ]
    )
    confidence = items_with_sku / max(total_items, 1)

    return BOMOutput(
        candidate_id=morphology.design.candidate_id,
        structural_items=structural_items,
        actuator_items=actuator_items,
        electronics_items=electronics_items,
        fastener_items=fastener_items,
        total_cost_usd=round(total_cost, 2) if total_cost > 0 else None,
        procurement_confidence=round(confidence, 2),
        missing_items=missing,
    )


def generate_bom_for_candidate(candidate: RobotDesignCandidate) -> BOMOutput:
    """End-to-end: design candidate -> componentized -> BOM."""
    morphology = design_to_componentized_morphology(candidate)
    return componentized_to_bom(morphology)
