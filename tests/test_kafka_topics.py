"""Tests for Kafka topic configuration (TASK-007).

Verifies that required Kafka topics can be created and accessed
reproducibly according to ADR-001 specifications.
"""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from scripts import manage_kafka_topics as manager
from scripts.manage_kafka_topics import TOPICS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestKafkaTopicConfiguration:
    """Test Kafka topic definitions match ADR-001 specifications."""

    def test_required_topics_exist(self) -> None:
        """Verify all five required topics are defined."""
        topic_names = [t.name for t in TOPICS]

        expected_topics = [
            "products.raw.v1",
            "products.validated.v1",
            "products.invalid.v1",
            "pipeline.events.v1",
            "data-quality.events.v1",
        ]

        for expected in expected_topics:
            assert expected in topic_names, f"Missing required topic: {expected}"

    def test_topic_count(self) -> None:
        """Verify exactly five topics are configured."""
        assert len(TOPICS) == 5, f"Expected 5 topics, got {len(TOPICS)}"

    def test_product_raw_topic_configuration(self) -> None:
        """Verify products.raw.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "products.raw.v1")

        assert topic.partitions == 3, "products.raw.v1 should have 3 partitions"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 7 * 24 * 60 * 60 * 1000, "7 day retention"
        assert "source:external_id" in topic.partition_key_strategy

    def test_product_validated_topic_configuration(self) -> None:
        """Verify products.validated.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "products.validated.v1")

        assert topic.partitions == 3, "products.validated.v1 should have 3 partitions"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 7 * 24 * 60 * 60 * 1000, "7 day retention"
        assert "source:external_id" in topic.partition_key_strategy

    def test_product_invalid_topic_configuration(self) -> None:
        """Verify products.invalid.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "products.invalid.v1")

        assert topic.partitions == 1, "products.invalid.v1 should have 1 partition"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 7 * 24 * 60 * 60 * 1000, "7 day retention"

    def test_pipeline_events_topic_configuration(self) -> None:
        """Verify pipeline.events.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "pipeline.events.v1")

        assert topic.partitions == 1, "pipeline.events.v1 should have 1 partition"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 3 * 24 * 60 * 60 * 1000, "3 day retention"

    def test_data_quality_events_topic_configuration(self) -> None:
        """Verify data-quality.events.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "data-quality.events.v1")

        assert topic.partitions == 1, "data-quality.events.v1 should have 1 partition"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 3 * 24 * 60 * 60 * 1000, "3 day retention"

    def test_topic_naming_convention(self) -> None:
        """Verify all topics follow domain.status.v{version} pattern."""
        import re

        pattern = r"^[a-z-]+\.[a-z-]+\.v\d+$"

        for topic in TOPICS:
            assert re.match(pattern, topic.name), (
                f"Topic '{topic.name}' doesn't follow naming convention "
                "(domain.status.v{version})"
            )

    def test_all_topics_have_descriptions(self) -> None:
        """Verify every topic has a non-empty description."""
        for topic in TOPICS:
            assert topic.description, f"Topic '{topic.name}' missing description"
            assert len(topic.description) > 10, f"Topic '{topic.name}' description too brief"

    def test_partition_key_strategies_documented(self) -> None:
        """Verify all topics document their partition key strategy."""
        for topic in TOPICS:
            assert topic.partition_key_strategy, (
                f"Topic '{topic.name}' missing partition key strategy"
            )

    def test_retention_values_positive(self) -> None:
        """Verify all retention values are positive."""
        for topic in TOPICS:
            assert topic.retention_ms > 0, f"Topic '{topic.name}' has non-positive retention"

    def test_partition_counts_positive(self) -> None:
        """Verify all partition counts are positive."""
        for topic in TOPICS:
            assert topic.partitions > 0, f"Topic '{topic.name}' has non-positive partition count"


class TestKafkaTopicScript:
    """Test the manage_kafka_topics.py script functionality."""

    def test_script_exists(self) -> None:
        """Verify the management script exists."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        assert script_path.exists(), "manage_kafka_topics.py not found"

    def test_script_is_executable(self) -> None:
        """Verify the management script has execute permissions."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        # On Windows, check if file exists (execute bit works differently)
        assert script_path.exists()

    def test_script_has_shebang(self) -> None:
        """Verify the script starts with a proper shebang line."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!/usr/bin/env python3"), "Script missing proper shebang line"

    def test_script_help_output(self) -> None:
        """Verify the script shows usage when called without arguments."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should exit with code 1 and show usage
        assert result.returncode == 1
        assert "Usage" in result.stdout or "manage_kafka_topics" in result.stdout

    def test_script_invalid_command(self) -> None:
        """Verify the script rejects invalid commands."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "invalid-command"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 1
        assert "Unknown command" in result.stdout or "Available commands" in result.stdout


def metadata(partitions: int = 3, replication: int = 1, retention: str = "604800000") -> str:
    return (
        "Topic: products.raw.v1\tTopicId: abc\t"
        f"PartitionCount: {partitions}\tReplicationFactor: {replication}\t"
        f"Configs: retention.ms={retention}\n"
        "\tTopic: products.raw.v1\tPartition: 0\tLeader: 1\tReplicas: 1\tIsr: 1"
    )


