# TASK-FIX-KAFKA-LAG-PROBE-TEST — Review

## 1. Review Header

- **Task ID:** TASK-FIX-KAFKA-LAG-PROBE-TEST (fix + regression tests for the TASK-112 Kafka lag probe)
- **Review date:** 2026-09-25
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set:** `5a47aedb38e42042a36c771f606151af30947a1f..b4519cb004a1df80e3b6c3c5fd7fd29f472ecc08`
- **Reviewed HEAD:** `b4519cb004a1df80e3b6c3c5fd7fd29f472ecc08` on `feature/TASK-FIX-KAFKA-LAG-PROBE-TEST`
- **Commits reviewed:**
  - `5a47aed` — `fix: correct Kafka consumer lag offset query`
  - `b4519cb` — `test(TASK-FIX-KAFKA-LAG-PROBE-TEST): add regression tests for Kafka lag probe`
- **Scope:** Corrects the `AdminClient.list_consumer_group_offsets()` call in `libs/load_test/kafka_lag_probe.py` and adds deterministic regression tests for it.
- **Verdict:** `APPROVED WITH NON-BLOCKING FINDINGS`

### Authorities consulted

- `ai/AGENTS.md` (§7 testing, §8 distributed-systems semantics, §11 agent roles, §16 git task isolation)
- `ai/REVIEWER.md`
- `ai/tasks/TASK-112-measure-kafka-lag.md` (the task this fix targets; see Finding F2)
- `ai/PROJECT.md` (§10 Observability Principles; §9 at-least-once semantics)
- `docs/reviews/TASK-112-review.md` (prior review of the code under fix)
- Installed `confluent_kafka` 2.15.0 source (`AdminClient.list_consumer_group_offsets`, `_model.ConsumerGroupTopicPartitions`, `cimpl.TopicPartition`)

No authority conflicts identified.

> Note: no `ai/tasks/TASK-FIX-KAFKA-LAG-PROBE-TEST.md` exists in the repository. There is therefore no primary task specification for this fix; the review treats it as a follow-up correction to TASK-112 (see Finding F2).

---

## 2. Requirements Coverage

There is no task specification for `TASK-FIX-KAFKA-LAG-PROBE-TEST`. The following coverage table is therefore framed against the *defect* the changes address: the confluent_kafka API incompatibility in the TASK-112 lag probe, plus the open TASK-112 review finding F1 (no test coverage for `kafka_lag_probe.py`).

| Requirement / intent | Status | Implementation evidence |
|---|---|---|
| Correct the `list_consumer_group_offsets` request to use `_ConsumerGroupTopicPartitions` objects instead of bare group-ID strings | **Met** | `kafka_lag_probe.py:138` builds `request = [_ConsumerGroupTopicPartitions(group_id=group_id)]`. Verified against `confluent_kafka 2.15.0` `AdminClient.list_consumer_group_offsets`, whose `_check_list_consumer_group_offsets_request` requires `_ConsumerGroupTopicPartitions` elements. |
| Read committed offsets via `result.topic_partitions` attribute (not `result.items()`) | **Met** | `kafka_lag_probe.py:144-146` reads `getattr(result, "topic_partitions", None) or []`. The `.result()` value is a `ConsumerGroupTopicPartitions` whose `topic_partitions` defaults to `None`; the `or []` guard is correct. |
| Preserve `futures[group_id]` access (futures are keyed by group-id string) | **Met** | `kafka_lag_probe.py:139-141`. Verified: `list_consumer_group_offsets` returns `Dict[str, Future]` keyed by group id (`AdminClient._make_futures([request.group_id ...])`), so `if group_id not in futures` / `futures[group_id]` remain valid. |
| Missing committed offset → `-1`; lag semantics unchanged | **Met** | `offset_lookup.get((topic, p), -1)` preserves the prior no-commit convention; `query()` lag math (`high - committed`, `max(0, ...)`, no-commit → `high - low`) is untouched. |
| Add deterministic tests for the fixed module (TASK-112 review F1) | **Met** | `tests/test_load_test/test_kafka_lag_probe.py` adds 15 tests covering request-object shape, `topic_partitions` access, offset mapping, `-1` defaults, multi-topic/multi-partition, lag math, clamping, and error-skip paths. |
| No unrelated changes / no new dependencies / no secrets | **Met** | Diff is confined to `kafka_lag_probe.py` and one new test file; no dependency, config, or infra changes. |

---

## 3. Git Diff Review

**Files changed (2 files, +509 / −8):**

| File | Change |
|---|---|
| `libs/load_test/kafka_lag_probe.py` | Modified (+9/−8): `_get_committed_offsets` rewritten |
| `tests/test_load_test/test_kafka_lag_probe.py` | New (+500): 15 regression tests |

