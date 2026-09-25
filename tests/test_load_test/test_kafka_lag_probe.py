"""Regression tests for Kafka lag probe API contract (TASK-112 fix).

These tests protect against the confluent_kafka API incompatibility
discovered during live TASK-112 verification: AdminClient.list_consumer_group_offsets()
requires _ConsumerGroupTopicPartitions objects, not bare group-ID strings,
and results expose topic_partitions as an attribute, not dict items.

All tests are deterministic and do not require a running Kafka broker.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch


def _make_topic_partition_cls() -> type:
    """Return a lightweight TopicPartition stand-in for mocking."""

    class TopicPartition:
        def __init__(self, topic: str, partition: int, offset: int = -1) -> None:
            self.topic = topic
            self.partition = partition
            self.offset = offset

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, TopicPartition):
                return NotImplemented
            return self.topic == other.topic and self.partition == other.partition

        def __hash__(self) -> int:
            return hash((self.topic, self.partition))

    return TopicPartition


def _make_consumer_group_topic_partitions_cls() -> type:
    """Mimic confluent_kafka.admin._ConsumerGroupTopicPartitions."""

    class _ConsumerGroupTopicPartitions:
        def __init__(self, group_id: str) -> None:
            self.group_id = group_id

    return _ConsumerGroupTopicPartitions


def _patch_confluent_kafka() -> tuple[dict[str, Any], type, type]:
    """Patch confluent_kafka modules that are lazily imported by the probe."""
    tp_cls = _make_topic_partition_cls()
    cgtp_cls = _make_consumer_group_topic_partitions_cls()

    admin_mod = MagicMock()
    admin_mod._ConsumerGroupTopicPartitions = cgtp_cls

    confluent_mod = MagicMock()
    confluent_mod.TopicPartition = tp_cls

    patches = {
        "confluent_kafka": confluent_mod,
        "confluent_kafka.admin": admin_mod,
        "confluent_kafka.TopicPartition": tp_cls,
    }
    return patches, tp_cls, cgtp_cls


class TestGetCommittedOffsets:
    """Tests for _get_committed_offsets — the function that was fixed."""

    def test_uses_consumer_group_topic_partitions_in_request(self) -> None:
        """Regression: list_consumer_group_offsets must receive
        _ConsumerGroupTopicPartitions objects, not bare group-ID strings."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()
            future = MagicMock()
            future.result.return_value = SimpleNamespace(topic_partitions=[])
            admin.list_consumer_group_offsets.return_value = {"my-group": future}

            _get_committed_offsets(admin, "my-group", ["t"], 1)

            call_args = admin.list_consumer_group_offsets.call_args[0][0]
            assert len(call_args) == 1
            request_obj = call_args[0]
            assert isinstance(request_obj, cgtp_cls)
            assert getattr(request_obj, "group_id") == "my-group"

    def test_would_fail_with_bare_group_id(self) -> None:
        """If someone reverts to passing a bare string, the request
        object will not be a _ConsumerGroupTopicPartitions instance."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()
            future = MagicMock()
            future.result.return_value = SimpleNamespace(topic_partitions=[])
            admin.list_consumer_group_offsets.return_value = {"g": future}

            _get_committed_offsets(admin, "g", ["t"], 1)

            call_args = admin.list_consumer_group_offsets.call_args[0][0]
            request_obj = call_args[0]
            assert not isinstance(request_obj, str)

    def test_reads_topic_partitions_attribute(self) -> None:
        """Regression: result.topic_partitions is accessed as an attribute,
        not via result.items()."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()

            result_tp_0 = tp_cls(topic="products.raw.v1", partition=0, offset=100)
            result_tp_1 = tp_cls(topic="products.raw.v1", partition=1, offset=200)
            result_tp_2 = tp_cls(topic="products.raw.v1", partition=2, offset=300)

            result = SimpleNamespace(topic_partitions=[result_tp_0, result_tp_1, result_tp_2])

            future = MagicMock()
            future.result.return_value = result
            admin.list_consumer_group_offsets.return_value = {"processor": future}

            committed = _get_committed_offsets(admin, "processor", ["products.raw.v1"], 3)

            assert len(committed) == 3
            assert committed[tp_cls(topic="products.raw.v1", partition=0)] == 100
            assert committed[tp_cls(topic="products.raw.v1", partition=1)] == 200
            assert committed[tp_cls(topic="products.raw.v1", partition=2)] == 300

    def test_missing_committed_offset_defaults_to_minus_one(self) -> None:
        """Partitions with no committed offset should map to -1."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()
            result_tp = tp_cls(topic="t", partition=0, offset=50)
            result = SimpleNamespace(topic_partitions=[result_tp])

            future = MagicMock()
            future.result.return_value = result
            admin.list_consumer_group_offsets.return_value = {"g": future}

            committed = _get_committed_offsets(admin, "g", ["t"], 3)

            assert committed[tp_cls(topic="t", partition=0)] == 50
            assert committed[tp_cls(topic="t", partition=1)] == -1
            assert committed[tp_cls(topic="t", partition=2)] == -1

    def test_group_not_in_futures_returns_empty(self) -> None:
        """When the group is absent from the futures dict, return {}."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()
            admin.list_consumer_group_offsets.return_value = {}

            committed = _get_committed_offsets(admin, "unknown-group", ["t"], 1)
            assert committed == {}

    def test_empty_topic_partitions_returns_all_minus_one(self) -> None:
        """When result has no topic_partitions, all requested partitions get -1."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()
            result = SimpleNamespace(topic_partitions=[])

            future = MagicMock()
            future.result.return_value = result
            admin.list_consumer_group_offsets.return_value = {"g": future}

            committed = _get_committed_offsets(admin, "g", ["t"], 2)

            assert committed[tp_cls(topic="t", partition=0)] == -1
            assert committed[tp_cls(topic="t", partition=1)] == -1

    def test_multiple_topics_and_partitions(self) -> None:
        """Correctly handles offsets across multiple topics and partitions."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import _get_committed_offsets

            admin = MagicMock()
            result_tps = [
                tp_cls(topic="topic_a", partition=0, offset=10),
                tp_cls(topic="topic_a", partition=1, offset=20),
                tp_cls(topic="topic_b", partition=0, offset=30),
            ]
            result = SimpleNamespace(topic_partitions=result_tps)

            future = MagicMock()
            future.result.return_value = result
            admin.list_consumer_group_offsets.return_value = {"g": future}

            committed = _get_committed_offsets(admin, "g", ["topic_a", "topic_b"], 2)

            assert committed[tp_cls(topic="topic_a", partition=0)] == 10
            assert committed[tp_cls(topic="topic_a", partition=1)] == 20
            assert committed[tp_cls(topic="topic_b", partition=0)] == 30
            assert committed[tp_cls(topic="topic_b", partition=1)] == -1


