# TASK-077 Review — Kafka Deployment and Configuration for kind (Round 2)

## 1. Review Header

- **Task ID:** TASK-077
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:**
  `5f217c5deb36132c683e0a36c01b16e06dca16b0..466284f109eecda9096c09d261257dcf87c128d0`
  (three commits: `98d9e25` feat, `44c0dd2` round-1 review record, `466284f` fix)
- **Reviewed HEAD:** `466284f109eecda9096c09d261257dcf87c128d0` on `feature/TASK-077`
- **Scope:** Kafka broker Deployment (single-node KRaft), NodePort Service, a
  topic-creation Job, `kubernetes/README.md` documentation, and manifest
  validation tests in `tests/test_kubernetes_manifests.py`.
- **Verdict:** **APPROVED WITH NON-BLOCKING FINDINGS**

This is a **round-2 review**. The round-1 review (`44c0dd2`) returned
**CHANGES REQUIRED** with one blocking finding (F1) and six non-blocking
findings (F2–F7). The fix commit `466284f` addresses F1, F3, F4, and F5. This
report re-evaluates HEAD `466284f` and records the disposition of every round-1
finding plus any new observations.

---

## 2. Requirements Coverage

The task objective is: deploy/configure Kafka for kind consistently with current
architecture; make it reachable by ingestion/processor/writers; create/verify
established topics; preserve delivery/consumer semantics; document diagnosis.

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Deploy Kafka broker for kind | Met | `kubernetes/deployments/kafka-deployment.yaml` (`apps/v1/Deployment`, `name: kafka`, `apache/kafka:4.3.1`). |
| R2 | Single-node KRaft (no ZooKeeper), consistent with docker-compose | Met | `KAFKA_PROCESS_ROLES=broker,controller`, `KAFKA_NODE_ID=1`, `KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER`; controller quorum now `1@localhost:29093` (fixes F1). |
| R3 | Reachable in-cluster by ingestion/processor/writers | Met | `kafka-service.yaml` exposes `kafka:29092` (PLAINTEXT listener). Sibling deployments consume via `APP_KAFKA_BOOTSTRAP_SERVERS=kafka:29092`. |
| R4 | Create/verify the five established topics | Partially met | `kafka-topics-job.yaml` creates all five ADR-001 topics with `--if-not-exists` and per-topic retention; still **does not validate** created/existing topics (F6). |
| R5 | Correct partition counts and retention per ADR-001 | Met | Job values match ADR-001 exactly: raw/validated 3p/7d, invalid 1p/7d, pipeline/data-quality 1p/3d (`retention.ms` = 604800000 / 259200000). |
| R6 | Preserve delivery/consumer semantics (at-least-once + replay) | Partially met | Auto-create disabled, explicit topics, `KAFKA_DEFAULT_REPLICATION_FACTOR=1`; but **no persistent storage**, so replay/offsets/topics are lost on pod restart (F2, still open). |
| R7 | Document diagnosis (kubectl/kafka CLI) | Met | README documents `kubectl apply/get/logs/exec` plus `kafka-topics.sh`/`kafka-broker-api-versions.sh` inside the pod. One stale port reference noted (N1). |
| R8 | Declarative manifests + consistent labels/selectors | Met | Labels `app.kubernetes.io/name|part-of|component`; Service selector (`name`+`part-of`) matches template labels; mirrors sibling deployments. |
| R9 | Never commit real secrets | Met | No credentials in any manifest. |
| R10 | Remain Helm-compatible without implementing Helm | Met | Plain declarative manifests; no Helm artifacts. |
| R11 | No unrelated changes | Met | Diff limited to task-scoped files (see §3). |

---

## 3. Git Diff Review

Range contains three commits. Aggregate diffstat:

| File | Change |
|---|---|
| `kubernetes/deployments/kafka-deployment.yaml` | new manifest (70 lines) |
| `kubernetes/deployments/kafka-service.yaml` | new manifest (24 lines) |
| `kubernetes/deployments/kafka-topics-job.yaml` | new manifest (78 lines) |
| `tests/test_kubernetes_manifests.py` | +129 lines (3 new test classes) |
| `kubernetes/README.md` | +38/-1 (tree, Kafka section, port-mapping table) |
| `docs/reviews/TASK-077-review.md` | +299 (round-1 review record) |

- **Scope correctness:** All changes belong to TASK-077. No application code was
  modified — this task wires Kafka infrastructure only.
- **Unrelated changes:** None. The `docs/reviews/TASK-077-review.md` entry is the
  round-1 review record, which is an authorized review artifact.
- **Architectural changes:** None. Kafka remains transport/buffering/replay
  infrastructure (PROJECT.md §4); no service-boundary, event-contract, or
  topic-ownership change.