- **Scope correctness:** Both changes belong to the stated fix. The commit range `5a47aed..b4519cb` contains exactly these two commits (equivalent to `42455c4..b4519cb`).
- **Unrelated changes:** None.
- **Architectural changes:** None. Service boundaries, event contract, ADR-001 partitioning, and at-least-once semantics are untouched. The fix is confined to the read-side admin-query mechanics of the load-test probe.
- **Dependency/configuration changes:** None. `confluent_kafka` was already established by TASK-112.
- **Accidental changes:** None (no debug code, temp files, generated artifacts, or secrets).
- **Test changes that weaken validation:** None. No existing test was modified; the addition is purely additive.

### Out-of-scope / still-open items (from TASK-112 review)

The following prior findings are **not** addressed by this change set and remain open (correctly out of scope for a targeted fix): probe client resource leak (F2), `LagSample` name collision with `libs.observability.kafka_metrics.LagSample` (F3), silent lag-monitor failure (F4), hardcoded partition count (F5), `group.id` from `id()` (F6), no-commit reported as full partition depth (F7), test placement (F8), docstring drift (F9), non-configurable thresholds (F10). These are noted for completeness, not as new defects introduced here.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_load_test/test_kafka_lag_probe.py` (new) — 15 tests:
  - `TestGetCommittedOffsets` (7): request uses `_ConsumerGroupTopicPartitions`; a bare string would not be accepted; `topic_partitions` attribute read; missing offset → `-1`; group absent from futures → `{}`; empty `topic_partitions` → all `-1`; multi-topic/multi-partition mapping.
  - `TestCreateLagQueryFn` (8): lag with committed offset, lag without committed offset (`high - low`), non-negative clamp, multiple groups, multiple partitions, committed-offset error skips group, watermark error skips partition, `elapsed_sec` propagation.

### Verification classification

| Check | Status | Evidence |
|---|---|---|
| `python -m pytest tests/test_load_test/test_kafka_lag_probe.py -v` | **Independently verified** | `15 passed in 8.08s` |
| `python -m pytest tests/test_load_test/ -q` | **Independently verified** | `64 passed in 11.70s` |
| `python -m ruff check libs/load_test/kafka_lag_probe.py tests/test_load_test/test_kafka_lag_probe.py` | **Independently verified** | `All checks passed!` |
| `python -m ruff format --check …` | **Independently verified** | `2 files already formatted` |
| `python -m mypy libs/load_test/kafka_lag_probe.py tests/test_load_test/test_kafka_lag_probe.py` | **Independently verified** | `Success: no issues found in 2 source files` |
| Kafka integration tests (`pytest -m integration`) | **Unverified / not rerun** | Requires the Docker Compose stack; not run by the reviewer. The API-contract correctness was instead verified directly against the installed `confluent_kafka 2.15.0` source (see below). |

### Independent API-contract verification (no broker required)

The correctness of the fix rests on the confluent_kafka admin API, so I inspected the installed `confluent_kafka 2.15.0` source rather than a live broker:

- `AdminClient.list_consumer_group_offsets(...)` returns `Dict[str, Future]` keyed by **group id**, and `_check_list_consumer_group_offsets_request` requires `_ConsumerGroupTopicPartitions` elements. → the request-object change and the `futures[group_id]` access are correct.
- The future `.result()` returns a `ConsumerGroupTopicPartitions` (module `confluent_kafka._model`), which exposes `topic_partitions: Optional[List[TopicPartition]]` (default `None`). → `getattr(result, "topic_partitions", None) or []` is correct.
- `confluent_kafka.TopicPartition` (cimpl) exposes `.topic`, `.partition`, and `.offset`. → the `offset_lookup` construction is correct.
- The public class is `confluent_kafka.ConsumerGroupTopicPartitions`; the imported `_ConsumerGroupTopicPartitions` is a private alias of the same object (`is` identity confirmed). → functional but fragile naming (Finding F1).

### Test adequacy

The tests are thorough for the function under fix and correctly encode the post-fix contract. The most notable adequacy limitation is that they mock the entire `confluent_kafka` module (`patch.dict(sys.modules, …)`), so they assert the code's *intended* contract rather than validating it against the real library (Finding F3). This is an acceptable unit-test trade-off, but it means the suite would not catch a future confluent_kafka API change on its own.

---

## 5. Findings

### F1 — Moderate: uses a private confluent_kafka class name
- **Affected:** `libs/load_test/kafka_lag_probe.py:136,138`
- **Problem:** The fix imports `from confluent_kafka.admin import _ConsumerGroupTopicPartitions`. This is an underscore-prefixed private alias; the stable public name `confluent_kafka.ConsumerGroupTopicPartitions` exists and is the *same* class (confirmed `P is U == True`, module `confluent_kafka._model`).
- **Impact:** The whole point of this fix is API compatibility with confluent_kafka, yet it pins to a private symbol that could be removed or renamed in a future release without notice — recreating the exact class of breakage this task fixes.
- **Recommendation:** Use `from confluent_kafka import ConsumerGroupTopicPartitions` (public, top-level) and update the test's `_patch_confluent_kafka` to patch the public name accordingly.

### F2 — Moderate: no task specification exists for this fix
- **Affected:** `ai/tasks/` (missing `TASK-FIX-KAFKA-LAG-PROBE-TEST.md`)
- **Problem:** The branch (`feature/TASK-FIX-KAFKA-LAG-PROBE-TEST`) and both commit messages reference a task spec that does not exist in the repository. Other fix tasks do ship a spec (e.g. `TASK-K8S-FIX-001.md`, `TASK-K8S-FIX-003.md`). Per REVIEWER.md, the task specification is the primary source for judging scope and acceptance.
- **Impact:** Governance gap — acceptance criteria and scope cannot be verified against a primary source; the review is forced to infer them from the TASK-112 defect and the open TASK-112 review finding F1.
- **Recommendation:** Add `ai/tasks/TASK-FIX-KAFKA-LAG-PROBE-TEST.md` documenting the defect, scope, and acceptance criteria, or fold this into the TASK-112 spec. Note the branch name also deviates from the `feature/TASK-xxx` convention.

### F3 — Minor: regression tests mock confluent_kafka instead of validating the real API
- **Affected:** `tests/test_load_test/test_kafka_lag_probe.py` (`_patch_confluent_kafka`, `_make_consumer_group_topic_partitions_cls`, `_make_topic_partition_cls`)
- **Problem:** All 15 tests patch `sys.modules` with `MagicMock` stand-ins for `confluent_kafka`, `confluent_kafka.admin`, and `TopicPartition`. They assert the code's internal contract (request object is the mocked class; result has a `topic_partitions` attribute) but never confirm that this matches the *actual* confluent_kafka API.
- **Impact:** A future confluent_kafka change to the result shape, keying, or request type would not be caught — the tests would keep passing against the mock while production broke. The contract was only verified correct today because I cross-checked the installed library source.
- **Recommendation:** Add one non-broker test that asserts the real `confluent_kafka` objects satisfy the assumptions (e.g. `ConsumerGroupTopicPartitions('g').topic_partitions is None`; `TopicPartition('t',0,1).offset == 1`), or a broker-backed `@pytest.mark.integration` test.

### F4 — Minor: verbose test scaffolding obscures intent
- **Affected:** `tests/test_load_test/test_kafka_lag_probe.py` (repeated `_patch_confluent_kafka` + `patch.dict(sys.modules, …)` blocks)
- **Problem:** Each test repeats the module-patching and mock-construction boilerplate (~15–30 lines each), which makes the 500-line file harder to scan than its 15 assertions warrant.
- **Impact:** Readability/maintenance only.
- **Recommendation:** Extract a `pytest.fixture` for the patched module environment and/or a small `_run_query` helper; consolidate the duplicated `make_futures` side-effect builders.

---

## 6. Non-Defect Observations

- **The fix is correct against the installed confluent_kafka 2.15.0.** Independently confirmed at the source level: futures are keyed by group-id string, `.result()` yields a `ConsumerGroupTopicPartitions` with a nullable `topic_partitions` list, and each `TopicPartition` carries `.offset`. The previous implementation (`list_consumer_group_offsets([group_id])` with bare strings + `result.items()`) would have failed against this version, so the change fixes a real defect, not a cosmetic one.
- **Good defensive handling of the nullable result.** `getattr(result, "topic_partitions", None) or []` correctly handles the case where a group has no committed offsets (empty/`None` `topic_partitions`), and `offset_lookup.get(..., -1)` preserves the documented no-commit convention.
- **Tests are genuinely deterministic and broker-free** (no sleeps, no network, no flaky timing), and pass consistently (`15 passed`, `64 passed` for the full load-test suite).
- **No weakening of existing tests** and no behavior change to `query()`'s lag math, error skipping, or sample shape — the fix is tightly scoped to the admin offset query.
- **The test file naming/placement** (`tests/test_load_test/test_kafka_lag_probe.py`) resolves TASK-112 review finding F8's organizational concern for the probe (the collector's own test still lives at `tests/test_lag_collector.py`, which remains out of scope here).

---

## 7. Verdict

**`APPROVED WITH NON-BLOCKING FINDINGS`**

The fix correctly repairs the confluent_kafka admin-query incompatibility in `kafka_lag_probe.py`, and the new 15-test regression suite is deterministic, lint/type-clean, and passes. The correctness of the change was independently verified against the installed `confluent_kafka 2.15.0` source, not just against the mocks.

No Critical or High findings. The two Moderate findings are non-blocking: F1 (prefer the public `ConsumerGroupTopicPartitions` name over the private `_ConsumerGroupTopicPartitions` alias) and F2 (missing task specification for this fix). F3/F4 are minor test-quality observations.

Recommended follow-ups before relying on this probe downstream (TASK-113/114/115): switch to the public class name (F1) and, if possible, add a single broker-backed integration test to lock the contract against the real library rather than mocks (F3).
