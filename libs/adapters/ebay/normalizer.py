"""Normalization utilities for eBay seller/listing data.

This module transforms eBay-specific response models into the generic
``Seller`` and ``MarketplaceListing`` marketplace models defined in
TASK-042.  Normalization is deterministic, idempotent, and separated
from HTTP I/O so that it can be unit-tested without network access.

Design rationale
----------------
* All transformations are pure functions (no side effects) so they can
  be composed inside adapters or downstream processors.
* Missing/partial metadata is handled deterministically rather than
  raising exceptions — this allows partial observations to flow through
  the pipeline with clear diagnostics.
* Distinct sellers/listings are never silently collapsed; identity is
  preserved via qualified IDs (``source:raw_id``).
* Fuzzy product matching is explicitly out of scope — product grouping
  relies on explicit identifiers provided by the source or assigned by
  a separate identity-resolution component.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from libs.adapters.ebay.models import (
    EbayListingSummary,
    EbayPrice,
)
from libs.adapters.ebay.models import (
    EbaySeller as EbaySellerModel,
)
from libs.marketplace.identity import build_seller_id
from libs.marketplace.listing import MarketplaceListing
from libs.marketplace.seller import Seller

# Canonical condition mapping from eBay condition strings to normalized values.
# eBay uses various condition labels; we normalize to a small set that
# downstream consumers can rely on without knowing eBay's taxonomy.
EBAY_CONDITION_MAP: dict[str, str] = {
    "new": "new",
    "brand new": "new",
    "like new": "like_new",
    "excellent": "like_new",
    "very good": "good",
    "good": "good",
    "acceptable": "acceptable",
    "for parts or not working": "for_parts",
    "used": "used",
}


def normalize_ebay_seller(
    ebay_seller: EbaySellerModel | None,
    source: str = "ebay",
) -> Seller | None:
    """Normalize an eBay seller model into the generic ``Seller`` model.

    Parameters
    ----------
    ebay_seller:
        Raw seller data from the eBay API.  May be ``None`` when the
        listing does not expose seller information.
    source:
        Source adapter name.  Defaults to ``"ebay"`` but can be
        overridden for testing or future multi-tenant scenarios.

    Returns
    -------
    Seller | None
        A generic seller instance with stable identity, or ``None`` if
        the input is ``None`` or lacks a username.

    Notes
    -----
    The seller's qualified ID is built as ``"ebay:<username>"`` which
    is stable across observations of the same seller.  Optional fields
    like feedback score are preserved in ``metadata`` for diagnostics
    but do not affect identity.
    """
    if ebay_seller is None:
        return None

    username = ebay_seller.username.strip()
    if not username:
        return None

    # Build deterministic seller identity
    seller_id = build_seller_id(source, username)

    # Collect optional diagnostic metadata
    metadata: dict[str, Any] = {}
    if ebay_seller.feedback_score is not None:
        metadata["feedback_score"] = ebay_seller.feedback_score
    if ebay_seller.feedback_percentage is not None:
        metadata["feedback_percentage"] = ebay_seller.feedback_percentage

    return Seller(
        seller_id=seller_id,
        source=source,
        display_name=username,
        metadata=metadata,
    )


def normalize_price(
    ebay_price: EbayPrice | None,
) -> tuple[Decimal | None, str]:
    """Normalize an eBay price into a canonical ``(amount, currency)`` pair.

    Parameters
    ----------
    ebay_price:
        Raw price object from the eBay API.  May be ``None`` when the
        listing does not provide pricing information.

    Returns
    -------
    tuple[Decimal | None, str]
        A tuple of ``(price_amount, currency_code)``.  When the input
        is ``None`` or invalid, returns ``(None, "USD")`` as a safe
        default.  Currency defaults to USD because eBay.com (the
        primary target) uses USD.

    Notes
    -----
    Price normalization is lenient: invalid or negative prices are
    treated as missing rather than causing the entire observation to
    fail.  This allows partial data to flow through the pipeline.
    """
    if ebay_price is None:
        return None, "USD"

    try:
        amount = Decimal(str(ebay_price.value))
        if amount < 0:
            # Negative prices are nonsensical; treat as missing.
            return None, ebay_price.currency.upper() if ebay_price.currency else "USD"
        return amount, ebay_price.currency.upper() if ebay_price.currency else "USD"
    except (InvalidOperation, ValueError):
        return None, ebay_price.currency.upper() if ebay_price.currency else "USD"


def normalize_condition(
    raw_condition: str | None,
) -> str | None:
    """Normalize an eBay condition string to a canonical value.

    Parameters
    ----------
    raw_condition:
        Raw condition label from the eBay API (e.g. ``"Brand New"``,
        ``"Used"``, ``"For parts or not working"``).

    Returns
    -------
    str | None
        A normalized condition value from the set
        ``{"new", "like_new", "good", "acceptable", "for_parts", "used"}``,
        or ``None`` if the input is unrecognised or missing.

    Notes
    -----
    The mapping is case-insensitive.  Unknown conditions return ``None``
    rather than raising an exception, allowing the observation to
    proceed with incomplete metadata.
    """
    if raw_condition is None:
        return None

    normalized = EBAY_CONDITION_MAP.get(raw_condition.strip().lower())
    return normalized


def normalize_listing_url(
    item_id: str,
    item_web_url: str | None = None,
) -> str:
    """Build a canonical URL for an eBay listing.

    Parameters
    ----------
    item_id:
        The eBay item/listing identifier.
    item_web_url:
        Optional full URL from the eBay API.  When present, this is
        preferred because it may include tracking parameters or regional
        variants.  Falls back to a constructed URL when ``None``.

    Returns
    -------
    str
        A stable URL for the listing.  Prefers the API-provided URL;
        otherwise constructs ``"https://www.ebay.com/itm/<item_id>"``.
    """
    if item_web_url:
        return item_web_url.strip()
    return f"https://www.ebay.com/itm/{item_id}"


def normalize_listing(
    summary: EbayListingSummary,
    source: str = "ebay",
    product_key: str | None = None,
) -> MarketplaceListing:
    """Normalize an eBay listing summary into a generic ``MarketplaceListing``.

    This is the core normalization function for TASK-043.  It transforms
    an eBay-specific listing summary into the source-agnostic marketplace
    model while preserving all diagnostic information.

    Parameters
    ----------
    summary:
        Raw listing summary from the eBay Browse API.
    source:
        Source adapter name.  Defaults to ``"ebay"``.
    product_key:
        Optional logical product key for grouping multiple listings of
        the same product.  When ``None``, the listing remains ungrouped
        until a downstream identity-resolution component assigns one.

    Returns
    -------
    MarketplaceListing
        A generic listing with:
        * Stable ``listing_id`` (``"ebay:<item_id>"``)
        * Normalized ``seller`` (if available)
        * Exact ``price`` and ``currency`` (or ``None``/``"USD"`` default)
        * Normalized ``condition`` in metadata
        * Deterministic ``url``
        * Availability inferred from the availability object

    Notes
    -----
    * The listing ID is deterministic: the same ``item_id`` always
      produces the same qualified ID.
    * Seller normalization is delegated to ``normalize_ebay_seller``.
    * Price/currency normalization handles missing or invalid values
      gracefully.
    * Condition is normalized to a small canonical set and stored in
      ``metadata`` to avoid coupling downstream consumers to eBay's
      taxonomy.
    * Availability is inferred from the ``availability.is_in_stock``
      property and stored in ``metadata`` for diagnostics.
    """
    # Build stable listing identity (use raw item_id; MarketplaceListing.qualified_id
    # will prepend the source automatically)
    listing_id = summary.item_id

    # Normalize seller (may be None)
    seller = normalize_ebay_seller(summary.seller, source=source)

    # Normalize price and currency
    price, currency = normalize_price(summary.price)

    # Normalize URL
    url = normalize_listing_url(summary.item_id, summary.item_web_url)

    # Normalize condition
    condition = normalize_condition(summary.condition)

    # Build metadata with diagnostic information
    metadata: dict[str, Any] = {}
    if condition is not None:
        metadata["condition"] = condition
    if summary.availability is not None:
        metadata["availability_raw"] = summary.availability.is_in_stock
    if summary.category_ids:
        # Store the most specific category for reference
        metadata["category_id"] = summary.category_ids[-1]

    # Include raw price info for diagnostics when price was valid
    if price is not None and summary.price is not None:
        metadata["price_original"] = float(summary.price.value)

    return MarketplaceListing(
        listing_id=listing_id,
        source=source,
        seller=seller,
        product_key=product_key,
        title=summary.title.strip(),
        url=url,
        metadata=metadata,
    )


def normalize_listing_with_product_key(
    summary: EbayListingSummary,
    mapper: Any | None = None,
    source: str = "ebay",
) -> MarketplaceListing:
    """Normalize a listing and attempt to assign a product key.

    This variant attempts to look up or assign a product key using an
    optional ``ListingProductMapper``.  If no mapper is provided, the
    listing is returned without a product key (same as
    ``normalize_listing``).

    Parameters
    ----------
    summary:
        Raw listing summary from the eBay Browse API.
    mapper:
        Optional ``ListingProductMapper`` instance for looking up or
        assigning product keys.  When ``None``, the listing remains
        ungrouped.
    source:
        Source adapter name.

    Returns
    -------
    MarketplaceListing
        A normalized listing, potentially with a ``product_key`` if the
        mapper could resolve one.

    Notes
    -----
    Product key assignment is NOT fuzzy matching.  It relies on explicit
    identifiers already stored in the mapper (e.g. from prior
    observations or manual curation).  This keeps the normalization
    layer deterministic and testable.
    """
    # First normalize without a product key
    listing = normalize_listing(summary, source=source)

    # Attempt to resolve or assign a product key
    if mapper is not None:
        qualified_id = listing.qualified_id
        existing_key = mapper.get_product_key(qualified_id)

        if existing_key is not None:
            # Rebuild listing with the resolved product key
            listing = MarketplaceListing(
                listing_id=listing.listing_id,
                source=listing.source,
                seller=listing.seller,
                product_key=existing_key,
                title=listing.title,
                url=listing.url,
                metadata=listing.metadata,
            )

    return listing
