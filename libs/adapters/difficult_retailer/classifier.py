"""Response classification for difficult source HTTP responses.

Difficult sources return more than just success/failure. The client must
distinguish between product pages, bot-detection challenges, rate-limit
responses, maintenance pages, and other non-product responses. This module
provides the classification types used by the client and surfaced through
SourceFetchError to downstream consumers.
"""

from __future__ import annotations

from enum import StrEnum


class ResponseKind(StrEnum):
    """Classification of an HTTP response from a difficult source.

    These categories let downstream consumers (retry strategies, degradation
    detectors) make source-aware decisions rather than treating all failures
    identically.
    """

    SUCCESS = "success"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    STRUCTURAL_CHANGE = "structural_change"
    UNKNOWN_ERROR = "unknown_error"


_BLOCK_INDICATORS = (
    "captcha",
    "robot check",
    "are you a human",
    "bot detection",
    "access denied",
    "verify you are human",
)

_UNAVAILABLE_INDICATORS = (
    "service unavailable",
    "under maintenance",
    "temporarily unavailable",
    "we'll be back",
    "sorry for the inconvenience",
)


def classify_response(status_code: int, body: str) -> ResponseKind:
    """Classify an HTTP response into a ResponseKind.

    Uses status code as the primary signal and body content as secondary
    signal for ambiguous cases (e.g. 200 with a CAPTCHA page).
    """
    if status_code == 429:
        return ResponseKind.RATE_LIMITED

    if status_code == 503:
        return ResponseKind.UNAVAILABLE

    if status_code == 403:
        body_lower = body.lower()
        if any(indicator in body_lower for indicator in _BLOCK_INDICATORS):
            return ResponseKind.BLOCKED
        return ResponseKind.BLOCKED

    if status_code == 200:
        body_lower = body.lower()
        if any(indicator in body_lower for indicator in _BLOCK_INDICATORS):
            return ResponseKind.BLOCKED
        if any(indicator in body_lower for indicator in _UNAVAILABLE_INDICATORS):
            return ResponseKind.UNAVAILABLE

    if status_code >= 400:
        return ResponseKind.UNKNOWN_ERROR

    return ResponseKind.SUCCESS