- **Accidental changes / debug code / generated artifacts / secrets:** None found.
- **Dependencies:** `pyproject.toml` unchanged; no new Python dependencies.
- **Configuration/infrastructure changes:** Three new manifests, consistent in shape
  with sibling deployments; no changes to kind config, namespace, or CI.
- **Branch/task isolation:** Reviewed on `feature/TASK-077`; working tree clean; the
  range contains exactly three TASK-077 commits. Correct isolation.

The fix commit `466284f` modifies only the three Kafka manifests and the manifest
test file — a tight, correctly-scoped fix.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_kubernetes_manifests.py::TestKafkaDeployment` — 9 tests: existence,
  resource kind, namespace, labels, selector/template match, KRaft mode, auto-create
  disabled, and container ports 29092/9092 exposed.
- `tests/test_kubernetes_manifests.py::TestKafkaService` — 6 tests: existence, kind,
  namespace, labels, selector→deployment-template match, NodePort type, and the
  `nodePort: 30092` mapping (now correctly asserted on the **external** 9092 port).
- `tests/test_kubernetes_manifests.py::TestKafkaTopicsJob` — 4 tests: existence, kind,
  namespace, and that all five topic *names* appear in the Job command script.

These validate **manifest structure only** (YAML file content), consistent with the
TASK-070 test convention ("tests run without a live cluster"). They do **not** deploy
Kafka or verify reachability — actual kind deployment/integration smoke tests are
deferred to TASK-079 per the ROADMAP.

### Verification classification

- **Independently verified (reviewer-executed):**
  - `python -m pytest tests/test_kubernetes_manifests.py -q` → **86 passed** (1.00s).
  - `python -m ruff check tests/test_kubernetes_manifests.py` → **All checks passed**.
  - `python -m mypy tests/test_kubernetes_manifests.py` → **Success: no issues found**.
- **Implementation evidence reviewed:** the diff is minimal and targeted; the new
  YAML parses successfully (confirmed by the passing `_load_yaml`-based tests); the
  topic names/partitions/retention were cross-checked against ADR-001 and
  `scripts/manage_kafka_topics.py` and match.
- **Unverified:** `python -m pytest -m integration` and any live
  `kubectl apply/get/logs/exec` run against a kind cluster. This task touches the
  Kafka infrastructure boundary, so the reviewer flags it. No evidence was supplied
  that the TASK-077 manifests were applied to a running kind cluster, so the "Kafka
  broker actually starts and is reachable" acceptance behavior is **not demonstrated**
  by the submitted change. The F1 fix uses the standard single-node KRaft pattern
  (`1@localhost:29093`), which is theoretically sound, but has not been confirmed in a
  live cluster. TASK-079 is explicitly scoped to add Kubernetes integration smoke
  tests (including CrashLoopBackOff/ImagePullBackOff reproduction), so this deferral
  is architecturally sanctioned and is not treated as blocking here.

---

## 5. Findings

### Disposition of round-1 findings

#### F1 — High: KRaft controller listener port (29093) not exposed by the Service — **RESOLVED**

- **Status:** Fixed in `466284f`.
- **Change:** `KAFKA_CONTROLLER_QUORUM_VOTERS` changed from `1@kafka:29093` to
  `1@localhost:29093` (`kubernetes/deployments/kafka-deployment.yaml`).
- **Assessment:** This is the standard single-node combined broker+controller KRaft
  pattern. The controller listener still binds `CONTROLLER://:29093` inside the pod,
  and `localhost:29093` resolves pod-locally without a Service round-trip, so the
  broker can reach its own quorum. Correct and complete. The controller port is not
  declared as a `containerPort`, but that is harmless because it is reached via
  pod-local localhost, not via the Service. No residual issue.

#### F2 — Moderate: no persistent storage for Kafka data; topics lost on pod restart — **OPEN**

- **Severity:** Moderate
- **Status:** Not addressed.
- **Affected:** `kubernetes/deployments/kafka-deployment.yaml` (no `volumeMounts`/PVC,
  no `CLUSTER_ID`, no `KAFKA_LOG_DIRS`).
- **Problem:** `docker-compose.yml` persists Kafka state via the `kafka_data` volume,
  pins `CLUSTER_ID`, and sets `KAFKA_LOG_DIRS`. The Deployment has none of these, so
  the KRaft metadata log and all topic data live in the container's ephemeral
  writable layer. Any pod/container restart reformats the log as a new cluster and
  wipes all topics and messages. Because `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false` and
  `kafka-topics-setup` is a one-shot Job (its pod template is immutable), topics are
  not automatically re-created after a restart.
