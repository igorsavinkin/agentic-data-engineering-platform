# Runtime Verification: Airflow -> PostgreSQL build_daily_metrics DAG

## Purpose

Verify the end-to-end runtime path from PostgreSQL source data through the
Airflow `build_daily_metrics` DAG to persisted analytical metrics:

```
PostgreSQL.product_observations
        |
Airflow build_daily_metrics DAG
        |
DailyMetricsCalculator
        |
MetricsResultWriter
        |
PostgreSQL.daily_metrics
```

## Verdict: PASS

All six success criteria demonstrated with observed runtime evidence.

## Environment

| Component | Value |
|-----------|-------|
| Date | 2026-09-25 |
| OS | Windows 10 (WSL2 kernel 6.6.87.2) |
| Kubernetes | kind v1.31.0, context `kind-ai-data-platform` |
| Kubernetes namespace | `ai-data-platform` |
| PostgreSQL pod | `postgresql-0` |
| PostgreSQL database | `warehouse` |
| PostgreSQL user | `postgres` (no password) |
| PostgreSQL service | ClusterIP `10.96.189.70:5432` |
| Docker | Docker Desktop (Windows) |
| Airflow image | `apache/airflow:2.10.4-python3.12` |
| Airflow executor | SequentialExecutor (task test mode) |
| Airflow metadata DB | SQLite (ephemeral, container-local) |
| Python | 3.12 (container) |
| Polars | installed at container startup via pip |

## Runtime Topology

```
+------------------+     port-forward      +-------------------+
| kind cluster     |  15432 -> 5432        | Host (Windows)    |
|                  | <-------------------- |                   |
| postgresql-0     |     localhost:15432   | Docker Desktop    |
| (warehouse DB)   |                       |                   |
+------------------+                       +---------+---------+
                                                    |
                                                    | host.docker.internal:15432
                                                    v
                                           +--------+---------+
                                           | Airflow container |
                                           | (docker run)      |
                                           |                   |
                                           | DAGs: /opt/airflow/dags (ro) |
                                           | libs: /opt/airflow/libs (ro)  |
                                           +-------------------+
```

The Airflow container reaches the Kubernetes PostgreSQL via:
1. `kubectl port-forward svc/postgresql 15432:5432` on the host
2. `host.docker.internal:15432` from inside the Docker container

The Airflow container uses an ephemeral SQLite metadata DB (SequentialExecutor).
No Airflow scheduler or webserver was needed; `airflow tasks test` executes the
task directly.

## PostgreSQL Connection Configuration

The DAG uses `MetricsPersistenceConfig.from_env()` which reads:

| Variable | Value |
|----------|-------|
| `WAREHOUSE_DB_HOST` | `host.docker.internal` |
| `WAREHOUSE_DB_PORT` | `15432` |
| `WAREHOUSE_DB_NAME` | `warehouse` |
| `WAREHOUSE_DB_USER` | `postgres` |
| `WAREHOUSE_DB_PASSWORD` | (empty) |

Resulting URL: `postgresql://postgres:@host.docker.internal:15432/warehouse`

Connectivity verified from inside a Docker container before DAG execution:

```
product_observations: 29782
daily_metrics: 0
CONNECTIVITY OK
```

## PostgreSQL State Before

### product_observations

```sql
SELECT COUNT(*) FROM product_observations;
-- Result: 29782
```

### Observation date distribution

```sql
SELECT DATE(collected_at) AS observation_date, COUNT(*)
FROM product_observations
GROUP BY DATE(collected_at)
ORDER BY observation_date DESC;
```

| observation_date | count |
|------------------|-------|
| 2026-09-24 | 8582 |
| 2026-09-23 | 12140 |
| 2026-09-22 | 9060 |

### daily_metrics (before)

```sql
SELECT COUNT(*) FROM daily_metrics;
-- Result: 0
```

## Observation Date Selected

**2026-09-23** -- selected because it has the highest observation count (12140).

The DAG logical date `2026-09-23` covers the interval `[2026-09-23, 2026-09-24)`
which matches the `collected_at` filter in the DAG query.

## Airflow DAG Visibility

