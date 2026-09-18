"""Add daily_metrics table (TASK-062).

Stores daily analytical metrics computed from product_observations by the
build_daily_metrics Airflow DAG. Each row captures one metric value for
one day, optionally scoped by a dimension (e.g. source name).

A deterministic ``replay_key`` makes writes idempotent: re-running the
same logical interval is a no-op via ``ON CONFLICT DO NOTHING``.

Downgrade drops the table entirely.
"""

# mypy: disable-error-code="import-untyped,import-not-found"
import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False, server_default=""),
        sa.Column("value", sa.Numeric(16, 4), nullable=False),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("logical_date", sa.Text(), nullable=False, server_default=""),
        sa.Column("replay_key", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("replay_key", name="uk_daily_metrics_replay_key"),
    )
    op.create_index(
        "ix_daily_metrics_date_name",
        "daily_metrics",
        ["metric_date", "metric_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_metrics_date_name", table_name="daily_metrics")
    op.drop_table("daily_metrics")
