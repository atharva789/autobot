"""
TDD tests for Phase 4: Procurement stack.

Tests for vendor API interfaces and quote generation.
"""

import pytest
from packages.pipeline.procurement import (
    ProcurementResult,
    PartQuery,
    VendorQuote,
    generate_procurement_report,
)
from packages.pipeline.procurement.providers.digikey import DigiKeyProvider
from packages.pipeline.procurement.providers.mcmaster import McMasterProvider
from packages.pipeline.components.catalog_models import (
    ComponentCategory,
    VendorPart,
    CustomPart,
)
from packages.pipeline.components.slot_resolver import (
    resolve_robot_components,
)
from packages.pipeline.ir.design_ir import (
    RobotDesignIR,
    LinkIR,
    JointIR,
    JointType,
    ActuatorSlot,
)


class TestPartQuery:
    """Tests for part query construction."""

    def test_query_from_sku(self):
        """Can create query from SKU."""
        query = PartQuery(sku="902-0135-000", vendor="Robotis")
        assert query.sku == "902-0135-000"

    def test_query_from_description(self):
        """Can create query from description."""
        query = PartQuery(
            description="M3x10 socket head cap screw",
            category=ComponentCategory.STRUCTURAL,
        )
        assert query.description is not None


class TestVendorProviders:
    """Tests for vendor API providers."""

    def test_digikey_provider_exists(self):
        """DigiKey provider is available."""
        provider = DigiKeyProvider()
        assert provider.name == "DigiKey"

    def test_mcmaster_provider_exists(self):
        """McMaster provider is available."""
        provider = McMasterProvider()
        assert provider.name == "McMaster-Carr"

    def test_provider_search_returns_results(self):
        """Provider search returns VendorQuote list."""
        provider = DigiKeyProvider()
        query = PartQuery(
            description="10K resistor 0805",
            category=ComponentCategory.ELECTRONICS,
        )
        results = provider.search(query, limit=5)
        assert isinstance(results, list)
        # May be empty in mock mode

    def test_provider_lookup_by_sku(self):
        """Provider can lookup by SKU."""
        provider = DigiKeyProvider()
        quote = provider.lookup("311-10KARCT-ND")
        # Returns quote or None
        assert quote is None or isinstance(quote, VendorQuote)


class TestVendorQuote:
    """Tests for vendor quote structure."""

    def test_quote_has_price(self):
        """Quote includes price information."""
        quote = VendorQuote(
            sku="ABC-123",
            vendor="TestVendor",
            description="Test Part",
            unit_price_usd=9.99,
            quantity_available=100,
        )
        assert quote.unit_price_usd == 9.99

    def test_quote_has_availability(self):
        """Quote includes availability."""
        quote = VendorQuote(
            sku="ABC-123",
            vendor="TestVendor",
            description="Test Part",
            unit_price_usd=9.99,
            quantity_available=0,
            in_stock=False,
        )
        assert quote.in_stock is False


class TestProcurementReport:
    """Tests for procurement report generation."""

    def test_generate_report_from_resolution(self):
        """Can generate procurement report from component resolution."""
        ir = RobotDesignIR(
            name="test_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                    actuator=ActuatorSlot(actuator_type="servo", max_torque=10.0),
                )
            ],
        )
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        assert isinstance(report, ProcurementResult)
        assert report.total_items > 0

    def test_report_separates_vendor_and_custom(self):
        """Report separates vendor parts from custom."""
        ir = RobotDesignIR(
            name="mixed_robot",
            links=[
                LinkIR(name="base"),
                LinkIR(name="custom_link", is_custom_part=True),
            ],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="custom_link",
                    actuator=ActuatorSlot(actuator_type="servo"),
                )
            ],
        )
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        assert len(report.vendor_items) > 0 or len(report.custom_items) > 0

    def test_report_includes_unresolved(self):
        """Report flags unresolved items."""
        ir = RobotDesignIR(
            name="exotic_robot",
            links=[LinkIR(name="base"), LinkIR(name="link")],
            joints=[
                JointIR(
                    name="hydraulic_joint",
                    joint_type=JointType.PRISMATIC,
                    parent_link="base",
                    child_link="link",
                    actuator=ActuatorSlot(
                        actuator_type="hydraulic",
                        max_torque=1000.0,
                    ),
                )
            ],
        )
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        # Hydraulic should be unresolved
        assert len(report.unresolved_items) > 0

    def test_report_estimates_total_cost(self):
        """Report includes cost estimate."""
        ir = RobotDesignIR(
            name="simple_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                    actuator=ActuatorSlot(actuator_type="servo", max_torque=5.0),
                )
            ],
        )
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        # Should have some cost estimate
        assert report.estimated_total_usd is None or report.estimated_total_usd >= 0


class TestProcurementConfidence:
    """Tests for procurement confidence scoring."""

    def test_high_confidence_all_resolved(self):
        """High confidence when all parts resolved."""
        ir = RobotDesignIR(
            name="standard_robot",
            links=[LinkIR(name="base"), LinkIR(name="arm")],
            joints=[
                JointIR(
                    name="j1",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="arm",
                    actuator=ActuatorSlot(actuator_type="servo", max_torque=10.0),
                )
            ],
        )
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        assert report.confidence >= 0.5  # At least medium confidence

    def test_low_confidence_with_unresolved(self):
        """Lower confidence with unresolved items."""
        ir = RobotDesignIR(
            name="exotic_robot",
            links=[LinkIR(name="base"), LinkIR(name="link")],
            joints=[
                JointIR(
                    name="exotic_joint",
                    joint_type=JointType.REVOLUTE,
                    parent_link="base",
                    child_link="link",
                    actuator=ActuatorSlot(actuator_type="hydraulic", max_torque=500.0),
                )
            ],
        )
        resolution = resolve_robot_components(ir)
        report = generate_procurement_report(resolution)

        # Should have lower confidence
        assert report.confidence < 1.0
