"""Raw Writer service — Bronze Parquet persistence (TASK-021).

Consumes ``products.raw.v1`` from Kafka and persists raw/minimally transformed
canonical observations as Bronze Parquet in MinIO/S3.  The service is
independently restartable and replayable: at-least-once delivery plus
idempotent processing guarantees no data loss while avoiding duplicate files
through deterministic object keys.

See ``ai/SPECIFICATION.md`` §6.3 and ``docs/raw-writer.md``.
"""
