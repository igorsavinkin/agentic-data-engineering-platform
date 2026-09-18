"""Add quality-result analytical columns and replay identity (TASK-057).

Extends ``data_quality_results`` with:
- ``records_checked`` / ``failed_records`` — analytical counts from the
  quality framework (TASK-056 ``QualityResult``).
- ``details`` — JSONB diagnostic metadata produced by each check.
- ``replay_key`` — deterministic identity key for idempotent writes.

A unique constraint on ``replay_key`` makes writes replay-safe: re-inserting
the same result is a no-op via ``ON CONFLICT DO NOTHING``.

Downgrade drops the added columns and constraint without data loss to
pre-existing columns.
"""

# mypy: disable-error-code="import-untyped,import-not-found"
import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_quality_results",
        sa.Column("records_checked", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "data_quality_results",
        sa.Column("failed_records", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "data_quality_results",
        sa.Column("details", sa.dialects.postgresql.JSONB()),
    )
    op.add_column(
        "data_quality_results",
        sa.Column("replay_key", sa.Text(), nullable=False, server_default=""),
    )
    op.create_unique_constraint(
        "uk_data_quality_results_replay_key",
        "data_quality_results",
        ["replay_key"],
    )
    op.create_index(
        "ix_data_quality_results_check_checked_at",
        "data_quality_results",
        ["check_name", "checked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_data_quality_results_check_checked_at", table_name="data_quality_results")
    op.drop_constraint("uk_data_quality_results_replay_key", table_name="data_quality_results")
    op.drop_column("data_quality_results", "replay_key")
    op.drop_column("data_quality_results", "details")
    op.drop_column("data_quality_results", "failed_records")
    op.drop_column("data_quality_results", "records_checked")