```
$ airflow dags list

dag_id              | fileloc                                      | owners        | is_paused
====================+==============================================+===============+==========
build_daily_metrics | /opt/airflow/dags/build_daily_metrics_dag.py | data-platform | None
daily_data_quality  | /opt/airflow/dags/daily_data_quality_dag.py  | data-platform | None
```

Note: `ingestion_health_dag.py` and `parquet_compaction_dag.py` fail to import
due to missing `pydantic_settings` module. This does not affect
`build_daily_metrics` which has no dependency on that package.

## DAG Run Evidence (First Run)

Command:

```bash
airflow tasks test build_daily_metrics compute_daily_metrics 2026-09-23
```

Key log output:

```
Executing <Task(PythonOperator): compute_daily_metrics> on 2026-09-23 00:00:00+00:00
...
daily_metrics_written
build_daily_metrics_complete
Done. Returned value was: {
  'metric_date': '2026-09-23',
  'logical_date': '2026-09-23T00:00:00',
  'observations_processed': 12140,
  'metrics_computed': 6,
  'metrics_written': 6,
  'errors': []
}
Marking task as SUCCESS.
```

## PostgreSQL State After (First Run)

```sql
SELECT COUNT(*) FROM daily_metrics;
-- Result: 6
```

### Persisted metrics

```sql
SELECT metric_date, metric_name, dimension, value, logical_date, replay_key
FROM daily_metrics ORDER BY metric_name, dimension;
```

| metric_date | metric_name | dimension | value | logical_date | replay_key |
|-------------|-------------|-----------|-------|--------------|------------|
| 2026-09-23 | availability_in_stock | | 12140.0000 | 2026-09-23T00:00:00 | availability_in_stock:2026-09-23:_ |
| 2026-09-23 | availability_out_of_stock | | 0.0000 | 2026-09-23T00:00:00 | availability_out_of_stock:2026-09-23:_ |
| 2026-09-23 | avg_price | | 126.1210 | 2026-09-23T00:00:00 | avg_price:2026-09-23:_ |
| 2026-09-23 | observation_count | | 12140.0000 | 2026-09-23T00:00:00 | observation_count:2026-09-23:_ |
| 2026-09-23 | source_observation_count | fake_store | 12140.0000 | 2026-09-23T00:00:00 | source_observation_count:2026-09-23:fake_store |
| 2026-09-23 | unique_products | | 10.0000 | 2026-09-23T00:00:00 | unique_products:2026-09-23:_ |

All 6 metrics correspond to metric_date `2026-09-23` and logical_date
`2026-09-23T00:00:00`, matching the selected observation date.

## Idempotency / Replay Result

Command (same logical date, second run):

```bash
airflow tasks test build_daily_metrics compute_daily_metrics 2026-09-23
```

Replay log output:

```
Done. Returned value was: {
  'metric_date': '2026-09-23',
  'logical_date': '2026-09-23T00:00:00',
  'observations_processed': 12140,
  'metrics_computed': 6,
  'metrics_written': 6,
  'errors': []
}
Marking task as SUCCESS.
```

Post-replay count:

```sql
SELECT COUNT(*) FROM daily_metrics;
-- Result: 6 (unchanged)
```

The `ON CONFLICT (replay_key) DO NOTHING` constraint prevented duplicate
insertion. The replay_key unique constraint (`uk_daily_metrics_replay_key`)
ensures idempotency.

## Counts Summary

| Stage | daily_metrics count |
|-------|---------------------|
| Before first run | 0 |
| After first run | 6 |
| After replay | 6 |

## Success Criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Airflow connects to the existing `warehouse` PostgreSQL database | PASS -- connectivity verified, data read from Kubernetes postgresql-0 |
| 2 | `build_daily_metrics` reads an interval containing real observations | PASS -- 12140 observations processed for 2026-09-23 |
| 3 | The DAG completes successfully | PASS -- task marked SUCCESS, no errors |
| 4 | Rows are persisted into `daily_metrics` | PASS -- 6 rows inserted |
| 5 | Resulting rows correspond to the selected date | PASS -- all rows have metric_date=2026-09-23 |
| 6 | Replay does not create duplicates | PASS -- count remains 6 after replay |

