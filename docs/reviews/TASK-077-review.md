# TASK-077 Review — Kafka Deployment and Configuration for kind

## 1. Review Header

- **Task ID:** TASK-077
- **Review date:** 2026-09-19
- **Reviewer:** Qwen Code (independent review, no code modified)
- **Reviewed change set / Git range:**
  `5f217c5deb36132c683e0a36c01b16e06dca16b0..98d9e25c9c4dfd7f52de11b116dabb6737dfa5c6`
  (single commit: `98d9e25` — `feat(TASK-077): Kafka Deployment and Configuration for kind`)
- **Reviewed HEAD:** `98d9e25c9c4dfd7f52de11b116dabb6737dfa5c6` on `feature/TASK-077`
- **Scope:** Kafka broker Deployment (single-node KRaft), NodePort Service, a
  topic-creation Job, `kubernetes/README.md` documentation, and manifest
  validation tests in `tests/test_kubernetes_manifests.py`.
- **Verdict:** **CHANGES REQUIRED**

---

## 2. Requirements Coverage

The task objective is: deploy/configure Kafka for kind consistently with current
architecture; make it reachable by ingestion/processor/writers; create/verify
established topics; preserve delivery/consumer semantics; document diagnosis.

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1 | Deploy Kafka broker for kind | Met | `kubernetes/deployments/kafka-deployment.yaml` (`apps/v1/Deployment`, `name: kafka`, `apache/kafka:4.3.1`). |
| R2 | Single-node KRaft (no ZooKeeper), consistent with docker-compose | Met | `KAFKA_PROCESS_ROLES=broker,controller`, `KAFKA_NODE_ID=1`, `KAFKA_CONTROLLER_QUORUM_VOTERS`, `KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER`. Mirrors `docker-compose.yml`. |
| R3 | Reachable in-cluster by ingestion/processor/writers | Met (in-cluster only) | `kafka-service.yaml` exposes `kafka:29092` (PLAINTEXT listener). Sibling deployments consume via `APP_KAFKA_BOOTSTRAP_SERVERS=kafka:29092`. |
| R4 | Create/verify the five established topics | Partially met | `kafka-topics-job.yaml` creates all five ADR-001 topics with `--if-not-exists` and per-topic retention; **does not validate** created/existing topics (see F6). |
| R5 | Correct partition counts and retention per ADR-001 | Met | Job values match ADR-001 exactly: raw/validated 3p/7d, invalid 1p/7d, pipeline/data-quality 1p/3d (`retention.ms` = 604800000 / 259200000). |
| R6 | Preserve delivery/consumer semantics (at-least-once + replay) | Partially met | Auto-create disabled, explicit topics, `KAFKA_DEFAULT_REPLICATION_FACTOR=1`; but **no persistent storage**, so replay/offsets/topics are lost on pod restart (see F2). |
| R7 | Document diagnosis (kubectl/kafka CLI) | Met | README documents `kubectl apply/get/logs/exec` plus `kafka-topics.sh`/`kafka-broker-api-versions.sh` inside the pod. |
| R8 | Declarative manifests + consistent labels/selectors | Met | Labels `app.kubernetes.io/name|part-of|component`; Service selector (`name`+`part-of`) matches template labels; mirrors sibling deployments. |
| R9 | Never commit real secrets | Met | No credentials in any manifest. |
| R10 | Remain Helm-compatible without implementing Helm | Met | Plain declarative manifests; no Helm artifacts. |
| R11 | No unrelated changes | Met | Diff limited to five task-scoped files (see §3). |

---

## 3. Git Diff Review

Single commit in range (`98d9e25`). Diffstat:

| File | Change |
|---|---|
| `kubernetes/deployments/kafka-deployment.yaml` | new manifest (68 lines) |
| `kubernetes/deployments/kafka-service.yaml` | new manifest (24 lines) |
| `kubernetes/deployments/kafka-topics-job.yaml` | new manifest (71 lines) |
| `tests/test_kubernetes_manifests.py` | +129 lines (3 new test classes, 17 tests) |
| `kubernetes/README.md` | +38/-1 (tree, Kafka section, port-mapping table) |

