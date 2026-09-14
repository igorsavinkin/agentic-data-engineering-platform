"""Ingestion service: wires source adapters to Kafka (TASK-037).

This service orchestrates the fetch-publish loop for all configured source
adapters, publishing canonical ProductObservationEvent instances to the raw
Kafka topic for downstream processing.
"""

from services.ingestion.runner import IngestionRunner

__all__ = ["IngestionRunner"]
