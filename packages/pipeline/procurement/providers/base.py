"""Base class for vendor providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.pipeline.procurement import PartQuery, VendorQuote


class VendorProvider(ABC):
    """Abstract base class for vendor API providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Vendor name."""
        ...

    @abstractmethod
    def search(self, query: "PartQuery", limit: int = 10) -> list["VendorQuote"]:
        """
        Search for parts matching query.

        Args:
            query: Part query parameters
            limit: Maximum results to return

        Returns:
            List of matching vendor quotes
        """
        ...

    @abstractmethod
    def lookup(self, sku: str) -> "VendorQuote | None":
        """
        Look up a specific SKU.

        Args:
            sku: The vendor SKU

        Returns:
            VendorQuote if found, None otherwise
        """
        ...
