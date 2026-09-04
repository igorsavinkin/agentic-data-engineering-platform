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
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker address (default: localhost:9092)
    KAFKA_BIN_DIR: Path to Kafka bin directory for CLI tools (optional,
                   uses docker exec for local development if not set)
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


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
    """Get Kafka bootstrap servers from environment or default."""
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def run_kafka_command(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a Kafka CLI command and return exit code, stdout, stderr."""
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
    except FileNotFoundError as e:
        return 1, "", f"Command not found: {e}"


def create_topic(topic: TopicConfig, bootstrap_servers: str) -> bool:
    """Create a Kafka topic if it doesn't already exist.

    Returns True if topic was created or already exists with correct config.
    """
    # Check if topic already exists
    list_cmd = [
        "docker",
        "exec",
        "ai-data-platform-kafka-1",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--list",
    ]
    returncode, stdout, stderr = run_kafka_command(list_cmd)

    if returncode != 0:
        # Fallback to direct kafka-topics if docker exec fails
        list_cmd = [
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            bootstrap_servers,
            "--list",
        ]
        returncode, stdout, stderr = run_kafka_command(list_cmd)

    if returncode != 0:
        print(f"ERROR: Failed to list topics: {stderr}")
        return False

    existing_topics = [t.strip() for t in stdout.strip().split("\n") if t.strip()]

    if topic.name in existing_topics:
        print(f"Topic '{topic.name}' already exists, skipping creation")
        return True

    # Create the topic
    create_cmd = [
        "docker",
        "exec",
        "ai-data-platform-kafka-1",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--create",
        "--topic",
        topic.name,
        "--partitions",
        str(topic.partitions),
        "--replication-factor",
        str(topic.replication_factor),
        "--config",
        f"retention.ms={topic.retention_ms}",
        "--if-not-exists",
    ]

    print(f"Creating topic '{topic.name}'...")
    returncode, stdout, stderr = run_kafka_command(create_cmd)

    if returncode != 0:
        # Fallback to direct command
        create_cmd = [
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            bootstrap_servers,
            "--create",
            "--topic",
            topic.name,
            "--partitions",
            str(topic.partitions),
            "--replication-factor",
            str(topic.replication_factor),
            "--config",
            f"retention.ms={topic.retention_ms}",
            "--if-not-exists",
        ]
        returncode, stdout, stderr = run_kafka_command(create_cmd)

    if returncode != 0:
        print(f"ERROR: Failed to create topic '{topic.name}': {stderr}")
        return False

    print(f"Successfully created topic '{topic.name}'")
    return True


def validate_topic(topic: TopicConfig, bootstrap_servers: str) -> bool:
    """Validate that a topic exists and has the correct configuration."""
    describe_cmd = [
        "docker",
        "exec",
        "ai-data-platform-kafka-1",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--describe",
        "--topic",
        topic.name,
    ]

    returncode, stdout, stderr = run_kafka_command(describe_cmd)

    if returncode != 0:
        # Fallback to direct command
        describe_cmd = [
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            bootstrap_servers,
            "--describe",
            "--topic",
            topic.name,
        ]
        returncode, stdout, stderr = run_kafka_command(describe_cmd)

    if returncode != 0:
        print(f"ERROR: Topic '{topic.name}' does not exist")
        return False

    # Parse the output to validate configuration
    lines = stdout.strip().split("\n")
    if not lines:
        print(f"ERROR: No description found for topic '{topic.name}'")
        return False

    # First line contains topic metadata
    metadata_line = lines[0]

    # Check partition count
    if f"PartitionCount:{topic.partitions}" not in metadata_line:
        print(
            f"ERROR: Topic '{topic.name}' has wrong partition count. "
            f"Expected {topic.partitions}, got different value"
        )
        print(f"Metadata: {metadata_line}")
        return False

    # Check replication factor
    if f"ReplicationFactor:{topic.replication_factor}" not in metadata_line:
        print(
            f"ERROR: Topic '{topic.name}' has wrong replication factor. "
            f"Expected {topic.replication_factor}, got different value"
        )
        return False

    # Check retention from Configs line
    configs_line = next((line for line in lines if "Configs:" in line), None)
    if configs_line:
        expected_retention = f"retention.ms={topic.retention_ms}"
        if expected_retention not in configs_line:
            print(
                f"WARNING: Topic '{topic.name}' retention may not match expected value. "
                f"Expected {expected_retention}"
            )
            print(f"Configs: {configs_line}")
    else:
        print(f"WARNING: Could not verify retention for topic '{topic.name}'")

    print(f"Topic '{topic.name}' configuration is valid")
    return True


def list_topics(bootstrap_servers: str) -> bool:
    """List all topics with their configurations."""
    list_cmd = [
        "docker",
        "exec",
        "ai-data-platform-kafka-1",
        "/opt/kafka/bin/kafka-topics.sh",
        "--bootstrap-server",
        "localhost:9092",
        "--list",
    ]

    returncode, stdout, stderr = run_kafka_command(list_cmd)

    if returncode != 0:
        # Fallback to direct command
        list_cmd = [
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            bootstrap_servers,
            "--list",
        ]
        returncode, stdout, stderr = run_kafka_command(list_cmd)

    if returncode != 0:
        print(f"ERROR: Failed to list topics: {stderr}")
        return False

    topics = [t.strip() for t in stdout.strip().split("\n") if t.strip()]

    if not topics:
        print("No topics found")
        return True

    print(f"Found {len(topics)} topic(s):\n")

    for topic_name in sorted(topics):
        # Describe each topic
        describe_cmd = [
            "docker",
            "exec",
            "ai-data-platform-kafka-1",
            "/opt/kafka/bin/kafka-topics.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--describe",
            "--topic",
            topic_name,
        ]

        returncode, stdout, stderr = run_kafka_command(describe_cmd)

        if returncode == 0:
            print(stdout)
        else:
            print(f"  {topic_name} (could not retrieve details)")

    return True


def main():
    """Main entry point for Kafka topic management."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()
    bootstrap_servers = get_bootstrap_servers()

    if command == "create":
        print("Creating Kafka topics...\n")
        success = True
        for topic in TOPICS:
            if not create_topic(topic, bootstrap_servers):
                success = False
        if success:
            print("\nAll topics created successfully")
            sys.exit(0)
        else:
            print("\nSome topics failed to create", file=sys.stderr)
            sys.exit(1)

    elif command == "validate":
        print("Validating Kafka topic configuration...\n")
        success = True
        for topic in TOPICS:
            if not validate_topic(topic, bootstrap_servers):
                success = False
        if success:
            print("\nAll topics validated successfully")
            sys.exit(0)
        else:
            print("\nSome topics failed validation", file=sys.stderr)
            sys.exit(1)

    elif command == "list":
        if not list_topics(bootstrap_servers):
            sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        print("Available commands: create, validate, list")
        sys.exit(1)


if __name__ == "__main__":
    main()
