"""Generic MarketplaceListing model.

A MarketplaceListing represents one seller's offer for a logical product
within a marketplace.  Multiple listings may exist for the same product
(different sellers, conditions, or prices).  The listing carries enough
identity information for downstream components to track historical
observations without confusing one listing for another.

Source-specific listing details remain behind the adapter boundary.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from libs.marketplace.seller import Seller


class MarketplaceListing(BaseModel):
    """Source-agnostic marketplace listing.

    Parameters
    ----------
    listing_id:
        Stable identifier for this listing within a given source.
        For many adapters this equals ``external_id`` from the
        canonical event, but the two concepts are deliberately
        separated so that non-marketplace sources can keep using
        ``external_id`` as a plain product identifier.
    source:
        Source adapter that produced this listing.
    seller:
        The seller offering this listing.  Optional because some
        sources may not expose seller information.
    product_key:
        Optional logical product identifier that groups multiple
        listings of the same product.  When ``None``, downstream
        identity resolution has not yet assigned a product grouping.
    title:
        Listing title or name.
    url:
        Canonical URL for this listing.
    metadata:
        Opaque source-specific listing attributes (e.g. condition,
        shipping info).  Kept as a dictionary to avoid coupling
        downstream consumers to source-specific schemas.
    """

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    listing_id: str = Field(
        ...,
        min_length=1,
        description="Stable listing identifier within a source.",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Source adapter that produced this listing.",
    )
    seller: Seller | None = Field(
        default=None,
        description="Seller offering this listing.",
    )
    product_key: str | None = Field(
        default=None,
        description="Logical product key grouping multiple listings.",
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Listing title or name.",
    )
    url: str = Field(
        ...,
        min_length=1,
        description="Canonical URL for this listing.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Opaque source-specific listing attributes.",
    )

    @property
    def qualified_id(self) -> str:
        """Return a globally unique listing key: ``source:listing_id``."""
        return f"{self.source}:{self.listing_id}"
