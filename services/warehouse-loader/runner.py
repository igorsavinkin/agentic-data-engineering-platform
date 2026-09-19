"""Warehouse Loader runner — periodic Silver-to-PostgreSQL loading.

Reads configuration from environment variables:
- WAREHOUSE_DB_HOST / PORT / NAME / USER / PASSWORD for PostgreSQL
- APP_MINIO_ENDPOINT / ACCESS_KEY / SECRET_KEY for object storage
- APP_WAREHOUSE_LOAD_INTERVAL_SECONDS for the loop interval (default 300)

Does not run Alembic migrations — schema management is a separate concern
handled outside this service boundary.
"""

from __future__ import annotations

import logging
import os
import signal
import time

from libs.common.minio_storage import MinIOSettings, MinIOStorage
from libs.observability.metrics_http_server import MetricsHTTPServer
from libs.observability.prometheus_exporter import create_prometheus_registry
from libs.parquet_reader.reader import PartitionFilter
from libs.partitioning import LakeLayer
from warehouse.loader.batch_loader import WarehouseLoader

logger = logging.getLogger(__name__)

_shutdown = False


def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown
    logger.info("Received signal %s, shutting down gracefully", signum)
    _shutdown = True


def _build_db_url() -> str:
    host = os.getenv("WAREHOUSE_DB_HOST", "localhost")
    port = os.getenv("WAREHOUSE_DB_PORT", "5432")
    dbname = os.getenv("WAREHOUSE_DB_NAME", "warehouse")
    user = os.getenv("WAREHOUSE_DB_USER", "postgres")
    password = os.getenv("WAREHOUSE_DB_PASSWORD", "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


def run() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    interval = int(os.getenv("APP_WAREHOUSE_LOAD_INTERVAL_SECONDS", "300"))
    db_url = _build_db_url()
    storage = MinIOStorage(MinIOSettings())
    loader = WarehouseLoader(db_url=db_url, storage=storage)

    logger.info("Warehouse loader started (interval=%ds)", interval)

    registry, _collector = create_prometheus_registry(service_name="warehouse-loader")
    metrics_server = MetricsHTTPServer(registry=registry, port=9100)
    metrics_server.start()
    logger.info("prometheus_metrics_server_started (port=%d)", 9100)

    try:
        while not _shutdown:
            try:
                result = loader.load_from_lake(PartitionFilter(layer=LakeLayer.SILVER))
                logger.info(
                    "Load cycle complete: read=%d loaded=%d failed=%d",
                    result.rows_read,
                    result.rows_loaded,
                    result.rows_failed,
                )
            except Exception:
                logger.exception("Load cycle failed")

            for _ in range(interval):
                if _shutdown:
                    break
                time.sleep(1)
    finally:
        metrics_server.stop()

    logger.info("Warehouse loader stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    run()