- **Scope correctness:** All changes belong to TASK-077. No application code was
  modified — this task wires Kafka infrastructure only.
- **Unrelated changes:** None.
- **Architectural changes:** None. Kafka remains transport/buffering/replay
  infrastructure (PROJECT.md §4); no service-boundary, event-contract, or
  topic-ownership change.
- **Accidental changes / debug code / generated artifacts / secrets:** None found.
- **Dependencies:** `pyproject.toml` unchanged; no new Python dependencies.
- **Configuration/infrastructure changes:** Three new manifests, consistent in shape
  with sibling deployments; no changes to kind config, namespace, or CI. The Kafka
  env block is a near-literal translation of `docker-compose.yml`'s Kafka service.
- **Branch/task isolation:** Reviewed on `feature/TASK-077`; working tree clean; the
  range contains exactly one TASK-077 commit. Correct isolation.

---

## 4. Test and Verification Review

### Tests examined

- `tests/test_kubernetes_manifests.py::TestKafkaDeployment` — 9 tests: existence,
  resource kind, namespace, labels, selector/template match, KRaft mode
  (`KAFKA_PROCESS_ROLES` contains broker+controller), auto-create disabled, and
  container ports 29092/9092 exposed.
- `tests/test_kubernetes_manifests.py::TestKafkaService` — 6 tests: existence, kind,
  namespace, labels, selector→deployment-template match, NodePort type, and the
  internal port 29092 carrying `nodePort: 30092`.
- `tests/test_kubernetes_manifests.py::TestKafkaTopicsJob` — 4 tests: existence, kind,
  namespace, and that all five topic *names* appear in the Job command script.

These validate **manifest structure only** (YAML file content), consistent with the
TASK-070 test convention ("tests run without a live cluster"). They do **not** deploy
Kafka or verify reachability — actual kind deployment/integration smoke tests are
deferred to TASK-079 per the ROADMAP.

### Verification classification

- **Independently verified (reviewer-executed):**
  - `python -m pytest tests/test_kubernetes_manifests.py -q` → **86 passed** (1.21s).
  - `python -m ruff check tests/test_kubernetes_manifests.py` → **All checks passed**.
  - `python -m mypy tests/test_kubernetes_manifests.py` → **Success: no issues found**.
- **Implementation evidence reviewed:** the diff is minimal and targeted; the new
  YAML parses successfully (confirmed by the passing `_load_yaml`-based tests); the
  topic names/partitions/retention were cross-checked by hand against ADR-001 and
  `scripts/manage_kafka_topics.py` and match.
- **Unverified:** `python -m pytest -m integration` and any live
  `kubectl apply/get/logs/exec` run against a kind cluster. This task touches the
  Kafka infrastructure boundary, so the reviewer flagged it; the integration marker
  in `pyproject.toml` is Docker-Compose-scoped (`tests/test_datalake_integration.py`
  uses `confluentinc/cp-kafka` in a Compose harness), which is **not** a kind
  deployment test. No evidence was supplied that the TASK-077 manifests were applied
  to a running kind cluster, so the "reachable by ingestion/processor/writers" and
  "Kafka broker actually starts" acceptance behavior is **not demonstrated** by the
  submitted change. TASK-079 is explicitly scoped to add Kubernetes integration smoke
  tests (including CrashLoopBackOff/ImagePullBackOff reproduction).

---

## 5. Findings

### F1 — High: KRaft controller listener port (29093) is not exposed by the Service

- **Severity:** High
- **Affected:** `kubernetes/deployments/kafka-deployment.yaml` (env
  `KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:29093`, `KAFKA_LISTENERS=...CONTROLLER://:29093...`,
  container `ports` lists only 29092/9092) and `kubernetes/deployments/kafka-service.yaml`
  (`ports` lists only 29092 and 9092).
