"""eBay Browse API source adapter package.

This package provides the eBay adapter implementation that fetches product
listings from the eBay Browse API and emits canonical ProductObservationEvent
instances into the platform pipeline.

Usage:
    from libs.adapters.ebay import EbayAdapter

    adapter = EbayAdapter(query="laptop", limit=50)
    result = await adapter.fetch()
    for event in result.events:
        # Publish to Kafka
        pass
    await adapter.close()
"""

from libs.adapters.ebay.adapter import EbayAdapter
from libs.adapters.ebay.client import EbayClient
from libs.adapters.ebay.models import (
    EbayListingSummary,
    EbaySearchResponse,
)

__all__ = [
    "EbayAdapter",
    "EbayClient",
    "EbayListingSummary",
    "EbaySearchResponse",
]
