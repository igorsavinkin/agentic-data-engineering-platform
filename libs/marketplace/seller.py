"""Generic Seller model for marketplace sources.

A Seller represents the entity offering a listing in a marketplace.
This model is source-agnostic: source-specific seller details (e.g.
eBay feedback scores) remain behind the adapter boundary.  Only the
stable identity fields needed for downstream observation and grouping
appear here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Seller(BaseModel):
    """Source-agnostic seller identity.

    Parameters
    ----------
    seller_id:
        Stable identifier for the seller within a given source.
        Must be non-empty and should not change across observations
        of the same seller.
    source:
        Source adapter that provided this seller record.  Matches the
        ``source`` field on observation events.
    display_name:
        Human-readable seller name.  Optional because some sources
        do not expose a meaningful display name.
    metadata:
        Source-specific seller attributes (e.g. rating, join date).
        Kept as an opaque dictionary so that downstream consumers are
        not forced to depend on source-specific schemas.
    """

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    seller_id: str = Field(
        ...,
        min_length=1,
        description="Stable seller identifier within a source.",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Source adapter that provided this seller.",
    )
    display_name: str | None = Field(
        default=None,
        description="Human-readable seller name.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Opaque source-specific seller attributes.",
    )

    @property
    def qualified_id(self) -> str:
        """Return a globally unique seller key: ``source:seller_id``."""
        return f"{self.source}:{self.seller_id}"