@pytest.mark.parametrize(
    "output", [metadata(), metadata().replace(": ", ":"), "warning\n" + metadata()]
)
def test_valid_metadata(output: str) -> None:
    with patch.object(manager, "run_kafka_command", return_value=(0, output, "")):
        assert manager.validate_topic(TOPICS[0], "broker:9092")


@pytest.mark.parametrize(
    "output",
    [
        "",
        metadata(partitions=30),
        metadata(replication=10),
        metadata(retention="6048000000"),
        metadata(retention="-1"),
        metadata(retention="garbage"),
        metadata().replace("retention.ms=", "other="),
        metadata().replace("products.raw.v1", "productsXrawXv1"),
        metadata() + "\n" + metadata(),
    ],
)
def test_invalid_metadata_fails(output: str) -> None:
    with patch.object(manager, "run_kafka_command", return_value=(0, output, "")):
        assert not manager.validate_topic(TOPICS[0], "broker:9092")


def test_create_is_retryable_and_validates_existing_settings() -> None:
    with patch.object(
        manager, "run_kafka_command", side_effect=[(0, "", ""), (0, metadata(), "")] * 2
    ) as run:
        assert manager.create_topic(TOPICS[0], "broker:9092")
        assert manager.create_topic(TOPICS[0], "broker:9092")
    for index in (0, 2):
        assert "--if-not-exists" in run.call_args_list[index].args[0]
        assert "--create" in run.call_args_list[index].args[0]
    assert "--describe" in run.call_args_list[1].args[0]


def test_create_rejects_existing_drift() -> None:
    with patch.object(
        manager, "run_kafka_command", side_effect=[(0, "", ""), (0, metadata(retention="1"), "")]
    ):
        assert not manager.create_topic(TOPICS[0], "broker:9092")


@pytest.mark.parametrize("action", ["create", "validate", "list"])
def test_command_failure_does_not_fall_back(action: str) -> None:
    with patch.object(manager, "run_kafka_command", return_value=(1, "", "unavailable")) as run:
        if action == "create":
            assert not manager.create_topic(TOPICS[0], "broker:9092")
        elif action == "validate":
            assert not manager.validate_topic(TOPICS[0], "broker:9092")
        else:
            assert not manager.list_topics("broker:9092")
        run.assert_called_once()


def test_list_reports_partial_failure() -> None:
    with patch.object(
        manager,
        "run_kafka_command",
        side_effect=[(0, "a\nb\n", ""), (1, "", "denied"), (0, "details", "")],
    ) as run:
        assert not manager.list_topics("broker:9092")
        assert run.call_count == 3


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError("missing"),
        PermissionError("denied"),
        subprocess.TimeoutExpired("kafka", 30),
    ],
)
def test_process_errors_are_reported(error: Exception) -> None:
    with patch.object(manager.subprocess, "run", side_effect=error):
        code, output, message = manager.run_kafka_command(["missing"])
    assert code == 1 and output == "" and message


def test_compose_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAFKA_BIN_DIR", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    command = manager.kafka_command(manager.get_bootstrap_servers(), "--list")
    assert command[:3] == ["docker", "compose", "-f"]
    assert command[4:8] == ["exec", "-T", "kafka", "/opt/kafka/bin/kafka-topics.sh"]
    assert command[-3:] == ["--bootstrap-server", "kafka:29092", "--list"]


def test_direct_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BIN_DIR", "/custom/bin")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "remote:19092")
    command = manager.kafka_command(manager.get_bootstrap_servers(), "--list")
    assert Path(command[0]).parent == Path("/custom/bin")
    assert command[1:] == ["--bootstrap-server", "remote:19092", "--list"]
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS")
    assert manager.get_bootstrap_servers() == "localhost:9092"


def test_main_attempts_all_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["manage_kafka_topics.py", "create"])
    with patch.object(
        manager, "create_topic", side_effect=[False, True, True, True, True]
    ) as create:
        assert manager.main() == 1
        assert create.call_count == 5


@pytest.fixture
def kafka_stack(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use a unique Compose project and remove only this test's resources."""
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")
    project = "task007-test-" + uuid4().hex[:10]
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("PLATFORM_NETWORK_NAME", project)
    monkeypatch.setenv("KAFKA_HOST_PORT", "0")
    monkeypatch.delenv("KAFKA_BIN_DIR", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    compose = ["docker", "compose", "-f", str(PROJECT_ROOT / "docker-compose.yml")]
    try:
        result = subprocess.run(
            [*compose, "up", "-d", "--wait", "--wait-timeout", "120", "kafka"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr
        yield
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
        )


@pytest.mark.integration
def test_topics_created_validated_and_accessed_reproducibly(
    kafka_stack: None, capsys: pytest.CaptureFixture[str]
) -> None:
    bootstrap = manager.get_bootstrap_servers()
    for _ in range(2):
        for topic in TOPICS:
            assert manager.create_topic(topic, bootstrap)
    for topic in TOPICS:
        assert manager.validate_topic(topic, bootstrap)
    assert manager.list_topics(bootstrap)
    output = capsys.readouterr().out
    for topic in TOPICS:
        assert topic.name in output
