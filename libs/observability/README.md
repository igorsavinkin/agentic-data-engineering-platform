# observability/

Shared metrics, structured-logging, and tracing helpers used across services. See `ai/PROJECT.md` §10 (Observability Principles).

`kafka_metrics.py` provides instance-local Kafka counter snapshots for later
Prometheus collection. See [Kafka metrics](../../docs/kafka-metrics.md) for counter
semantics and the consumer's committed-offset lag API.
