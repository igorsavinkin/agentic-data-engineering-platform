"""Identity mapping utilities for marketplace listings.

This module provides deterministic helpers for building stable identifiers
for listings and sellers, and for mapping between listings and logical
product keys.

Design rationale
----------------
* ``build_listing_id`` and ``build_seller_id`` produce deterministic
  qualified identifiers from ``(source, raw_id)`` pairs.  Determinism
  is important for replay and idempotent processing: the same source
  record must always produce the same identity.
* ``ListingProductMapper`` maintains an in-memory mapping from listing
  qualified IDs to logical product keys.  It is intentionally simple
  (a dictionary) so that it can be used inside adapters, the processor,
  or tests without external dependencies.  Persistent storage of the
  mapping is a downstream concern (warehouse / data-lake layer).
* Product key derivation prefers explicit/stable identifiers (UPC, EAN,
  ASIN, GTIN) over title-based heuristics. When no explicit identifier
  exists, listings remain unmapped rather than being merged by similarity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def build_listing_id(source: str, raw_listing_id: str) -> str:
    """Build a globally unique listing identifier.

    Parameters
    ----------
    source:
        Source adapter name (e.g. ``"ebay"``).
    raw_listing_id:
        Source-level listing identifier.

    Returns
    -------
    str
        ``"source:raw_listing_id"`` — stable across restarts and replays.

    Raises
    ------
    ValueError
        If either argument is empty.
    """
    if not source:
        raise ValueError("source must be non-empty")
    if not raw_listing_id:
        raise ValueError("raw_listing_id must be non-empty")
    return f"{source}:{raw_listing_id}"


def build_seller_id(source: str, raw_seller_id: str) -> str:
    """Build a globally unique seller identifier.

    Parameters
    ----------
    source:
        Source adapter name.
    raw_seller_id:
        Source-level seller identifier.

    Returns
    -------
    str
        ``"source:raw_seller_id"`` — stable across restarts and replays.

    Raises
    ------
    ValueError
        If either argument is empty.
    """
    if not source:
        raise ValueError("source must be non-empty")
    if not raw_seller_id:
        raise ValueError("raw_seller_id must be non-empty")
    return f"{source}:{raw_seller_id}"


def build_product_key(source: str, product_identifier: str) -> str:
    """Build a logical product key for grouping listings.

    For non-marketplace sources the product key typically equals
    ``source:external_id``.  For marketplace sources the product key
    groups multiple listings that refer to the same logical product.

    Parameters
    ----------
    source:
        Source adapter name.
    product_identifier:
        Source-level product identifier (e.g. UPC, ASIN, or a
        normalised title hash).

    Returns
    -------
    str
        ``"source:product_identifier"`` — stable across restarts.

    Raises
    ------
    ValueError
        If either argument is empty.
    """
    if not source:
        raise ValueError("source must be non-empty")
    if not product_identifier:
        raise ValueError("product_identifier must be non-empty")
    return f"{source}:{product_identifier}"


# Standard product identifier keys commonly found in listing metadata.
# Ordered by preference: GTIN (most universal) > UPC/EAN > ASIN (Amazon-specific).
_PRODUCT_ID_KEYS = [
    "gtin",
    "upc",
    "ean",
    "isbn",
    "asin",
    "mpn",  # Manufacturer Part Number (less reliable but sometimes available)
]

# Regex patterns for validating common product identifier formats.
_GTIN_PATTERNS = {
    "gtin": re.compile(r"^\d{8,14}$"),  # GTIN-8/12/13/14: variable digit length
    "upc": re.compile(r"^\d{12}$"),  # UPC-A: 12 digits
    "ean": re.compile(r"^\d{13}$"),  # EAN-13: 13 digits
    "isbn": re.compile(r"^(?:97[89])?\d{9}[\dX]$"),  # ISBN-10/13
    "asin": re.compile(r"^[A-Z0-9]{10}$"),  # Amazon ASIN: 10 alphanumeric
    "mpn": re.compile(r"^[A-Za-z0-9\-_.]{4,30}$"),  # MPN: 4-30 alphanumeric with hyphens/dots
}


def extract_product_identifier_from_metadata(
    metadata: dict[str, Any],
) -> tuple[str, str] | None:
    """Extract a product identifier from listing metadata.

    Scans metadata for standard product identifier fields (GTIN, UPC, EAN,
    ISBN, ASIN, MPN) and returns the first valid identifier found, along
    with its type. Validation uses format-specific regex patterns to reject
    malformed values.

    This function implements the TASK-044 requirement to prefer explicit/
    stable identifiers over fuzzy matching. When no valid identifier exists,
    it returns None rather than attempting title-based heuristics.

    Parameters
    ----------
    metadata:
        Listing metadata dictionary, potentially containing product
        identifier fields like "upc", "ean", "asin", etc.

    Returns
    -------
    tuple[str, str] | None
        ``(identifier_type, value)`` if a valid identifier is found,
        e.g. ``("upc", "012345678905")``, or ``None`` if no valid
        identifier exists.

    Examples
    --------
    >>> extract_product_identifier_from_metadata({"upc": "012345678905"})
    ('upc', '012345678905')
    >>> extract_product_identifier_from_metadata({"title": "Widget"})
    None
    >>> extract_product_identifier_from_metadata({"upc": "invalid"})
    None
    """
    if not isinstance(metadata, dict):
        return None

    for key in _PRODUCT_ID_KEYS:
        value = metadata.get(key)
        if value is None:
            continue

        # Normalize to string for validation
        value_str = str(value).strip()
        if not value_str:
            continue

        # Validate against format-specific pattern
        pattern = _GTIN_PATTERNS.get(key)
        if pattern is not None and not pattern.match(value_str):
            # Invalid format — skip this identifier
            continue

        # Found a valid identifier
        return key, value_str

    return None


def derive_product_key_from_listing(
    source: str,
    listing_id: str,
    metadata: dict[str, Any],
) -> str | None:
    """Derive a product key from a normalized listing.

    Attempts to extract an explicit product identifier from the listing's
    metadata and builds a deterministic product key. If no valid identifier
    exists, returns None — the listing remains unmapped rather than being
    merged by title similarity.

    This implements the core TASK-044 principle: ambiguous matches must
    remain unresolved/separate.

    Parameters
    ----------
    source:
        Source adapter name (e.g. "ebay", "bestbuy").
    listing_id:
        Qualified listing ID (for logging/debugging purposes).
    metadata:
        Normalized listing metadata, potentially containing product
        identifiers.

    Returns
    -------
    str | None
        Product key like ``"ebay:UPC-012345678905"`` if an explicit
        identifier is found, or ``None`` if the listing should remain
        unmapped.

    Examples
    --------
    >>> derive_product_key_from_listing(
    ...     "ebay", "ebay:12345", {"upc": "012345678905"}
    ... )
    'ebay:012345678905'
    >>> derive_product_key_from_listing("ebay", "ebay:12345", {})
    None
    """
    result = extract_product_identifier_from_metadata(metadata)
    if result is None:
        return None

    identifier_type, value = result
    # Use the raw identifier value as the product key component
    # (not prefixed with type, to keep keys concise)
    return build_product_key(source, value)


def listing_id_to_external_id(qualified_listing_id: str) -> tuple[str, str]:
    """Decompose a qualified listing ID back into ``(source, raw_id)``.

    Parameters
    ----------
    qualified_listing_id:
        A string of the form ``"source:raw_id"``.

    Returns
    -------
    tuple[str, str]
        ``(source, raw_listing_id)``.

    Raises
    ------
    ValueError
        If the string does not contain exactly one colon separator
        or either part is empty.
    """
    parts = qualified_listing_id.split(":", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"invalid qualified listing id: {qualified_listing_id!r}; "
            "expected format 'source:raw_id'"
        )
    return parts[0], parts[1]


@dataclass
class ListingProductMapper:
    """In-memory mapper from listing qualified IDs to logical product keys.

    The mapper is deliberately a simple dictionary so that it can be used
    inside adapters, the processor, or tests without external dependencies.
    Persistence of the mapping is a downstream concern.

    Thread safety is not guaranteed; callers that require concurrent access
    must provide their own synchronisation.

    Examples
    --------
    >>> mapper = ListingProductMapper()
    >>> mapper.assign("ebay:12345", "ebay:UPC-0001")
    >>> mapper.get_product_key("ebay:12345")
    'ebay:UPC-0001'
    >>> mapper.get_listing_ids("ebay:UPC-0001")
    {'ebay:12345'}
    """

    _listing_to_product: dict[str, str] = field(default_factory=dict)
    _product_to_listings: dict[str, set[str]] = field(default_factory=dict)

    def assign(self, qualified_listing_id: str, product_key: str) -> None:
        """Assign a listing to a logical product.

        Parameters
        ----------
        qualified_listing_id:
            Globally unique listing ID (``"source:raw_id"``).
        product_key:
            Logical product key grouping this listing with others.

        Raises
        ------
        ValueError
            If either argument is empty.
        """
        if not qualified_listing_id:
            raise ValueError("qualified_listing_id must be non-empty")
        if not product_key:
            raise ValueError("product_key must be non-empty")

        # Remove any previous assignment for this listing.
        old_product = self._listing_to_product.get(qualified_listing_id)
        if old_product is not None and old_product != product_key:
            old_listings = self._product_to_listings.get(old_product)
            if old_listings is not None:
                old_listings.discard(qualified_listing_id)
                if not old_listings:
                    del self._product_to_listings[old_product]

        self._listing_to_product[qualified_listing_id] = product_key
        self._product_to_listings.setdefault(product_key, set()).add(qualified_listing_id)

    def get_product_key(self, qualified_listing_id: str) -> str | None:
        """Return the product key for a listing, or ``None`` if unmapped."""
        return self._listing_to_product.get(qualified_listing_id)

    def get_listing_ids(self, product_key: str) -> set[str]:
        """Return all listing IDs assigned to a product key.

        Returns an empty set when the product key is unknown.
        """
        return set(self._product_to_listings.get(product_key, set()))

    def has_listing(self, qualified_listing_id: str) -> bool:
        """Whether a listing has been assigned to any product."""
        return qualified_listing_id in self._listing_to_product

    def has_product(self, product_key: str) -> bool:
        """Whether any listing has been assigned to this product."""
        return product_key in self._product_to_listings

    @property
    def listing_count(self) -> int:
        """Number of mapped listings."""
        return len(self._listing_to_product)

    @property
    def product_count(self) -> int:
        """Number of distinct product keys."""
        return len(self._product_to_listings)

    def clear(self) -> None:
        """Remove all mappings."""
        self._listing_to_product.clear()
        self._product_to_listings.clear()
