"""
Catalog models for robot components.

Defines the data structures for:
- Vendor parts (off-the-shelf components with SKUs)
- Custom parts (manufactured components)
- Component stacks (full resolution of a joint/link)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class ComponentCategory(str, Enum):
    """Categories of robot components."""
    STRUCTURAL = "structural"
    ACTUATION = "actuation"
    TRANSMISSION = "transmission"
    JOINT_SUPPORT = "joint_support"
    ELECTRONICS = "electronics"
    SENSORS = "sensors"
    WIRING = "wiring"
    PRINTED_CUSTOM = "printed_custom"
    MACHINED_CUSTOM = "machined_custom"


@dataclass(frozen=True)
class VendorPart:
    """An off-the-shelf part from a vendor."""
    name: str
    sku: str
    vendor: str
    category: ComponentCategory
    unit_price_usd: float | None = None
    datasheet_url: str | None = None
    cad_url: str | None = None
    in_stock: bool = True
    lead_time_days: int | None = None

    @property
    def is_custom(self) -> bool:
        return False


@dataclass(frozen=True)
class CustomPart:
    """A part that must be manufactured."""
    name: str
    category: ComponentCategory
    manufacturing_method: Literal["3d_print", "cnc", "laser_cut", "sheet_metal", "cast"]
    material: str
    estimated_cost_usd: float | None = None
    cad_file: str | None = None
    print_time_hours: float | None = None

    @property
    def is_custom(self) -> bool:
        return True

    @property
    def sku(self) -> None:
        """Custom parts don't have SKUs."""
        return None


@dataclass
class ActuatorSpec:
    """Specification for an actuator."""
    part: VendorPart | CustomPart
    max_torque_nm: float = 10.0
    max_velocity_rad_s: float = 6.28
    continuous_torque_nm: float | None = None
    gear_ratio: float = 1.0
    encoder_resolution: int | None = None
    control_interface: Literal["pwm", "can", "rs485", "ethernet"] = "pwm"


@dataclass
class TransmissionSpec:
    """Specification for a transmission."""
    type: Literal["direct", "belt", "gear", "harmonic", "cycloidal", "cable"]
    gear_ratio: float = 1.0
    efficiency: float = 0.95
    backlash_deg: float = 0.0
    parts: list[VendorPart | CustomPart] = field(default_factory=list)


@dataclass
class BearingSpec:
    """Specification for bearings/joint support."""
    type: Literal["ball", "roller", "needle", "plain", "magnetic"]
    inner_diameter_mm: float
    outer_diameter_mm: float
    part: VendorPart | None = None


@dataclass
class ComponentStack:
    """
    Complete component resolution for a joint.

    Every actuated joint must have:
    - actuator (motor/servo)
    - transmission (direct or geared)
    - bearings/support (optional but common)
    - mounting hardware (fasteners)
    """
    actuator: ActuatorSpec | None = None
    transmission: TransmissionSpec | None = None
    bearings: list[BearingSpec] = field(default_factory=list)
    fasteners: list[VendorPart] = field(default_factory=list)
    custom_mounts: list[CustomPart] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Check if stack has minimum required components."""
        if self.actuator is None:
            return False
        if self.transmission is None:
            return False
        return True

    @property
    def total_cost_usd(self) -> float | None:
        """Estimate total cost if all prices known."""
        total = 0.0
        parts = []

        if self.actuator:
            parts.append(self.actuator.part)
        if self.transmission:
            parts.extend(self.transmission.parts)
        for bearing in self.bearings:
            if bearing.part:
                parts.append(bearing.part)
        parts.extend(self.fasteners)
        parts.extend(self.custom_mounts)

        for part in parts:
            if isinstance(part, VendorPart) and part.unit_price_usd:
                total += part.unit_price_usd
            elif isinstance(part, CustomPart) and part.estimated_cost_usd:
                total += part.estimated_cost_usd
            else:
                return None  # Unknown price

        return total


@dataclass
class LinkComponents:
    """Component resolution for a link."""
    structural_parts: list[VendorPart | CustomPart] = field(default_factory=list)
    sensors: list[VendorPart] = field(default_factory=list)
    electronics: list[VendorPart] = field(default_factory=list)

    @property
    def has_custom_parts(self) -> bool:
        return any(p.is_custom for p in self.structural_parts)

    @property
    def has_vendor_parts(self) -> bool:
        return any(not p.is_custom for p in self.structural_parts)

    @property
    def custom_parts(self) -> list[CustomPart]:
        return [p for p in self.structural_parts if isinstance(p, CustomPart)]

    @property
    def vendor_parts(self) -> list[VendorPart]:
        return [p for p in self.structural_parts if isinstance(p, VendorPart)]
