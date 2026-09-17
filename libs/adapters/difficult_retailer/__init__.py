"""Difficult retailer source adapter (TASK-051).

Implements SourceAdapterProtocol for a high-traffic retailer that exhibits
challenging collection behaviors: bot detection, rate limiting, service
unavailability, structural page changes, and partial parseability.
"""

from libs.adapters.difficult_retailer.adapter import DifficultRetailerAdapter

__all__ = ["DifficultRetailerAdapter"]
