"""Kafka consumer-group lag probe for load-test monitoring (TASK-112).

Uses ``confluent_kafka`` AdminClient to list consumer-group committed offsets
and a lightweight Consumer to query broker high watermarks.  The probe does
not join any real consumer group and does not consume messages.

The probe is designed for periodic invocation from a background thread
during load tests.  Each call to ``sample()`` queries all configured
consumer groups and returns a list of ``LagSample`` values.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from libs.load_test.lag_collector import LagSample

logger = logging.getLogger(__name__)


def create_lag_query_fn(
    bootstrap_servers: str,
    consumer_groups: list[str],
    topics: list[str],
    partition_count: int = 3,
) -> Callable[[float], list[LagSample]]:
    """Create a callable that queries Kafka for consumer-group lag.

    Parameters
    ----------
    bootstrap_servers:
        Kafka broker address.
    consumer_groups:
        Consumer group IDs to monitor (e.g. ``["processor", "raw-writer"]``).
    topics:
        Topics to monitor (e.g. ``["products.raw.v1"]``).
    partition_count:
        Number of partitions per topic.  Defaults to 3, matching the
        platform's default topic configuration.

    Returns
    -------
    Callable
        A function ``(elapsed_sec) -> list[LagSample]`` that queries the
        broker and returns current lag for each group/topic/partition.
    """
    from confluent_kafka import Consumer
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": bootstrap_servers})

    watermark_consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": f"lag-probe-{id(admin)}",
        }
    )
    _assign_probe_partitions(watermark_consumer, topics, partition_count)

    def query(elapsed_sec: float) -> list[LagSample]:
        samples: list[LagSample] = []
        for group_id in consumer_groups:
            try:
                committed = _get_committed_offsets(admin, group_id, topics, partition_count)
            except Exception:
                logger.debug(
                    "lag_probe_committed_failed",
                    extra={"consumer_group": group_id},
                    exc_info=True,
                )
                continue

            for tp, committed_offset in committed.items():
                try:
                    low, high = watermark_consumer.get_watermark_offsets(
                        tp, timeout=5.0, cached=False
                    )
                except Exception:
                    logger.debug(
                        "lag_probe_watermark_failed",
                        extra={"topic": tp.topic, "partition": tp.partition},
                        exc_info=True,
                    )
                    continue

                if committed_offset < 0:
                    lag = high - low
                else:
                    lag = max(0, high - committed_offset)

                samples.append(
                    LagSample(
                        elapsed_sec=elapsed_sec,
                        consumer_group=group_id,
                        topic=tp.topic,
                        partition=tp.partition,
                        lag=lag,
                    )
                )
        return samples

    return query


def _assign_probe_partitions(
    consumer: Any,
    topics: list[str],
    partition_count: int,
) -> None:
    """Manually assign topic partitions to the probe consumer.

    Uses ``assign()`` rather than ``subscribe()`` so the probe does not
    trigger consumer-group rebalances or consume messages.
    """
    from confluent_kafka import TopicPartition

    partitions = [
        TopicPartition(topic=topic, partition=p) for topic in topics for p in range(partition_count)
    ]
    consumer.assign(partitions)


def _get_committed_offsets(
    admin: Any,
    group_id: str,
    topics: list[str],
    partition_count: int,
) -> dict:
    """Query committed offsets for a consumer group via AdminClient.

    Returns a dict mapping ``TopicPartition`` to committed offset (int).
    Partitions with no committed offset map to -1.
    """
    from confluent_kafka import TopicPartition
    from confluent_kafka.admin import _ConsumerGroupTopicPartitions

    request = [_ConsumerGroupTopicPartitions(group_id=group_id)]
    futures = admin.list_consumer_group_offsets(request)
    if group_id not in futures:
        return {}

    result = futures[group_id].result(timeout=10.0)
    committed: dict = {}

    offset_lookup: dict[tuple[str, int], int] = {}
    topic_partitions = getattr(result, "topic_partitions", None) or []
    for tp in topic_partitions:
        offset_lookup[(tp.topic, tp.partition)] = tp.offset

    for topic in topics:
        for p in range(partition_count):
            tp = TopicPartition(topic=topic, partition=p)
            committed[tp] = offset_lookup.get((topic, p), -1)

    return committed
