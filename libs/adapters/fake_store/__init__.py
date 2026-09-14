"""Fake Store API adapter package."""

from libs.adapters.fake_store.adapter import FakeStoreAdapter
from libs.adapters.fake_store.client import FakeStoreClient
from libs.adapters.fake_store.models import FakeStoreProduct, FakeStoreRating

__all__ = [
    "FakeStoreAdapter",
    "FakeStoreClient",
    "FakeStoreProduct",
    "FakeStoreRating",
]
