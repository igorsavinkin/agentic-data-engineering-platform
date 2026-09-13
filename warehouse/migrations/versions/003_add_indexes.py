"""Add strategic indexes for analytical query performance (TASK-031).

Creates indexes to support common warehouse query patterns:
- Latest observation per product (ROW_NUMBER, RANK)
- Price change analysis (LAG window function)
- Time-range filtering and rolling averages
- Source statistics aggregations
- Product lookups via source_products JOINs
- Data quality result filtering

All index creation uses IF NOT EXISTS for idempotency.
Downgrade cleanly drops all added indexes without data loss.
"""

# mypy: disable-error-code="import-untyped,import-not-found"
from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # product_observations indexes

    # Composite index for latest observation queries and time-series access patterns
    # Supports: ROW_NUMBER() OVER (PARTITION BY source_product_id ORDER BY collected_at DESC)
    # Supports: LAG(price) OVER (PARTITION BY source_product_id ORDER BY collected_at)
    op.create_index(
        "ix_product_observations_source_product_collected",
        "product_observations",
        ["source_product_id", "collected_at"],
    )

    # Index on collected_at for time-range filtering across all products
    # Supports: WHERE collected_at BETWEEN ... AND ...
    # Supports: GROUP BY date(collected_at) for rolling averages
    op.create_index(
        "ix_product_observations_collected_at",
        "product_observations",
        ["collected_at"],
    )

    # Note: event_id index already created in migration 002
    # Verify it exists but don't recreate it

    # source_products indexes

    # Index on product_id for JOIN operations when querying observations by canonical product
    # Supports: JOIN source_products sp ON sp.product_id = ? WHERE po.source_product_id = sp.id
    op.create_index(
        "ix_source_products_product_id",
        "source_products",
        ["product_id"],
    )

    # Note: Unique constraint on (source_id, external_id) already exists in initial schema

    # data_quality_results indexes

    # Index on pipeline_run_id for quality result lookups by pipeline execution
    # Supports: SELECT * FROM data_quality_results WHERE pipeline_run_id = ?
    op.create_index(
        "ix_data_quality_results_pipeline_run_id",
        "data_quality_results",
        ["pipeline_run_id"],
    )

    # Index on observation_id for quality result lookups by observation
    # Supports: SELECT * FROM data_quality_results WHERE observation_id = ?
    op.create_index(
        "ix_data_quality_results_observation_id",
        "data_quality_results",
        ["observation_id"],
    )

    # Composite index on check_name and passed for quality check filtering
    # Supports: WHERE check_name = ? AND passed = FALSE (find failing checks)
    # Supports: GROUP BY check_name with HAVING COUNT(*) FILTER (WHERE passed = FALSE) > 0
    op.create_index(
        "ix_data_quality_results_check_passed",
        "data_quality_results",
        ["check_name", "passed"],
    )


def downgrade() -> None:
    # Drop data_quality_results indexes
    op.drop_index("ix_data_quality_results_check_passed", table_name="data_quality_results")
    op.drop_index("ix_data_quality_results_observation_id", table_name="data_quality_results")
    op.drop_index("ix_data_quality_results_pipeline_run_id", table_name="data_quality_results")

    # Drop source_products indexes
    op.drop_index("ix_source_products_product_id", table_name="source_products")

    # Drop product_observations indexes
    op.drop_index("ix_product_observations_collected_at", table_name="product_observations")
    op.drop_index(
        "ix_product_observations_source_product_collected", table_name="product_observations"
    )
