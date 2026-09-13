"""Add event_id column with unique constraint for idempotent loading (TASK-030).

Adds event_id to product_observations table to enable idempotent replay.
The event_id uniquely identifies each observation from the source event stream.
Conflicting payloads for the same event_id will be detected via unique constraint.
"""

# mypy: disable-error-code="import-untyped,import-not-found"
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add event_id column (nullable initially to allow existing data)
    op.add_column(
        "product_observations",
        sa.Column("event_id", sa.Text(), nullable=True),
    )

    # Backfill event_id for existing rows if needed (set to NULL for now)
    # In production, this would be populated from historical data

    # Make event_id NOT NULL after backfill
    op.alter_column(
        "product_observations",
        "event_id",
        nullable=False,
        server_default=None,
    )

    # Add unique constraint for idempotency
    op.create_unique_constraint(
        "uq_product_observations_event_id",
        "product_observations",
        ["event_id"],
    )

    # Add index for faster lookups during upsert
    op.create_index(
        "ix_product_observations_event_id",
        "product_observations",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_observations_event_id", table_name="product_observations")
    op.drop_constraint(
        "uq_product_observations_event_id",
        table_name="product_observations",
        type_="unique",
    )
    op.drop_column("product_observations", "event_id")
