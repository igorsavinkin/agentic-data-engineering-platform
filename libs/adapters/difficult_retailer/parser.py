"""HTML parser for a difficult retailer product listing pages.

Handles structural variations gracefully: when expected CSS selectors are
absent, returns empty results rather than crashing. Detects structural
changes (missing expected containers) so the adapter can report them.

All CSS selectors and HTML-structure knowledge is confined to this module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

_CURRENCY_SYMBOLS: dict[str, str] = {
    "$": "USD",
    "\u20ac": "EUR",
    "\u00a3": "GBP",
}

_THOUSANDS_RE = re.compile(r"(?<=\d)[,.](?=\d{3}(?:[^\d]|$))")


@dataclass(frozen=True)
class ParsedProduct:
    """Intermediate representation of a product extracted from HTML."""

    product_id: str
    name: str
    price: Decimal | None
    currency: str
    availability: str
    category: str
    url: str


@dataclass(frozen=True)
class ParseResult:
    """Result of parsing a difficult retailer listing page.

    Attributes
    ----------
    products:
        Successfully parsed products.
    malformed:
        Records that could not be parsed with diagnostic reasons.
    structural_change:
        True when expected page containers are missing, indicating the
        source may have changed its HTML structure.
    """

    products: list[ParsedProduct]
    malformed: list[dict[str, Any]]
    structural_change: bool


def parse_listing_page(html: str, page_url: str = "") -> ParseResult:
    """Parse a difficult retailer listing page.

    Returns a ParseResult with products, malformed records, and a flag
    indicating whether the page structure has changed unexpectedly.
    """
    if not html or not html.strip():
        return ParseResult(products=[], malformed=[], structural_change=False)

    tree = HTMLParser(html)

    product_grid = tree.css_first("div.product-grid, div.product-list, ol.product-list")
    if product_grid is None:
        articles = tree.css("article.product-card, div.product-card, li.product-item")
        if not articles:
            return ParseResult(products=[], malformed=[], structural_change=True)
    else:
        articles = product_grid.css("article.product-card, div.product-card, li.product-item")

    if not articles:
        return ParseResult(products=[], malformed=[], structural_change=False)

    category = _extract_category(tree)
    products: list[ParsedProduct] = []
    malformed: list[dict[str, Any]] = []

    for article in articles:
        try:
            product, reason = _parse_article(article, page_url, category)
            if product is not None:
                products.append(product)
            elif reason is not None:
                malformed.append(reason)
        except Exception:
            logger.warning("Skipping unparseable product card", exc_info=True)

    return ParseResult(
        products=products,
        malformed=malformed,
        structural_change=False,
    )


def _extract_category(tree: HTMLParser) -> str:
    """Extract the page-level category from breadcrumb or heading."""
    for selector in ("ul.breadcrumb > li", "nav.breadcrumb > li"):
        items = tree.css(selector)
        if items:
            labels = [item.text(strip=True) for item in items]
            labels = [label for label in labels if label and label.lower() != "home"]
            if labels:
                return labels[-1]

    nav = tree.css_first("nav.breadcrumb")
    if nav is not None:
        spans = nav.css("span")
        if spans:
            last = spans[-1].text(strip=True)
            if last:
                return last

    heading = tree.css_first("h1.category-title, h1.page-title")
    if heading:
        text = heading.text(strip=True)
        if text:
            return text

    return "General"


def _parse_article(
    article: Any, page_url: str, category: str
) -> tuple[ParsedProduct | None, dict[str, Any] | None]:
    """Parse a single product card element.

    Returns (product, None) on success or (None, malformed_entry) when
    required fields are missing.
    """
    name_el = article.css_first("h2.product-name a, h3.product-name a, a.product-link")
    if name_el is None:
        name_el = article.css_first("h2 a, h3 a")

    if name_el is None:
        return None, {
            "raw_record": {"html_snippet": str(article.html)[:200]},
            "reason": "Missing product name link",
        }

    name = name_el.attributes.get("title") or name_el.text(strip=True) or ""
    name = name.strip()

    relative_url = name_el.attributes.get("href") or ""
    url = _resolve_url(relative_url, page_url)

    if not name:
        return None, {
            "raw_record": {"html_snippet": str(article.html)[:200], "url": url},
            "reason": "Missing product name",
        }
    if not url:
        return None, {
            "raw_record": {"name": name, "html_snippet": str(article.html)[:200]},
            "reason": "Missing product URL",
        }

    product_id = _extract_product_id(relative_url)
    if not product_id:
        product_id = name.lower().replace(" ", "-")[:80]

    price_text = _get_text(article, "span.price, p.price, span.product-price, data.price")
    if not price_text:
        price_el = article.css_first("[data-price]")
        if price_el is not None:
            price_text = price_el.attributes.get("data-price", "")

    price, currency = _parse_price(price_text)
    availability = _parse_availability(article)

    return ParsedProduct(
        product_id=product_id,
        name=name,
        price=price,
        currency=currency,
        availability=availability,
        category=category,
        url=url,
    ), None


def _get_text(node: Any, selector: str) -> str:
    """Get stripped text from the first matching element, or empty string."""
    el = node.css_first(selector)
    if el is None:
        return ""
    return str(el.text(strip=True))


def _resolve_url(relative_url: str, page_url: str) -> str:
    """Resolve a relative product URL against the page URL."""
    if not relative_url:
        return ""
    if relative_url.startswith(("http://", "https://")):
        return relative_url
    if not page_url:
        return relative_url
    return urljoin(page_url, relative_url)


def _extract_product_id(url: str) -> str:
    """Derive a stable product identifier from the URL path.

    For URLs like ``/product/12345-slug``, returns ``12345``.
    For URLs like ``/product/12345``, returns ``12345``.
    """
    if not url:
        return ""
    parts = url.rstrip("/").split("/")
    last = parts[-1] if parts else ""
    if not last:
        return ""

    id_part = last.split("-")[0] if "-" in last else last
    if id_part.isdigit():
        return id_part

    return last


def _parse_price(text: str) -> tuple[Decimal | None, str]:
    """Parse a price string like '$29.99' into (Decimal, currency_code).

    Returns (None, 'USD') when the text is empty or unparseable.
    """
    if not text or not text.strip():
        return None, "USD"

    currency = "USD"
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            currency = code
            break

    cleaned = text.strip()
    for symbol in _CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()

    if not cleaned:
        return None, currency

    cleaned = _THOUSANDS_RE.sub("", cleaned)

    try:
        return Decimal(cleaned), currency
    except InvalidOperation:
        return None, currency


def _parse_availability(article: Any) -> str:
    """Map availability indicators to canonical values.

    Checks text content first, then CSS classes, then data attributes.
    """
    avail_el = article.css_first("span.availability, p.availability, span.stock-status")
    if avail_el is not None:
        text = avail_el.text(strip=True).lower()
        if "in stock" in text or "available" in text:
            return "in_stock"
        if "out of stock" in text or "unavailable" in text:
            return "out_of_stock"
        if "preorder" in text or "pre-order" in text or "coming soon" in text:
            return "preorder"

    for selector in ("span.in-stock", "span.available", "[data-available='true']"):
        if article.css_first(selector) is not None:
            return "in_stock"
    for selector in (
        "span.out-of-stock",
        "span.unavailable",
        "[data-available='false']",
    ):
        if article.css_first(selector) is not None:
            return "out_of_stock"

    return "unknown"
