"""Typed response models for the Fake Store API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FakeStoreRating(BaseModel):
    """Nested rating object in Fake Store product response."""

    model_config = ConfigDict(extra="forbid")

    rate: float = Field(..., description="Average rating value")
    count: int = Field(..., description="Number of ratings")


class FakeStoreProduct(BaseModel):
    """Raw product response from Fake Store API /products endpoint."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., description="Source-level product identifier")
    title: str = Field(..., description="Product name/title")
    price: float = Field(..., description="Product price")
    description: str = Field(..., description="Product description")
    category: str = Field(..., description="Product category")
    image: Optional[str] = Field(None, description="Product image URL")
    rating: Optional[FakeStoreRating] = Field(None, description="Product rating info")
