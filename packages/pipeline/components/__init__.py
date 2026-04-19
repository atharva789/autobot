"""
Component resolution and catalog models.

This package handles the mapping from abstract robot design (IR) to
concrete purchasable/manufacturable components.

Modules:
- catalog_models: Data models for vendor parts, custom parts, component stacks
- slot_resolver: Resolves IR joints/links to concrete component stacks
- procurement_enricher: Enriches components with vendor data (Phase 4)
"""

from packages.pipeline.components.catalog_models import (
    ComponentCategory,
    VendorPart,
    CustomPart,
    ComponentStack,
)
from packages.pipeline.components.slot_resolver import (
    resolve_joint_components,
    resolve_link_components,
    resolve_robot_components,
)

__all__ = [
    "ComponentCategory",
    "VendorPart",
    "CustomPart",
    "ComponentStack",
    "resolve_joint_components",
    "resolve_link_components",
    "resolve_robot_components",
]
