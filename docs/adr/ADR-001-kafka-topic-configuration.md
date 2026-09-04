# ADR-001 — Kafka Topic Configuration

**Status:** Accepted
**Date:** 2026-09-05
**Context:** TASK-007 — Kafka Topic Configuration

## Decision

Configure five initial Kafka topics for the AI Data Platform with explicit partitioning, retention, and consumer-group policies.

### Topics

| Topic | Partitions | Retention | Purpose | Partition Key | Consumer Groups |
|---|---|---|---|---|---|
| `products.raw.v1` | 3 | 7 days | Canonical observations from ingestion | `source:external_id` (concatenated) | `processor`, `raw-writer` |
| `products.validated.v1` | 3 | 7 days | Validated/normalized product events | `source:external_id` (concatenated) | `lake-writer` |
| `products.invalid.v1` | 1 | 7 days | Invalid/dead-letter product events | None (round-robin) | N/A (monitoring/DLQ) |
| `pipeline.events.v1` | 1 | 3 days | Pipeline lifecycle events | None (event type routing) | `monitoring`, `metadata` |
| `data-quality.events.v1` | 1 | 3 days | Data quality check results | None (check name routing) | `quality-monitoring` |

### Partition Count Rationale

- **Product topics (3 partitions):** Balances ordering requirements with throughput. Three partitions allow parallel consumption by multiple processor instances while preserving per-source-product ordering. For local development this provides realistic concurrency without excessive resource usage. Production scaling can increase this count via topic reassignment.

- **Lifecycle/quality topics (1 partition):** These topics carry low-volume operational events where global ordering is more valuable than parallelism. Single-partition ensures all pipeline events are seen in order by monitoring consumers.

### Partition Key Strategy

For `products.raw.v1` and `products.validated.v1`, the partition key is the concatenation of `source` and `external_id` separated by a colon (`:`). This ensures:

1. All observations for the same source/product combination land in the same partition
2. Ordering is preserved for sequential observations of the same product from the same source
3. Different products/sources distribute across partitions for parallel processing

Example key: `bestbuy:12345`, `ebay:listing-abc`

### Retention Policy

- **Product event topics (7 days):** Supports replay demonstrations and local development iteration without treating Kafka as permanent storage. Seven days allows testing failure recovery scenarios and reprocessing logic.

- **Operational topics (3 days):** Pipeline and quality events are transient diagnostics. Three days provides sufficient history for troubleshooting recent failures without accumulating stale operational noise.

### Naming Convention

Topics follow the pattern: `{domain}.{status/purpose}.v{version}`

- **Domain:** Logical grouping (`products`, `pipeline`, `data-quality`)
- **Status/Purpose:** Event state or function (`raw`, `validated`, `invalid`, `events`)
- **Version:** Schema version suffix (`v1`) enabling future schema evolution without breaking existing consumers

This convention supports clear topic identification and safe schema migration paths.

### Consumer Group Assignments

Each service uses a dedicated consumer group to enable independent scaling and offset management:

- **`processor`:** Consumes `products.raw.v1` for validation/transformation
- **`raw-writer`:** Consumes `products.raw.v1` for Bronze persistence
- **`lake-writer`:** Consumes `products.validated.v1` for Silver persistence

Multiple services consuming the same topic with different groups enables at-least-once delivery semantics per service.

### Ordering Assumptions

- **Within a partition:** Kafka guarantees total ordering. The partition key strategy ensures all observations for a given source/product are ordered within their partition.

- **Across partitions:** No global ordering guarantee. Consumers must not assume that events from different source/product combinations arrive in any particular order relative to each other.

- **Temporal ordering:** `collected_at` timestamps may not be monotonically increasing across partitions due to network delays, source latency differences, or clock skew. Processing logic should use `collected_at` for business logic, not arrival order.

## Consequences

### Positive

- Explicit partitioning strategy prevents ordering bugs in downstream deduplication logic
- Versioned topic names enable safe schema evolution
- Separate consumer groups allow independent service scaling and restart
- Documented retention prevents Kafka from becoming de facto permanent storage
- Clear naming convention simplifies topic discovery and operational debugging

### Negative

- Three partitions for product topics limits maximum parallel consumer instances to three per group
- Concatenated partition keys require consistent formatting across all producers
- Manual topic creation required during deployment (auto-create disabled)

### Risks Mitigated

- **Ordering violations:** Partition key strategy preserves per-product ordering
- **Schema drift:** Versioned topic names force explicit migration decisions
- **Data loss:** 7-day retention provides replay window for failure recovery
- **Consumer coupling:** Separate consumer groups prevent offset conflicts between services

## Implementation Notes

Topics are created via `scripts/manage_kafka_topics.py` which:
1. Reads configuration from environment variables or defaults
2. Creates topics idempotently (skips if already exists)
3. Validates topic configuration matches expected settings
4. Returns non-zero exit code on failure for CI/CD integration

Local development uses Docker Compose health checks to ensure Kafka is ready before topic creation.

## Alternatives Considered

1. **Single partition for all topics:** Rejected because it would serialize all product processing and eliminate parallelism benefits of Kafka.

2. **Auto-create topics:** Rejected because implicit topic creation leads to typos, inconsistent configuration, and makes deployment state unclear.

3. **Higher partition counts (6+):** Rejected for initial implementation. Local development resources are limited and three partitions provides sufficient parallelism demonstration. Production scaling can increase partition count via topic reassignment when actual throughput requirements are measured.

4. **Time-based partition keys:** Rejected because time-based keys would scatter observations for the same product across many partitions, breaking ordering guarantees needed for deduplication.