- **Problem:** The KRaft controller listener is configured on port 29093, and the
  quorum voter address is `kafka:29093`. In Docker Compose this works because `kafka`
  resolves directly to the container on the `platform` network (all listening ports
  reachable). In Kubernetes, `kafka` resolves to the **Service ClusterIP**, which only
  forwards the ports it declares — 29092 and 9092, **not 29093**. When
  `controller.quorum.bootstrap.servers` is unset, the broker derives its
  controller-bootstrap endpoints from `controller.quorum.voters` and attempts to
  connect to `kafka:29093`; that connection is refused/dropped because the Service has
  no such port. This is likely to prevent the combined broker+controller from
  completing startup (metadata load) and can manifest as a CrashLoopBackOff.
- **Impact:** The Kafka pod may never become ready in kind, which defeats the core
  task objective. This would not be caught by the current structural tests.
- **Recommendation:** Either (a) add `port: 29093` / `targetPort: 29093` (and declare
  `containerPort: 29093`) so the Service routes the controller listener, or (b) set
  `KAFKA_CONTROLLER_QUORUM_VOTERS: "1@localhost:29093"` so the single-node controller
  is reached pod-locally without a Service round-trip (the common single-node KRaft
  pattern). Verify by actually applying the manifests in kind and inspecting
  `kubectl get pods` / `kubectl logs deployment/kafka`.

### F2 — Moderate: no persistent storage for Kafka data; topics are lost on pod restart

- **Severity:** Moderate
- **Affected:** `kubernetes/deployments/kafka-deployment.yaml` (no `volumeMounts`/PVC,
  no `KAFKA_LOG_DIRS`, no `CLUSTER_ID`).
- **Problem:** `docker-compose.yml` persists Kafka state via the `kafka_data` volume
  and pins `CLUSTER_ID` and `KAFKA_LOG_DIRS`. The Kubernetes Deployment has none of
  these, so the KRaft metadata log and all topic data live in the container's
  ephemeral writable layer. Any pod restart (OOMKill, image update, node restart,
  `kubectl rollout restart`) reformats the log as a new cluster and wipes all topics
  and messages. Because `KAFKA_AUTO_CREATE_TOPICS_ENABLE=false` and
  `kafka-topics-setup` is a one-shot Job (re-applying the same Job name is rejected
  once it exists — Jobs have immutable pod templates), the topics are **not**
  automatically re-created after a restart.
