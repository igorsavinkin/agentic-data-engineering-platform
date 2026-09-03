# TASK-006 — Product Observation Event Schema

## Status
Ready

## Objective
Implement the canonical Kafka event contract for product observations exactly as defined by `ai/SPECIFICATION.md`.

## References
- `ai/PROJECT.md`
- `ai/SPECIFICATION.md` — Event Contract and Delivery Semantics
- `ai/AGENTS.md`
- `ai/AGENT_WORKFLOW.md`
- `ai/tasks/TASK-007-kafka-topic-configuration.md` — downstream Kafka configuration dependency

## Scope
### In scope
- Define the canonical product-observation event model.
- Implement explicit validation and deterministic serialization/deserialization.
- Implement explicit schema-version handling.
- Add focused unit tests for valid and invalid events.
- Document the event contract at the implementation boundary if needed.

### Out of scope
- Kafka producer/consumer implementation.
- Topic creation or broker configuration.
- Deduplication storage or database implementation.
- Data-lake persistence.
- Source-specific scraping or adapters.
- Changing the canonical event contract defined by `ai/SPECIFICATION.md`.

## Required Envelope
The event envelope must contain exactly these required logical fields:
- `event_id`
- `event_type`
- `schema_version`
- `source`
- `produced_at`
- `payload`

## Required Product Observation Payload
The canonical payload must contain:
- `external_id` — source-provided identifier; this is not the platform/database `products.id`.
- `name`
- `url`
- `price`
- `currency`
- `availability`
- `category`
- `collected_at` — timestamp representing when the observation was collected from the source.

## Contract Requirements
- `event_id` uniquely identifies an observation event.
- `external_id` identifies the product/listing within the source and must not be confused with the platform-assigned product ID.
- `price` must support a null value when a source does not provide a usable price; non-null prices must be validated as non-negative.
- `availability` must use the explicit enum:
  - `in_stock`
  - `out_of_stock`
  - `preorder`
  - `unknown`
- `produced_at` describes event production time.
- `collected_at` describes source-observation collection time; these timestamps must not be conflated.
- Timestamps must be explicitly typed and validated.
- Currency must be represented consistently with the specification and validated as a three-letter currency code.
- Schema versioning must be explicit; unsupported schema versions must be rejected rather than silently accepted.
- Serialization and deserialization must be deterministic and preserve the validated contract.
- Different source adapters must normalize their source-specific data into this canonical contract.
- Consumers must tolerate duplicate delivery. This task does not implement deduplication, but the event model must provide the stable identifiers required for downstream idempotent processing.

## Validation Requirements
At minimum, validation must reject:
- missing required envelope fields;
- missing required payload fields;
- malformed or invalid timestamps;
- negative or otherwise invalid non-null prices;
- invalid data types;
- invalid availability values;
- invalid currency representation;
- empty values where the contract requires a meaningful identifier or name;
- unsupported schema versions.

The implementation should fail explicitly with actionable validation errors. Do not silently coerce malformed contract data into a valid-looking event.

## Tests Required
Include tests covering at least:
1. valid event creation;
2. deterministic serialization and deserialization;
3. missing required envelope field;
4. missing required payload field;
5. invalid `produced_at`;
6. invalid `collected_at`;
7. negative price;
8. null price;
9. invalid price type;
10. invalid availability enum value;
11. invalid currency;
12. unsupported schema version;
13. duplicate `event_id` representation remains stable for downstream idempotency;
14. `external_id` is preserved distinctly from any platform/database product identifier.

## Acceptance Criteria
- A valid product-observation event can be created, serialized, validated, deserialized, and compared deterministically.
- The implementation uses `external_id`, not `product_id`, for the source-level product/listing identity.
- `collected_at` is present and distinct from `produced_at`.
- `availability` accepts only the four specified enum values.
- `price` is nullable and non-null prices cannot be negative.
- Unsupported schema versions are rejected explicitly.
- Tests cover all required validation cases and pass.
- The implementation does not invent or modify architectural behavior outside this task.

## Agent Instructions
Read `ai/PROJECT.md`, `ai/SPECIFICATION.md`, and `ai/AGENTS.md` before implementing. Treat the specification as the source of truth. Do not rename contract fields, change enum values, add alternative meanings, or introduce Kafka/database behavior without an explicit architectural decision. If the existing codebase conflicts with the specification, stop and report the conflict rather than silently changing the architecture.
