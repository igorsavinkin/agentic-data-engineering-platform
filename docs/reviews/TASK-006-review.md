# TASK-006 Review — Product Observation Event Schema

## 1. Review Header

- **Task:** [TASK-006 — Product Observation Event Schema](../../ai/tasks/TASK-006-product-observation-event-schema.md)
- **Review date:** 2026-09-08
- **Reviewed change set / Git range:** `a31aec276fb07fc27513c56a1774d6dbab0b482a..451af1264a0a2449175b2e9e44f4aba9d32afb57`
- **Reviewed HEAD:** `451af1264a0a2449175b2e9e44f4aba9d32afb57` on branch `feature/TASK-006`
- **Commits reviewed:**
  - `ae7c8f0` — `feat: implement TASK-006 product observation event schema`
  - `451af12` — `script update`
- **Scope:** Canonical product-observation Kafka event envelope and payload model, validation, deterministic serialization, and unit tests. No Kafka producer/consumer, topic, deduplication-storage, or adapter implementation.
- **Reviewer:** Qwen Code (independent review; no implementation code modified)
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

---

## 2. Requirements Coverage

### Required envelope (all six logical fields present)

| Requirement | Status | Evidence |
| --- | --- | --- |
| `event_id` | ✅ Satisfied | `ProductObservationEvent.event_id: str = Field(..., min_length=1)` |
| `event_type` | ✅ Satisfied | `event_type: Literal["product.observation"]` (only valid value) |
| `schema_version` | ✅ Satisfied | `schema_version: int = Field(ge=1)` + membership validator (`SUPPORTED_SCHEMA_VERSIONS == {1}`) |
| `source` | ✅ Satisfied | `source: str = Field(..., min_length=1)` |
| `produced_at` | ✅ Satisfied | `produced_at: datetime = Field(...)` + timezone-aware validator |
| `payload` | ✅ Satisfied | `payload: ProductObservationPayload = Field(...)` |

### Required payload

| Requirement | Status | Evidence |
| --- | --- | --- |
| `external_id` (source identity, not `products.id`) | ✅ Satisfied | `external_id: str = Field(..., min_length=1)`; no `product_id` field exists (asserted by test) |
| `name` | ✅ Satisfied | `name: str = Field(..., min_length=1)` |
| `url` | ✅ Satisfied | `url: str = Field(..., min_length=1)` |
| `price` (nullable, non-negative when set) | ✅ Satisfied | `price: Decimal \| None = Field(...)` + `_validate_price_non_negative` |
| `currency` | ✅ Satisfied | `currency: str = Field(..., pattern=r"^[A-Z]{3}$")` |
| `availability` (four-value enum) | ✅ Satisfied | `Availability(str, Enum)` = `in_stock`/`out_of_stock`/`preorder`/`unknown` |
| `category` | ✅ Satisfied | `category: str = Field(..., min_length=1)` |
| `collected_at` | ✅ Satisfied | `collected_at: datetime = Field(...)` + timezone-aware validator |

### Contract requirements

| Requirement | Status | Evidence |
| --- | --- | --- |
| `produced_at` vs `collected_at` not conflated | ✅ Satisfied | Separate fields on envelope vs payload; test `test_collected_at_and_produced_at_are_distinct` |
| Timestamps explicitly typed and validated | ✅ Satisfied | `datetime` type + timezone-aware validators on both; naive datetimes rejected |
| Currency as three-letter code | ✅ Satisfied | `^[A-Z]{3}$` pattern |
| Schema versioning explicit; unsupported rejected | ✅ Satisfied | `_validate_schema_version` raises for values outside `{1}` |
| Deterministic serialize/deserialize | ✅ Satisfied | `serialize_event` (field-order-stable `model_dump_json`) / `deserialize_event`; test asserts round-trip equality |
| Canonical normalization target for adapters | ✅ Satisfied | Single canonical `ProductObservationEvent`/`ProductObservationPayload` model at the `libs/event_contracts` boundary |
| Stable identifiers for downstream idempotency | ✅ Satisfied | `event_id` preserved verbatim; deterministic `make_event_id()` helper; `partition_key` = `source:external_id` |
| `event_id` uniqueness / duplicate tolerance | ✅ Satisfied | Duplicate `event_id` representation remains stable across serialization (test `test_duplicate_event_id_is_stable`); no dedup implemented (correctly out of scope) |