- **Impact:** Weakened replay/recovery semantics (PROJECT.md §9, ADR-001 "Consequences
  — manual topic creation required"), and downstream consumers will fail with unknown
  topics after a broker restart.
- **Recommendation:** Add a PVC (e.g. `kafka-data`) mounted at `/var/lib/kafka/data`
  and set `CLUSTER_ID` (and optionally `KAFKA_LOG_DIRS`) to mirror docker-compose; or,
  if ephemeral state is an intentional local-kind trade-off, document it explicitly and
  add a topic-reconciliation mechanism (an initContainer or a re-runnable
  uniquely-named Job) so restart recovery is automated. This is a deliberate decision,
  not a silent omission.

### F3 — Moderate: advertised-listener / NodePort mismatch breaks host access via `localhost:9092`

- **Severity:** Moderate
- **Affected:** `kubernetes/deployments/kafka-service.yaml` (nodePort 30092 targets
  `port: 29092`) + `kubernetes/kind/kind-config.yaml` (host 9092 → node 30092) +
  `kubernetes/deployments/kafka-deployment.yaml`
  (`KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092`).
- **Problem:** The kind port mapping routes host `9092` → node `30092` → Service
  nodePort `30092` → pod **29092** (the PLAINTEXT listener). A host client connecting
  to `localhost:9092` therefore receives broker metadata advertising
  `PLAINTEXT://kafka:29092` — an in-cluster DNS name that is unresolvable/unreachable
  from the host — and fails to reconnect. The listener actually intended for host
  clients (`PLAINTEXT_HOST://:9092`, advertised `localhost:9092`) has no NodePort, so
  it is unreachable from the host. In-cluster access (the primary requirement) is
  unaffected.
- **Impact:** The README's host-access path is misleading/broken; a host-side producer
  or `kafka-console-producer` using `localhost:9092` will not work.
- **Recommendation:** Point `nodePort: 30092` at `targetPort: 9092` (the PLAINTEXT_HOST
  listener) so host clients get the `localhost:9092` advertisement; or drop the
  `localhost:9092` claim and document `kubectl port-forward` as the host path. Reconcile
  in TASK-078/079.

### F4 — Moderate: missing `KAFKA_HEAP_OPTS` risks OOMKill under the 1Gi memory limit

- **Severity:** Moderate
- **Affected:** `kubernetes/deployments/kafka-deployment.yaml` (no `KAFKA_HEAP_OPTS`;
  `resources.limits.memory: 1Gi`).
- **Problem:** `docker-compose.yml` sets `KAFKA_HEAP_OPTS: -Xmx512M -Xms256M`; the
  Deployment omits it, so the broker falls back to the Kafka JVM default heap
  (`-Xmx1G -Xms1G`). A 1G heap plus JVM metaspace/thread/direct-buffer and OS overhead
  can exceed the 1Gi container limit and be OOMKilled.
- **Impact:** Potential intermittent CrashLoopBackOff/restarts under load, which would
  again trigger F2 (state loss) since there is no persistent volume.
- **Recommendation:** Set `KAFKA_HEAP_OPTS: "-Xmx512M -Xms256M"` to match docker-compose,
  or raise `resources.limits.memory` to comfortably exceed 1G heap (e.g. 2Gi).

### F5 — Minor: topic-creation Job has an unbounded readiness wait

- **Severity:** Minor
- **Affected:** `kubernetes/deployments/kafka-topics-job.yaml` (the
  `until ... do sleep 2; done` loop).
- **Problem:** If Kafka never becomes ready, the wait loop never terminates; with
  `backoffLimit: 3` the pod is restarted up to three times, but each run can hang
  indefinitely. No `activeDeadlineSeconds` bounds the Job, and no
  `ttlSecondsAfterFinished` cleans up completed Job pods.
- **Impact:** A hung Job can sit forever and mask the underlying broker failure
  (F1) instead of surfacing it promptly.
- **Recommendation:** Bound the wait (e.g. a retry/timeout counter or
  `activeDeadlineSeconds`), and consider `ttlSecondsAfterFinished` to remove completed
  Job pods.

### F6 — Minor: topics Job creates but does not validate topic configuration

- **Severity:** Minor
- **Affected:** `kubernetes/deployments/kafka-topics-job.yaml` (creation only, no
  `--describe` validation).
- **Problem:** The Docker Compose workflow (`scripts/manage_kafka_topics.py`) runs
  `create` then `validate` to enforce exact partition count, replication factor, and
  explicit retention, and to detect drift on re-runs. The Job only runs
  `--create --if-not-exists`; a pre-existing topic with wrong partitions/retention is
  silently skipped (no drift detection), and `--if-not-exists` never corrects it.
- **Impact:** Divergence from the established drift-detection behavior; a misconfigured
  pre-existing topic would not be flagged. For a fresh kind cluster this is benign.
- **Recommendation:** Add a `--describe` verification step (or otherwise mirror the
  validate semantics) so the Job fails loudly on drift.

### F7 — Minor: manifest test asserts topic names only, not partition/retention values

- **Severity:** Minor
- **Affected:** `tests/test_kubernetes_manifests.py::TestKafkaTopicsJob`
  (`test_kafka_topics_job_creates_all_topics`).
- **Problem:** The test checks only that the five topic *names* appear as substrings in
  the Job command. The ADR-001 partition counts and retention values (hardcoded in the
  Job) are not asserted, so a regression changing `--partitions 3` to `--partitions 1`
  or `retention.ms=604800000` to `retention.ms=86400000` would still pass green.
  (The canonical values are pinned elsewhere by `tests/test_kafka_topics.py`, but that
  covers `manage_kafka_topics.py`, not this Job.)
- **Impact:** The structural safety net does not actually protect the topic contract it
  nominally validates.
- **Recommendation:** Assert `--partitions N` and `retention.ms=<value>` per topic in
  the Job script, mirroring the assertions in `tests/test_kafka_topics.py`.

---

## 6. Non-Defect Observations

- **No secrets committed** — confirmed; all manifests are credential-free.
- **Topic set and parameters match ADR-001 exactly** — five topics, correct partition
  counts (3/3/1/1/1) and retention (7d/7d/7d/3d/3d), replication factor 1.
- **Broker defaults redundant but harmless** — both `KAFKA_LOG_RETENTION_HOURS=168` and
  `KAFKA_LOG_RETENTION_MS=604800000` are set to the same 7-day value; `log.retention.ms`
  takes precedence. Minor clutter, not a defect.
- **Resources are appropriate for Kafka** — `200m/512Mi` request and `1/1Gi` limit are
  higher than sibling services (100m/256Mi, 500m/512Mi), which is reasonable for a
  broker; note the F4 heap-vs-limit interaction.
- **No probes** — the Deployment has no liveness/readiness/startup probes. This is
  consistent with the ROADMAP (probes are TASK-079's scope), although `api-deployment`
  (TASK-076) already carries probes, so probe coverage is currently inconsistent across
  the deployment set and TASK-079 should standardize.
- **`imagePullPolicy` omitted** — `apache/kafka:4.3.1` is a public image and defaults to
  `IfNotPresent`; not an issue.
- **The README port table is now partially self-contradictory** — it documents
  "host 9092 → node 30092 → pod 29092" accurately, but does not flag the advertised-listener
  redirect consequence (F3).
- **No ADR change needed** — ADR-001 already covers topic configuration; this task is a
  deployment realization of it.
- **Forward references** — `KAFKA_HEAP_OPTS`/`CLUSTER_ID`/persistence and the controller
  port are exactly the kind of things TASK-079's integration smoke tests (CrashLoopBackOff,
  OOMKilled) are scoped to surface if not addressed first.

---

## 7. Verdict

**CHANGES REQUIRED**

The implementation is correctly scoped, secret-free, consistent with sibling manifests,
and its five topics match ADR-001 exactly. The structural tests (86) pass, and the
manifests lint and type-check cleanly.

However, **F1 (High)** is a likely startup blocker: the KRaft controller listener
(port 29093) is referenced in `KAFKA_CONTROLLER_QUORUM_VOTERS`/`KAFKA_LISTENERS` but is
not exposed by the Service (nor declared in the container `ports`). In Kubernetes the
`kafka:29093` address resolves to the Service ClusterIP, which does not forward 29093,
so the single-node broker is likely to fail to connect to its own controller quorum.
Because the submitted change contains no live-kind deployment evidence, the "Kafka is
reachable by ingestion/processor/writers" acceptance behavior is unverified, and the
current structural tests cannot catch this. The fix is small (expose 29093 or use
`1@localhost:29093`) and should be applied and verified in a real kind cluster before
acceptance.

F2 (no persistence), F3 (host access mismatch), and F4 (heap vs 1Gi limit) are Moderate
reliability/operability concerns that should be addressed or explicitly deferred with
documentation; F5–F7 are Minor hardening items.

Blocking: **F1** (must fix and verify before acceptance). The remaining findings are
non-blocking but recommended.
