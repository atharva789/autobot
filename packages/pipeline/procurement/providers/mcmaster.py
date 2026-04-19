"""
McMaster-Carr API provider.

In production, this would use the McMaster-Carr API:
https://www.mcmaster.com/help/api/

For now, this is a mock implementation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from packages.pipeline.procurement.providers.base import VendorProvider

if TYPE_CHECKING:
    from packages.pipeline.procurement import PartQuery, VendorQuote


# Mock catalog for testing
MCMASTER_CATALOG = {
    "91292A113": {
        "description": "Socket Head Cap Screw M3 x 10mm, 18-8 SS",
        "unit_price_usd": 0.15,
        "quantity_available": 10000,
    },
    "91292A115": {
        "description": "Socket Head Cap Screw M3 x 16mm, 18-8 SS",
        "unit_price_usd": 0.18,
        "quantity_available": 8500,
    },
    "6061K13": {
        "description": "Aluminum 6061-T6 Rod, 1/4\" Diameter, 12\" Long",
        "unit_price_usd": 3.50,
        "quantity_available": 500,
    },
    "57155K374": {
        "description": "Ball Bearing, 8mm ID x 22mm OD x 7mm Wide",
        "unit_price_usd": 8.75,
        "quantity_available": 1200,
    },
}


class McMasterProvider(VendorProvider):
    """McMaster-Carr mechanical/structural vendor provider."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("MCMASTER_API_KEY")

    @property
    def name(self) -> str:
        return "McMaster-Carr"

    def search(self, query: "PartQuery", limit: int = 10) -> list["VendorQuote"]:
        """Search McMaster-Carr catalog."""
        from packages.pipeline.procurement import VendorQuote

        results = []

        # Mock search - in production would call API
        if query.description:
            search_term = query.description.lower()
            for sku, data in MCMASTER_CATALOG.items():
                if search_term in data["description"].lower():
                    results.append(
                        VendorQuote(
                            sku=sku,
                            vendor=self.name,
                            description=data["description"],
                            unit_price_usd=data["unit_price_usd"],
                            quantity_available=data["quantity_available"],
                            in_stock=data["quantity_available"] > 0,
                        )
                    )
                    if len(results) >= limit:
                        break

        return results

    def lookup(self, sku: str) -> "VendorQuote | None":
        """Look up a McMaster-Carr part number."""
        from packages.pipeline.procurement import VendorQuote

        data = MCMASTER_CATALOG.get(sku)
        if data is None:
            return None

        return VendorQuote(
            sku=sku,
            vendor=self.name,
            description=data["description"],
            unit_price_usd=data["unit_price_usd"],
            quantity_available=data["quantity_available"],
            in_stock=data["quantity_available"] > 0,
        )
