"""Ingestion runner: orchestrates adapter fetch → Kafka publish loop.

This module wires source adapters to the Kafka producer, executing periodic
fetch cycles and publishing canonical ProductObservationEvent instances to
the raw topic. It handles error isolation per source so one failing adapter
does not block others.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from libs.adapters import FetchResult, SourceAdapterProtocol, SourceFetchError
from libs.common.kafka_errors import PublishError
from libs.common.kafka_producer import (
    DeliveryReceipt,
    EventSerializationError,
    KafkaEventProducer,
)
from libs.event_contracts import ProductObservationEvent
from libs.observability.kafka_metrics import KafkaMetric
from libs.observability.otel_config import (
    get_current_trace_id,
    get_tracer,
    inject_trace_context,
    safe_attributes,
)
from libs.observability.source_metrics import SourceMetrics

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


@dataclass
class SourceStatus:
    """Runtime status for a single source adapter."""

    source_name: str
    last_fetch_success: bool = True
    last_fetch_time: datetime | None = None
    events_published: int = 0
    malformed_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class IngestionStats:
    """Aggregate ingestion statistics across all sources."""

    total_events_published: int = 0
    total_malformed: int = 0
    total_errors: int = 0
    sources: dict[str, SourceStatus] = field(default_factory=dict)


class IngestionRunner:
    """Orchestrate periodic fetch-publish cycles for configured adapters.

    Parameters
    ----------
    adapters:
        Sequence of source adapter instances implementing SourceAdapterProtocol.
    producer:
        KafkaEventProducer instance for publishing canonical events.
    interval_seconds:
        Seconds between fetch cycles. Defaults to 60s for production use.
    max_retries:
        Maximum retry attempts per source on transient SourceFetchError.
        Defaults to 3 with exponential backoff.
    """

    def __init__(
        self,
        adapters: Sequence[SourceAdapterProtocol],
        producer: KafkaEventProducer,
        interval_seconds: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        if not adapters:
            raise ValueError("at least one adapter is required")
        self._adapters = list(adapters)
        self._producer = producer
        self._interval = interval_seconds
        self._max_retries = max_retries
        self._stats = IngestionStats()
        self._running = False

        # Initialize per-source status tracking and metrics
        self._source_metrics: dict[str, SourceMetrics] = {}
        for adapter in self._adapters:
            self._stats.sources[adapter.source_name] = SourceStatus(source_name=adapter.source_name)
            # Create metrics for this source (reuse if adapter already has one)
            if hasattr(adapter, "_metrics") and isinstance(adapter._metrics, SourceMetrics):
                self._source_metrics[adapter.source_name] = adapter._metrics
            else:
                self._source_metrics[adapter.source_name] = SourceMetrics(
                    source_name=adapter.source_name
                )

    @property
    def stats(self) -> IngestionStats:
        """Return current ingestion statistics."""
        return self._stats

    @property
    def source_metrics(self) -> dict[str, SourceMetrics]:
        """Return source-level metrics for all configured adapters."""
        return dict(self._source_metrics)

    def get_source_freshness(self) -> dict[str, dict[str, Any]]:
        """Get freshness information for all sources.

        Returns a dict mapping source name to freshness data including:
        - last_successful_fetch: ISO timestamp or None
        - freshness_age_seconds: age in seconds or None
        """
        result = {}
        for source_name, metrics in self._source_metrics.items():
            result[source_name] = {
                "last_successful_fetch": metrics.get_last_successful_fetch(),
                "freshness_age_seconds": metrics.get_freshness_age_seconds(),
            }
        return result

    def get_source_health(self) -> dict[str, dict[str, Any]]:
        """Get health assessment for all sources with health trackers.

        Returns a dict mapping source name to health data including:
        - state: degradation state string
        - reasons: list of diagnostic reasons
        - signals: measurable signals dict

        Sources without health trackers are omitted.
        """
        result: dict[str, dict[str, Any]] = {}
        for adapter in self._adapters:
            if hasattr(adapter, "health_assessment"):
                assessment = adapter.health_assessment()
                result[adapter.source_name] = {
                    "state": assessment.state.value,
                    "reasons": assessment.reasons,
                    "signals": assessment.signals,
                }
        return result

    async def run_once(self) -> IngestionStats:
        """Execute one fetch-publish cycle across all adapters.

        Each adapter runs independently; failures in one source do not
        prevent other sources from being fetched. Malformed records are
        logged but do not halt the cycle.

        Returns
        -------
        IngestionStats
            Updated aggregate statistics after this cycle.
        """
        logger.info(
            "ingestion_cycle_start",
            extra={
                "operation": "ingestion_cycle",
                "source_count": len(self._adapters),
            },
        )

        for adapter in self._adapters:
            await self._fetch_and_publish(adapter)

        logger.info(
            "ingestion_cycle_complete",
            extra={
                "operation": "ingestion_cycle",
                "total_published": self._stats.total_events_published,
                "total_malformed": self._stats.total_malformed,
                "total_errors": self._stats.total_errors,
            },
        )

        return self._stats

    async def run_continuous(self) -> None:
        """Run fetch-publish cycles continuously at the configured interval.

        This method blocks until cancelled via KeyboardInterrupt or an
        unhandled exception. Use run_once() for single-cycle execution.
        """
        self._running = True
        logger.info(
            "ingestion_service_started",
            extra={
                "operation": "ingestion_start",
                "interval_seconds": self._interval,
                "sources": [a.source_name for a in self._adapters],
            },
        )

        try:
            while self._running:
                await self.run_once()
                await asyncio.sleep(self._interval)
        except KeyboardInterrupt:
            logger.info("ingestion_service_stopped", extra={"operation": "ingestion_stop"})
            self._running = False

    async def _fetch_and_publish(self, adapter: SourceAdapterProtocol) -> None:
        """Fetch from one adapter and publish all valid events to Kafka.

        Implements retry logic with exponential backoff for transient
        SourceFetchError. Permanent failures update source status but do
        not propagate.

        Parameters
        ----------
        adapter:
            The source adapter to fetch from.
        """
        source_name = adapter.source_name
        status = self._stats.sources[source_name]
        metrics = self._producer.metrics

        attempt = 0
        while attempt <= self._max_retries:
            try:
                result: FetchResult[Any] = await adapter.fetch()
                status.last_fetch_time = datetime.now(timezone.utc)
                status.last_fetch_success = True

                # Log fetch outcome
                logger.info(
                    "adapter_fetch_complete",
                    extra={
                        "operation": "fetch",
                        "source": source_name,
                        "events": len(result.events),
                        "malformed": len(result.malformed),
                        "total_records": result.total_records,
                    },
                )

                # Track malformed records
                if result.has_malformed:
                    status.malformed_count += len(result.malformed)
                    self._stats.total_malformed += len(result.malformed)
                    for _ in range(len(result.malformed)):
                        metrics.increment(KafkaMetric.INVALID)
                    logger.warning(
                        "adapter_malformed_records",
                        extra={
                            "operation": "fetch",
                            "source": source_name,
                            "count": len(result.malformed),
                        },
                    )

                # Publish valid events
                published = 0
                for event in result.events:
                    receipt = await self._publish_event(event, source_name)
                    if receipt is not None:
                        published += 1

                status.events_published += published
                self._stats.total_events_published += published
                for _ in range(published):
                    metrics.increment(KafkaMetric.PRODUCED)

                logger.info(
                    "adapter_publish_complete",
                    extra={
                        "operation": "publish",
                        "source": source_name,
                        "published": published,
                    },
                )

                # Success — exit retry loop
                break

            except SourceFetchError as exc:
                attempt += 1
                status.last_fetch_success = False
                error_msg = f"Attempt {attempt}/{self._max_retries}: {exc}"
                status.errors.append(error_msg)
                self._stats.total_errors += 1
                metrics.increment(KafkaMetric.PRODUCER_ERRORS)

                logger.error(
                    "adapter_fetch_error",
                    extra={
                        "operation": "fetch",
                        "source": source_name,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )

                if attempt <= self._max_retries:
                    # Exponential backoff: 1s, 2s, 4s, ...
                    backoff = 2 ** (attempt - 1)
                    logger.info(
                        "adapter_retry_scheduled",
                        extra={
                            "operation": "retry",
                            "source": source_name,
                            "backoff_seconds": backoff,
                            "attempt": attempt,
                        },
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "adapter_fetch_exhausted",
                        extra={
                            "operation": "fetch",
                            "source": source_name,
                            "max_retries": self._max_retries,
                        },
                    )

            except Exception as exc:
                # Unexpected error — log and stop retries for this cycle
                status.last_fetch_success = False
                error_msg = f"Unexpected error: {exc}"
                status.errors.append(error_msg)
                self._stats.total_errors += 1
                metrics.increment(KafkaMetric.PRODUCER_ERRORS)

                logger.exception(
                    "adapter_unexpected_error",
                    extra={
                        "operation": "fetch",
                        "source": source_name,
                    },
                )
                break

    async def _publish_event(
        self, event: ProductObservationEvent, source_name: str
    ) -> DeliveryReceipt | None:
        """Publish a single event to Kafka with error handling.

        Parameters
        ----------
        event:
            Canonical product observation event to publish.
        source_name:
            Source identifier for diagnostic context.

        Returns
        -------
        DeliveryReceipt | None
            Receipt on success, None on serialization/delivery failure.
        """
        with tracer.start_as_current_span("ingestion.publish") as span:
            span.set_attributes(
                safe_attributes(
                    {
                        "source": source_name,
                        "event_id": event.event_id,
                    }
                )
            )
            try:
                carrier: dict[str, bytes] = {}
                inject_trace_context(carrier)
                kafka_headers = [(k, v) for k, v in carrier.items()] or None

                receipt = self._producer.publish(event, headers=kafka_headers)
                trace_id = get_current_trace_id()
                logger.debug(
                    "event_published",
                    extra={
                        "operation": "publish",
                        "source": source_name,
                        "event_id": event.event_id,
                        "partition": receipt.partition,
                        "offset": receipt.offset,
                        "trace_id": trace_id,
                    },
                )
                return receipt

            except EventSerializationError as exc:
                span.record_exception(exc)
                logger.error(
                    "event_serialization_failed",
                    extra={
                        "operation": "serialize",
                        "source": source_name,
                        "event_id": event.event_id,
                        "error": str(exc),
                    },
                )
                return None

            except PublishError as exc:
                span.record_exception(exc)
                logger.error(
                    "event_publish_failed",
                    extra={
                        "operation": "publish",
                        "source": source_name,
                        "event_id": event.event_id,
                        "error": str(exc),
                    },
                )
                return None

    def stop(self) -> None:
        """Signal the continuous runner to stop after the current cycle."""
        self._running = False
        logger.info("ingestion_stop_signaled", extra={"operation": "ingestion_stop"})
