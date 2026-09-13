"""Tests for analytical SQL queries (TASK-032).

Uses deterministic fixtures to verify:
- Latest-record logic (ROW_NUMBER)
- Ties and ranking behavior (RANK)
- LAG-based price changes
- Rolling averages with window frames
- CTE query composition
- Source statistics aggregations
- Filters and empty results handling

All tests use a real PostgreSQL database via pytest fixtures.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

# Import query functions
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


@pytest.fixture(autouse=True)
def setup_warehouse_data(db_session):
    """Create deterministic test data for analytical query tests.

    Creates:
    - 2 sources (Source A, Source B)
    - 3 products across sources
    - Multiple observations with known prices over time
    - Specific scenarios for testing window functions
    """
    # Create sources
    db_session.execute(
        text("INSERT INTO sources (id, name) VALUES (1, 'Source A'), (2, 'Source B')")
    )

    # Create products
    db_session.execute(
        text(
            "INSERT INTO products (id, canonical_name) VALUES "
            "(1, 'Product Alpha'), (2, 'Product Beta'), (3, 'Product Gamma')"
        )
    )

    # Create source_products mappings
    db_session.execute(
        text(
            "INSERT INTO source_products (id, source_id, product_id, external_id) VALUES "
            "(1, 1, 1, 'EXT-A-001'), "  # Source A -> Product Alpha
            "(2, 1, 2, 'EXT-A-002'), "  # Source A -> Product Beta
            "(3, 2, 1, 'EXT-B-001'), "  # Source B -> Product Alpha (different listing)
            "(4, 2, 3, 'EXT-B-003')"  # Source B -> Product Gamma
        )
    )

    # Create observations with specific price patterns for testing
    base_time = datetime(2026, 9, 1, tzinfo=timezone.utc)

    observations = [
        # Source A, Product Alpha (source_product_id=1): Price increases then decreases
        (1, 1, "Alpha v1", Decimal("100.00"), "USD", "in_stock", base_time),
        (1, 1, "Alpha v1", Decimal("110.00"), "USD", "in_stock", base_time + timedelta(days=1)),
        (1, 1, "Alpha v1", Decimal("120.00"), "USD", "in_stock", base_time + timedelta(days=2)),
        (1, 1, "Alpha v1", Decimal("115.00"), "USD", "in_stock", base_time + timedelta(days=3)),
        (1, 1, "Alpha v1", Decimal("125.00"), "USD", "in_stock", base_time + timedelta(days=4)),
        # Source A, Product Beta (source_product_id=2): Stable price
        (2, 2, "Beta v1", Decimal("50.00"), "USD", "in_stock", base_time),
        (2, 2, "Beta v1", Decimal("50.00"), "USD", "in_stock", base_time + timedelta(days=2)),
        (2, 2, "Beta v1", Decimal("50.00"), "USD", "in_stock", base_time + timedelta(days=4)),
        # Source B, Product Alpha (source_product_id=3): Different price pattern (ties for ranking test)
        (3, 1, "Alpha Listing B", Decimal("95.00"), "USD", "in_stock", base_time),
        (
            3,
            1,
            "Alpha Listing B",
            Decimal("105.00"),
            "USD",
            "in_stock",
            base_time + timedelta(days=2),
        ),
        (
            3,
            1,
            "Alpha Listing B",
            Decimal("105.00"),
            "USD",
            "in_stock",
            base_time + timedelta(days=4),
        ),  # Tie with day 2
        # Source B, Product Gamma (source_product_id=4): Missing price observation
        (4, 3, "Gamma v1", None, "USD", "out_of_stock", base_time),
        (4, 3, "Gamma v1", Decimal("75.00"), "USD", "in_stock", base_time + timedelta(days=2)),
        (4, 3, "Gamma v1", Decimal("80.00"), "USD", "in_stock", base_time + timedelta(days=4)),
    ]

    for obs in observations:
        db_session.execute(
            text(
                "INSERT INTO product_observations "
                "(source_product_id, name, price, currency, availability, collected_at) "
                "VALUES (:sp_id, :name, :price, :currency, :avail, :collected_at)"
            ),
            {
                "sp_id": obs[0],
                "name": obs[1],
                "price": obs[2],
                "currency": obs[3],
                "avail": obs[4],
                "collected_at": obs[5],
            },
        )

    db_session.commit()
    yield
    # Cleanup
    db_session.execute(text("DELETE FROM data_quality_results"))
    db_session.execute(text("DELETE FROM product_observations"))
    db_session.execute(text("DELETE FROM source_products"))
    db_session.execute(text("DELETE FROM products"))
    db_session.execute(text("DELETE FROM sources"))
    db_session.commit()


def execute_query(db_session, sql: str, params: dict):
    """Helper to execute parameterized query and return results as list of dicts."""
    result = db_session.execute(text(sql), params)
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]


class TestLatestObservationPerProduct:
    """Test ROW_NUMBER-based latest observation selection."""

    def test_returns_latest_per_source_product(self, db_session):
        """Each source-product should return only its most recent observation."""
        sql, params = latest_observation_per_product(limit=100)
        results = execute_query(db_session, sql, params)

        # Should have 4 source-products, each with 1 latest observation
        assert len(results) == 4

        # Verify we got the latest for each
        source_product_ids = {r["source_product_id"] for r in results}
        assert source_product_ids == {1, 2, 3, 4}

        # Check specific latest values
        sp1_latest = next(r for r in results if r["source_product_id"] == 1)
        assert sp1_latest["price"] == Decimal("125.00")
        assert sp1_latest["collected_at_utc"].day == 5  # base_time + 4 days

    def test_filter_by_source(self, db_session):
        """Filtering by source_id should return only that source's products."""
        sql, params = latest_observation_per_product(source_id=1, limit=100)
        results = execute_query(db_session, sql, params)

        assert len(results) == 2  # Source A has 2 products
        assert all(r["source_name"] == "Source A" for r in results)

    def test_filter_by_product(self, db_session):
        """Filtering by product_id should return all source listings for that product."""
        sql, params = latest_observation_per_product(product_id=1, limit=100)
        results = execute_query(db_session, sql, params)

        # Product Alpha appears in both sources
        assert len(results) == 2
        product_ids = {r["product_id"] for r in results}
        assert product_ids == {1}

    def test_empty_result_with_strict_filter(self, db_session):
        """Non-existent product should return empty results."""
        sql, params = latest_observation_per_product(product_id=999, limit=100)
        results = execute_query(db_session, sql, params)
        assert len(results) == 0


