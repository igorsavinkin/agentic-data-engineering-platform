# Raw Writer Service — Bronze Parquet Persistence (TASK-021)

## Overview

The Raw Writer consumes canonical product observation events from `products.raw.v1` and persists them as Bronze-layer Apache Parquet files in MinIO/S3 object storage. It is the first persistence boundary in the data lake, storing raw/minimally transformed observations before validation and normalization.

## Architecture

```
Kafka (products.raw.v1)
        ↓
   Raw Writer Consumer
        ↓
   BronzeWriter (batch accumulator)
        ↓
   MinIOStorage (TASK-020)
        ↓
   s3://bronze/source=<source>/year=<YYYY>/month=<MM>/day=<DD>/<event_id>.parquet
```

## Key Design Decisions

### Partitioning Strategy

Bronze data is partitioned by **source** and **temporal dimensions**:

```
bronze/
  source=fake-store/
    year=2026/
      month=09/
        day=03/
          evt-abc123.parquet
          evt-def456.parquet
```

This avoids high-cardinality product identifiers as primary partitions while enabling efficient time-range queries per source.

### Idempotency

Object keys are deterministic, derived from `event_id`:

```python
key = f"bronze/source={source}/year={Y}/month={M}/day={D}/{event_id}.parquet"
```

Replaying the same event overwrites the existing file rather than creating duplicates. This is safe because:

- Kafka provides at-least-once delivery
- The consumer commits offsets ONLY after successful writes
- On restart, uncommitted records are redelivered and safely overwrite

### Offset Semantics

| Scenario | Behavior |
|----------|----------|
| Successful write | Offset committed after `flush_batch()` returns |
| Storage failure | Offset NOT committed; record redelivered on restart |
| Deserialization error | Routed to DLQ sink; offset committed |
| Graceful shutdown | Remaining batch flushed before close |

### Batch Accumulation

Events are accumulated in memory up to a configurable `batch_size` (default: 100). When the threshold is reached, all events are written as individual Parquet files. The batch can also be flushed explicitly (e.g., on shutdown).

## Components

| Module | Responsibility |
|--------|---------------|
| `bronze_writer.py` | Event→Parquet serialization, batch accumulation, MinIO upload |
| `consumer.py` | Kafka consumer loop, offset management, signal handling |

## Configuration

The service uses standard settings loaded via `load_settings()`:

- `KafkaConsumerSettings` — bootstrap servers, group ID, auto-offset-reset
- `MinIOSettings` — endpoint, credentials, bucket names

See `.env.example` for available environment variables.

## Running

```bash
python -m services.raw_writer.consumer
```

## Testing

```bash
# Unit tests (no MinIO required)
pytest tests/test_bronze_writer.py -v

# Integration tests (requires running MinIO container)
pytest tests/test_bronze_writer_integration.py -v
```

## Failure Handling

- **Transient storage errors**: Retried via `RetryPolicy`; offset not committed until success
- **Permanent storage failures**: Exception propagates; consumer closes without committing
- **Deserialization errors**: Routed to DLQ with full diagnostic context
- **Shutdown**: SIGINT/SIGTERM triggers graceful flush of remaining batch

## See Also

- `ai/SPECIFICATION.md` §6.3 — Raw Writer service boundary
- `docs/minio-storage.md` — MinIO client documentation (TASK-020)
- `libs/event_contracts/product_observation.py` — Canonical event model
