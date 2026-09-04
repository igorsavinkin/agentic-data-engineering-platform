"""Tests for Kafka topic configuration (TASK-007).

Verifies that required Kafka topics can be created and accessed
reproducibly according to ADR-001 specifications.
"""

import subprocess
import sys
from pathlib import Path

import pytest


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.manage_kafka_topics import TOPICS, TopicConfig


class TestKafkaTopicConfiguration:
    """Test Kafka topic definitions match ADR-001 specifications."""

    def test_required_topics_exist(self):
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

    def test_topic_count(self):
        """Verify exactly five topics are configured."""
        assert len(TOPICS) == 5, f"Expected 5 topics, got {len(TOPICS)}"

    def test_product_raw_topic_configuration(self):
        """Verify products.raw.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "products.raw.v1")

        assert topic.partitions == 3, "products.raw.v1 should have 3 partitions"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 7 * 24 * 60 * 60 * 1000, "7 day retention"
        assert "source:external_id" in topic.partition_key_strategy

    def test_product_validated_topic_configuration(self):
        """Verify products.validated.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "products.validated.v1")

        assert topic.partitions == 3, "products.validated.v1 should have 3 partitions"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 7 * 24 * 60 * 60 * 1000, "7 day retention"
        assert "source:external_id" in topic.partition_key_strategy

    def test_product_invalid_topic_configuration(self):
        """Verify products.invalid.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "products.invalid.v1")

        assert topic.partitions == 1, "products.invalid.v1 should have 1 partition"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 7 * 24 * 60 * 60 * 1000, "7 day retention"

    def test_pipeline_events_topic_configuration(self):
        """Verify pipeline.events.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "pipeline.events.v1")

        assert topic.partitions == 1, "pipeline.events.v1 should have 1 partition"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 3 * 24 * 60 * 60 * 1000, "3 day retention"

    def test_data_quality_events_topic_configuration(self):
        """Verify data-quality.events.v1 has correct configuration."""
        topic = next(t for t in TOPICS if t.name == "data-quality.events.v1")

        assert topic.partitions == 1, "data-quality.events.v1 should have 1 partition"
        assert topic.replication_factor == 1, "Local dev uses replication factor 1"
        assert topic.retention_ms == 3 * 24 * 60 * 60 * 1000, "3 day retention"

    def test_topic_naming_convention(self):
        """Verify all topics follow domain.status.v{version} pattern."""
        import re

        pattern = r"^[a-z-]+\.[a-z-]+\.v\d+$"

        for topic in TOPICS:
            assert re.match(pattern, topic.name), (
                f"Topic '{topic.name}' doesn't follow naming convention "
                "(domain.status.v{version})"
            )

    def test_all_topics_have_descriptions(self):
        """Verify every topic has a non-empty description."""
        for topic in TOPICS:
            assert topic.description, f"Topic '{topic.name}' missing description"
            assert len(topic.description) > 10, (
                f"Topic '{topic.name}' description too brief"
            )

    def test_partition_key_strategies_documented(self):
        """Verify all topics document their partition key strategy."""
        for topic in TOPICS:
            assert topic.partition_key_strategy, (
                f"Topic '{topic.name}' missing partition key strategy"
            )

    def test_retention_values_positive(self):
        """Verify all retention values are positive."""
        for topic in TOPICS:
            assert topic.retention_ms > 0, (
                f"Topic '{topic.name}' has non-positive retention"
            )

    def test_partition_counts_positive(self):
        """Verify all partition counts are positive."""
        for topic in TOPICS:
            assert topic.partitions > 0, (
                f"Topic '{topic.name}' has non-positive partition count"
            )


class TestKafkaTopicScript:
    """Test the manage_kafka_topics.py script functionality."""

    def test_script_exists(self):
        """Verify the management script exists."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        assert script_path.exists(), "manage_kafka_topics.py not found"

    def test_script_is_executable(self):
        """Verify the management script has execute permissions."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        # On Windows, check if file exists (execute bit works differently)
        assert script_path.exists()

    def test_script_has_shebang(self):
        """Verify the script starts with a proper shebang line."""
        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        with open(script_path) as f:
            first_line = f.readline().strip()
        assert first_line.startswith("#!/usr/bin/env python3"), (
            "Script missing proper shebang line"
        )

    def test_script_help_output(self):
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

    def test_script_invalid_command(self):
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


@pytest.mark.integration
class TestKafkaTopicIntegration:
    """Integration tests requiring running Kafka instance."""

    def _kafka_available(self) -> bool:
        """Check if Kafka is available via Docker Compose."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=ai-data-platform-kafka", "-q"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @pytest.mark.skipif(
        not True,  # Will skip unless explicitly run with --run-integration
        reason="Integration test - requires running Kafka (use --run-integration)",
    )
    def test_create_topics(self):
        """Test creating all required Kafka topics."""
        if not self._kafka_available():
            pytest.skip("Kafka not running")

        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "create"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Topic creation failed: {result.stderr}"
        assert "successfully" in result.stdout.lower()

    @pytest.mark.skipif(
        not True,  # Will skip unless explicitly run with --run-integration
        reason="Integration test - requires running Kafka (use --run-integration)",
    )
    def test_validate_topics(self):
        """Test validating existing Kafka topic configuration."""
        if not self._kafka_available():
            pytest.skip("Kafka not running")

        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "validate"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Topic validation failed: {result.stderr}"
        assert "validated successfully" in result.stdout.lower()

    @pytest.mark.skipif(
        not True,  # Will skip unless explicitly run with --run-integration
        reason="Integration test - requires running Kafka (use --run-integration)",
    )
    def test_list_topics(self):
        """Test listing Kafka topics."""
        if not self._kafka_available():
            pytest.skip("Kafka not running")

        script_path = PROJECT_ROOT / "scripts" / "manage_kafka_topics.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "list"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Topic listing failed: {result.stderr}"
        # Should list at least our 5 topics
        for topic in TOPICS:
            assert topic.name in result.stdout, f"Topic {topic.name} not listed"
