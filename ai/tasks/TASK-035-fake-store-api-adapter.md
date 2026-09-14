# TASK-035 — Fake Store API Adapter

## Objective
Implement Fake Store API as the first deterministic reference source using the shared adapter contract from TASK-034.

## Requirements
- Add typed HTTP client/response models.
- Map source records into the canonical event boundary.
- Preserve source-level external identity.
- Handle price/category/availability/timestamps according to current canonical rules.
- Handle timeout, HTTP error, malformed and empty responses explicitly.
- Keep source-specific fields inside the adapter boundary.
- CI tests must use deterministic mocks/fixtures rather than a live service.

## Tests Required
- representative product mapping
- multiple records
- nullable fields
- malformed upstream record
- HTTP timeout/error
- empty source response
- canonical event compatibility

## Acceptance Criteria
Fake Store data can be converted into canonical observation events with no downstream source-specific code.

## Agent Instructions
Implement TASK-035 only.
