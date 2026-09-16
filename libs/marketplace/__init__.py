"""Marketplace listing and seller models with identity mapping utilities.

This package provides generic, source-agnostic models for marketplace
concepts (listings, sellers) and deterministic identity-mapping helpers.
Source-specific structures remain behind the adapter boundary; only
stable identity fields appear here.

The relationship model is:

    Source  1 ─── * Listing  * ─── 1 Seller (optional)
                      │
                      └── product_key (optional logical grouping)

Multiple listings from the same or different sellers can represent one
logical product via ``product_key``.  Non-marketplace sources continue
to use ``external_id`` without marketplace fields.
"""

from __future__ import annotations

from libs.marketplace.identity import (
    ListingProductMapper,
    build_listing_id,
    build_product_key,
    build_seller_id,
    listing_id_to_external_id,
)
from libs.marketplace.listing import MarketplaceListing
from libs.marketplace.seller import Seller

__all__ = [
    "ListingProductMapper",
    "MarketplaceListing",
    "Seller",
    "build_listing_id",
    "build_product_key",
    "build_seller_id",
    "listing_id_to_external_id",
]
