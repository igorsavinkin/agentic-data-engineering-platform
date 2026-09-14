"""Typed response models for the Best Buy Products API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class BestBuyCategoryPath(BaseModel):
    """Represents a single category in the category path hierarchy."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Category identifier")
    name: str = Field(..., description="Category display name")


class BestBuyProduct(BaseModel):
    """Typed model for a Best Buy product record from the Products API v1.

    Maps the key fields needed for canonical ProductObservationPayload while
    preserving source-specific details inside this boundary.
    """

    model_config = ConfigDict(extra="forbid")

    sku: int = Field(..., description="Best Buy SKU / product identifier")
    name: str = Field(..., description="Product name/title")
    salePrice: Optional[float] = Field(None, description="Current sale price")
    regularPrice: Optional[float] = Field(None, description="Regular/list price")
    manufacturer: Optional[str] = Field(None, description="Manufacturer/brand")
    modelNumber: Optional[str] = Field(None, description="Manufacturer model number")
    categoryPath: Optional[list[dict[str, Any]]] = Field(
        None, description="Category hierarchy as list of {id, name} dicts"
    )
    url: Optional[str] = Field(None, description="Product detail page URL")
    image: Optional[str] = Field(None, description="Product image URL")
    customerReviewCount: Optional[int] = Field(None, description="Number of customer reviews")
    customerReviewAverage: Optional[float] = Field(None, description="Average review rating (0-5)")
    inStoreAvailability: Optional[bool] = Field(None, description="Available in physical stores")
    onlineAvailability: Optional[bool] = Field(None, description="Available for online purchase")
    releaseDate: Optional[str] = Field(None, description="Product release date (YYYY-MM-DD)")
