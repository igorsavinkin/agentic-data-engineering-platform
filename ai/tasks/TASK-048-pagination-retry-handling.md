# TASK-048 — Pagination and Retry Handling

## Objective
Add pagination and resilient retry handling to the retailer adapter. The adapter must fetch multiple pages of product listings automatically and handle transient HTTP failures with bounded retries and backoff, following the same patterns established by the eBay adapter's `tenacity`-based retry and the ingestion runner's retry logic.

## Required Context Before Coding
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, the TASK-046/047 implementation in `libs/adapters/<retailer>/`, the eBay adapter's retry pattern in `libs/adapters/ebay/client.py`, and the ingestion runner's retry in `services/ingestion/runner.py`. Higher-authority repository documents win on conflicts.

## Requirements
- Implement pagination: detect the next-page link or page parameter from the HTML, fetch successive pages until no more pages are available or a configurable `max_pages` limit is reached.
- Add a `max_pages` configuration parameter (environment variable or constructor argument) with a sensible default (e.g., 3-5 pages) to bound fetches for local testing and CI.
- Aggregate `FetchResult` across all pages: combine events and malformed records from every page into a single `FetchResult` return.
- Implement retry with bounded exponential backoff for transient HTTP failures (5xx, timeouts, connection errors). Use `tenacity` (already a project dependency via eBay adapter) or the same retry pattern. Do NOT retry 4xx errors (except 429).
- Handle 429 (rate limit) specifically: respect `Retry-After` header if present, otherwise use exponential backoff. Raise `SourceFetchError` after exhausting retries.
- Add a configurable `retry_attempts` parameter (default 3) consistent with existing adapter conventions.
- Track per-page metrics: record success/failure for each page fetch via `SourceMetrics` if available.
- Ensure idempotency: if the same page is fetched twice (retry), it must not produce duplicate events. The deterministic `event_id` pattern (`source:external_id:collected_at`) handles this at the event level.
- Handle pagination failures gracefully: if page N succeeds but page N+1 fails after retries, return the events collected from pages 1..N rather than losing everything. Log the failure clearly.

## Tests
Add unit tests using mocked HTTP responses with fixed HTML fixtures:
- Multi-page pagination (3 pages of products → all events aggregated)
- `max_pages` limit respected (stops after N pages even if more exist)
- No next-page link on first page → single page result
- Retry on 500 then success → events returned
- Retry exhaustion (3 failures) → `SourceFetchError`
- 429 with `Retry-After` header → waits and retries
- Partial page failure (page 1 OK, page 2 fails) → returns page 1 events, logs error
- No duplicate events across retries of the same page
- Empty pages in pagination sequence handled correctly

CI tests must use deterministic mocks/fixtures.

## Acceptance Criteria
The retailer adapter automatically paginates through product listing pages up to a configurable limit. Transient HTTP failures trigger bounded retries with exponential backoff. Partial failures return successfully fetched pages rather than losing all data. All retry and pagination behavior is covered by deterministic tests.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-048 only.
