# TASK-036 — Best Buy API Adapter

## Objective
Implement Best Buy API as the second initial source using the same shared adapter contract.

## Requirements
- Add typed Best Buy client/response models.
- Configure the API key through existing secrets/config conventions; never commit or log it.
- Fetch a bounded deterministic product set suitable for local testing.
- Preserve Best Buy product/SKU identity as source-level external identity.
- Keep source-specific fields inside the adapter.
- Handle auth/rate-limit/HTTP errors explicitly.
- CI tests must not require a real API key.
- Output must be compatible with exactly the same canonical downstream pipeline as Fake Store.

## Tests Required
- representative mapping
- API-key/config validation
- malformed response
- auth failure
- rate-limit/error response
- empty results
- canonical compatibility

## Acceptance Criteria
Best Buy observations use the same canonical event contract and downstream pipeline as Fake Store.

## Status
**COMPLETED** — Merged to main via PR #49 (fix commit b6a7093)

### Implementation Summary
- `libs/adapters/best_buy/` — Client, models, and adapter implementing SourceAdapterProtocol
- API key configuration via environment variable (BESTBUY_API_KEY), never hardcoded
- Bounded product fetch with configurable page_size for deterministic testing
- SKU-based external identity preservation
- ConfigDict(extra="ignore") to tolerate real API's additional fields
- Malformed record capture with DLQ routing (tuple return pattern)
- 19 tests covering mapping, auth failures, rate limits, malformed records, empty results
- Qwen review approved (docs/reviews/TASK-036-fix-review.md)

### Commits
- Initial implementation: merged via PR #46/#47
- Fix commit: b6a7093 (resolved R1/R2 blocking issues)
- Review report: 9ee345d (committed Qwen approval)

## Agent Instructions
Implement TASK-036 only.
