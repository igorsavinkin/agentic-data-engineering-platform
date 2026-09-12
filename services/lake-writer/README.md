# lake-writer/

Lake Writer service. Consumes `products.validated.v1` and persists validated/normalized records as Silver Parquet. Owns the validated-event-to-Silver boundary and is not coupled to PostgreSQL. See `ai/SPECIFICATION.md` §6.4.

## Architecture

```
Kafka (products.validated.v1)
    ↓
Lake Writer Consumer
    ↓
SilverWriter → MinIO/S3 (silver bucket)
```

The Lake Writer is a separate service from the Processor so that lake persistence can be independently scaled, restarted, or replayed without affecting processing throughput.

## Key Design Decisions

### At-least-once delivery with idempotent writes
Each event is written to object storage before the Kafka offset is committed. If the write fails, the offset is not committed and the record will be redelivered on restart. Because object keys are deterministic (derived from `event_id`), replay overwrites rather than duplicates.

### Partitioning strategy
Silver data is partitioned by source and temporal dimensions:

```
silver/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet
```

This mirrors the Bronze layout, enabling efficient cross-layer reconciliation and time-range queries per source. High-cardinality product identifiers are not used as primary partitions.

### Per-event files
Each event produces its own Parquet file. This simplifies deduplication and replay at the cost of more PUT calls. Batch mode exists but is deprecated for production use.

### Fail-closed DLQ
When a message cannot be deserialized or processed, the dead-letter sink logs the failure and raises `RuntimeError` so the caller does NOT commit the offset. The record will be redelivered on restart for manual inspection.

## Running

```bash
python -m services.lake_writer.consumer
```

## Configuration

Environment variables (see `libs/common/config.py`):

| Variable | Default | Description |
|---|---|---|
| `MINIO_ENDPOINT` | `http://localhost:9000` | Object storage endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | Access key |
| `MINIO_SECRET_KEY` | `minioadmin-local` | Secret key |
| `MINIO_BUCKET_SILVER` | `silver` | Silver bucket name |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka brokers |
| `KAFKA_GROUP_ID` | `lake-writer` | Consumer group ID |

## Replay / Idempotency

Because each event's S3 key includes the `event_id`, reprocessing the same event overwrites the existing file. No duplicate records are created during replay.

## Tests

Unit tests validate event-to-row conversion, partition key generation, and writer behavior. Integration tests require a running MinIO container and Kafka cluster.

```bash
# Unit tests
python -m pytest tests/test_silver_writer.py

# Integration tests (requires Docker Compose)
python -m pytest -m integration tests/test_silver_writer_integration.py
```