## Findings

1. **Runtime path works end-to-end.** The Airflow DAG successfully reads from
   the Kubernetes PostgreSQL warehouse, computes metrics via
   `DailyMetricsCalculator`, and persists results via `MetricsResultWriter`
   with replay-safe identity.

2. **Airflow is not deployed in Kubernetes.** The local runtime uses Docker
   containers (as defined in `docker-compose.yml`) for Airflow, while the
   warehouse database runs in Kubernetes. Connectivity requires
   `kubectl port-forward` + `host.docker.internal`.

3. **Airflow image missing `polars`.** The standard `apache/airflow:2.10.4-python3.12`
   image does not include `polars`. The DAG requires it at import time.
   Production use requires a custom Airflow image with `polars` pre-installed,
   or a custom Dockerfile extending the base image.

4. **Other DAGs have unmet dependencies.** `ingestion_health_dag.py` and
   `parquet_compaction_dag.py` fail to load due to missing `pydantic_settings`.
   This is a separate issue and does not affect `build_daily_metrics`.

5. **WAREHOUSE_DB_* vs AIRFLOW_VAR_*.** The DAG uses
   `MetricsPersistenceConfig.from_env()` which reads `WAREHOUSE_DB_*`
   environment variables. The docker-compose.yml sets
   `AIRFLOW_VAR_WAREHOUSE_DB_HOST` (an Airflow Variable), which is NOT the
   same as an environment variable. For the DAG to connect correctly,
   `WAREHOUSE_DB_HOST` must be set as an actual environment variable in the
   Airflow container, not just as an Airflow Variable.

6. **All observations come from a single source (fake_store).** The 29782
   observations in the warehouse are all from the `fake_store` source, which
   is reflected in the `source_observation_count` metric.

## Follow-up Required

- Custom Airflow image: build an Airflow Docker image that includes `polars`
  (and optionally `pydantic_settings` for other DAGs) to avoid runtime
  `pip install` at container startup.

- Docker Compose environment variables: add `WAREHOUSE_DB_*` environment
  variables to the Airflow services in `docker-compose.yml` so the DAG can
  reach the warehouse when running via `docker compose up`.

- Airflow in Kubernetes: the current local topology has Airflow in Docker
  and PostgreSQL in Kubernetes. For production, both should run in Kubernetes
  per the architecture specification.

## Commands to Reproduce

```bash
# 1. Start port-forward to Kubernetes PostgreSQL
kubectl --context kind-ai-data-platform port-forward \
  -n ai-data-platform svc/postgresql 15432:5432 &

# 2. Run the Airflow task test (from repository root)
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd)/airflow/dags:/opt/airflow/dags:ro" \
  -v "$(pwd)/libs:/opt/airflow/libs:ro" \
  -e AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="sqlite:////tmp/airflow.db" \
  -e AIRFLOW__CORE__EXECUTOR="SequentialExecutor" \
  -e AIRFLOW__CORE__LOAD_EXAMPLES="false" \
  -e AIRFLOW__CORE__DAGS_FOLDER="/opt/airflow/dags" \
  -e AIRFLOW__WEBSERVER__SECRET_KEY="test-verification-key" \
  -e WAREHOUSE_DB_HOST="host.docker.internal" \
  -e WAREHOUSE_DB_PORT="15432" \
  -e WAREHOUSE_DB_NAME="warehouse" \
  -e WAREHOUSE_DB_USER="postgres" \
  -e WAREHOUSE_DB_PASSWORD="" \
  -e PYTHONPATH="/opt/airflow" \
  apache/airflow:2.10.4-python3.12 \
  bash -c "
    pip install polars --quiet &&
    airflow db migrate > /dev/null 2>&1 &&
    airflow dags list &&
    airflow tasks test build_daily_metrics compute_daily_metrics 2026-09-23
  "

# 3. Verify results
kubectl --context kind-ai-data-platform exec -n ai-data-platform \
  postgresql-0 -- psql -U postgres -d warehouse \
  -c "SELECT * FROM daily_metrics ORDER BY metric_name;"
```
