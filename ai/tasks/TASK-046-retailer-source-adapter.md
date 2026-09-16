# TASK-046 — Retailer Source Selection and Adapter

## Objective
Select a real retailer website as the Milestone 5B web-retailer source and implement the adapter skeleton behind the existing `SourceAdapterProtocol`. Add typed configuration, an HTTP client capable of fetching HTML pages, and the adapter class that wires into the same ingestion architecture as Fake Store, Best Buy, and eBay. Do not implement HTML parsing or pagination here — those belong to TASK-047 and TASK-048.

## Required Context Before Coding
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, and the relevant contracts/implementations from prior tasks (especially `libs/adapters/protocol.py`, `libs/adapters/fake_store/`, `libs/adapters/best_buy/`, `libs/adapters/ebay/`). Higher-authority repository documents win on conflicts.

## Requirements
- Select a retailer that is scrapable via plain HTTP + HTML parsing (no browser automation required). The site must have product listing pages with name, price, and availability in the HTML. Prefer a stable, well-known retailer. If the chosen site requires JavaScript rendering, document the decision and escalate.
- Implement `libs/adapters/<retailer>/` following the same package layout as existing adapters (`adapter.py`, `client.py`, `models.py`).
- The adapter must implement `SourceAdapterProtocol` with a unique `source_name`.
- The HTTP client must fetch a single product listing page and return the raw HTML body. Parsing the HTML into product records is out of scope for this task — return an empty `FetchResult` or raise `NotImplementedError` for the mapping step, with a clear path for TASK-047 to fill in.
- Externalize configuration (base URL, timeout, request headers including User-Agent) through environment variables or existing config conventions.
- Handle HTTP errors (timeout, 4xx, 5xx, connection failure) explicitly by raising `SourceFetchError`.
- Do not leak HTML structure or source-specific details downstream.
- Follow existing repository conventions: typed Python, `httpx.AsyncClient`, deterministic tests with mocked HTTP responses.
- Never commit or log credentials.

## Tests
Add unit tests for:
- Adapter construction and `source_name` correctness
- HTTP client success (mocked 200 response returns HTML body)
- HTTP client failure modes (timeout, 403, 404, 500, connection error → `SourceFetchError`)
- Configuration validation (missing/invalid base URL, timeout)
- Adapter protocol compliance (returns `FetchResult`, event source matches `source_name`)

CI tests must not depend on a live external website.

## Acceptance Criteria
The retailer adapter skeleton implements `SourceAdapterProtocol`, fetches HTML via HTTP with proper error handling, is configurable through environment variables, and has deterministic mocked tests covering success and failure modes. The adapter is ready for TASK-047 to add HTML parsing.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-046 only.
