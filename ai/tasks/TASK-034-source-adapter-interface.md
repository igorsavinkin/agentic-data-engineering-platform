# TASK-034 — Source Adapter Interface and Shared Ingestion Contract

## Objective
Define the common source-adapter interface and shared ingestion contract used by all external product-data sources.

## Context
Milestone 5 connects real reference sources to the existing canonical pipeline. The initial sources are Fake Store API and Best Buy API. All source-specific behavior must remain behind adapters, while downstream components continue to consume the same canonical event model.

## Scope
- Define a typed source-adapter protocol/interface.
- Define adapter lifecycle and fetch contract.
- Define error/result semantics for source failures.
- Define the boundary from source-specific records to canonical product-observation events.
- Add reusable source metadata/configuration conventions.

## Requirements
1. Every source adapter must emit data through the same canonical ingestion boundary.
2. Source-specific response models must not leak into Kafka consumers, processor, warehouse, API, or agent layers.
3. The interface must support deterministic testing.
4. Adapter output must contain enough information to build the existing canonical event.
5. Preserve source identity and source-level external IDs.
6. Keep networking/fetching separate from canonical mapping where practical.
7. Define clear behavior for no records, partial source failure, malformed upstream data, and transient request failures.
8. Do not implement Fake Store or Best Buy behavior here.

## Tests Required
- adapter contract/protocol behavior
- canonical mapping boundary
- source identity preservation
- empty result behavior
- malformed record behavior
- deterministic mock adapter

## Acceptance Criteria
- A new source can implement one clear interface and feed the same downstream pipeline.
- No downstream service requires source-specific branching.
- Contract is documented and tested.

## Agent Instructions
Implement TASK-034 only.
