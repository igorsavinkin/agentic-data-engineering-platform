#!/usr/bin/env python3
"""Manage Kafka topics for the AI Data Platform.

Creates, validates, and lists Kafka topics according to the platform's
topic configuration (ADR-001). Designed for both local development
(Docker Compose) and CI/CD pipelines.

Usage:
    # Create all required topics
    python scripts/manage_kafka_topics.py create

    # Validate existing topics match expected configuration
    python scripts/manage_kafka_topics.py validate

    # List current topics with details
    python scripts/manage_kafka_topics.py list

Environment Variables:
    KAFKA_BOOTSTRAP_SERVERS: Broker address reachable by the selected CLI
                           (Compose default: kafka:29092; direct: localhost:9092)
    KAFKA_BIN_DIR: Path to Kafka bin directory for CLI tools (optional,
                   uses docker compose exec if not set)
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TopicConfig:
    """Configuration for a single Kafka topic."""

    name: str
    partitions: int
    replication_factor: int
    retention_ms: int
    description: str
    partition_key_strategy: str = "none"


# Topic definitions from ADR-001
TOPICS = [
    TopicConfig(
        name="products.raw.v1",
        partitions=3,
        replication_factor=1,
        retention_ms=7 * 24 * 60 * 60 * 1000,  # 7 days
        description="Canonical product observations from ingestion services",
        partition_key_strategy="source:external_id concatenation",
    ),
    TopicConfig(
        name="products.validated.v1",
        partitions=3,
        replication_factor=1,
        retention_ms=7 * 24 * 60 * 60 * 1000,  # 7 days
        description="Validated and normalized product events",
        partition_key_strategy="source:external_id concatenation",
    ),
    TopicConfig(
        name="products.invalid.v1",
        partitions=1,
        replication_factor=1,
        retention_ms=7 * 24 * 60 * 60 * 1000,  # 7 days
        description="Invalid or dead-letter product events with diagnostic context",
        partition_key_strategy="none (round-robin)",
    ),
    TopicConfig(
        name="pipeline.events.v1",
        partitions=1,
        replication_factor=1,
        retention_ms=3 * 24 * 60 * 60 * 1000,  # 3 days
        description="Pipeline lifecycle events (job.started, job.completed, etc.)",
        partition_key_strategy="none (event type routing)",
    ),
    TopicConfig(
        name="data-quality.events.v1",
        partitions=1,
        replication_factor=1,
        retention_ms=3 * 24 * 60 * 60 * 1000,  # 3 days
        description="Data quality check results and violations",
        partition_key_strategy="none (check name routing)",
    ),
]


def get_bootstrap_servers() -> str:
    """Select the listener reachable from the explicitly selected CLI mode."""
    default = "localhost:9092" if os.environ.get("KAFKA_BIN_DIR") else "kafka:29092"
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", default)


def kafka_command(bootstrap_servers: str, *arguments: str) -> list[str]:
    """Use one target consistently; never fall back to a different cluster."""
    bin_dir = os.environ.get("KAFKA_BIN_DIR")
    if bin_dir:
        executable = "kafka-topics.bat" if os.name == "nt" else "kafka-topics.sh"
        prefix = [str(Path(bin_dir) / executable)]
    else:
        prefix = [
            "docker",
            "compose",
            "-f",
            str(Path(__file__).resolve().parents[1] / "docker-compose.yml"),
            "exec",
            "-T",
            "kafka",
            "/opt/kafka/bin/kafka-topics.sh",
        ]
    return [*prefix, "--bootstrap-server", bootstrap_servers, *arguments]


def run_kafka_command(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Bound each CLI call and surface failures to the caller."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s"
    except OSError as error:
        return 1, "", f"Cannot execute Kafka CLI: {error}"


def create_topic(topic: TopicConfig, bootstrap_servers: str) -> bool:
    """Create if absent, then verify settings even on retries or concurrent creation.

    No alter/delete commands are issued: a drifted topic requires operator action.
    If execution times out after creation, rerunning safely verifies the result.
    """
    command = kafka_command(
        bootstrap_servers,
        "--create",
        "--if-not-exists",
        "--topic",
        topic.name,
        "--partitions",
        str(topic.partitions),
        "--replication-factor",
        str(topic.replication_factor),
        "--config",
        f"retention.ms={topic.retention_ms}",
    )
    code, _, error = run_kafka_command(command)
    if code:
        print(f"ERROR: Failed to create topic '{topic.name}': {error}", file=sys.stderr)
        return False
    return validate_topic(topic, bootstrap_servers)


def validate_topic(topic: TopicConfig, bootstrap_servers: str) -> bool:
    """Require exact metadata and explicit retention overrides from ADR-001."""
    code, output, error = run_kafka_command(
        kafka_command(bootstrap_servers, "--describe", "--topic", topic.name)
    )
    if code:
        print(f"ERROR: Cannot describe topic '{topic.name}': {error}", file=sys.stderr)
        return False

    # Kafka accepts a regex for --topic. Select this exact topic's summary, not
    # another regex match or a partition-detail line. Whitespace varies by version.
    summaries = []
    for line in output.splitlines():
        fields = dict(re.findall(r"(Topic|PartitionCount|ReplicationFactor):\s*([^\s]+)", line))
        if fields.get("Topic") == topic.name and "PartitionCount" in fields:
            summaries.append((line, fields))
    if len(summaries) != 1:
        print(f"ERROR: Missing or ambiguous metadata for '{topic.name}'", file=sys.stderr)
        return False
    line, fields = summaries[0]
    expected = {
        "PartitionCount": str(topic.partitions),
        "ReplicationFactor": str(topic.replication_factor),
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            print(
                f"ERROR: Topic '{topic.name}' {key}: expected {value}, got {fields.get(key)!r}",
                file=sys.stderr,
            )
            return False
    configs = line.split("Configs:", 1)[1] if "Configs:" in line else ""
    retention = re.search(r"(?:^|[,\s])retention\.ms=(-?\d+)(?=,|\s|$)", configs)
    if retention is None or int(retention[1]) != topic.retention_ms:
        print(
            f"ERROR: Topic '{topic.name}' requires retention.ms={topic.retention_ms}; "
            "explicit value is missing or different",
            file=sys.stderr,
        )
        return False
    print(f"Topic '{topic.name}' configuration is valid")
    return True


def list_topics(bootstrap_servers: str) -> bool:
    """Describe listed topics, failing if any details cannot be retrieved."""
    code, output, error = run_kafka_command(kafka_command(bootstrap_servers, "--list"))
    if code:
        print(f"ERROR: Failed to list topics: {error}", file=sys.stderr)
        return False
    success = True
    for name in sorted(filter(None, (line.strip() for line in output.splitlines()))):
        code, details, error = run_kafka_command(
            kafka_command(bootstrap_servers, "--describe", "--topic", name)
        )
        if code:
            print(f"ERROR: Cannot describe topic '{name}': {error}", file=sys.stderr)
            success = False
        else:
            print(details)
    return success


def main() -> int:
    """Return a failing exit status for any partial failure."""
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    command = sys.argv[1].lower()
    bootstrap_servers = get_bootstrap_servers()
    if command == "list":
        return 0 if list_topics(bootstrap_servers) else 1
    if command not in ("create", "validate"):
        print(f"Unknown command: {command}. Available commands: create, validate, list")
        return 1
    operation = create_topic if command == "create" else validate_topic
    # Evaluate every topic even if an earlier operation failed.
    results = [operation(topic, bootstrap_servers) for topic in TOPICS]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
