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
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
