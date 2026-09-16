"""Typed response models for the eBay Browse API."""

from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class EbayPrice(BaseModel):
    """Price object from eBay Browse API."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    value: float = Field(..., description="Price amount")
    currency: str = Field(..., description="ISO-4217 currency code")


class EbayAvailability(BaseModel):
    """Availability information from eBay listing."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ship_to_location_availability: list[dict] = Field(
        default_factory=list,
        description="Shipping availability by location",
        validation_alias=AliasChoices(
            "shipToLocationAvailability", "ship_to_location_availability"
        ),
    )
    pickup_at_store_availability: list[dict] = Field(
        default_factory=list,
        description="Store pickup availability",
        validation_alias=AliasChoices("pickupAtStoreAvailability", "pickup_at_store_availability"),
    )

    @property
    def is_in_stock(self) -> bool:
        """Check if any shipping or pickup option shows availability."""
        return (
            len(self.ship_to_location_availability) > 0
            or len(self.pickup_at_store_availability) > 0
        )


class EbaySeller(BaseModel):
    """Seller information from eBay listing."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    username: str = Field(..., description="Seller username")
    feedback_score: Optional[int] = Field(
        None,
        description="Seller feedback score",
        validation_alias=AliasChoices("feedbackScore", "feedback_score"),
    )
    feedback_percentage: Optional[float] = Field(
        None,
        description="Positive feedback percentage",
        validation_alias=AliasChoices("positiveFeedbackPercent", "feedback_percentage"),
    )


class EbayImage(BaseModel):
    """Image reference from eBay listing."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    image_url: Optional[str] = Field(
        None,
        description="URL to the product image",
        validation_alias=AliasChoices("imageUrl", "image_url"),
    )


class EbayListingSummary(BaseModel):
    """Summary-level listing data from eBay Browse API search results.

    This represents the lightweight listing summary returned by the
    /browse/v1/item_summary/search endpoint. It contains enough fields
    for basic price/availability observations without full item detail.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    item_id: str = Field(
        ...,
        description="eBay item/listing identifier",
        validation_alias=AliasChoices("itemId", "item_id"),
    )
    title: str = Field(..., description="Listing title")
    price: Optional[EbayPrice] = Field(None, description="Current price")
    condition: Optional[str] = Field(None, description="Item condition")
    item_web_url: Optional[str] = Field(
        None,
        description="URL to the listing on eBay.com",
        validation_alias=AliasChoices("itemWebUrl", "item_web_url"),
    )
    seller: Optional[EbaySeller] = Field(None, description="Seller information")
    image: Optional[EbayImage] = Field(None, description="Primary image")
    availability: Optional[EbayAvailability] = Field(None, description="Availability info")
    category_ids: Optional[list[str]] = Field(
        None,
        description="Category hierarchy IDs",
        validation_alias=AliasChoices("categoryIds", "category_ids"),
    )


class EbaySearchResponse(BaseModel):
    """Top-level response from eBay Browse API item_summary search."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    total: int = Field(..., description="Total number of matching listings")
    item_summaries: list[EbayListingSummary] = Field(
        default_factory=list,
        description="List of listing summaries",
        validation_alias=AliasChoices("itemSummaries", "item_summaries"),
    )
