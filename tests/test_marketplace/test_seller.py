"""Tests for the generic Seller model (TASK-042)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.marketplace.seller import Seller

# ---------------------------------------------------------------------------
# Construction and field validation
# ---------------------------------------------------------------------------


def test_seller_minimal_construction() -> None:
    """A seller requires only seller_id and source."""
    seller = Seller(seller_id="s-001", source="ebay")
    assert seller.seller_id == "s-001"
    assert seller.source == "ebay"
    assert seller.display_name is None
    assert seller.metadata == {}


def test_seller_full_construction() -> None:
    """All fields can be provided at construction."""
    seller = Seller(
        seller_id="s-001",
        source="ebay",
        display_name="TopSeller",
        metadata={"feedback_score": 1234, "positive_pct": 99.5},
    )
    assert seller.display_name == "TopSeller"
    assert seller.metadata["feedback_score"] == 1234


def test_seller_empty_seller_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Seller(seller_id="", source="ebay")
    assert "seller_id" in str(exc_info.value)


def test_seller_empty_source_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Seller(seller_id="s-001", source="")
    assert "source" in str(exc_info.value)


def test_seller_strips_whitespace() -> None:
    """str_strip_whitespace trims leading/trailing spaces."""
    seller = Seller(seller_id="  s-001  ", source="  ebay  ")
    assert seller.seller_id == "s-001"
    assert seller.source == "ebay"


def test_seller_is_frozen() -> None:
    """Frozen model prevents mutation after creation."""
    seller = Seller(seller_id="s-001", source="ebay")
    with pytest.raises(ValidationError):
        seller.seller_id = "s-002"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Qualified ID
# ---------------------------------------------------------------------------


def test_qualified_id() -> None:
    seller = Seller(seller_id="s-001", source="ebay")
    assert seller.qualified_id == "ebay:s-001"


def test_qualified_id_is_deterministic() -> None:
    a = Seller(seller_id="s-001", source="ebay")
    b = Seller(seller_id="s-001", source="ebay")
    assert a.qualified_id == b.qualified_id


# ---------------------------------------------------------------------------
# Equality (frozen Pydantic models use structural equality)
# ---------------------------------------------------------------------------


def test_seller_equality() -> None:
    a = Seller(seller_id="s-001", source="ebay")
    b = Seller(seller_id="s-001", source="ebay")
    assert a == b


def test_seller_inequality_different_id() -> None:
    a = Seller(seller_id="s-001", source="ebay")
    b = Seller(seller_id="s-002", source="ebay")
    assert a != b


def test_seller_inequality_different_source() -> None:
    a = Seller(seller_id="s-001", source="ebay")
    b = Seller(seller_id="s-001", source="other")
    assert a != b


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_seller_serialization_round_trip() -> None:
    seller = Seller(
        seller_id="s-001",
        source="ebay",
        display_name="TopSeller",
        metadata={"score": 100},
    )
    data = seller.model_dump()
    restored = Seller.model_validate(data)
    assert restored == seller


def test_seller_json_round_trip() -> None:
    seller = Seller(
        seller_id="s-001",
        source="ebay",
        display_name="TopSeller",
    )
    json_str = seller.model_dump_json()
    restored = Seller.model_validate_json(json_str)
    assert restored == seller
