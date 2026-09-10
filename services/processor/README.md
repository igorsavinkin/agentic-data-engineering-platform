# processor/

Processor service. Consumes `products.raw.v1`, validates and normalizes observations, applies Polars transformations and deduplication, publishes valid records to `products.validated.v1`, and routes invalid records to `products.invalid.v1` with diagnostic context. Does not write directly to PostgreSQL. See `ai/SPECIFICATION.md` §6.2.

## Module Structure

### `polars_transform.py` (TASK-013)

Core Polars-based transformation module that converts canonical `ProductObservationEvent` objects into Polars DataFrame representations for downstream analytical processing.

**Key function:**
- `events_to_polars(events: Sequence[ProductObservationEvent]) -> pl.DataFrame` — Primary entry point that transforms a sequence of validated events into a deterministic Polars DataFrame with fixed column ordering.

**Design principles:**
- **Pure transformation logic** — No Kafka I/O, no PostgreSQL writes, no Parquet persistence
- **Transport-independent** — Operates on in-memory event lists without knowledge of message brokers
- **Deterministic** — Same input always produces identical output; does not mutate input events
- **No premature policy** — Does not perform normalization, validation, deduplication, DLQ routing, or metrics collection (deferred to TASK-014 through TASK-018)

**DataFrame schema:**
The output DataFrame has the following columns in fixed order:
1. `event_id` — Unique event identifier
2. `event_type` — Event type discriminator (`product.observation`)
3. `schema_version` — Event schema version
4. `source` — Source adapter identifier
5. `produced_at` — Event publication timestamp
6. `external_id` — Source-specific product/listing identifier
7. `name` — Product name
8. `url` — Product URL
9. `price` — Observed price (float when non-null, None otherwise)
10. `currency` — ISO-4217 currency code
11. `availability` — Availability state string
12. `category` — Product category
13. `collected_at` — Observation collection timestamp

## Integration Boundaries

### Upstream (TASK-009 / TASK-010)
Receives validated `ProductObservationEvent` instances from the Kafka consumer layer. The consumer deserializes raw Kafka messages, validates them against the event contract, and passes validated events to the processor core.

### Downstream (TASK-014–018)
The Polars DataFrame produced by this module is consumed by subsequent processing stages:
- **TASK-014** — Schema normalization
- **TASK-015** — Data validation
- **TASK-016** — Deduplication
- **TASK-017** — Invalid event / DLQ handling
- **TASK-018** — Processor metrics

### Out of Scope
This module does NOT:
- Write to PostgreSQL (handled by Warehouse Loader in Milestone 4)
- Write to Parquet (handled by Lake Writer in Milestone 3)
- Publish to Kafka topics (handled by producer layer)
- Perform data validation or normalization (future tasks)
- Handle deduplication (future task)
- Route to DLQ (future task)
- Collect metrics (future task)

## Testing

Unit tests are located in `tests/test_processor_polars.py` and cover:
- Single event to Polars row/DataFrame conversion
- Multi-event deterministic schema/columns
- Exact identifier/timestamp preservation
- Nullable/optional fields (null price)
- Empty input handling
- Deterministic behavior without input mutation

Run tests with:
```bash
pytest tests/test_processor_polars.py -v
```
