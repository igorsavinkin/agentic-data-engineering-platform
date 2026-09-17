# airflow/

Apache Airflow local deployment for scheduled/batch workflows (TASK-058).

## Structure

```
airflow/
  init/           PostgreSQL init scripts (airflow DB creation)
  dags/           Business DAG definitions (TASK-059+)
```

## Architecture

- **Executor:** LocalExecutor (single-machine, suitable for development)
- **Metadata DB:** PostgreSQL `airflow` database (created by init script)
- **DAG discovery:** `airflow/dags/` mounted into containers
- **Platform connectivity:** Airflow containers reach Kafka, MinIO, and PostgreSQL via the shared `platform` Docker network

## Services (docker-compose.yml)

| Service | Purpose |
|---------|---------|
| `airflow-init` | One-shot: runs `db migrate` + creates admin user |
| `airflow-scheduler` | Schedules and monitors DAG tasks |
| `airflow-webserver` | UI at http://localhost:8080 (admin/admin) |

## Usage

```bash
docker compose up -d --wait
# Airflow UI: http://localhost:8080 (admin / admin)
```

## Platform Variables (available in DAGs)

DAGs access platform services via Airflow Variables:

- `kafka_bootstrap_servers` → `kafka:29092`
- `minio_endpoint` → `http://minio:9000`
- `warehouse_db_host` → `postgres`

See `ai/SPECIFICATION.md` §15 for the full Airflow architecture.
