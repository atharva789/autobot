"""
Procurement stack for robot components.

This package handles vendor lookup, quote generation, and
procurement report creation.

Modules:
- providers/: Vendor API interfaces (DigiKey, Mouser, McMaster)
- quote_engine: Quote aggregation and comparison
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from packages.pipeline.components.catalog_models import (
    ComponentCategory,
    VendorPart,
    CustomPart,
)

if TYPE_CHECKING:
    from packages.pipeline.components.slot_resolver import RobotComponentResolution


@dataclass
class PartQuery:
    """Query for finding a part."""
    sku: str | None = None
    vendor: str | None = None
    description: str | None = None
    category: ComponentCategory | None = None
    min_quantity: int = 1


@dataclass
class VendorQuote:
    """Quote from a vendor for a part."""
    sku: str
    vendor: str
    description: str
    unit_price_usd: float | None = None
    quantity_available: int = 0
    in_stock: bool = True
    lead_time_days: int | None = None
    datasheet_url: str | None = None
    url: str | None = None


@dataclass
class ProcurementItem:
    """An item in the procurement list."""
    name: str
    quantity: int = 1
    quote: VendorQuote | None = None
    is_custom: bool = False
    custom_part: CustomPart | None = None
    resolved: bool = True


@dataclass
class ProcurementResult:
    """Complete procurement report for a robot."""
    vendor_items: list[ProcurementItem] = field(default_factory=list)
    custom_items: list[ProcurementItem] = field(default_factory=list)
    unresolved_items: list[str] = field(default_factory=list)
    estimated_total_usd: float | None = None
    confidence: float = 1.0

    @property
    def total_items(self) -> int:
        return len(self.vendor_items) + len(self.custom_items)


def generate_procurement_report(
    resolution: "RobotComponentResolution",
) -> ProcurementResult:
    """
    Generate a procurement report from component resolution.

    Args:
        resolution: The resolved robot components

    Returns:
        ProcurementResult with vendor items, custom items, and estimates
    """
    result = ProcurementResult()
    total_cost = 0.0
    has_unknown_cost = False

    # Process joint resolutions
    for joint_name, joint_res in resolution.joint_resolutions.items():
        # Add unresolved items
        result.unresolved_items.extend(joint_res.unresolved_items)

        # Add vendor parts
        for part in joint_res.vendor_parts:
            item = ProcurementItem(
                name=part.name,
                quote=VendorQuote(
                    sku=part.sku,
                    vendor=part.vendor,
                    description=part.name,
                    unit_price_usd=part.unit_price_usd,
                    in_stock=part.in_stock,
                ),
            )
            result.vendor_items.append(item)
            if part.unit_price_usd:
                total_cost += part.unit_price_usd
            else:
                has_unknown_cost = True

        # Add custom parts
        for part in joint_res.custom_parts:
            item = ProcurementItem(
                name=part.name,
                is_custom=True,
                custom_part=part,
            )
            result.custom_items.append(item)
            if part.estimated_cost_usd:
                total_cost += part.estimated_cost_usd
            else:
                has_unknown_cost = True

    # Process link resolutions
    for link_name, link_res in resolution.link_resolutions.items():
        for part in link_res.custom_parts:
            item = ProcurementItem(
                name=part.name,
                is_custom=True,
                custom_part=part,
            )
            result.custom_items.append(item)
            if part.estimated_cost_usd:
                total_cost += part.estimated_cost_usd
            else:
                has_unknown_cost = True

        for part in link_res.vendor_parts:
            item = ProcurementItem(
                name=part.name,
                quote=VendorQuote(
                    sku=part.sku,
                    vendor=part.vendor,
                    description=part.name,
                ),
            )
            result.vendor_items.append(item)

    # Set total cost
    result.estimated_total_usd = total_cost if not has_unknown_cost else None

    # Calculate confidence
    total = result.total_items + len(result.unresolved_items)
    if total > 0:
        resolved_ratio = result.total_items / total
        result.confidence = resolved_ratio
    else:
        result.confidence = 1.0

    return result


__all__ = [
    "PartQuery",
    "VendorQuote",
    "ProcurementItem",
    "ProcurementResult",
    "generate_procurement_report",
]