class TestCreateLagQueryFn:
    """Tests for the full lag query function returned by create_lag_query_fn."""

    def _setup_mocks(
        self,
        committed_offsets_by_group: dict[str, list[tuple[str, int, int]]],
        watermarks: dict[tuple[str, int], tuple[int, int]],
    ) -> tuple[dict[str, Any], type, MagicMock, MagicMock]:
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        admin_instance = MagicMock()

        def make_futures(request: list) -> dict:
            futures: dict[str, MagicMock] = {}
            for req in request:
                group_id = req.group_id
                offsets = committed_offsets_by_group.get(group_id, [])
                result_tps = [tp_cls(topic=t, partition=p, offset=o) for t, p, o in offsets]
                result = SimpleNamespace(topic_partitions=result_tps)
                future = MagicMock()
                future.result.return_value = result
                futures[group_id] = future
            return futures

        admin_instance.list_consumer_group_offsets.side_effect = make_futures

        consumer_instance = MagicMock()

        def get_watermarks(
            tp: Any, timeout: float | None = None, cached: bool | None = None
        ) -> tuple[int, int]:
            key = (tp.topic, tp.partition)
            return watermarks.get(key, (0, 100))

        consumer_instance.get_watermark_offsets.side_effect = get_watermarks

        admin_mod = patches["confluent_kafka.admin"]
        admin_mod.AdminClient = MagicMock(return_value=admin_instance)

        confluent_mod = patches["confluent_kafka"]
        confluent_mod.Consumer = MagicMock(return_value=consumer_instance)

        return patches, tp_cls, admin_instance, consumer_instance

    def test_lag_calculation_with_committed_offsets(self) -> None:
        """Lag = high_watermark - committed_offset when committed >= 0."""
        committed = {
            "processor": [("products.raw.v1", 0, 80), ("products.raw.v1", 1, 90)],
        }
        watermarks = {
            ("products.raw.v1", 0): (0, 100),
            ("products.raw.v1", 1): (0, 100),
        }
        patches, tp_cls, admin, consumer = self._setup_mocks(committed, watermarks)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["processor"],
                topics=["products.raw.v1"],
                partition_count=2,
            )
            samples = query(5.0)

        assert len(samples) == 2
        by_partition = {s.partition: s for s in samples}

        assert by_partition[0].lag == 20  # 100 - 80
        assert by_partition[0].consumer_group == "processor"
        assert by_partition[0].topic == "products.raw.v1"
        assert by_partition[1].lag == 10  # 100 - 90

    def test_lag_calculation_without_committed_offset(self) -> None:
        """When committed offset is -1, lag = high - low (full range)."""
        committed = {
            "processor": [("t", 0, -1)],
        }
        watermarks = {
            ("t", 0): (10, 100),
        }
        patches, tp_cls, admin, consumer = self._setup_mocks(committed, watermarks)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["processor"],
                topics=["t"],
                partition_count=1,
            )
            samples = query(1.0)

        assert len(samples) == 1
        assert samples[0].lag == 90  # high(100) - low(10)

    def test_lag_is_non_negative(self) -> None:
        """Lag is clamped to >= 0 even if committed offset exceeds high watermark."""
        committed = {
            "processor": [("t", 0, 200)],
        }
        watermarks = {
            ("t", 0): (0, 100),
        }
        patches, tp_cls, admin, consumer = self._setup_mocks(committed, watermarks)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["processor"],
                topics=["t"],
                partition_count=1,
            )
            samples = query(1.0)

        assert samples[0].lag == 0  # max(0, 100 - 200) = 0

    def test_multiple_consumer_groups(self) -> None:
        """Samples are produced for each consumer group independently."""
        committed = {
            "processor": [("t", 0, 50)],
            "raw-writer": [("t", 0, 30)],
        }
        watermarks = {
            ("t", 0): (0, 100),
        }
        patches, tp_cls, admin, consumer = self._setup_mocks(committed, watermarks)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["processor", "raw-writer"],
                topics=["t"],
                partition_count=1,
            )
            samples = query(2.0)

        assert len(samples) == 2
        by_group = {s.consumer_group: s for s in samples}
        assert by_group["processor"].lag == 50  # 100 - 50
        assert by_group["raw-writer"].lag == 70  # 100 - 30

    def test_multiple_partitions(self) -> None:
        """Each partition produces its own LagSample."""
        committed = {
            "processor": [
                ("t", 0, 10),
                ("t", 1, 20),
                ("t", 2, 30),
            ],
        }
        watermarks = {
            ("t", 0): (0, 100),
            ("t", 1): (0, 100),
            ("t", 2): (0, 100),
        }
        patches, tp_cls, admin, consumer = self._setup_mocks(committed, watermarks)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["processor"],
                topics=["t"],
                partition_count=3,
            )
            samples = query(3.0)

        assert len(samples) == 3
        by_partition = {s.partition: s for s in samples}
        assert by_partition[0].lag == 90  # 100 - 10
        assert by_partition[1].lag == 80  # 100 - 20
        assert by_partition[2].lag == 70  # 100 - 30

    def test_committed_offsets_error_skips_group(self) -> None:
        """If querying committed offsets fails for a group, it is skipped."""
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        admin_instance = MagicMock()
        admin_instance.list_consumer_group_offsets.side_effect = RuntimeError("broker unreachable")

        consumer_instance = MagicMock()
        consumer_instance.get_watermark_offsets.return_value = (0, 100)

        patches["confluent_kafka.admin"].AdminClient = MagicMock(return_value=admin_instance)
        patches["confluent_kafka"].Consumer = MagicMock(return_value=consumer_instance)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["failing-group"],
                topics=["t"],
                partition_count=1,
            )
            samples = query(1.0)

        assert samples == []

    def test_watermark_error_skips_partition(self) -> None:
        """If watermark query fails for a partition, that partition is skipped."""
        committed = {
            "processor": [("t", 0, 50), ("t", 1, 60)],
        }
        watermarks = {
            ("t", 0): (0, 100),
        }
        patches, tp_cls, cgtp_cls = _patch_confluent_kafka()

        admin_instance = MagicMock()

        def make_futures(request: list) -> dict:
            futures: dict[str, MagicMock] = {}
            for req in request:
                group_id = req.group_id
                offsets = committed.get(group_id, [])
                result_tps = [tp_cls(topic=t, partition=p, offset=o) for t, p, o in offsets]
                result = SimpleNamespace(topic_partitions=result_tps)
                future = MagicMock()
                future.result.return_value = result
                futures[group_id] = future
            return futures

        admin_instance.list_consumer_group_offsets.side_effect = make_futures

        consumer_instance = MagicMock()

        def get_watermarks(
            tp: Any, timeout: float | None = None, cached: bool | None = None
        ) -> tuple[int, int]:
            key = (tp.topic, tp.partition)
            if key in watermarks:
                return watermarks[key]
            raise RuntimeError("watermark unavailable")

        consumer_instance.get_watermark_offsets.side_effect = get_watermarks

        patches["confluent_kafka.admin"].AdminClient = MagicMock(return_value=admin_instance)
        patches["confluent_kafka"].Consumer = MagicMock(return_value=consumer_instance)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["processor"],
                topics=["t"],
                partition_count=2,
            )
            samples = query(1.0)

        assert len(samples) == 1
        assert samples[0].partition == 0
        assert samples[0].lag == 50

    def test_elapsed_sec_propagated_to_samples(self) -> None:
        """The elapsed_sec parameter is passed through to each LagSample."""
        committed = {
            "g": [("t", 0, 50)],
        }
        watermarks = {("t", 0): (0, 100)}
        patches, tp_cls, admin, consumer = self._setup_mocks(committed, watermarks)

        with patch.dict(sys.modules, patches):
            from libs.load_test.kafka_lag_probe import create_lag_query_fn

            query = create_lag_query_fn(
                bootstrap_servers="localhost:9092",
                consumer_groups=["g"],
                topics=["t"],
                partition_count=1,
            )
            samples = query(42.5)

        assert all(s.elapsed_sec == 42.5 for s in samples)
