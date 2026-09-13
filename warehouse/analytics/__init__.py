"""Analytical SQL queries for the warehouse (TASK-032).

Provides parameterized, tested SQL queries demonstrating PostgreSQL
capabilities: CTEs, ROW_NUMBER, RANK, LAG, rolling averages, and more.

All queries use explicit timezone semantics and return stable/typed result shapes.
No unsafe identifier interpolation — only parameterized values.
"""

from warehouse.analytics.queries import (
    cte_analytical_query,
    latest_observation_per_product,
    latest_record_selection,
    price_change_analysis,
    product_price_history,
    products_ranked_by_price_increase,
    rolling_average_query,
    source_statistics_summary,
)

__all__ = [
    "latest_observation_per_product",
    "product_price_history",
    "price_change_analysis",
    "products_ranked_by_price_increase",
    "latest_record_selection",
    "rolling_average_query",
    "source_statistics_summary",
    "cte_analytical_query",
]
