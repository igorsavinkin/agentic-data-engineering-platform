"""Pydantic models for web retailer product data.

TASK-046: Placeholder models. HTML parsing and field extraction belong to TASK-047.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WebRetailerProduct(BaseModel):
    """Minimal product model for web retailer HTML extraction.

    Fields will be populated from HTML parsing in TASK-047.
    """

    model_config = ConfigDict(extra="ignore")

    product_id: str
    name: str
    price: float | None = None
    currency: str = "GBP"
    availability: str = "unknown"
    category: str = "uncategorized"
    url: str = ""
