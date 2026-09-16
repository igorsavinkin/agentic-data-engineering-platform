"""Web retailer source adapter package.

Targets books.toscrape.com — a realistic bookstore with standard e-commerce
product pages (name, price, availability, category) served as plain HTML
without bot protection or JavaScript rendering requirements.
"""

from libs.adapters.web_retailer.adapter import WebRetailerAdapter
from libs.adapters.web_retailer.client import WebRetailerClient
from libs.adapters.web_retailer.models import WebRetailerProduct

__all__ = ["WebRetailerAdapter", "WebRetailerClient", "WebRetailerProduct"]
