# monitoring/

Monitoring configuration for the AI Data Platform (Milestone 10).

## Prometheus (TASK-084)

`prometheus.yml` configures Prometheus to scrape metrics from platform services.

### Architecture

- **API service** (`api:8000`): exposes `/api/v1/metrics` via FastAPI
- **Background services** (`*:9100`): expose `/metrics` via a lightweight HTTP server
  - ingestion, processor, raw-writer, lake-writer, warehouse-loader

### Local development

Prometheus runs in Docker Compose. Start it with:

```bash
docker compose up -d prometheus
```

Access the Prometheus UI at http://localhost:9090.

### Metrics exposed

| Metric | Type | Source |
|--------|------|--------|
| `ingestion_events_total` | Counter | KafkaMetrics |
| `ingestion_errors_total` | Counter | KafkaMetrics |
| `kafka_events_consumed_total` | Counter | KafkaMetrics |
| `kafka_events_processed_total` | Counter | KafkaMetrics |
| `events_invalid_total` | Counter | KafkaMetrics |
| `kafka_consumer_errors_total` | Counter | KafkaMetrics |
| `kafka_processing_errors_total` | Counter | KafkaMetrics |
| `kafka_dead_letter_events_total` | Counter | KafkaMetrics |
| `processor_events_processed_total` | Counter | ProcessorMetrics |
| `processor_events_valid_total` | Counter | ProcessorMetrics |
| `processor_events_invalid_total` | Counter | ProcessorMetrics |
| `processor_processing_seconds` | Summary | ProcessorMetrics |
| `source_fetch_attempts_total` | Counter | SourceMetrics |
| `source_fetch_success_total` | Counter | SourceMetrics |
| `source_fetch_failure_total` | Counter | SourceMetrics |
| `source_fetch_latency_seconds` | Summary | SourceMetrics |
| `source_freshness_age_seconds` | Gauge | SourceMetrics |

All metrics carry a `service` label. Source metrics also carry a `source` label.

### Implementation

- `libs/observability/prometheus_exporter.py` — bridges snapshot-based metrics to Prometheus
- `libs/observability/metrics_http_server.py` — HTTP server for background services
- `services/api/routes/v1/metrics.py` — FastAPI `/metrics` endpoint

## Planned

- Grafana dashboards (TASK-085+)
- OpenTelemetry integration (TASK-090+)
