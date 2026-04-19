"""
Canonical Intermediate Representation (IR) for robot designs.

This package contains the single source of truth for all downstream compilers.
All exports (URDF, MJCF, USD, BOM, UI) derive from these canonical representations.

Modules:
- task_intent: User goal, environment, payload, constraints
- embodiment: Topology family, limb inventory, sensor intent, module choices
- design_ir: Canonical robot graph (RobotDesignIR)
- components: Link/joint component slots and resolution
- export_manifest: Export artifact tracking
"""

from packages.pipeline.ir.design_ir import RobotDesignIR, LinkIR, JointIR

__all__ = ["RobotDesignIR", "LinkIR", "JointIR"]