- **Impact:** Weakened replay/recovery semantics (PROJECT.md §9; ADR-001
  "manual topic creation required"), and downstream consumers fail with unknown
  topics after a broker restart. The "preserve delivery/consumer semantics" objective
  is only partially met.
- **Recommendation:** Add a PVC (e.g. `kafka-data`) mounted at `/var/lib/kafka/data`
  and set `CLUSTER_ID` (and optionally `KAFKA_LOG_DIRS`) to mirror docker-compose; or,
  if ephemeral state is an intentional local-kind trade-off, document it explicitly
  and add a topic-reconciliation mechanism (an initContainer or a re-runnable
  uniquely-named Job) so restart recovery is automated. This is a deliberate decision,
  not a silent omission, and it should not be left silent. TASK-079's integration
  tests are likely to surface this if not addressed.

#### F3 — Moderate: advertised-listener / NodePort mismatch for host access — **RESOLVED**

- **Status:** Fixed in `466284f`.
- **Change:** `kubernetes/deployments/kafka-service.yaml` moved `nodePort: 30092` from
  the internal `port: 29092` to the external `port: 9092`/`targetPort: 9092`
  (PLAINTEXT_HOST listener).
- **Assessment:** The kind port map (host 9092 → node 30092) now routes host clients
  to the PLAINTEXT_HOST listener, which advertises `localhost:9092`. Host clients
  receive usable metadata and can reconnect. Correct on a single-node kind cluster.
  (See N1 for a related stale README reference.)

#### F4 — Moderate: missing `KAFKA_HEAP_OPTS` risks OOMKill under the 1Gi memory limit — **RESOLVED**

- **Status:** Fixed in `466284f`.
- **Change:** Added `KAFKA_HEAP_OPTS: "-Xmx512M -Xms256M"` to
  `kubernetes/deployments/kafka-deployment.yaml`, matching docker-compose.
- **Assessment:** The 512M heap now sits comfortably under the 1Gi limit. Correct.

#### F5 — Minor: topic-creation Job has an unbounded readiness wait — **RESOLVED (with minor residual)**

- **Status:** Core issue fixed in `466284f`.
- **Change:** `kubernetes/deployments/kafka-topics-job.yaml` now sets `TIMEOUT=120`
  and increments `ELAPSED` each iteration, exiting non-zero after 120s.
- **Assessment:** The readiness wait is now bounded, so a hung broker surfaces
  promptly. **Residual (non-blocking):** no `ttlSecondsAfterFinished` to clean up the
  completed Job pod, and no `activeDeadlineSeconds`. The in-script timeout makes the
  latter redundant for the wait loop; the former is a minor hygiene improvement.

#### F6 — Minor: topics Job creates but does not validate topic configuration — **OPEN**

- **Severity:** Minor
- **Status:** Not addressed.
- **Affected:** `kubernetes/deployments/kafka-topics-job.yaml` (creation only, no
  `--describe` validation).
- **Problem:** The Docker Compose workflow (`scripts/manage_kafka_topics.py`) runs
  `create` then `validate` to enforce exact partition count, replication factor, and
  explicit retention, and to detect drift on re-runs. The Job only runs
  `--create --if-not-exists`; a pre-existing topic with wrong partitions/retention is
  silently skipped, and `--if-not-exists` never corrects it.
- **Impact:** Divergence from the established drift-detection behavior; the "verify
  established topics" part of the objective is not met. For a fresh kind cluster this
  is benign.
- **Recommendation:** Add a `--describe` verification step (or otherwise mirror the
  `validate` semantics) so the Job fails loudly on drift.

#### F7 — Minor: manifest test asserts topic names only, not partition/retention values — **OPEN**

- **Severity:** Minor
- **Status:** Not addressed.
- **Affected:** `tests/test_kubernetes_manifests.py::TestKafkaTopicsJob`
  (`test_kafka_topics_job_creates_all_topics`).
- **Problem:** The test checks only that the five topic *names* appear as substrings
  in the Job command. The ADR-001 partition counts and retention values (hardcoded in
  the Job) are not asserted, so a regression changing `--partitions 3` to
  `--partitions 1` or `retention.ms=604800000` to `retention.ms=86400000` would still
  pass green. (The canonical values are pinned elsewhere by `tests/test_kafka_topics.py`,
  but that covers `manage_kafka_topics.py`, not this Job.)
- **Impact:** The structural safety net does not actually protect the topic contract
  it nominally validates.
- **Recommendation:** Assert `--partitions N` and `retention.ms=<value>` per topic in
  the Job script, mirroring the assertions in `tests/test_kafka_topics.py`.

### New findings introduced by / remaining after the fix

#### N1 — Minor: README port-path description is now stale after the F3 fix

