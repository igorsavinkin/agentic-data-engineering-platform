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

## Status
**COMPLETED** — Merged to main via PR #48 (fix commit b899cf5)

### Implementation Summary
- `libs/adapters/fake_store/` — Client, models, and adapter implementing SourceAdapterProtocol
- Canonical event mapping with proper handling of nullable prices, categories, availability
- Malformed record capture with DLQ routing (tuple return pattern)
- 18 tests covering mapping, malformed records, HTTP errors, empty responses
- Qwen review approved (docs/reviews/TASK-035-fix-review.md)

### Commits
- Initial implementation: merged via PR #46/#47
- Fix commit: b899cf5 (resolved F1/F2/F3 blocking issues)
- Review report: 9ee345d (committed Qwen approval)

## Agent Instructions
Implement TASK-035 only.
