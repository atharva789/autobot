"""FastAPI router for robot design exports.

Endpoints:
- POST /designs/{design_id}/compile - Compile design to artifacts
- GET /designs/{design_id}/artifacts - List compiled artifacts
- POST /designs/{design_id}/export/mujoco - Export MuJoCo MJCF
- POST /designs/{design_id}/export/print - Export print files (STL/STEP)
- GET /designs/{design_id}/procurement - Get procurement report
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apps.api.workspace_store import workspace_store

router = APIRouter(prefix="/designs", tags=["exports"])
logger = logging.getLogger(__name__)


class CompileResponse(BaseModel):
    design_id: str
    artifacts: dict[str, str]
    success: bool
    errors: list[str] = []


class ArtifactsResponse(BaseModel):
    design_id: str
    mjcf: str | None = None
    urdf: str | None = None
    ui_scene: dict | None = None


class ExportMujocoResponse(BaseModel):
    design_id: str
    mjcf_path: str | None = None
    success: bool


class ExportPrintResponse(BaseModel):
    design_id: str
    step_files: list[str] = []
    stl_files: list[str] = []
    success: bool


class ProcurementResponse(BaseModel):
    design_id: str
    vendor_items: list[dict[str, Any]] = []
    custom_items: list[dict[str, Any]] = []
    estimated_total_usd: float | None = None
    confidence: float = 0.0


def _get_design_or_404(design_id: str) -> dict:
    """Get design from store or raise 404."""
    design = workspace_store.get_design(design_id)
    if design is None:
        raise HTTPException(status_code=404, detail=f"Design {design_id} not found")
    return design


@router.post("/{design_id}/compile", response_model=CompileResponse)
def compile_design(design_id: str) -> CompileResponse:
    """Compile a design to all artifacts (MJCF, URDF, UI scene)."""
    design = _get_design_or_404(design_id)

    # Import compilers
    from packages.pipeline.ir.design_ir import RobotDesignIR, LinkIR, JointIR, JointType
    from packages.pipeline.compilers.mjcf_compiler import compile_to_mjcf
    from packages.pipeline.ui.scene_compiler import compile_ui_scene

    try:
        # Build IR from stored design
        ir = _design_to_ir(design)

        # Compile artifacts
        mjcf = compile_to_mjcf(ir)
        ui_scene = compile_ui_scene(ir)

        # Store artifacts
        workspace_store.set_design_artifact(design_id, "mjcf", mjcf)
        workspace_store.set_design_artifact(design_id, "ui_scene", ui_scene)

        return CompileResponse(
            design_id=design_id,
            artifacts={"mjcf": "compiled", "ui_scene": "compiled"},
            success=True,
        )

    except Exception as e:
        logger.exception("Compile failed for %s", design_id)
        return CompileResponse(
            design_id=design_id,
            artifacts={},
            success=False,
            errors=[str(e)],
        )


@router.get("/{design_id}/artifacts", response_model=ArtifactsResponse)
def get_artifacts(design_id: str) -> ArtifactsResponse:
    """Get compiled artifacts for a design."""
    _get_design_or_404(design_id)

    mjcf = workspace_store.get_design_artifact(design_id, "mjcf")
    ui_scene = workspace_store.get_design_artifact(design_id, "ui_scene")

    return ArtifactsResponse(
        design_id=design_id,
        mjcf=mjcf,
        ui_scene=ui_scene,
    )


@router.post("/{design_id}/export/mujoco", response_model=ExportMujocoResponse)
def export_mujoco(design_id: str) -> ExportMujocoResponse:
    """Export design as MuJoCo MJCF file."""
    design = _get_design_or_404(design_id)

    # Check if already compiled
    mjcf = workspace_store.get_design_artifact(design_id, "mjcf")
    if mjcf is None:
        # Compile first
        compile_result = compile_design(design_id)
        if not compile_result.success:
            return ExportMujocoResponse(
                design_id=design_id,
                success=False,
            )
        mjcf = workspace_store.get_design_artifact(design_id, "mjcf")

    return ExportMujocoResponse(
        design_id=design_id,
        mjcf_path=f"artifacts/{design_id}/robot.mjcf",
        success=True,
    )


@router.post("/{design_id}/export/print", response_model=ExportPrintResponse)
def export_print(design_id: str) -> ExportPrintResponse:
    """Export design as print files (STL/STEP)."""
    design = _get_design_or_404(design_id)

    from packages.pipeline.ir.design_ir import RobotDesignIR
    from packages.pipeline.cad.print_export import export_robot_parts

    try:
        ir = _design_to_ir(design)
        result = export_robot_parts(ir, f"data/exports/{design_id}")

        return ExportPrintResponse(
            design_id=design_id,
            step_files=result.step_files,
            stl_files=result.stl_files,
            success=True,
        )
    except Exception as e:
        logger.exception("Print export failed for %s", design_id)
        return ExportPrintResponse(
            design_id=design_id,
            success=False,
        )


@router.get("/{design_id}/procurement", response_model=ProcurementResponse)
def get_procurement(design_id: str) -> ProcurementResponse:
    """Get procurement report for a design."""
    design = _get_design_or_404(design_id)

    from packages.pipeline.ir.design_ir import RobotDesignIR
    from packages.pipeline.components.slot_resolver import resolve_robot_components
    from packages.pipeline.procurement import generate_procurement_report

    try:
        ir = _design_to_ir(design)
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        return ProcurementResponse(
            design_id=design_id,
            vendor_items=[
                {"name": item.name, "sku": item.quote.sku if item.quote else None}
                for item in report.vendor_items
            ],
            custom_items=[
                {"name": item.name, "is_custom": True}
                for item in report.custom_items
            ],
            estimated_total_usd=report.estimated_total_usd,
            confidence=report.confidence,
        )
    except Exception as e:
        logger.exception("Procurement report failed for %s", design_id)
        return ProcurementResponse(design_id=design_id)


_LINK_TYPE_DEFAULTS: dict[str, dict[str, float]] = {
    "body":       {"length": 0.15, "radius": 0.03, "mass": 0.5},
    "limb_upper": {"length": 0.15, "radius": 0.02, "mass": 0.3},
    "limb_lower": {"length": 0.10, "radius": 0.02, "mass": 0.2},
    "end_eff":    {"length": 0.03, "radius": 0.03, "mass": 0.1},
    "wheel":      {"length": 0.05, "radius": 0.04, "mass": 0.15},
}

_NAME_PATTERNS: dict[str, str] = {
    "torso": "body", "trunk": "body", "base": "body", "body": "body", "spine": "body",
    "upper": "limb_upper", "shoulder": "limb_upper", "thigh": "limb_upper", "hip": "limb_upper",
    "lower": "limb_lower", "elbow": "limb_lower", "knee": "limb_lower", "shin": "limb_lower",
    "foot": "end_eff", "hand": "end_eff", "gripper": "end_eff", "end": "end_eff",
    "wheel": "wheel",
}


def _infer_link_type(name: str, explicit_type: str | None) -> str:
    if explicit_type and explicit_type in _LINK_TYPE_DEFAULTS:
        return explicit_type
    lower = name.lower()
    for pattern, link_type in _NAME_PATTERNS.items():
        if pattern in lower:
            return link_type
    return "body"


def _capsule_inertia(mass: float, radius: float, half_length: float) -> tuple[float, float, float]:
    """Compute principal inertia moments for a capsule (cylinder approximation)."""
    ixx = mass * (3 * radius**2 + (2 * half_length)**2) / 12.0
    iyy = ixx
    izz = mass * radius**2 / 2.0
    return ixx, iyy, izz


def _design_to_ir(design: dict) -> "RobotDesignIR":
    """Convert stored design dict to RobotDesignIR with physical attributes."""
    from packages.pipeline.ir.design_ir import (
        RobotDesignIR,
        LinkIR,
        JointIR,
        JointType,
        JointLimits,
        ActuatorSlot,
        Inertial,
        Geometry,
        Visual,
        Collision,
        Vector3,
    )

    morphology = design.get("morphology", {})
    links_data = morphology.get("links", [{"name": "base"}])
    joints_data = morphology.get("joints", [])

    links = []
    for i, ld in enumerate(links_data):
        name = ld.get("name", f"link_{i}")
        link_type = _infer_link_type(name, ld.get("type"))
        defaults = _LINK_TYPE_DEFAULTS[link_type]

        length = ld.get("length", defaults["length"])
        radius = ld.get("radius", defaults["radius"])
        mass = ld.get("mass", defaults["mass"])
        half_len = length / 2.0

        if link_type == "end_eff":
            geom = Geometry(type="sphere", size=(radius,))
        elif link_type == "wheel":
            geom = Geometry(type="cylinder", size=(radius, length))
        else:
            geom = Geometry(type="capsule", size=(radius, length))

        ixx, iyy, izz = _capsule_inertia(mass, radius, half_len)

        links.append(LinkIR(
            name=name,
            inertial=Inertial(mass=mass, ixx=ixx, iyy=iyy, izz=izz),
            visual=Visual(geometry=geom),
            collision=Collision(geometry=geom),
        ))

    joints = []
    for jd in joints_data:
        joint_type_str = jd.get("type", "revolute").upper()
        try:
            joint_type = JointType[joint_type_str]
        except KeyError:
            joint_type = JointType.REVOLUTE

        theta_r = jd.get("theta_r", 1.047)
        max_torque = jd.get("max_torque", 1.0)

        axis_data = jd.get("axis", [0.0, 1.0, 0.0])
        origin_data = jd.get("origin", [0.0, 0.0, 0.0])

        joints.append(JointIR(
            name=jd.get("name", f"joint_{len(joints)}"),
            joint_type=joint_type,
            parent_link=jd.get("parent", links[0].name if links else "base"),
            child_link=jd.get("child", links[-1].name if links else "link"),
            axis=Vector3(x=axis_data[0], y=axis_data[1], z=axis_data[2]),
            origin=Vector3(x=origin_data[0], y=origin_data[1], z=origin_data[2]),
            limits=JointLimits(
                lower=-theta_r,
                upper=theta_r,
                effort=max_torque,
            ),
            actuator=ActuatorSlot(
                actuator_type="position",
                max_torque=max_torque,
            ),
        ))

    return RobotDesignIR(
        name=design.get("name", "unnamed_robot"),
        links=links,
        joints=joints,
    )
