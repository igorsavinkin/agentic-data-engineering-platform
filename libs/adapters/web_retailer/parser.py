"""HTML parser for books.toscrape.com product listing pages.

All CSS selectors and HTML-structure knowledge is confined to this module.
No HTML-specific code may leak into the adapter, event contracts, or
downstream consumers.
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
    "\u00a3": "GBP",
    "$": "USD",
    "\u20ac": "EUR",
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


def parse_listing_page(
    html: str, page_url: str = ""
) -> tuple[list[ParsedProduct], list[dict[str, Any]]]:
    """Parse a books.toscrape.com listing page into ParsedProduct records.

    Returns ``(products, malformed)`` where malformed contains articles that
    could not be parsed (missing required fields) with a diagnostic reason.
    Returns empty lists when the page has no product articles.
    """
    if not html or not html.strip():
        return [], []

    tree = HTMLParser(html)
    category = _extract_category(tree)
    products: list[ParsedProduct] = []
    malformed: list[dict[str, Any]] = []

    for article in tree.css("article.product_pod"):
        try:
            product, reason = _parse_article(article, page_url, category)
            if product is not None:
                products.append(product)
            elif reason is not None:
                malformed.append(reason)
        except Exception:
            logger.warning("Skipping unparseable product article", exc_info=True)

    return products, malformed


def _extract_category(tree: HTMLParser) -> str:
    """Extract the page-level category from the breadcrumb."""
    items = tree.css("ul.breadcrumb > li")
    if not items:
        return "Books"
    labels = [item.text(strip=True) for item in items]
    labels = [label for label in labels if label and label.lower() != "home"]
    return labels[-1] if labels else "Books"


def _parse_article(
    article: Any, page_url: str, category: str
) -> tuple[ParsedProduct | None, dict[str, Any] | None]:
    """Parse a single <article class='product_pod'> element.

    Returns ``(product, None)`` on success or ``(None, malformed_entry)``
    when required fields are missing.
    """
    title_link = article.css_first("h3 a")
    if title_link is None:
        return None, {
            "raw_record": {"html_snippet": str(article.html)[:200]},
            "reason": "Missing h3 a element",
        }

    name = title_link.attributes.get("title") or ""
    name = name.strip()

    relative_url = title_link.attributes.get("href") or ""
    url = _resolve_url(relative_url, page_url)

    if not name and not relative_url:
        return None, {
            "raw_record": {"html_snippet": str(article.html)[:200]},
            "reason": "Missing name and URL",
        }
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

    price_text = _get_text(article, "p.price_color")
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

    For URLs like ``slug-name_123/index.html``, returns ``slug-name_123``.
    For URLs like ``product.html``, returns ``product``.
    """
    if not url:
        return ""
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2 and parts[-1] == "index.html":
        return parts[-2]
    if parts:
        slug = parts[-1]
        if slug.endswith(".html"):
            slug = slug[:-5]
        if slug:
            return slug
    return ""


def _parse_price(text: str) -> tuple[Decimal | None, str]:
    """Parse a price string like '£51.77' into (Decimal, currency_code).

    Returns (None, 'GBP') when the text is empty or unparseable.
    """
    if not text or not text.strip():
        return None, "GBP"

    currency = "GBP"
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
    """Map availability element to canonical Availability enum value.

    Text content is the primary signal; CSS classes are a fallback.
    """
    el = article.css_first("p.availability")
    if el is None:
        return "unknown"

    text = el.text(strip=True).lower()

    if "in stock" in text:
        return "in_stock"
    if "out of stock" in text:
        return "out_of_stock"
    if "preorder" in text or "pre-order" in text:
        return "preorder"

    classes = el.attributes.get("class", "")
    if "instock" in classes:
        return "in_stock"

    return "unknown"