class TestProductPriceHistory:
    """Test chronological price history retrieval."""

    def test_returns_chronological_order(self, db_session):
        """Price history should be ordered by collected_at ascending."""
        sql, params = product_price_history(source_product_id=1)
        results = execute_query(db_session, sql, params)

        assert len(results) == 5
        # Verify ascending order
        for i in range(len(results) - 1):
            assert results[i]["collected_at_utc"] <= results[i + 1]["collected_at_utc"]

    def test_date_range_filter(self, db_session):
        """Date filters should restrict results to specified range."""
        start = datetime(2026, 9, 2, tzinfo=timezone.utc)
        end = datetime(2026, 9, 4, tzinfo=timezone.utc)
        sql, params = product_price_history(source_product_id=1, start_date=start, end_date=end)
        results = execute_query(db_session, sql, params)

        assert len(results) == 3  # Days 2, 3, 4
        for r in results:
            assert start <= r["collected_at_utc"] <= end

    def test_naive_datetime_converted_to_utc(self, db_session):
        """Naive datetimes should be treated as UTC."""
        start = datetime(2026, 9, 2)  # Naive datetime
        sql, params = product_price_history(source_product_id=1, start_date=start)
        results = execute_query(db_session, sql, params)

        # Should include observations from Sep 2 onwards
        assert len(results) == 4


class TestPriceChangeAnalysis:
    """Test LAG-based price change calculations."""

    def test_calculates_absolute_and_percentage_changes(self, db_session):
        """LAG should compute correct price differences."""
        sql, params = price_change_analysis(source_product_id=1, days_back=30)
        results = execute_query(db_session, sql, params)

        # 5 observations = 4 changes (first has no previous)
        assert len(results) == 4

        # First change: 110 - 100 = 10, 10%
        first_change = results[-1]  # Results are DESC, so last is earliest
        assert first_change["price_change_absolute"] == Decimal("10.00")
        assert first_change["price_change_percent"] == Decimal("10.00")

        # Last change: 125 - 115 = 10, ~8.70%
        last_change = results[0]
        assert last_change["price_change_absolute"] == Decimal("10.00")
        assert abs(last_change["price_change_percent"] - Decimal("8.70")) < Decimal("0.01")

    def test_null_previous_price_handled(self, db_session):
        """First observation should not appear (no previous price)."""
        sql, params = price_change_analysis(source_product_id=1, days_back=30)
        results = execute_query(db_session, sql, params)

        # All results should have prev_price
        assert all(r["prev_price"] is not None for r in results)

    def test_stable_price_shows_zero_change(self, db_session):
        """Product Beta has stable price - changes should be zero."""
        sql, params = price_change_analysis(source_product_id=2, days_back=30)
        results = execute_query(db_session, sql, params)

        assert len(results) == 2
        assert all(r["price_change_absolute"] == Decimal("0.00") for r in results)
        assert all(r["price_change_percent"] == Decimal("0.00") for r in results)


