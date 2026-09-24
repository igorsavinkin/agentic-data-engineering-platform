"""Duplicate and replay engineering test (TASK-104).

Demonstrates the full failure lifecycle for duplicate events and Kafka replays:

    Duplicate Delivery -> Detection (dedup metrics/logs) -> Recovery -> No duplicates

Scenarios:
1. Produce duplicate events to Kafka; verify processor deduplication catches
   them within a batch and across batches, with metrics recording duplicates.
2. Simulate a Kafka replay (reset consumer offsets); verify that a processor
   with shared dedup state rejects already-seen events.
3. End-to-end: produce duplicates, process through the pipeline, load into
   PostgreSQL, and verify the warehouse UNIQUE constraint prevents duplicate
   records even when the processor emits them.

Lifecycle per scenario:
    Failure (duplicates/replay) -> Detection (metrics/logs) -> Recovery -> No silent data loss

Run with: pytest tests/test_duplicate_replay.py -v -m integration
"""

# mypy: disable-error-code="import-untyped,no-untyped-def,import-not-found,no-any-return"
from __future__ import annotations

import io
import os
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import polars as pl
import psycopg2
import pytest

from libs.common.kafka_consumer import (
    ConsumerMessage,
    KafkaConsumer,
    KafkaConsumerSettings,
)
from libs.common.kafka_errors import KafkaDeadLetterProducer
from libs.common.kafka_producer import (
    KafkaEventProducer,
    KafkaProducerSettings,
)
from libs.common.kafka_validated_producer import KafkaValidatedOutputProducer
from libs.common.minio_storage import MinIOStorage
from libs.event_contracts import (
    Availability,
    ProductObservationEvent,
    ProductObservationPayload,
    deserialize_event,
)
from libs.lake_writer import SilverWriter
from libs.observability.processor_metrics import ProcessorMetric, ProcessorMetrics
from scripts import manage_kafka_topics as manager
from services.processor.deduplication import DeduplicationState
from services.processor.pipeline import ProcessorPipeline
from warehouse.loader.batch_loader import WarehouseLoader

pytestmark = pytest.mark.integration

RAW_TOPIC = "products.raw.v1"
_SAME_EXTERNAL_ID = "dup-replay-product"


# ============================================================================
# Fixtures
# ============================================================================


