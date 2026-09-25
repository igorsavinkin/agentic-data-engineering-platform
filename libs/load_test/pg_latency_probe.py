"""PostgreSQL latency probe for end-to-end latency measurement (TASK-113).

Queries the ``product_observations`` table to detect when load-test events
become visible in PostgreSQL.  The probe uses the same factory pattern as
``kafka_lag_probe.py``: it returns a callable that the runner invokes
periodically with a list of pending event IDs.

The probe connects directly to PostgreSQL using psycopg2.  It filters by
``source`` to isolate load-test events from production traffic.
"""

from __future__ import annotations

import logging
from typing import Callable

# mypy: disable-error-code="import-untyped"
import psycopg2

logger = logging.getLogger(__name__)


def create_pg_probe_fn(
    db_url: str,
    source: str = "load-test",
) -> Callable[[list[str]], list[str]]:
    """Create a function that checks PostgreSQL for event arrivals.

    Parameters
    ----------
    db_url:
        PostgreSQL connection URL.  Both ``postgresql://`` and
        ``postgresql+psycopg2://`` schemes are accepted.
    source:
        Source label to filter ``product_observations`` by.  This
        isolates load-test events from other traffic.

    Returns
    -------
    Callable
        A function ``(event_ids: list[str]) -> list[str]`` that returns
        the subset of event IDs found in PostgreSQL.
    """
    dsn = db_url.replace("postgresql+psycopg2://", "postgresql://")

    _BATCH_SIZE = 1000

    def probe(event_ids: list[str]) -> list[str]:
        if not event_ids:
            return []
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        try:
            found: list[str] = []
            cur = conn.cursor()
            for batch_start in range(0, len(event_ids), _BATCH_SIZE):
                batch = event_ids[batch_start : batch_start + _BATCH_SIZE]
                placeholders = ", ".join(["%s"] * len(batch))
                query = (
                    "SELECT DISTINCT po.event_id "
                    "FROM product_observations po "
                    "JOIN source_products sp ON po.source_product_id = sp.id "
                    "JOIN sources s ON sp.source_id = s.id "
                    f"WHERE s.name = %s AND po.event_id IN ({placeholders})"
                )
                params = [source, *batch]
                cur.execute(query, params)
                found.extend(row[0] for row in cur.fetchall())
            cur.close()
            return found
        finally:
            conn.close()

    return probe
