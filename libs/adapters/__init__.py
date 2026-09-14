"""Source adapter interface and shared ingestion contract.

This package defines the protocol that every external source adapter must
implement to emit canonical product-observation events into the platform
pipeline.  Source-specific response models never leak beyond this boundary.
"""

from libs.adapters.mock import MockSourceAdapter
from libs.adapters.protocol import (
    FetchResult,
    MalformedRecordError,
    SourceAdapterProtocol,
    SourceFetchError,
)

__all__ = [
    "FetchResult",
    "MalformedRecordError",
    "MockSourceAdapter",
    "SourceAdapterProtocol",
    "SourceFetchError",
]