### Validation requirements (must reject)

| Requirement | Status | Evidence |
| --- | --- | --- |
| Missing required envelope field | ✅ Satisfied | `test_missing_required_envelope_field` (removes `source`) |
| Missing required payload field | ✅ Satisfied | `test_missing_required_payload_field` (removes `name`) |
| Malformed / invalid timestamps | ✅ Satisfied | Naive `produced_at`/`collected_at` rejected; non-datetime rejected by type |
| Negative or invalid non-null price | ✅ Satisfied | `test_negative_price` (Decimal `-0.01`) |
| Invalid data types | ✅ Satisfied | `test_invalid_price_type` (`"not-a-number"`) |
| Invalid availability | ✅ Satisfied | `test_invalid_availability_enum_value` (`back_soon`) |
| Invalid currency | ✅ Satisfied | `test_invalid_currency` (`euro`) |
| Empty identifier / name | ✅ Satisfied | `test_empty_external_id_is_rejected`; all `str` fields use `min_length=1` |
| Unsupported schema version | ✅ Satisfied | `test_unsupported_schema_version` (`99`) |

All 14 test cases mandated by the task are covered (see §4).

---

## 3. Git Diff Review

### Files changed (`a31aec2..451af12`)

| File | Change | In scope? |
| --- | --- | --- |
| `libs/event_contracts/product_observation.py` | New canonical model (173 lines) | ✅ Core task |
| `libs/event_contracts/__init__.py` | Package exports | ✅ Core task |
| `libs/event_contracts/py.typed` | Empty PEP 561 marker | ✅ Core task |
| `libs/event_contracts/README.md` | New package doc | ✅ Core task |
| `libs/event-contracts/README.md` | Deleted (rename) | ✅ Related to rename |
| `libs/README.md` | Documents spec-vs-package name mapping | ✅ Related to rename |
| `scripts/verify_repository_structure.py` | `event-contracts` → `event_contracts` | ✅ Related to rename |
| `tests/test_product_observation_event.py` | 19 unit tests | ✅ Core task |
| `scripts/qwen_review_task.ps1` | Review-launcher tooling change | ⚠️ Out of scope (see F2) |

### Scope correctness

The implementation commit `ae7c8f0` is tightly scoped: it adds the event-contract model, tests, and the minimal structural/doc updates required by the package rename. No Kafka producer/consumer, topic configuration, deduplication storage, lake persistence, or adapter code was introduced — consistent with the task's out-of-scope list.

### Architectural changes

- **Directory rename `event-contracts/` → `event_contracts/`.** The specification's §5 boundary is named `libs/event-contracts/`, but a hyphen is not a valid Python identifier, so the package was implemented as `event_contracts` (snake_case). This is technically sound and documented in `libs/README.md` and `libs/event_contracts/README.md`, and `verify_repository_structure.py` was updated to match. However, `ai/SPECIFICATION.md` §5 still names `event-contracts/`, leaving the authoritative spec and the code out of sync. See finding F1.
- No service boundaries, event semantics, or ownership rules were otherwise altered. `partition_key` is a computed property and is not serialized, so the envelope remains exactly the six required fields.

### Unrelated changes

- `scripts/qwen_review_task.ps1` (commit `451af12`, "script update") changes how the review is launched (interactive prompt instead of piping the diff via stdin). This is workflow/tooling maintenance, not TASK-006 event-contract work. See finding F2.

### Accidental / debugging / secrets

- None found. No debug prints, dead code, generated artifacts, temporary files, or credentials. `py.typed` is intentionally empty (valid PEP 561 marker).

### Dependency / configuration changes

- None. `pydantic>=2.12` was already a runtime dependency (from TASK-003); no new dependency was introduced. `pyproject.toml` unchanged.

---

## 4. Test and Verification Review

### Tests examined

`tests/test_product_observation_event.py` — 19 tests. All 14 task-mandated cases are covered:

