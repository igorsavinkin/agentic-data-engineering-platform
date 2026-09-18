"""Add ingestion_health_results table (TASK-059).

Stores periodic source health assessments produced by the ingestion_health
Airflow DAG. Each row captures one evaluation of one source at a point in
time. A deterministic ``replay_key`` makes writes idempotent: re-running
the same logical interval is a no-op via ``ON CONFLICT DO NOTHING``.

Downgrade drops the table entirely.
"""

# mypy: disable-error-code="import-untyped,import-not-found"
import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_health_results",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("freshness_state", sa.Text(), nullable=False),
        sa.Column("reasons", sa.JSON()),
        sa.Column("signals", sa.JSON()),
        sa.Column("freshness_age_seconds", sa.Float()),
        sa.Column("assessed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("logical_date", sa.Text(), nullable=False, server_default=""),
        sa.Column("replay_key", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("replay_key", name="uk_ingestion_health_results_replay_key"),
    )
    op.create_index(
        "ix_ingestion_health_source_assessed",
        "ingestion_health_results",
        ["source_name", "assessed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_health_source_assessed", table_name="ingestion_health_results")
    op.drop_table("ingestion_health_results")
