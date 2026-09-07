# Local Development Infrastructure

The local development stack (TASK-004) runs the infrastructure the platform
depends on — Kafka, MinIO, and PostgreSQL — in Docker containers, so services
can be developed and tested incrementally against real dependencies.

This stack is for local development only. Production runs on Kubernetes
(`ai/SPECIFICATION.md` §19); production configuration is supplied by the
deployment environment, never by this repository.

## Prerequisites

- Docker (with the Docker daemon running) and Docker Compose v2
  (`docker compose` subcommand). The stack is exercised on Docker Engine 29 /
  Compose v5; any recent version should work.

## Starting and stopping

From the repository root:

```bash
docker compose up -d --wait
```

`--wait` blocks until every service reports healthy, so the command returning
successfully means the stack is ready to use. First start pulls the images and
takes a while; subsequent starts are fast.

To stop the stack while keeping all data (Kafka log segments, MinIO objects,
PostgreSQL databases — each service stores its data in a named volume):

```bash
docker compose down
```

To stop the stack and delete all data:

```bash
docker compose down --volumes
```

## What runs

| Service   | Image                                       | Purpose                                              |
| --------- | ------------------------------------------- | ---------------------------------------------------- |
| Kafka     | `apache/kafka:4.3.1` (KRaft, single node)   | Event backbone                                       |
| MinIO     | `minio/minio:RELEASE.2025-09-07T16-13-09Z`  | S3-compatible object storage (raw and lake zones)    |
| PostgreSQL| `postgres:17`                               | Warehouse and platform metadata                      |

All three services join a shared Docker network (`ai-data-platform` by
default) so application services can reach them by service name in later
tasks. Containers restart automatically after a Docker daemon restart
(`restart: unless-stopped`) unless you stopped them explicitly.

Kafka topics are created explicitly, never automatically
(`KAFKA_AUTO_CREATE_TOPICS_ENABLE=false`); topic definitions are part of
`ai/SPECIFICATION.md` §8 and are provisioned by later tasks.

## Connecting

From the host machine:

- Kafka: `localhost:9092`
- MinIO API: `localhost:9000` (console at `http://localhost:9001`)
- PostgreSQL: `localhost:5432`, database `platform`, user `platform`,
  password `platform-local`

From another container on the shared network:

- Kafka: `kafka:29092`
- MinIO: `minio:9000`
- PostgreSQL: `postgres:5432`

## Configuration

All stack variables have working defaults; nothing needs to be configured
before the first start. To override ports or credentials, copy `.env.example`
to `.env` and adjust — see the "Local infrastructure" section there. Stack
variables (no `APP_` prefix) configure Docker Compose itself; `APP_`-prefixed
variables configure application services (`docs/configuration.md`). Both kinds
may share the same `.env` file.

## Verifying

```bash
docker compose ps        # all three services must report "healthy"
```

To verify Kafka answers API calls (from inside the stack, use the internal
listener — the host listener advertises `localhost:<host port>`, which only
resolves on the host):

```bash
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:29092 --list
```

The reachability and restart-persistence checks are automated in
`tests/test_docker_compose.py`:

```bash
pytest -m integration    # requires the Docker daemon; skips otherwise
```

## Troubleshooting

- `docker compose up -d --wait` fails with a port conflict: another service
  on your machine already uses 9092, 9000, 9001, or 5432. Override the host
  ports in `.env` (see `.env.example`).
- Kafka reports unhealthy for a while after first start: the healthcheck has a
  30-second start period; KRaft needs a moment to elect itself controller.
  If it never becomes healthy, inspect logs with `docker compose logs kafka`.
- `docker compose down --volumes` removes all data — including Kafka's
  formatted storage. After that, the next `up` re-formats the cluster with the
  same fixed cluster ID, so a clean slate is expected, not a bug.