1. valid event creation → `test_valid_event_creation`
2. deterministic serialize/deserialize → `test_deterministic_serialization_and_deserialization`
3. missing required envelope field → `test_missing_required_envelope_field`
4. missing required payload field → `test_missing_required_payload_field`
5. invalid `produced_at` → `test_invalid_produced_at_naive`
6. invalid `collected_at` → `test_invalid_collected_at_naive`
7. negative price → `test_negative_price`
8. null price → `test_null_price`
9. invalid price type → `test_invalid_price_type`
10. invalid availability → `test_invalid_availability_enum_value`
11. invalid currency → `test_invalid_currency`
12. unsupported schema version → `test_unsupported_schema_version`
13. duplicate `event_id` stability → `test_duplicate_event_id_is_stable`
14. `external_id` distinct from `product_id` → `test_external_id_is_distinct_from_product_id`

Plus 5 additional coverage tests (event-type default, partition key, deterministic event-id helper, `collected_at`/`produced_at` distinctness, empty `external_id`).

### Test adequacy

Adequate for the task. Tests exercise the actual serialized contract shape, assert equality (not just non-exception), and use `pytest.raises` with message assertions on the failure cases so they are not vacuous. No test was weakened to make the implementation pass.

### Independently executed by the reviewer (all passed)

| Check | Command | Result |
| --- | --- | --- |
| Unit tests (targeted) | `python -m pytest tests/test_product_observation_event.py -v` | **19 passed** |
| Full suite | `python -m pytest` | **40 passed, 7 deselected (integration)** |
| Lint | `python -m ruff check libs/event_contracts tests/test_product_observation_event.py scripts/verify_repository_structure.py` | **All checks passed** |
| Format | `python -m ruff format --check libs/event_contracts tests/test_product_observation_event.py` | **4 files already formatted** |
| Type check | `python -m mypy libs/event_contracts tests/test_product_observation_event.py` | **Success — no issues** |
| Structure | `python scripts/verify_repository_structure.py` | **Passed** |

### Verification classification

- **Independently verified** — the six commands above were executed by the reviewer.
- **Implementation evidence reviewed** — the commit message reports `pytest (35/35)`; the current tree runs 40 unit tests (the suite grew slightly since that count), so the commit-message figure is stale rather than misleading.
- **Unverified** — none applicable; no Docker/Kafka/integration tests are required by this task (Kafka behavior is explicitly out of scope).

---

## 5. Findings

### F1 — Moderate — SPECIFICATION.md §5 boundary name is out of sync with the implementation

- **File/line:** `ai/SPECIFICATION.md` §5 (`libs/event-contracts/`) vs `libs/event_contracts/` in the tree
- **Problem:** The normative boundary in `ai/SPECIFICATION.md` §5 is `event-contracts/`. The implementation (correctly, for Python importability) uses `event_contracts/`, and `scripts/verify_repository_structure.py` now enforces `libs/event_contracts`. The authoritative specification was not updated, so the spec and the code now disagree on a normative directory name.
- **Impact:** Future agents reading §5 as the source of truth will expect `event-contracts/` and may re-create or mis-target the directory; the repo-structure check enforces the opposite name. This is a governance/spec-drift issue, not a runtime defect.
- **Recommendation:** Update `ai/SPECIFICATION.md` §5 to `libs/event_contracts/` (or add an ADR/note documenting the "spec uses kebab-case, Python package uses snake_case" convention), keeping the READMEs and structure verifier in agreement.

### F2 — Moderate — Out-of-scope workflow-tooling commit on the TASK branch

- **File/line:** `scripts/qwen_review_task.ps1` (commit `451af12`, "script update")
- **Problem:** The review range contains a second commit that rewrites the review-launcher script (switches from piping the diff via stdin to an interactive prompt). This is workflow/tooling maintenance, not TASK-006 event-contract work. Per `ai/AGENTS.md` §16 "Workflow Maintenance Changes", tooling maintenance should use a dedicated `codex/<maintenance-name>` branch, separate from TASK branches.
- **Impact:** Dilutes task/commit isolation for `feature/TASK-006`; the TASK-006 code itself is unaffected.
- **Recommendation:** Keep workflow/tooling maintenance on a `codex/<name>` branch. No action is needed on the code; the change is small and self-consistent.

### F3 — Moderate — `str_strip_whitespace` silently normalizes identity fields

