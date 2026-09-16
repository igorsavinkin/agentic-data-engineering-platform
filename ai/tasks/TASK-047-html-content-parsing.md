# TASK-047 — HTML/Dynamic-Content Parsing

## Objective
Implement HTML parsing for the retailer adapter from TASK-046. Extract product observations (name, price, availability, category, URL) from the retailer's HTML product listing pages and map them into the canonical `ProductObservationEvent` model via the existing `SourceAdapterProtocol.fetch()` method. Keep all HTML-specific logic behind the adapter boundary.

## Required Context Before Coding
Read current `ai/PROJECT.md`, applicable ADRs, `ai/SPECIFICATION.md`, `ai/ROADMAP.md`, `ai/AGENTS.md`, `ai/AGENT_WORKFLOW.md`, the TASK-046 implementation in `libs/adapters/<retailer>/`, and the canonical event model in `libs/event_contracts/product_observation.py`. Higher-authority repository documents win on conflicts.

## Requirements
- Parse HTML product listing pages using a Python HTML parsing library (e.g., `selectolax`, `beautifulsoup4`, or `lxml` — choose the simplest reliable option). Add the dependency to the project if needed.
- Extract per product: name, price (as Decimal), currency, availability, category, product URL, and a stable external identifier from the HTML.
- Map extracted records into `ProductObservationEvent` using the same `_build_event()` helper pattern as existing adapters.
- Handle missing or malformed HTML elements gracefully: records with unparseable prices or missing required fields go into `malformed` (via `MalformedRecordError`), not into `events`.
- Handle structural HTML changes (missing selectors, unexpected layout) by returning empty events + informative logging, not crashes.
- Keep all CSS selectors / XPath expressions / parsing logic inside the adapter package. No HTML-specific code may leak into `libs/event_contracts/`, `libs/common/`, or downstream consumers.
- Preserve the `source_name` from TASK-046. The `external_id` must be a stable retailer-specific identifier (e.g., product SKU or slug from the URL).
- Currency should default to the retailer's local currency if not present in the HTML.
- Availability must be mapped to the canonical `Availability` enum (`in_stock`, `out_of_stock`, `preorder`, `unknown`).

## Tests
Add unit tests using fixed HTML fixture files (stored under `tests/fixtures/<retailer>/`):
- Representative product extraction (all fields populated)
- Multiple products on one page
- Missing price (→ malformed or null price per canonical rules)
- Missing availability (→ `unknown`)
- Malformed HTML / unexpected structure (→ empty events, no crash)
- Empty page (no products found → empty FetchResult)
- Canonical event compatibility (source matches, external_id is stable, event_id is deterministic)
- Price parsing edge cases (currency symbols, thousands separators, free/zero price)

CI tests must use deterministic HTML fixtures, not live HTTP calls.

## Acceptance Criteria
The retailer adapter can parse HTML product listing pages into canonical `ProductObservationEvent` records. Malformed or incomplete HTML produces malformed records rather than crashes. All HTML-specific logic is contained within the adapter package. Tests use fixed HTML fixtures.

## Definition of Done
Relevant tests, lint, format and type checks pass; acceptance criteria are verified; diff is inspected; documentation is updated where required; no secrets are introduced.

## Agent Instructions
Implement TASK-047 only.
