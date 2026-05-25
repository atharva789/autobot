"""LLM-assisted IR materializer: grammar nodes → RobotDesignIR.

An LLM agent writes physical attributes (geometry, mass, joints, actuators)
for each grammar node, then this module assembles them into a validated IR.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from packages.pipeline.ir.design_ir import (
    ActuatorSlot,
    Collision,
    Geometry,
    Inertial,
    JointIR,
    JointLimits,
    JointType,
    LinkIR,
    RobotDesignIR,
    Vector3,
    Visual,
)
from packages.research.prompts.registry import PromptRegistry
from packages.research.strategy.protocol import StrategyConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeContext:
    """Context passed to the LLM for a single grammar node."""

    node_name: str
    role: str
    neighbors: tuple[str, ...]
    depth: int
    is_root: bool


class LLMIRMaterializer:
    """Calls an LLM per grammar node to assign physical attributes."""

    def __init__(
        self,
        prompts: PromptRegistry | None = None,
        template_name: str = "v1_materializer",
    ) -> None:
        self._prompts = prompts or PromptRegistry()
        self._template_name = template_name

    def materialize(
        self,
        raw_output: dict[str, Any],
        prompt: str,
        config: StrategyConfig,
    ) -> list[RobotDesignIR]:
        structural_rules = raw_output.get("structural_rules", {})
        if not structural_rules:
            return []

        spec = raw_output.get("spec")
        morphology = _extract_morphology(spec)
        tree = _build_tree(structural_rules)
        llm = _make_llm(config.model_id)

        links: list[LinkIR] = []
        joints: list[JointIR] = []

        for i, ctx in enumerate(tree):
            attrs = self._attribute_node(
                ctx, prompt, morphology, config, llm, node_index=i
            )
            link = _attrs_to_link(ctx.node_name, attrs)
            links.append(link)

            if not ctx.is_root and ctx.neighbors:
                parent = ctx.neighbors[0]
                joint = _attrs_to_joint(
                    f"joint_{parent}_to_{ctx.node_name}",
                    parent,
                    ctx.node_name,
                    attrs,
                )
                joints.append(joint)

        ir = RobotDesignIR(
            name=f"grammar_{config.seed}",
            links=links,
            joints=joints,
            version="1.0.0",
            source_candidate_id=f"grammar_seed_{config.seed}",
        )

        errors = ir.validate()
        if errors:
            logger.warning(
                "IR validation errors (auto-fixing): %s", errors
            )
            ir = _fix_dangling_refs(ir)

        return [ir]

    def _attribute_node(
        self,
        ctx: NodeContext,
        prompt: str,
        morphology: str,
        config: StrategyConfig,
        llm: Any,
        node_index: int = 0,
    ) -> dict[str, Any]:
        rendered = self._prompts.render(
            self._template_name,
            user_prompt=prompt,
            node_name=ctx.node_name,
            node_role=ctx.role,
            neighbors=", ".join(ctx.neighbors),
            tree_depth=str(ctx.depth),
            morphology_family=morphology,
        )

        if llm is None:
            return _fallback_attributes(ctx, config.seed, node_index)

        try:
            response = llm.invoke(rendered)
            payload = _parse_llm_response(response)
            if payload is not None:
                return payload
        except Exception as exc:
            logger.warning(
                "LLM materialization failed for %s: %s", ctx.node_name, exc
            )

        return _fallback_attributes(ctx, config.seed, node_index)


def _build_tree(
    structural_rules: dict[str, list[str]],
) -> list[NodeContext]:
    """Parse structural rules into a flat list of NodeContext."""
    all_nodes: dict[str, NodeContext] = {}
    children_of: dict[str, list[str]] = {}

    for lhs, rhs in structural_rules.items():
        children_of.setdefault(lhs, []).extend(rhs)
        if lhs not in all_nodes:
            all_nodes[lhs] = NodeContext(
                node_name=lhs,
                role="root" if not any(
                    lhs in v for v in structural_rules.values()
                ) else "intermediate",
                neighbors=(),
                depth=0,
                is_root=not any(
                    lhs in v for v in structural_rules.values()
                ),
            )
        for node in rhs:
            if node not in all_nodes:
                is_leaf = node not in structural_rules
                all_nodes[node] = NodeContext(
                    node_name=node,
                    role="leaf" if is_leaf else "intermediate",
                    neighbors=(lhs,),
                    depth=all_nodes[lhs].depth + 1,
                    is_root=False,
                )

    return list(all_nodes.values())


def _extract_morphology(spec: Any) -> str:
    if spec is None:
        return "quadruped"
    try:
        from packages.pipeline.grammar_graph import _infer_morphology_family
        from packages.pipeline.schemas import TaskIntent
        if isinstance(spec, TaskIntent):
            return _infer_morphology_family(spec) or "quadruped"
        if isinstance(spec, dict):
            inferred = spec.get("inferred_morphology")
            if inferred:
                return str(inferred)
    except Exception:
        pass
    return "quadruped"


def _make_llm(model_id: str) -> Any:
    from packages.research.local_chat_models import make_chat_model

    return make_chat_model(model_id)


def _parse_llm_response(response: Any) -> dict[str, Any] | None:
    content = getattr(response, "content", None) or str(response)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                return None
    return None


def _seed_jitter(seed: int, node_index: int, slot: int) -> float:
    """Deterministic per-seed, per-node perturbation in [-0.15, +0.15]."""
    h = hashlib.md5(f"{seed}:{node_index}:{slot}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF - 0.5) * 0.3


def _fallback_attributes(
    ctx: NodeContext, seed: int = 0, node_index: int = 0
) -> dict[str, Any]:
    """Deterministic fallback when LLM is unavailable.

    Different seeds produce slightly varied geometry/mass so that
    multi-candidate fallback runs are not all identical.
    """
    j = _seed_jitter

    if ctx.is_root:
        return {
            "geometry_type": "box",
            "geometry_size": [
                round(0.3 * (1 + j(seed, node_index, 0)), 4),
                round(0.15 * (1 + j(seed, node_index, 1)), 4),
                round(0.1 * (1 + j(seed, node_index, 2)), 4),
            ],
            "mass": round(5.0 * (1 + j(seed, node_index, 3)), 2),
            "rgba": [0.4, 0.4, 0.6, 1.0],
            "joint_type": None,
            "joint_axis": None,
            "joint_limits": None,
            "actuator_type": None,
            "max_torque": None,
            "damping": 0.1,
        }

    depth_scale = max(0.3, 1.0 - ctx.depth * 0.15)
    return {
        "geometry_type": "capsule",
        "geometry_size": [
            round(0.03 * depth_scale * (1 + j(seed, node_index, 0)), 4),
            round(0.15 * depth_scale * (1 + j(seed, node_index, 1)), 4),
        ],
        "mass": round(0.8 * depth_scale * (1 + j(seed, node_index, 2)), 2),
        "rgba": [0.5, 0.5, 0.5, 1.0],
        "joint_type": "revolute",
        "joint_axis": [0.0, 0.0, 1.0],
        "joint_limits": [-1.047, 1.047],
        "actuator_type": "position",
        "max_torque": round(10.0 * depth_scale * (1 + j(seed, node_index, 3)), 2),
        "damping": 0.1,
    }


def _attrs_to_link(name: str, attrs: dict[str, Any]) -> LinkIR:
    geom_type_raw = str(attrs.get("geometry_type", "capsule"))
    valid_geom_types = ("box", "cylinder", "sphere", "mesh", "capsule")
    geom_type: str = geom_type_raw if geom_type_raw in valid_geom_types else "capsule"
    geom_size = tuple(float(s) for s in attrs.get("geometry_size", [0.03, 0.1]))
    mass = float(attrs.get("mass", 1.0))
    rgba = tuple(float(c) for c in attrs.get("rgba", [0.5, 0.5, 0.5, 1.0]))

    geometry = Geometry(type=geom_type, size=geom_size)  # type: ignore[arg-type]
    return LinkIR(
        name=name,
        inertial=Inertial(mass=mass),
        visual=Visual(geometry=geometry, rgba=rgba[:4] if len(rgba) >= 4 else (0.5, 0.5, 0.5, 1.0)),
        collision=Collision(geometry=geometry),
    )


def _attrs_to_joint(
    name: str,
    parent: str,
    child: str,
    attrs: dict[str, Any],
) -> JointIR:
    jtype_str = str(attrs.get("joint_type", "revolute"))
    jtype = JointType(jtype_str) if jtype_str in JointType.__members__.values() else JointType.REVOLUTE

    axis_raw = attrs.get("joint_axis") or [0.0, 0.0, 1.0]
    axis = Vector3(x=float(axis_raw[0]), y=float(axis_raw[1]), z=float(axis_raw[2]))

    limits = None
    limits_raw = attrs.get("joint_limits")
    if limits_raw and len(limits_raw) >= 2:
        limits = JointLimits(lower=float(limits_raw[0]), upper=float(limits_raw[1]))

    actuator = None
    act_type = attrs.get("actuator_type")
    valid_act_types = ("motor", "servo", "hydraulic", "pneumatic", "position")
    if act_type and str(act_type) in valid_act_types:
        actuator = ActuatorSlot(
            actuator_type=str(act_type),  # type: ignore[arg-type]
            max_torque=float(attrs.get("max_torque", 10.0)),
        )

    return JointIR(
        name=name,
        joint_type=jtype,
        parent_link=parent,
        child_link=child,
        axis=axis,
        limits=limits,
        actuator=actuator,
        damping=float(attrs.get("damping", 0.1)),
    )


def _fix_dangling_refs(ir: RobotDesignIR) -> RobotDesignIR:
    """Remove joints that reference missing links."""
    link_names = {link.name for link in ir.links}
    valid_joints = [
        j for j in ir.joints
        if j.parent_link in link_names and j.child_link in link_names
    ]
    return RobotDesignIR(
        name=ir.name,
        links=ir.links,
        joints=valid_joints,
        sensors=ir.sensors,
        version=ir.version,
        source_candidate_id=ir.source_candidate_id,
    )