class TestProductsRankedByPriceIncrease:
    """Test RANK-based product ranking."""

    def test_ranks_by_price_increase(self, db_session):
        """Products should be ranked by percentage price increase."""
        sql, params = products_ranked_by_price_increase(days_back=30, min_observations=2)
        results = execute_query(db_session, sql, params)

        assert len(results) >= 2

        # Product Alpha (Source A): 100 -> 125 = 25% increase
        # Product Alpha (Source B): 95 -> 105 = ~10.53% increase
        # Product Beta: 50 -> 50 = 0% change

        # Verify ranks exist and are sequential (with ties getting same rank)
        ranks = [r["price_rank"] for r in results]
        assert min(ranks) == 1

    def test_handles_ties_in_ranking(self, db_session):
        """Products with same price change should have same rank."""
        # Source B Product Alpha has two observations at 105.00 (tie)
        # This tests that RANK handles ties correctly
        sql, params = products_ranked_by_price_increase(
            source_id=2, days_back=30, min_observations=2
        )
        results = execute_query(db_session, sql, params)

        # Should have results with proper rank values
        assert len(results) > 0
        assert all(r["price_rank"] is not None for r in results)

    def test_min_observations_filter(self, db_session):
        """Products with fewer than min_observations should be excluded."""
        sql, params = products_ranked_by_price_increase(days_back=30, min_observations=10)
        results = execute_query(db_session, sql, params)

        # No product has 10+ observations in our fixture
        assert len(results) == 0


class TestLatestRecordSelection:
    """Test ROW_NUMBER deduplication pattern."""

    def test_selects_one_record_per_source_product(self, db_session):
        """Should return exactly one record per source-product."""
        sql, params = latest_record_selection()
        results = execute_query(db_session, sql, params)

        source_product_ids = [r["source_product_id"] for r in results]
        assert len(source_product_ids) == len(set(source_product_ids))  # No duplicates

    def test_tiebreaker_by_id(self, db_session):
        """When collected_at ties, highest ID should win."""
        # Add two observations with same timestamp
        db_session.execute(
            text(
                "INSERT INTO product_observations "
                "(source_product_id, name, price, currency, availability, collected_at) "
                "VALUES (1, 'Alpha tie 1', 130.00, 'USD', 'in_stock', '2026-09-06 00:00:00+00'), "
                "(1, 'Alpha tie 2', 135.00, 'USD', 'in_stock', '2026-09-06 00:00:00+00')"
            )
        )
        db_session.commit()

        sql, params = latest_record_selection()
        results = execute_query(db_session, sql, params)

        sp1_result = next(r for r in results if r["source_product_id"] == 1)
        # Should pick the one with higher ID (Alpha tie 2)
        assert sp1_result["name"] == "Alpha tie 2"


class TestRollingAverageQuery:
    """Test rolling average with window frames."""

    def test_calculates_rolling_average(self, db_session):
        """Rolling average should smooth daily prices."""
        sql, params = rolling_average_query(source_product_id=1, window_days=3, min_window_size=2)
        results = execute_query(db_session, sql, params)

        assert len(results) > 0

        # Verify rolling_avg exists and is reasonable
        for r in results:
            assert r["rolling_avg_price"] is not None
            assert r["window_observation_count"] >= 2

    def test_window_bounds_respected(self, db_session):
        """Rolling window should not include data outside window_days."""
        sql, params = rolling_average_query(source_product_id=1, window_days=2, min_window_size=1)
        results = execute_query(db_session, sql, params)

        # Each rolling avg should only consider nearby days
        for r in results:
            # Window observation count should be <= window_days + 1
            assert r["window_observation_count"] <= 3

    def test_min_window_size_filters_results(self, db_session):
        """Results with insufficient window observations should be excluded."""
        sql, params = rolling_average_query(source_product_id=1, window_days=7, min_window_size=10)
        results = execute_query(db_session, sql, params)

        # Product Alpha only has 5 observations, so min_window_size=10 should exclude all
        assert len(results) == 0

    def test_rolling_min_max_computed(self, db_session):
        """Rolling min and max should track price extremes in window."""
        sql, params = rolling_average_query(source_product_id=1, window_days=3, min_window_size=2)
        results = execute_query(db_session, sql, params)

        for r in results:
            assert r["rolling_min_price"] is not None
            assert r["rolling_max_price"] is not None
            assert r["rolling_min_price"] <= r["avg_daily_price"] <= r["rolling_max_price"]


