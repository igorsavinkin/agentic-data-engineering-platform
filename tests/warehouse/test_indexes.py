"""Tests for TASK-031 database indexes.

Verifies that strategic indexes exist after migration upgrade,
are dropped after downgrade, and are used by representative queries.
"""

import pytest


@pytest.mark.integration
def test_indexes_exist_after_upgrade(db_connection, alembic_cfg):
    """Verify all required indexes exist after running migration 003."""
    from alembic.command import upgrade

    # Run migration to head (includes 003)
    upgrade(alembic_cfg, "head")

    cur = db_connection.cursor()

    # Check product_observations indexes
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'product_observations'
        AND indexname IN (
            'ix_product_observations_source_product_collected',
            'ix_product_observations_collected_at',
            'ix_product_observations_event_id'
        )
        ORDER BY indexname
    """)
    po_indexes = {row[0] for row in cur.fetchall()}
    assert "ix_product_observations_source_product_collected" in po_indexes
    assert "ix_product_observations_collected_at" in po_indexes
    assert "ix_product_observations_event_id" in po_indexes

    # Check source_products indexes
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'source_products'
        AND indexname = 'ix_source_products_product_id'
    """)
    sp_indexes = {row[0] for row in cur.fetchall()}
    assert "ix_source_products_product_id" in sp_indexes

    # Check data_quality_results indexes
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'data_quality_results'
        AND indexname IN (
            'ix_data_quality_results_pipeline_run_id',
            'ix_data_quality_results_observation_id',
            'ix_data_quality_results_check_passed'
        )
        ORDER BY indexname
    """)
    dqr_indexes = {row[0] for row in cur.fetchall()}
    assert "ix_data_quality_results_pipeline_run_id" in dqr_indexes
    assert "ix_data_quality_results_observation_id" in dqr_indexes
    assert "ix_data_quality_results_check_passed" in dqr_indexes

    cur.close()


@pytest.mark.integration
def test_indexes_dropped_after_downgrade(db_connection, alembic_cfg):
    """Verify indexes are cleanly removed after downgrading migration 003."""
    from alembic.command import downgrade, upgrade

    # First upgrade to head
    upgrade(alembic_cfg, "head")

    # Downgrade to 002 (should drop 003 indexes)
    downgrade(alembic_cfg, "002")

    cur = db_connection.cursor()

    # Verify 003 indexes are gone
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'product_observations'
        AND indexname IN (
            'ix_product_observations_source_product_collected',
            'ix_product_observations_collected_at'
        )
    """)
    remaining = cur.fetchall()
    assert len(remaining) == 0, f"Indexes not dropped: {remaining}"

    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'source_products'
        AND indexname = 'ix_source_products_product_id'
    """)
    assert cur.fetchone() is None

    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'data_quality_results'
        AND indexname IN (
            'ix_data_quality_results_pipeline_run_id',
            'ix_data_quality_results_observation_id',
            'ix_data_quality_results_check_passed'
        )
    """)
    remaining = cur.fetchall()
    assert len(remaining) == 0, f"Quality result indexes not dropped: {remaining}"

    # Verify event_id index from 002 still exists
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'product_observations'
        AND indexname = 'ix_product_observations_event_id'
    """)
    assert cur.fetchone() is not None, "event_id index from migration 002 should remain"

    cur.close()


@pytest.mark.integration
def test_latest_observation_query_uses_index(db_connection, alembic_cfg):
    """EXPLAIN ANALYZE: Latest observation query uses composite index."""
    from alembic.command import upgrade

    # Ensure we're at head with indexes
    upgrade(alembic_cfg, "head")

    # Insert test data
    cur = db_connection.cursor()
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'EXT001') RETURNING id",
        (source_id, product_id),
    )
    sp_id = cur.fetchone()[0]

    # Insert multiple observations
    for i in range(100):
        cur.execute(
            """
            INSERT INTO product_observations
                (source_product_id, name, price, currency, availability, collected_at, event_id)
            VALUES (%s, %s, %s, %s, %s, NOW() - INTERVAL '%s days', %s)
            """,
            (sp_id, f"Product {i}", 10.0 + i, "USD", "in_stock", i, f"evt_{i}"),
        )

    db_connection.commit()

    # EXPLAIN ANALYZE latest observation query
    cur.execute(
        """
        EXPLAIN ANALYZE
        SELECT * FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY source_product_id ORDER BY collected_at DESC) as rn
            FROM product_observations
            WHERE source_product_id = %s
        ) sub
        WHERE rn = 1
    """,
        (sp_id,),
    )

    plan_lines = [row[0] for row in cur.fetchall()]
    plan_text = "\n".join(plan_lines)

    # Verify index is used (look for Index Scan or Index Only Scan)
    assert "Index" in plan_text, (
        f"Expected index usage in latest observation query. Plan:\n{plan_text}"
    )

    cur.close()


@pytest.mark.integration
def test_time_range_filter_uses_index(db_connection, alembic_cfg):
    """EXPLAIN ANALYZE: Time-range filter query uses collected_at index."""
    from alembic.command import upgrade

    upgrade(alembic_cfg, "head")

    # Insert test data
    cur = db_connection.cursor()
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'EXT001') RETURNING id",
        (source_id, product_id),
    )
    sp_id = cur.fetchone()[0]

    # Insert observations spanning a date range
    for i in range(200):
        cur.execute(
            """
            INSERT INTO product_observations
                (source_product_id, name, price, currency, availability, collected_at, event_id)
            VALUES (%s, %s, %s, %s, %s, NOW() - INTERVAL '%s days', %s)
            """,
            (sp_id, f"Product {i}", 10.0 + i, "USD", "in_stock", i, f"evt_timerange_{i}"),
        )

    db_connection.commit()

    # EXPLAIN ANALYZE time-range filter query
    cur.execute("""
        EXPLAIN ANALYZE
        SELECT COUNT(*), AVG(price)
        FROM product_observations
        WHERE collected_at BETWEEN NOW() - INTERVAL '30 days' AND NOW()
    """)

    plan_lines = [row[0] for row in cur.fetchall()]
    plan_text = "\n".join(plan_lines)

    # Verify index is used
    assert "Index" in plan_text, f"Expected index usage in time-range query. Plan:\n{plan_text}"

    cur.close()


@pytest.mark.integration
def test_product_lookup_uses_index(db_connection, alembic_cfg):
    """EXPLAIN ANALYZE: Product lookup JOIN uses product_id index on source_products."""
    from alembic.command import upgrade

    upgrade(alembic_cfg, "head")

    # Insert test data
    cur = db_connection.cursor()
    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product A') RETURNING id")
    product_a_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product B') RETURNING id")
    product_b_id = cur.fetchone()[0]

    # Create multiple source_products for each product
    for i in range(50):
        cur.execute(
            "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, %s) RETURNING id",
            (source_id, product_a_id if i % 2 == 0 else product_b_id, f"EXT_A_{i}"),
        )
        sp_id = cur.fetchone()[0]

        # Add an observation for each source_product
        cur.execute(
            """
            INSERT INTO product_observations
                (source_product_id, name, price, currency, availability, collected_at, event_id)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            """,
            (sp_id, f"Product {i}", 10.0, "USD", "in_stock", f"evt_lookup_{i}"),
        )

    db_connection.commit()

    # EXPLAIN ANALYZE product lookup query
    cur.execute(
        """
        EXPLAIN ANALYZE
        SELECT po.*
        FROM product_observations po
        JOIN source_products sp ON po.source_product_id = sp.id
        WHERE sp.product_id = %s
    """,
        (product_a_id,),
    )

    plan_lines = [row[0] for row in cur.fetchall()]
    plan_text = "\n".join(plan_lines)

    # Verify index is used on source_products
    assert "Index" in plan_text, f"Expected index usage in product lookup query. Plan:\n{plan_text}"

    cur.close()


@pytest.mark.integration
def test_quality_check_filter_uses_index(db_connection, alembic_cfg):
    """EXPLAIN ANALYZE: Quality check filtering uses composite index."""
    from alembic.command import upgrade

    upgrade(alembic_cfg, "head")

    # Insert test data
    cur = db_connection.cursor()
    cur.execute(
        "INSERT INTO pipeline_runs (run_type, status) VALUES ('load', 'completed') RETURNING id"
    )
    run_id = cur.fetchone()[0]

    cur.execute("INSERT INTO sources (name) VALUES ('test_source') RETURNING id")
    source_id = cur.fetchone()[0]

    cur.execute("INSERT INTO products (canonical_name) VALUES ('Test Product') RETURNING id")
    product_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO source_products (source_id, product_id, external_id) VALUES (%s, %s, 'EXT001') RETURNING id",
        (source_id, product_id),
    )
    sp_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO product_observations
            (source_product_id, name, price, currency, availability, collected_at, event_id)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s) RETURNING id
        """,
        (sp_id, "Test", 10.0, "USD", "in_stock", "evt_quality_1"),
    )
    obs_id = cur.fetchone()[0]

    # Insert quality results
    checks = ["price_valid", "name_not_null", "currency_valid"]
    for i, check in enumerate(checks):
        for passed in [True, False]:
            cur.execute(
                """
                INSERT INTO data_quality_results
                    (pipeline_run_id, observation_id, check_name, severity, passed, message)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (run_id, obs_id, check, "high" if not passed else "low", passed, f"Test {check}"),
            )

    db_connection.commit()

    # EXPLAIN ANALYZE quality check filter query
    cur.execute(
        """
        EXPLAIN ANALYZE
        SELECT check_name, COUNT(*) as fail_count
        FROM data_quality_results
        WHERE check_name = %s AND passed = %s
        GROUP BY check_name
    """,
        ("price_valid", False),
    )

    plan_lines = [row[0] for row in cur.fetchall()]
    plan_text = "\n".join(plan_lines)

    # Verify index is used
    assert "Index" in plan_text, (
        f"Expected index usage in quality check filter query. Plan:\n{plan_text}"
    )

    cur.close()