- **Severity:** Minor
- **Affected:** `kubernetes/README.md` (Kafka section — "host 9092 → node 30092 →
  pod 29092").
- **Problem:** The F3 fix moved `nodePort: 30092` to the PLAINTEXT_HOST listener
  (`targetPort: 9092`), but the README still describes the host path as terminating at
  "pod 29092". After the fix the correct path is host 9092 → node 30092 → pod 9092.
- **Impact:** The "document diagnosis" deliverable contains a factually incorrect
  port description that could mislead host-side debugging. In-cluster access (the
  primary path) is unaffected.
- **Recommendation:** Update the sentence to "host 9092 → node 30092 → pod 9092".

#### N2 — Minor: test method name no longer matches what it asserts

- **Severity:** Minor
- **Affected:** `tests/test_kubernetes_manifests.py`
  (`TestKafkaService::test_kafka_service_exposes_internal_port_with_nodeport`).
- **Problem:** After the F3 fix, this method asserts that the **external** 9092 port
  carries `nodePort: 30092`, but its name still says "internal port".
- **Impact:** Misleading test naming; no functional impact.
- **Recommendation:** Rename to `test_kafka_service_exposes_external_port_with_nodeport`.

---

## 6. Non-Defect Observations

- **No secrets committed** — confirmed; all manifests are credential-free.
- **Topic set and parameters match ADR-001 exactly** — five topics, correct partition
  counts (3/3/1/1/1) and retention (7d/7d/7d/3d/3d), replication factor 1.
- **Broker defaults redundant but harmless** — both `KAFKA_LOG_RETENTION_HOURS=168` and
  `KAFKA_LOG_RETENTION_MS=604800000` are set to the same 7-day value; `log.retention.ms`
  takes precedence. Minor clutter, not a defect.
- **`KAFKA_ADVERTISED_LISTENERS` hardcodes `localhost:9092`** — docker-compose uses
  `${KAFKA_HOST_PORT:-9092}`; the kind config pins host port 9092, so hardcoding here
  is acceptable and not a defect.
- **Resources are appropriate for Kafka** — `200m/512Mi` request and `1/1Gi` limit are
  higher than sibling services (100m/256Mi, 500m/512Mi), which is reasonable for a
  broker; the F4 heap-vs-limit interaction is now resolved.
- **No probes** — the Deployment has no liveness/readiness/startup probes. This is
  consistent with the ROADMAP (probes are TASK-079's scope), although `api-deployment`
  (TASK-076) already carries probes, so probe coverage is currently inconsistent across
  the deployment set and TASK-079 should standardize.
- **`imagePullPolicy` omitted** — `apache/kafka:4.3.1` is a public image and defaults to
  `IfNotPresent`; not an issue.
- **No ADR change needed** — ADR-001 already covers topic configuration; this task is a
  deployment realization of it.
- **Forward references** — persistence/`CLUSTER_ID` (F2), topic validation (F6), and
  integration smoke tests are exactly the kind of things TASK-079 (and TASK-078, for
  ConfigMaps/Secrets) are scoped to surface or complete if not addressed first.

---

## 7. Verdict

**APPROVED WITH NON-BLOCKING FINDINGS**

The blocking finding from round 1 (F1 — KRaft controller quorum) is correctly fixed
using the standard single-node KRaft pattern (`1@localhost:29093`), and F3
(NodePort routing), F4 (heap options), and F5 (readiness timeout) are also correctly
fixed. The implementation remains correctly scoped, secret-free, consistent with
sibling manifests, and its five topics match ADR-001 exactly. The structural tests
(86) pass, and the manifests lint and type-check cleanly (independently verified).

The remaining findings are non-blocking:

- **F2 (Moderate)** — no persistent storage / `CLUSTER_ID` / `KAFKA_LOG_DIRS`, so
  Kafka state is lost on pod restart and topics are not auto-recreated. This
  partially undercuts the "preserve delivery/consumer semantics" (replay) objective
  and should be resolved either with a PVC or by explicitly documenting the ephemeral
  trade-off plus a reconciliation path. This is the most significant open item.
- **F6 (Minor)** — the topics Job creates but does not validate topic configuration
  (the "verify" half of "create/verify" is missing).
- **F7 (Minor)** — the manifest test asserts topic names only, not partition/retention
  values.
- **N1 (Minor)** — README still says "pod 29092" where it should now say "pod 9092".
- **N2 (Minor)** — a test method name ("internal port") no longer matches what it
  asserts.

No finding blocks acceptance. Live-kind deployment verification (broker actually
starts and is reachable) remains unverified by the submitted change and is deferred
to TASK-079 by design; this is noted but not treated as blocking.