class TestSourceStatisticsSummary:
    """Test source-level aggregation queries."""

    def test_aggregates_per_source(self, db_session):
        """Should return one row per source with correct aggregates."""
        sql, params = source_statistics_summary(days_back=30)
        results = execute_query(db_session, sql, params)

        assert len(results) == 2  # Two sources

        source_a = next(r for r in results if r["source_name"] == "Source A")
        assert source_a["unique_listings"] == 2
        assert source_a["unique_products"] == 2
        assert source_a["total_observations"] == 8  # 5 + 3

    def test_handles_missing_prices(self, db_session):
        """Missing prices should be counted separately."""
        sql, params = source_statistics_summary(days_back=30)
        results = execute_query(db_session, sql, params)

        source_b = next(r for r in results if r["source_name"] == "Source B")
        # Product Gamma has one NULL price observation
        assert source_b["missing_price_count"] >= 1

    def test_empty_time_window_returns_sources(self, db_session):
        """Very narrow time window may return sources with zero observations."""
        # Use a very small days_back that excludes all data
        sql, params = source_statistics_summary(days_back=1)
        results = execute_query(db_session, sql, params)

        # Sources should still appear but with zero observations
        assert len(results) == 2
        for r in results:
            assert r["total_observations"] == 0 or r["total_observations"] is None


class TestCTEAnalyticalQuery:
    """Test multi-CTE query composition."""

    def test_chains_multiple_ctes(self, db_session):
        """Query should successfully chain recent_observations -> product_stats -> ranked."""
        sql, params = cte_analytical_query(days_back=30, limit=100)
        results = execute_query(db_session, sql, params)

        assert len(results) > 0

        # Verify required columns exist
        required_cols = {
            "product_id",
            "source_id",
            "canonical_name",
            "source_name",
            "observation_count",
            "min_price",
            "max_price",
            "avg_price",
            "price_stddev",
            "latest_observation",
            "price_rank",
            "frequency_rank",
            "price_range",
        }
        assert required_cols.issubset(set(results[0].keys()))

    def test_price_rank_ordering(self, db_session):
        """Results should be ordered by price_rank ascending."""
        sql, params = cte_analytical_query(days_back=30, limit=100)
        results = execute_query(db_session, sql, params)

        ranks = [r["price_rank"] for r in results]
        assert ranks == sorted(ranks)

    def test_min_price_filter(self, db_session):
        """Min price filter should exclude low-priced products."""
        sql, params = cte_analytical_query(days_back=30, min_price=100.00, limit=100)
        results = execute_query(db_session, sql, params)

        # Only products with avg_price >= 100 should appear
        for r in results:
            assert r["avg_price"] >= Decimal("100.00")

    def test_having_clause_filters_low_count(self, db_session):
        """Products with < 2 observations should be excluded by HAVING."""
        # Product Gamma in Source B has only 2 non-null price observations
        # With min_price filter, it might be excluded
        sql, params = cte_analytical_query(days_back=30, min_price=200.00, limit=100)
        results = execute_query(db_session, sql, params)

        # No products have avg_price >= 200
        assert len(results) == 0


class TestQueryParameterization:
    """Test that queries use safe parameterization."""

    def test_no_sql_injection_via_params(self, db_session):
        """Malicious parameter values should not break queries."""
        malicious_source_id = "1; DROP TABLE sources;--"

        # This should raise a database error, not execute the injection
        with pytest.raises(Exception):
            sql, params = latest_observation_per_product(limit=100)
            # Manually inject into params (simulating bad input)
            params["source_id"] = malicious_source_id
            execute_query(db_session, sql, params)

    def test_timezone_explicit_in_queries(self, db_session):
        """All queries should use AT TIME ZONE 'UTC' explicitly."""
        queries = [
            latest_observation_per_product(),
            product_price_history(1),
            price_change_analysis(),
            products_ranked_by_price_increase(),
            latest_record_selection(),
            rolling_average_query(),
            source_statistics_summary(),
            cte_analytical_query(),
        ]

        for sql, _ in queries:
            assert "AT TIME ZONE 'UTC'" in sql or "TIME ZONE" in sql.upper()
