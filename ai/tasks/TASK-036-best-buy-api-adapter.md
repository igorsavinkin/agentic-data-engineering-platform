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

## Agent Instructions
Implement TASK-036 only.