- **File/line:** `libs/event_contracts/product_observation.py` — `model_config = {"str_strip_whitespace": True}` on both models
- **Problem:** Both models strip leading/trailing whitespace from every string field, including the identity fields `event_id`, `external_id`, and `source`. The task states: "Do not silently coerce malformed contract data into a valid-looking event." Stripping a value such as `external_id = " SKU-1 "` to `"SKU-1"` silently alters the source-level identity and could collide with a genuinely distinct `"SKU-1"`, weakening the downstream idempotency/dedup key. Whitespace-only values are correctly rejected (they strip to empty and then fail `min_length=1`), so this is about normalization, not a bypass.
- **Impact:** Low probability but real data-integrity risk for identity semantics; it also contradicts the task's "fail explicitly rather than silently coerce" instruction for the fields that matter most to idempotency.
- **Recommendation:** Disable `str_strip_whitespace` for `event_id`, `external_id`, and `source` (e.g., a per-field `str_strip_whitespace=False` override), or document the normalization as an accepted boundary behavior. `name`, `url`, and `category` may reasonably keep trimming.

---

## 6. Non-Defect Observations

1. **`event_type` and `schema_version` are defaults, not strictly required inputs.** `event_type` defaults to the sole `Literal` value and `schema_version` defaults to `1` (the only supported version). A producer may omit them and still obtain a valid event, which technically softens SPEC §7's "required fields" wording. This is harmless: the defaults cannot produce an invalid value, and the serialized envelope still contains all six fields. Flagged as intentional design, not a defect.

2. **`partition_key` and `make_event_id` lightly anticipate TASK-007.** The `partition_key` (`source:external_id`) and deterministic `make_event_id` helper reference Kafka-partitioning/idempotency concerns that SPEC §8 defers to TASK-007/ADR-001. They are stable-identifier helpers at the contract boundary — not Kafka producer/consumer or topic behavior — and are consistent with the task's requirement to "provide the stable identifiers required for downstream idempotent processing." Acceptable.

3. **`url` is validated only as non-empty.** No URL-format validation is applied. The task requires only non-empty values for identifiers/names; URL-format checking is not required by SPEC or the task. Acceptable, but a future adapter-side URL check may be desirable.

4. **`currency` is pattern-validated, not ISO-4217 membership-checked.** `^[A-Z]{3}$` matches SPEC's "three uppercase letters" and the task's "three-letter currency code" requirement. Membership validation against the full ISO-4217 list is stricter than required.

5. **`Decimal` price and float inputs.** Adapters that feed raw Python floats (e.g., from `json.loads`) will be converted to `Decimal` via their string form, which preserves binary-float noise (e.g., `0.1 + 0.2` → `Decimal("0.30000000000000004")`). JSON serialization stores `Decimal` as a string, so round-trips are exact. Future adapters should supply prices as `Decimal` or strings to avoid precision noise in the monetary field.

6. **No ADR created for this task.** Correct — SPEC §8 records the concrete partition count/key in ADR-001 during TASK-007; TASK-006 introduces no architecture decision requiring an ADR.

7. **`py.typed` marker present.** The empty PEP 561 marker enables downstream mypy users to consume the package's types. Good practice.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The TASK-006 implementation correctly and completely realizes the canonical product-observation event contract from `ai/SPECIFICATION.md` §7. All six envelope fields and all eight payload fields are present with the required types and constraints; schema-version handling is explicit and rejects unsupported versions; serialization/deserialization is deterministic; and all 14 mandated validation/test cases are covered. The implementation commit (`ae7c8f0`) is tightly scoped and introduces no new dependencies, secrets, dead code, or out-of-scope Kafka/database behavior. All verification checks were independently executed by the reviewer and pass.

Three non-blocking findings remain, none of which is Critical or High:

- **F1** — update `ai/SPECIFICATION.md` §5 to reflect the `event_contracts/` (snake_case) package name so the authoritative spec and code agree.
- **F2** — the `script update` commit is workflow-tooling maintenance committed to the TASK branch; route such maintenance to a `codex/<name>` branch going forward.
- **F3** — `str_strip_whitespace` silently normalizes the identity fields; consider disabling it for `event_id`/`external_id`/`source` or documenting the normalization.

These do not block acceptance of the TASK-006 implementation.