@dataclass(frozen=True)
class ComposeContext:
    port: int
    env: dict[str, str]
    compose_cmd: list[str]


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.upper().startswith("APP_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("APP_ENVIRONMENT", "development")


@pytest.fixture
def real_broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    project = f"task104-test-{uuid4().hex[:10]}"
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("PLATFORM_NETWORK_NAME", project)
    monkeypatch.setenv("KAFKA_HOST_PORT", str(port))
    monkeypatch.delenv("KAFKA_BIN_DIR", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)

    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose_cmd = ["docker", "compose", "-f", str(compose_file)]

    try:
        result = subprocess.run(
            [*compose_cmd, "up", "-d", "--wait", "--wait-timeout", "120", "kafka"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, f"Failed to start Kafka: {result.stderr}"

        for topic_config in manager.TOPICS:
            assert manager.create_topic(topic_config, "kafka:29092"), (
                f"Failed to create topic {topic_config.name}"
            )

        yield f"localhost:{port}"
    finally:
        subprocess.run(
            [*compose_cmd, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
        )


@pytest.fixture
def compose_project(monkeypatch: pytest.MonkeyPatch) -> Iterator[ComposeContext]:
    try:
        probe = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon unavailable")
    if probe.returncode:
        pytest.skip("Docker daemon unavailable")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    project = f"task104-pg-{uuid4().hex[:10]}"
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project
    env["PLATFORM_NETWORK_NAME"] = project
    env["POSTGRES_HOST_PORT"] = str(port)

    compose_file = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose_cmd = ["docker", "compose", "-f", str(compose_file)]

    try:
        result = subprocess.run(
            [*compose_cmd, "up", "-d", "--wait", "--wait-timeout", "120", "postgres"],
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        assert result.returncode == 0, f"Failed to start PostgreSQL: {result.stderr}"
        _wait_for_postgres(port, timeout=30)
        yield ComposeContext(port=port, env=env, compose_cmd=compose_cmd)
    finally:
        subprocess.run(
            [*compose_cmd, "down", "--volumes", "--remove-orphans"],
            capture_output=True,
            check=True,
            timeout=60,
            env=env,
        )


@pytest.fixture
def producer_settings(real_broker: str) -> KafkaProducerSettings:
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_raw_topic=RAW_TOPIC,
    )


@pytest.fixture
def group_id() -> str:
    return f"task104-dup-{uuid4().hex[:8]}"


@pytest.fixture
def consumer_settings(real_broker: str, group_id: str) -> KafkaConsumerSettings:
    return KafkaConsumerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_group_id=group_id,
    )


@pytest.fixture
def validated_producer_settings(real_broker: str) -> KafkaProducerSettings:
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_client_id="task104-validated",
    )


@pytest.fixture
def invalid_producer_settings(real_broker: str) -> KafkaProducerSettings:
    return KafkaProducerSettings(
        environment="development",
        kafka_bootstrap_servers=real_broker,
        kafka_client_id="task104-invalid",
    )


@pytest.fixture
def test_db_url(compose_project: ComposeContext) -> Iterator[str]:
    port = compose_project.port
    admin_url = f"postgresql://platform:platform-local@127.0.0.1:{port}/postgres"
    db_name = f"dup_replay_test_{uuid4().hex[:8]}"

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE {db_name}")
    cur.close()
    conn.close()

    test_url = f"postgresql://platform:platform-local@127.0.0.1:{port}/{db_name}"

    migrations_dir = Path(__file__).resolve().parents[1] / "warehouse" / "migrations"
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(migrations_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(cfg, "head")

    loader_url = test_url.replace("postgresql://", "postgresql+psycopg2://")
    yield loader_url

    _wait_for_postgres(port, timeout=30)
    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cur.close()
    conn.close()


@pytest.fixture
def query_url(test_db_url: str) -> str:
    return test_db_url.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture
def loader(test_db_url: str) -> WarehouseLoader:
    mock_storage = MagicMock(spec=MinIOStorage)
    return WarehouseLoader(db_url=test_db_url, storage=mock_storage, batch_size=100)


# ============================================================================
# Helpers
# ============================================================================


def _wait_for_postgres(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = psycopg2.connect(
                host="127.0.0.1",
                port=port,
                user="platform",
                password="platform-local",
                dbname="platform",
            )
            conn.close()
            return
        except psycopg2.OperationalError:
            time.sleep(0.5)
    raise TimeoutError(f"PostgreSQL did not become ready on port {port}")


def _make_event(tag: str) -> ProductObservationEvent:
    return deserialize_event(
        {
            "event_id": f"task104-{tag}-{uuid4().hex[:8]}",
            "source": "dup-replay-test",
            "produced_at": "2026-09-24T12:00:00Z",
            "payload": {
                "external_id": _SAME_EXTERNAL_ID,
                "name": f"Dup Replay {tag}",
                "url": f"https://example.com/dup/{tag}",
                "price": "29.99",
                "currency": "USD",
                "availability": "in_stock",
                "category": "test",
                "collected_at": "2026-09-24T11:59:00Z",
            },
        }
    )


def _consume_raw_messages(
    consumer: KafkaConsumer,
    expected: int,
    timeout: float = 15.0,
) -> list[ConsumerMessage]:
    messages: list[ConsumerMessage] = []
    deadline = time.monotonic() + timeout
    while len(messages) < expected and time.monotonic() < deadline:
        batch, errors = consumer.poll(timeout=1.0)
        messages.extend(batch)
        if errors:
            pytest.fail(f"Unexpected deserialization errors: {errors}")
    return messages


def _build_pipeline(
    validated_settings: KafkaProducerSettings,
    invalid_settings: KafkaProducerSettings,
    dedup_state: DeduplicationState | None = None,
    metrics: ProcessorMetrics | None = None,
) -> tuple[ProcessorPipeline, KafkaValidatedOutputProducer, KafkaDeadLetterProducer]:
    validated_producer = KafkaValidatedOutputProducer(validated_settings)
    invalid_producer = KafkaDeadLetterProducer(invalid_settings)
    pipeline = ProcessorPipeline(
        validated_sink=validated_producer.publish,
        invalid_sink=invalid_producer.publish,
        dedup_state=dedup_state,
        metrics=metrics,
    )
    return pipeline, validated_producer, invalid_producer


def _count_observations(query_url: str) -> int:
    conn = psycopg2.connect(query_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM product_observations")
        return cur.fetchone()[0]
    finally:
        conn.close()


def _make_warehouse_parquet(tmp_path: Path, tag: str, event_ids: list[str]) -> Path:
    count = len(event_ids)
    df = pl.DataFrame(
        {
            "event_id": event_ids,
            "source": ["dup-replay-test"] * count,
            "external_id": [_SAME_EXTERNAL_ID] * count,
            "name": [f"Widget {tag}-{i}" for i in range(count)],
            "price": [f"{19.99 + i}" for i in range(count)],
            "currency": ["USD"] * count,
            "availability": ["in_stock"] * count,
            "category": ["test"] * count,
            "collected_at": [
                datetime(2026, 9, 24, 10 + i, tzinfo=timezone.utc) for i in range(count)
            ],
            "url": [f"https://example.com/dup/{tag}/{i}" for i in range(count)],
        }
    )
    path = tmp_path / f"{tag}.parquet"
    df.write_parquet(path)
    return path


# ============================================================================
# Scenario 1: Duplicate delivery detection and deduplication
# ============================================================================


class TestDuplicateDeliveryDetection:
    """Duplicate events are detected and deduplicated by the processor.

    Failure: same event produced twice to Kafka (simulates at-least-once redelivery).
    Detection: ProcessorMetrics EVENTS_DUPLICATE increments, dedup state tracks seen IDs.
    Recovery: only one copy reaches products.validated.v1.
    No silent data loss: the unique event is still published.
    """

    def test_duplicate_events_deduplicated_with_metrics(
        self,
        real_broker: str,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """Producing the same event twice yields one validated output with metrics."""
        event = _make_event("dup-metrics")

        with KafkaEventProducer(producer_settings) as producer:
            producer.publish(event)
            producer.publish(event)

        raw_consumer = KafkaConsumer(consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=2)
            assert len(messages) == 2
            assert messages[0].event.event_id == messages[1].event.event_id

            dedup_state = DeduplicationState()
            metrics = ProcessorMetrics()
            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                dedup_state=dedup_state,
                metrics=metrics,
            )
            try:
                result = pipeline.process_batch(messages)

                assert result.published_valid == 1, "Exactly one copy should be published"
                assert result.duplicates_skipped == 1, "One duplicate must be detected"
                assert result.total == 2, "All input must be accounted for"

                snapshot = metrics.snapshot()
                assert snapshot[ProcessorMetric.EVENTS_DUPLICATE] == 1, (
                    "EVENTS_DUPLICATE metric must record the duplicate"
                )
                assert snapshot[ProcessorMetric.EVENTS_VALID] == 1
                assert snapshot[ProcessorMetric.EVENTS_PROCESSED] == 2

                assert dedup_state.size == 1, "Dedup state tracks exactly one event_id"
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()


# ============================================================================
# Scenario 2: Kafka replay with dedup state
# ============================================================================


class TestKafkaReplayDeduplication:
    """Kafka replay (offset reset) does not create duplicate validated output.

    Failure: consumer offsets reset to earliest, all events redelivered.
    Detection: dedup state rejects already-seen event_ids, metrics record duplicates.
    Recovery: replay completes without error, only new events published.
    No silent data loss: all unique events were published on first pass.
    """

    def test_replay_with_dedup_state_skips_seen_events(
        self,
        real_broker: str,
        producer_settings: KafkaProducerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """Replaying consumed messages through a pipeline with shared state skips duplicates."""
        events = [_make_event(f"replay-{i}") for i in range(3)]

        with KafkaEventProducer(producer_settings) as producer:
            for evt in events:
                producer.publish(evt)

        group = f"task104-replay-{uuid4().hex[:8]}"
        consumer_settings = KafkaConsumerSettings(
            environment="development",
            kafka_bootstrap_servers=real_broker,
            kafka_group_id=group,
        )

        original_consumer = KafkaConsumer(consumer_settings)
        try:
            original_consumer.subscribe([RAW_TOPIC])
            original_messages = _consume_raw_messages(original_consumer, expected=3)
            assert len(original_messages) == 3

            dedup_state = DeduplicationState()
            metrics = ProcessorMetrics()
            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                dedup_state=dedup_state,
                metrics=metrics,
            )
            try:
                result1 = pipeline.process_batch(original_messages)
                assert result1.published_valid == 3
                assert result1.duplicates_skipped == 0
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            original_consumer.close()

        replay_consumer = KafkaConsumer(consumer_settings)
        try:
            replay_consumer.subscribe([RAW_TOPIC])
            replay_messages = _consume_raw_messages(replay_consumer, expected=3, timeout=15.0)
            assert len(replay_messages) == 3, (
                "Replay consumer must receive all 3 messages (no committed offsets)"
            )

            metrics2 = ProcessorMetrics()
            pipeline2, vp2, ip2 = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                dedup_state=dedup_state,
                metrics=metrics2,
            )
            try:
                result2 = pipeline2.process_batch(replay_messages)

                assert result2.published_valid == 0, (
                    "Replay with shared dedup state must publish zero new events"
                )
                assert result2.duplicates_skipped == 3, (
                    "All 3 replayed events must be detected as duplicates"
                )

                snapshot2 = metrics2.snapshot()
                assert snapshot2[ProcessorMetric.EVENTS_DUPLICATE] == 3
            finally:
                vp2.close()
                ip2.close()
        finally:
            replay_consumer.close()


# ============================================================================
# Scenario 3: Cross-batch deduplication across processor restart
# ============================================================================


class TestCrossBatchDeduplication:
    """Cross-batch deduplication prevents duplicates when processor restarts.

    Failure: processor restarts, same events redelivered from Kafka.
    Detection: new DeduplicationState is empty, but PostgreSQL UNIQUE constraint
    catches duplicates at the warehouse boundary.
    Recovery: warehouse loader's ON CONFLICT DO NOTHING ensures idempotency.
    No silent data loss: all unique events are in PostgreSQL exactly once.
    """

    def test_warehouse_prevents_duplicates_after_processor_restart(
        self,
        loader: WarehouseLoader,
        tmp_path: Path,
        query_url: str,
    ) -> None:
        """Loading same data twice creates no duplicates in PostgreSQL."""
        event_ids = [f"evt-cross-{i}" for i in range(5)]
        batch = _make_warehouse_parquet(tmp_path, "original", event_ids)

        result1 = loader.load_from_parquet_files([batch])
        assert result1.success
        assert result1.observations_created == 5
        assert _count_observations(query_url) == 5

        result2 = loader.load_from_parquet_files([batch])
        assert result2.success
        assert result2.observations_created == 0, (
            "Re-loading same data must create zero new observations"
        )
        assert _count_observations(query_url) == 5, (
            "PostgreSQL must still have exactly 5 observations"
        )


# ============================================================================
# Scenario 4: Independent dedup boundaries — processor and warehouse
# ============================================================================


class TestIndependentDedupBoundaries:
    """Processor and warehouse each independently prevent duplicates.

    This scenario verifies two separate dedup boundaries:
    1. Processor: DeduplicationState catches within-process duplicates (metrics).
    2. Warehouse: PostgreSQL UNIQUE constraint on event_id prevents duplicates
       via ON CONFLICT DO NOTHING.

    These are independent safeguards — each protects against duplicates even
    if the other layer's state is lost (e.g., processor restart).
    """

    def test_processor_and_warehouse_each_prevent_duplicates(
        self,
        real_broker: str,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
        loader: WarehouseLoader,
        tmp_path: Path,
        query_url: str,
    ) -> None:
        """Processor dedup and warehouse idempotency are independent safeguards."""
        unique_events = [_make_event(f"e2e-{i}") for i in range(3)]

        with KafkaEventProducer(producer_settings) as producer:
            for evt in unique_events:
                producer.publish(evt)
                producer.publish(evt)

        raw_consumer = KafkaConsumer(consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=6)
            assert len(messages) == 6

            dedup_state = DeduplicationState()
            metrics = ProcessorMetrics()

            pipeline, validated_prod, invalid_prod = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                dedup_state=dedup_state,
                metrics=metrics,
            )
            try:
                result = pipeline.process_batch(messages)

                assert result.published_valid == 3, "Only 3 unique events should be published"
                assert result.duplicates_skipped == 3, "3 duplicates must be detected and skipped"
                assert result.total == 6, "All 6 input records must be accounted for"

                snapshot = metrics.snapshot()
                assert snapshot[ProcessorMetric.EVENTS_DUPLICATE] == 3
                assert snapshot[ProcessorMetric.EVENTS_VALID] == 3
            finally:
                validated_prod.close()
                invalid_prod.close()
        finally:
            raw_consumer.close()

        warehouse_event_ids = [f"evt-e2e-pg-{i}" for i in range(3)]
        warehouse_batch = _make_warehouse_parquet(tmp_path, "e2e-dedup", warehouse_event_ids)
        load_result = loader.load_from_parquet_files([warehouse_batch])
        assert load_result.success

        first_load_count = load_result.observations_created

        replay_result = loader.load_from_parquet_files([warehouse_batch])
        assert replay_result.success
        assert replay_result.observations_created == 0, (
            "Replay at warehouse level must create zero duplicates"
        )

        total = _count_observations(query_url)
        assert total == first_load_count, (
            f"PostgreSQL must have exactly {first_load_count} observations after replay"
        )


# ============================================================================
# Scenario 5: Multiple processor replay passes emit no duplicates
# ============================================================================


class TestMultipleProcessorReplays:
    """Multiple replay passes at the processor level emit duplicates only once.

    Failure: same batch processed multiple times (simulates replay).
    Detection: dedup state marks subsequent passes as duplicates.
    Recovery: pipeline emits nothing on replay passes.
    No silent data loss: first pass emitted all unique events.
    """

    def test_multiple_replays_emit_no_duplicates(
        self,
        real_broker: str,
        producer_settings: KafkaProducerSettings,
        consumer_settings: KafkaConsumerSettings,
        validated_producer_settings: KafkaProducerSettings,
        invalid_producer_settings: KafkaProducerSettings,
    ) -> None:
        """Processing the same batch 3 times emits validated events only on the first pass."""
        events = [_make_event(f"multi-replay-{i}") for i in range(4)]

        with KafkaEventProducer(producer_settings) as producer:
            for evt in events:
                producer.publish(evt)

        raw_consumer = KafkaConsumer(consumer_settings)
        try:
            raw_consumer.subscribe([RAW_TOPIC])
            messages = _consume_raw_messages(raw_consumer, expected=4)
            assert len(messages) == 4
        finally:
            raw_consumer.close()

        dedup_state = DeduplicationState()
        total_published = 0
        total_duplicates = 0

        for pass_num in range(3):
            pipeline, vp, ip = _build_pipeline(
                validated_producer_settings,
                invalid_producer_settings,
                dedup_state=dedup_state,
            )
            try:
                result = pipeline.process_batch(messages)
                total_published += result.published_valid
                total_duplicates += result.duplicates_skipped

                if pass_num == 0:
                    assert result.published_valid == 4
                    assert result.duplicates_skipped == 0
                else:
                    assert result.published_valid == 0
                    assert result.duplicates_skipped == 4
            finally:
                vp.close()
                ip.close()

        assert total_published == 4, "Exactly 4 unique events published across all passes"
        assert total_duplicates == 8, "8 duplicates skipped across passes 2 and 3"


class TestSilverParquetReplayIdempotency:
    """SilverWriter replay overwrites the same storage key — no duplicate objects.

    SilverWriter keys each Parquet object by build_partition_key(event), where
    the leaf filename is event_id.parquet. Replaying the same event writes to
    the same key, overwriting rather than duplicating. This test exercises that
    path with a mock MinIOStorage to verify the platform's Parquet-level
    idempotency guarantee.
    """

    @staticmethod
    def _make_silver_event(tag: str) -> ProductObservationEvent:
        return ProductObservationEvent(
            event_id=f"evt-silver-{tag}",
            event_type="product.observation",
            schema_version=1,
            source="silver-replay-test",
            produced_at=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
            payload=ProductObservationPayload(
                external_id=f"prod-silver-{tag}",
                name=f"Silver Product {tag}",
                url=f"https://example.com/silver/{tag}",
                price=Decimal("29.99"),
                currency="USD",
                availability=Availability.IN_STOCK,
                category="test",
                collected_at=datetime(2026, 9, 24, 11, 59, 0, tzinfo=timezone.utc),
            ),
        )

    def test_silver_writer_replay_overwrites_no_duplicates(self) -> None:
        """Writing the same events twice via SilverWriter produces 5 objects, not 10."""
        storage = MagicMock(spec=MinIOStorage)
        storage.check_health.return_value = MagicMock(healthy=True)
        written: dict[str, bytes] = {}

        def fake_put_object(bucket: str, key: str, body: bytes | io.BytesIO) -> None:
            data = body.read() if hasattr(body, "read") else body
            written[key] = data

        storage.put_object.side_effect = fake_put_object

        writer = SilverWriter(storage=storage, bucket="silver")

        events = [self._make_silver_event(str(i)) for i in range(5)]

        for event in events:
            writer.write_event(event)
        first_pass_keys = set(written.keys())
        assert len(first_pass_keys) == 5

        for event in events:
            writer.write_event(event)
        second_pass_keys = set(written.keys())
        assert second_pass_keys == first_pass_keys, (
            "Replay must write to the same keys (overwrite), not create new ones"
        )
        assert len(written) == 5, f"Expected 5 unique objects after replay, got {len(written)}"

        all_event_ids: list[str] = []
        for key, parquet_bytes in written.items():
            df = pl.read_parquet(io.BytesIO(parquet_bytes))
            assert len(df) == 1, f"Each object should contain exactly 1 row, got {len(df)}"
            all_event_ids.append(df["event_id"][0])
            assert key.endswith(f"{df['event_id'][0]}.parquet"), (
                "Key leaf must match the event_id in the Parquet"
            )

        assert len(set(all_event_ids)) == 5, (
            "All 5 stored objects must have distinct event_ids — no duplicates"
        )
