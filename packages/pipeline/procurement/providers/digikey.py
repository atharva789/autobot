"""
DigiKey API provider.

In production, this would use the DigiKey API:
https://developer.digikey.com/products/product-information-v4/partsearch

For now, this is a mock implementation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from packages.pipeline.procurement.providers.base import VendorProvider

if TYPE_CHECKING:
    from packages.pipeline.procurement import PartQuery, VendorQuote


# Mock catalog for testing
DIGIKEY_CATALOG = {
    "311-10KARCT-ND": {
        "description": "RES 10K OHM 1% 1/8W 0805",
        "unit_price_usd": 0.10,
        "quantity_available": 50000,
    },
    "LM7805CT-ND": {
        "description": "IC REG LINEAR 5V 1.5A TO220",
        "unit_price_usd": 0.89,
        "quantity_available": 2500,
    },
    "296-1395-5-ND": {
        "description": "IC MCU 32BIT 256KB FLASH 64LQFP",
        "unit_price_usd": 8.50,
        "quantity_available": 1200,
    },
}


class DigiKeyProvider(VendorProvider):
    """DigiKey electronics vendor provider."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("DIGIKEY_API_KEY")

    @property
    def name(self) -> str:
        return "DigiKey"

    def search(self, query: "PartQuery", limit: int = 10) -> list["VendorQuote"]:
        """Search DigiKey catalog."""
        from packages.pipeline.procurement import VendorQuote

        results = []

        # Mock search - in production would call API
        if query.description:
            search_term = query.description.lower()
            for sku, data in DIGIKEY_CATALOG.items():
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
        """Look up a DigiKey part number."""
        from packages.pipeline.procurement import VendorQuote

        data = DIGIKEY_CATALOG.get(sku)
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
