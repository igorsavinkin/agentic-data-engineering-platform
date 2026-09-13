"""Parameterized analytical SQL queries for warehouse data.

Each function returns a (sql_string, params_dict) tuple suitable for
execution via psycopg or SQLAlchemy text() constructs.

SQL Techniques Demonstrated:
- CTEs (Common Table Expressions)
- ROW_NUMBER() window function
- RANK() window function
- LAG() window function
- Rolling averages via window frames
- Latest-record selection
- Price change calculations (absolute and percentage)
- Source-level statistics

All queries use explicit timezone handling (UTC) and avoid unsafe
identifier interpolation. Only parameterized values are used.
"""

from datetime import datetime, timezone
from typing import Any


def latest_observation_per_product(
    source_id: int | None = None,
    product_id: int | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Get the latest observation for each product using ROW_NUMBER().

    Uses a CTE to partition by source_product_id and select the most recent
    observation based on collected_at timestamp.

    Args:
        source_id: Optional filter by source ID.
        product_id: Optional filter by canonical product ID.
        limit: Maximum number of results to return.

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH latest_observations AS (
        SELECT
            po.id AS observation_id,
            po.source_product_id,
            po.name,
            po.price,
            po.currency,
            po.availability,
            po.collected_at AT TIME ZONE 'UTC' AS collected_at_utc,
            sp.external_id,
            s.name AS source_name,
            p.id AS product_id,
            p.canonical_name,
            ROW_NUMBER() OVER (
                PARTITION BY po.source_product_id
                ORDER BY po.collected_at DESC
            ) AS rn
        FROM product_observations po
        JOIN source_products sp ON po.source_product_id = sp.id
        JOIN sources s ON sp.source_id = s.id
        JOIN products p ON sp.product_id = p.id
        WHERE 1=1
    """

    params: dict[str, Any] = {}

    if source_id is not None:
        sql += " AND sp.source_id = %(source_id)s"
        params["source_id"] = source_id

    if product_id is not None:
        sql += " AND sp.product_id = %(product_id)s"
        params["product_id"] = product_id

    sql += """
    )
    SELECT
        observation_id,
        source_product_id,
        name,
        price,
        currency,
        availability,
        collected_at_utc,
        external_id,
        source_name,
        product_id,
        canonical_name
    FROM latest_observations
    WHERE rn = 1
    ORDER BY collected_at_utc DESC
    LIMIT %(limit)s
    """
    params["limit"] = limit

    return sql, params


def product_price_history(
    source_product_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Get complete price history for a specific source-product listing.

    Returns chronological price observations with explicit UTC timestamps.

    Args:
        source_product_id: The source-specific product listing ID.
        start_date: Optional start date filter (inclusive).
        end_date: Optional end date filter (inclusive).

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    SELECT
        po.id AS observation_id,
        po.name,
        po.price,
        po.currency,
        po.availability,
        po.collected_at AT TIME ZONE 'UTC' AS collected_at_utc
    FROM product_observations po
    WHERE po.source_product_id = %(source_product_id)s
    """

    params: dict[str, Any] = {"source_product_id": source_product_id}

    if start_date is not None:
        # Ensure timezone-aware datetime
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        sql += " AND po.collected_at >= %(start_date)s"
        params["start_date"] = start_date

    if end_date is not None:
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        sql += " AND po.collected_at <= %(end_date)s"
        params["end_date"] = end_date

    sql += """
    ORDER BY po.collected_at ASC
    """

    return sql, params


def price_change_analysis(
    source_product_id: int | None = None,
    days_back: int = 30,
) -> tuple[str, dict[str, Any]]:
    """Calculate absolute and percentage price changes using LAG().

    Compares each observation's price to the previous observation for the
    same source-product, computing both absolute change and percentage change.

    Uses LAG() window function to access the previous row's price value.

    Args:
        source_product_id: Optional filter for specific source-product.
        days_back: Number of days to look back (default 30).

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH price_changes AS (
        SELECT
            po.id AS observation_id,
            po.source_product_id,
            po.name,
            po.price,
            po.currency,
            po.collected_at AT TIME ZONE 'UTC' AS collected_at_utc,
            LAG(po.price) OVER (
                PARTITION BY po.source_product_id
                ORDER BY po.collected_at ASC
            ) AS prev_price,
            sp.external_id,
            s.name AS source_name
        FROM product_observations po
        JOIN source_products sp ON po.source_product_id = sp.id
        JOIN sources s ON sp.source_id = s.id
        WHERE po.collected_at >= (
            NOW() AT TIME ZONE 'UTC' - INTERVAL '%(days_back)s days'
        )
    """

    params: dict[str, Any] = {"days_back": days_back}

    if source_product_id is not None:
        sql += " AND po.source_product_id = %(source_product_id)s"
        params["source_product_id"] = source_product_id

    sql += """
    )
    SELECT
        observation_id,
        source_product_id,
        name,
        price,
        currency,
        collected_at_utc,
        prev_price,
        external_id,
        source_name,
        CASE
            WHEN prev_price IS NOT NULL AND prev_price > 0
            THEN price - prev_price
            ELSE NULL
        END AS price_change_absolute,
        CASE
            WHEN prev_price IS NOT NULL AND prev_price > 0
            THEN ROUND(((price - prev_price) / prev_price * 100)::numeric, 2)
            ELSE NULL
        END AS price_change_percent
    FROM price_changes
    WHERE prev_price IS NOT NULL
    ORDER BY collected_at_utc DESC
    """

    return sql, params


def products_ranked_by_price_increase(
    source_id: int | None = None,
    days_back: int = 30,
    min_observations: int = 2,
    limit: int = 50,
) -> tuple[str, dict[str, Any]]:
    """Rank products by price increase using RANK() window function.

    Calculates the total price change over a time window and ranks products
    by magnitude of increase (or decrease).

    Uses RANK() to handle ties in price change magnitude.

    Args:
        source_id: Optional filter by source.
        days_back: Time window for analysis (default 30 days).
        min_observations: Minimum observations required per product.
        limit: Maximum results to return.

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH price_ranges AS (
        SELECT
            po.source_product_id,
            MIN(po.price) FILTER (WHERE po.collected_at >= (
                NOW() AT TIME ZONE 'UTC' - INTERVAL '%(days_back)s days'
            )) AS min_recent_price,
            MAX(po.price) FILTER (WHERE po.collected_at >= (
                NOW() AT TIME ZONE 'UTC' - INTERVAL '%(days_back)s days'
            )) AS max_recent_price,
            COUNT(*) AS observation_count,
            FIRST_VALUE(po.price) OVER (
                PARTITION BY po.source_product_id
                ORDER BY po.collected_at ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ) AS first_price,
            LAST_VALUE(po.price) OVER (
                PARTITION BY po.source_product_id
                ORDER BY po.collected_at ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ) AS last_price
        FROM product_observations po
        JOIN source_products sp ON po.source_product_id = sp.id
        WHERE po.collected_at >= (
            NOW() AT TIME ZONE 'UTC' - INTERVAL '%(days_back)s days'
        )
    """

    params: dict[str, Any] = {"days_back": days_back}

    if source_id is not None:
        sql += " AND sp.source_id = %(source_id)s"
        params["source_id"] = source_id

    sql += """
        GROUP BY po.source_product_id
    ),
    ranked_products AS (
        SELECT
            pr.source_product_id,
            pr.first_price,
            pr.last_price,
            pr.observation_count,
            CASE
                WHEN pr.first_price IS NOT NULL AND pr.first_price > 0
                THEN ROUND(((pr.last_price - pr.first_price) / pr.first_price * 100)::numeric, 2)
                ELSE NULL
            END AS price_change_percent,
            RANK() OVER (
                ORDER BY
                    CASE
                        WHEN pr.first_price IS NOT NULL AND pr.first_price > 0
                        THEN ((pr.last_price - pr.first_price) / pr.first_price * 100)
                        ELSE 0
                    END DESC
            ) AS price_rank
        FROM price_ranges pr
        WHERE pr.observation_count >= %(min_observations)s
    )
    SELECT
        rp.source_product_id,
        rp.first_price,
        rp.last_price,
        rp.observation_count,
        rp.price_change_percent,
        rp.price_rank,
        sp.external_id,
        s.name AS source_name,
        p.canonical_name
    FROM ranked_products rp
    JOIN source_products sp ON rp.source_product_id = sp.id
    JOIN sources s ON sp.source_id = s.id
    JOIN products p ON sp.product_id = p.id
    ORDER BY rp.price_rank ASC
    LIMIT %(limit)s
    """
    params["min_observations"] = min_observations
    params["limit"] = limit

    return sql, params


def latest_record_selection(
    product_id: int | None = None,
    source_id: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Select latest record per source-product using ROW_NUMBER().

    Similar to latest_observation_per_product but focuses on demonstrating
    the ROW_NUMBER pattern for deduplication/latest-record selection.

    Args:
        product_id: Optional filter by canonical product.
        source_id: Optional filter by source.

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH ranked AS (
        SELECT
            po.id AS observation_id,
            po.source_product_id,
            po.name,
            po.price,
            po.currency,
            po.availability,
            po.collected_at AT TIME ZONE 'UTC' AS collected_at_utc,
            ROW_NUMBER() OVER (
                PARTITION BY po.source_product_id
                ORDER BY po.collected_at DESC, po.id DESC
            ) AS rn
        FROM product_observations po
        JOIN source_products sp ON po.source_product_id = sp.id
        WHERE 1=1
    """

    params: dict[str, Any] = {}

    if product_id is not None:
        sql += " AND sp.product_id = %(product_id)s"
        params["product_id"] = product_id

    if source_id is not None:
        sql += " AND sp.source_id = %(source_id)s"
        params["source_id"] = source_id

    sql += """
    )
    SELECT
        observation_id,
        source_product_id,
        name,
        price,
        currency,
        availability,
        collected_at_utc
    FROM ranked
    WHERE rn = 1
    ORDER BY collected_at_utc DESC
    """

    return sql, params


def rolling_average_query(
    source_product_id: int | None = None,
    window_days: int = 7,
    min_window_size: int = 3,
) -> tuple[str, dict[str, Any]]:
    """Calculate rolling average price over a defined time window.

    Uses window functions with frame specifications to compute moving averages.
    Requires at least min_window_size observations within the window.

    Args:
        source_product_id: Optional filter for specific source-product.
        window_days: Size of the rolling window in days.
        min_window_size: Minimum observations needed for valid average.

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH daily_prices AS (
        SELECT
            po.source_product_id,
            DATE(po.collected_at AT TIME ZONE 'UTC') AS observation_date,
            AVG(po.price) AS avg_daily_price,
            COUNT(*) AS observation_count
        FROM product_observations po
        WHERE po.price IS NOT NULL
    """

    params: dict[str, Any] = {}

    if source_product_id is not None:
        sql += " AND po.source_product_id = %(source_product_id)s"
        params["source_product_id"] = source_product_id

    sql += """
        GROUP BY po.source_product_id, DATE(po.collected_at AT TIME ZONE 'UTC')
    ),
    rolling_avgs AS (
        SELECT
            dp.source_product_id,
            dp.observation_date,
            dp.avg_daily_price,
            dp.observation_count,
            AVG(dp.avg_daily_price) OVER (
                PARTITION BY dp.source_product_id
                ORDER BY dp.observation_date
                ROWS BETWEEN %(window_days)s PRECEDING AND CURRENT ROW
            ) AS rolling_avg_price,
            COUNT(*) OVER (
                PARTITION BY dp.source_product_id
                ORDER BY dp.observation_date
                ROWS BETWEEN %(window_days)s PRECEDING AND CURRENT ROW
            ) AS window_observation_count,
            MIN(dp.avg_daily_price) OVER (
                PARTITION BY dp.source_product_id
                ORDER BY dp.observation_date
                ROWS BETWEEN %(window_days)s PRECEDING AND CURRENT ROW
            ) AS rolling_min_price,
            MAX(dp.avg_daily_price) OVER (
                PARTITION BY dp.source_product_id
                ORDER BY dp.observation_date
                ROWS BETWEEN %(window_days)s PRECEDING AND CURRENT ROW
            ) AS rolling_max_price
        FROM daily_prices dp
    )
    SELECT
        ra.source_product_id,
        ra.observation_date,
        ra.avg_daily_price,
        ra.observation_count,
        ra.rolling_avg_price,
        ra.window_observation_count,
        ra.rolling_min_price,
        ra.rolling_max_price,
        sp.external_id,
        s.name AS source_name
    FROM rolling_avgs ra
    JOIN source_products sp ON ra.source_product_id = sp.id
    JOIN sources s ON sp.source_id = s.id
    WHERE ra.window_observation_count >= %(min_window_size)s
    ORDER BY ra.source_product_id, ra.observation_date DESC
    """
    params["window_days"] = window_days - 1  # PRECEDING count (current row + preceding)
    params["min_window_size"] = min_window_size

    return sql, params


def source_statistics_summary(
    days_back: int = 30,
) -> tuple[str, dict[str, Any]]:
    """Generate source-level observation statistics summary.

    Provides aggregate metrics per source including observation counts,
    price ranges, and data quality indicators.

    Args:
        days_back: Time window for statistics (default 30 days).

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH source_stats AS (
        SELECT
            s.id AS source_id,
            s.name AS source_name,
            COUNT(DISTINCT sp.id) AS unique_listings,
            COUNT(DISTINCT sp.product_id) AS unique_products,
            COUNT(po.id) AS total_observations,
            MIN(po.collected_at) AS earliest_observation,
            MAX(po.collected_at) AS latest_observation,
            MIN(po.price) FILTER (WHERE po.price IS NOT NULL) AS min_price,
            MAX(po.price) FILTER (WHERE po.price IS NOT NULL) AS max_price,
            AVG(po.price) FILTER (WHERE po.price IS NOT NULL) AS avg_price,
            COUNT(po.id) FILTER (WHERE po.price IS NULL) AS missing_price_count,
            COUNT(po.id) FILTER (WHERE po.availability != 'in_stock') AS out_of_stock_count
        FROM sources s
        LEFT JOIN source_products sp ON s.id = sp.source_id
        LEFT JOIN product_observations po ON sp.id = po.source_product_id
            AND po.collected_at >= (NOW() AT TIME ZONE 'UTC' - INTERVAL '%(days_back)s days')
        GROUP BY s.id, s.name
    ),
    quality_stats AS (
        SELECT
            s.id AS source_id,
            COUNT(dqr.id) AS total_checks,
            COUNT(dqr.id) FILTER (WHERE dqr.passed = TRUE) AS passed_checks,
            COUNT(dqr.id) FILTER (WHERE dqr.passed = FALSE) AS failed_checks
        FROM sources s
        LEFT JOIN source_products sp ON s.id = sp.source_id
        LEFT JOIN product_observations po ON sp.id = po.source_product_id
        LEFT JOIN data_quality_results dqr ON po.id = dqr.observation_id
        GROUP BY s.id
    )
    SELECT
        ss.source_id,
        ss.source_name,
        ss.unique_listings,
        ss.unique_products,
        ss.total_observations,
        ss.earliest_observation AT TIME ZONE 'UTC' AS earliest_observation_utc,
        ss.latest_observation AT TIME ZONE 'UTC' AS latest_observation_utc,
        ss.min_price,
        ss.max_price,
        ROUND(ss.avg_price::numeric, 2) AS avg_price,
        ss.missing_price_count,
        ss.out_of_stock_count,
        qs.total_checks,
        qs.passed_checks,
        qs.failed_checks,
        CASE
            WHEN qs.total_checks > 0
            THEN ROUND((qs.passed_checks::numeric / qs.total_checks * 100), 2)
            ELSE NULL
        END AS quality_pass_rate_percent
    FROM source_stats ss
    LEFT JOIN quality_stats qs ON ss.source_id = qs.source_id
    ORDER BY ss.total_observations DESC
    """

    params: dict[str, Any] = {"days_back": days_back}

    return sql, params


def cte_analytical_query(
    days_back: int = 30,
    min_price: float | None = None,
    limit: int = 100,
) -> tuple[str, dict[str, Any]]:
    """Multi-CTE analytical query demonstrating complex query composition.

    This query chains multiple CTEs to:
    1. Filter recent observations
    2. Calculate per-product statistics
    3. Rank products by various metrics
    4. Join with source metadata

    Demonstrates how CTEs improve readability of complex analytical queries.

    Args:
        days_back: Time window for analysis.
        min_price: Optional minimum price filter.
        limit: Maximum results to return.

    Returns:
        Tuple of (SQL query string, parameters dict).
    """
    sql = """
    WITH recent_observations AS (
        -- CTE 1: Filter to recent observations with prices
        SELECT
            po.id AS observation_id,
            po.source_product_id,
            po.name,
            po.price,
            po.currency,
            po.collected_at AT TIME ZONE 'UTC' AS collected_at_utc,
            sp.product_id,
            sp.source_id,
            sp.external_id
        FROM product_observations po
        JOIN source_products sp ON po.source_product_id = sp.id
        WHERE po.collected_at >= (NOW() AT TIME ZONE 'UTC' - INTERVAL '%(days_back)s days')
          AND po.price IS NOT NULL
    """

    params: dict[str, Any] = {"days_back": days_back}

    if min_price is not None:
        sql += " AND po.price >= %(min_price)s"
        params["min_price"] = min_price

    sql += """
    ),
    product_stats AS (
        -- CTE 2: Aggregate statistics per product
        SELECT
            ro.product_id,
            ro.source_id,
            COUNT(*) AS observation_count,
            MIN(ro.price) AS min_price,
            MAX(ro.price) AS max_price,
            AVG(ro.price) AS avg_price,
            STDDEV(ro.price) AS price_stddev,
            MAX(ro.collected_at_utc) AS latest_observation
        FROM recent_observations ro
        GROUP BY ro.product_id, ro.source_id
        HAVING COUNT(*) >= 2
    ),
    ranked_products AS (
        -- CTE 3: Rank products by average price
        SELECT
            ps.product_id,
            ps.source_id,
            ps.observation_count,
            ps.min_price,
            ps.max_price,
            ROUND(ps.avg_price::numeric, 2) AS avg_price,
            ROUND(ps.price_stddev::numeric, 2) AS price_stddev,
            ps.latest_observation,
            RANK() OVER (ORDER BY ps.avg_price DESC) AS price_rank,
            RANK() OVER (ORDER BY ps.observation_count DESC) AS frequency_rank
        FROM product_stats ps
    )
    -- Final SELECT joining with metadata
    SELECT
        rp.product_id,
        rp.source_id,
        p.canonical_name,
        s.name AS source_name,
        rp.observation_count,
        rp.min_price,
        rp.max_price,
        rp.avg_price,
        rp.price_stddev,
        rp.latest_observation,
        rp.price_rank,
        rp.frequency_rank,
        rp.max_price - rp.min_price AS price_range
    FROM ranked_products rp
    JOIN products p ON rp.product_id = p.id
    JOIN sources s ON rp.source_id = s.id
    ORDER BY rp.price_rank ASC
    LIMIT %(limit)s
    """
    params["limit"] = limit

    return sql, params
