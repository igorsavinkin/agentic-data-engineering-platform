# scripts/

Development and operational helper scripts.

## Available Scripts

- `verify_repository_structure.py` — Checks the repository foundation required by TASK-001
- `manage_kafka_topics.py` — Creates, validates, and lists Kafka topics per ADR-001 (TASK-007)

## Kafka topics

From the repository root, with the Python environment active:

```powershell
docker compose up -d --wait kafka
python scripts/manage_kafka_topics.py create
python scripts/manage_kafka_topics.py validate
python scripts/manage_kafka_topics.py list
```

The default mode uses `docker compose exec -T kafka` with this repository's
Compose file and the internal listener `kafka:29092`. Set `COMPOSE_PROJECT_NAME`
consistently for startup and management if using a different project name.

For locally installed Kafka CLI tools, set `KAFKA_BIN_DIR` to the directory
containing `kafka-topics.sh` (or `kafka-topics.bat` on Windows). In this mode the
default broker is `localhost:9092`. `KAFKA_BOOTSTRAP_SERVERS` overrides the broker
in either mode and must be reachable from where the CLI runs. These are script
settings, separate from the application's `APP_` configuration.

Creation can be rerun safely: existing topics are checked for exact partition
count, replication factor, and explicit retention. A mismatch, unavailable
broker, missing executable, or timeout exits nonzero. The script never falls
back to another target or alters existing topics. Resolve drift deliberately;
after a partial failure or timeout, retry creation against the same target.

Run focused unit and integration checks:

```powershell
python -m pytest tests/test_kafka_topics.py
python -m pytest tests/test_kafka_topics.py -m integration
```

The integration test starts Kafka under a unique Compose project with its own
network, volumes, and dynamically allocated host port. It creates topics twice,
validates and lists them, then removes its resources. Docker must be available;
an unavailable daemon skips the test and does not establish integration success.
