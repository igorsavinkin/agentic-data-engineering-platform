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
| `source_records_collected_total` | Counter | SourceMetrics |
| `source_records_emitted_total` | Counter | SourceMetrics |
| `source_zero_record_fetches_total` | Counter | SourceMetrics |
| `source_pages_fetched_total` | Counter | SourceMetrics |
| `source_retry_attempts_total` | Counter | SourceMetrics |
| `source_malformed_records_total` | Counter | SourceMetrics |
| `source_partial_failures_total` | Counter | SourceMetrics |
| `processor_events_duplicate_total` | Counter | ProcessorMetrics |
| `processor_events_failed_total` | Counter | ProcessorMetrics |
| `kafka_consumer_lag` | Gauge | KafkaMetrics |

All metrics carry a `service` label. Source metrics also carry a `source` label.

### Implementation

- `libs/observability/prometheus_exporter.py` — bridges snapshot-based metrics to Prometheus
- `libs/observability/metrics_http_server.py` — HTTP server for background services
- `services/api/routes/v1/metrics.py` — FastAPI `/metrics` endpoint

## Structured Logging (TASK-089)

All platform services use structured JSON logging for machine-readable, searchable log output.

### Architecture

- **Centralized configuration**: `libs/observability/logging_config.py` provides `setup_logging()` for consistent log format across services
- **JSON format**: Every log record is a JSON object with standardized fields
- **Correlation IDs**: Optional request correlation via `set_correlation_id()` for tracing requests across services

### Log Format

Every log entry includes:

```json
{
  "timestamp": "2026-09-19T21:30:45.123456+00:00",
  "level": "INFO",
  "logger": "services.processor.__main__",
  "message": "processor_batch_complete",
  "service": "processor",
  "environment": "dev",
  "valid": 42,
  "invalid": 3,
  "duplicates": 1
}
```

**Standard fields:**
- `timestamp` — ISO 8601 UTC timestamp
- `level` — Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logger` — Logger name (module path)
- `message` — Log message
- `service` — Service name (processor, raw-writer, lake-writer, ingestion, warehouse-loader)
- `environment` — Deployment environment (dev, test, prod)
- `correlation_id` — (optional) Request correlation ID for tracing

**Extra fields:** Any fields passed via `logger.info("msg", extra={...})` are included in the JSON output. Non-JSON-serializable values are converted to strings.

### Usage

Services initialize logging at startup:

```python
from libs.observability.logging_config import setup_logging

setup_logging(service_name="processor")
```

Set correlation ID for request tracing:

```python
from libs.observability.logging_config import set_correlation_id

set_correlation_id("req-123-abc")
logger.info("processing_request", extra={"event_id": "evt-456"})
```

Clear correlation ID:

```python
set_correlation_id(None)
```

### Implementation

- `libs/observability/logging_config.py` — StructuredFormatter, setup_logging(), correlation ID management
- All services updated to use `setup_logging()` instead of `logging.basicConfig()`

### Exception Handling

Exceptions are automatically included in log output with full stack traces:

```python
try:
    risky_operation()
except Exception:
    logger.exception("operation_failed")
```

The `exception` field contains the formatted traceback.

## Distributed Tracing (TASK-091)

Distributed tracing propagates W3C Trace Context across service and Kafka boundaries, enabling end-to-end request tracking through the platform pipeline.

### Architecture

- **Trace context propagation**: `libs/observability/otel_config.py` provides `inject_trace_context()` / `extract_trace_context()` for W3C Trace Context via Kafka headers
- **Service spans**: Each service creates spans at processing boundaries (publish, consume, HTTP request)
- **Kafka headers**: Trace context is carried as Kafka message headers (`traceparent`, `tracestate`)
- **Jaeger**: Local trace viewing at http://localhost:16686
- **OTel Collector**: Forwards traces from services to Jaeger via OTLP gRPC

### Trace propagation flow

```
ingestion (producer)
  → creates span "ingestion.publish"
  → injects traceparent into Kafka headers
  → publishes to products.raw.v1

processor (consumer)
  → extracts traceparent from Kafka headers
  → creates child span "processor.process_batch"
  → sets correlation_id = trace_id for log-trace correlation

raw-writer (consumer)
  → extracts traceparent from Kafka headers
  → creates child span "raw-writer.process_message"

lake-writer (consumer)
  → extracts traceparent from Kafka headers
  → creates child span "lake-writer.process_message"

api (HTTP)
  → creates span per HTTP request "api.<METHOD> <path>"
  → returns X-Trace-Id response header
```

### Representative trace

A single product observation flowing through the platform produces a trace like:

```
Trace: abc123def456...
├── ingestion.publish (source=bestbuy, event_id=evt-001)
│   └── Kafka → products.raw.v1 (traceparent header)
├── processor.process_batch (topic=products.raw.v1, message_count=1)
│   └── Kafka → products.validated.v1
├── raw-writer.process_message (topic=products.raw.v1, partition=0, offset=42)
│   └── MinIO Bronze write
└── lake-writer.process_message (topic=products.validated.v1, partition=0, offset=15)
    └── MinIO Silver write
```

### Log-trace correlation

Processor, raw-writer, and lake-writer set the structured log `correlation_id` field to the current trace ID. This allows correlating log entries with traces:

```json
{
  "timestamp": "2026-09-19T22:00:00Z",
  "level": "INFO",
  "message": "processor_batch_complete",
  "service": "processor",
  "correlation_id": "abc123def456...",
  "trace_id": "abc123def456...",
  "valid": 1,
  "invalid": 0
}
```

### Local development

Start Jaeger and the OTel collector:

```bash
docker compose up -d jaeger otel-collector
```

Enable tracing in a service:

```bash
APP_OTEL_ENABLED=true APP_OTEL_EXPORTER_ENDPOINT=http://localhost:4317 \
  python -m services.ingestion
```

Access the Jaeger UI at http://localhost:16686 to view traces.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_OTEL_ENABLED` | `false` | Enable trace export |
| `APP_OTEL_EXPORTER_ENDPOINT` | `None` | OTLP gRPC endpoint (e.g., `http://localhost:4317`) |
| `JAEGER_UI_PORT` | `16686` | Jaeger UI host port |

### Implementation

- `libs/observability/otel_config.py` — `inject_trace_context()`, `extract_trace_context()`, `get_current_trace_id()`
- `libs/common/kafka_consumer.py` — `ConsumerMessage.headers` field for header extraction
- `libs/common/kafka_producer.py` — `publish(headers=...)` for header injection
- `services/ingestion/runner.py` — span + header injection at publish boundary
- `services/processor/__main__.py` — header extraction + child span at consume boundary
- `services/raw-writer/consumer.py` — header extraction + child span
- `services/lake-writer/consumer.py` — header extraction + child span
- `services/api/app.py` — HTTP request tracing middleware with `X-Trace-Id` response header
- `monitoring/otel-collector-config.yaml` — OTLP → Jaeger export pipeline
- `monitoring/grafana/datasources/prometheus.yml` — Jaeger datasource provisioning

## OpenTelemetry (TASK-090)

OpenTelemetry provides the foundation for distributed tracing across platform services.

### Architecture

- **SDK**: `libs/observability/otel_config.py` — shared configuration with consistent resource identity
- **Resource attributes**: `service.name`, `service.version`, `deployment.environment`
- **Exporters**: OTLP gRPC (default), Console (debug), or None
- **Safe attributes**: bounded string truncation (256 chars), sensitive key filtering, max 128 attributes
- **Collector**: OpenTelemetry Collector receives OTLP and exports to configured backends

### Configuration

Services initialize OpenTelemetry via `setup_opentelemetry(OTelSettings(...))`. Configuration is read from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_OTEL_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `APP_OTEL_EXPORTER_ENDPOINT` | `None` | OTLP exporter endpoint (e.g., `http://localhost:4317`) |
| `APP_OTEL_EXPORTER_TYPE` | `otlp` | Exporter type: `otlp`, `console`, or `none` |
| `APP_SERVICE_VERSION` | `0.1.0` | Service version for resource identity |

### Local development

Start the OTLP collector alongside the rest of the stack:

```bash
docker compose up -d otel-collector
```

The collector listens on gRPC port 4317 and HTTP port 4318. Default configuration logs traces to stdout for debugging.

Enable OTel in a service:

```bash
APP_OTEL_ENABLED=true APP_OTEL_EXPORTER_ENDPOINT=http://localhost:4317 python -m services.processor
```

### Kubernetes

Enable the OTel collector in Helm values:

```bash
helm upgrade --install ai-data-platform helm/ai-data-platform \
  --set opentelemetry.enabled=true \
  --set opentelemetry.config.enabled=true
```

Services will automatically export traces to `http://otel-collector:4317` when `APP_OTEL_ENABLED=true`.

### Implementation

- `libs/observability/otel_config.py` — OTel setup, resource identity, safe attributes
- `monitoring/otel-collector-config.yaml` — Collector configuration (Compose)
- `helm/ai-data-platform/values.yaml` — `opentelemetry:` section (Helm)

### Service integration

All platform services initialize OpenTelemetry on startup:

- `services/ingestion/__main__.py`
- `services/processor/__main__.py`
- `services/raw-writer/consumer.py`
- `services/lake-writer/consumer.py`
- `services/warehouse-loader/runner.py`
- `services/api/app.py`

Each service calls `setup_opentelemetry(OTelSettings(service_name="<service>"))` after `setup_logging()`.

## Grafana (TASK-085)

Grafana provides visualization of platform metrics collected by Prometheus.

### Architecture

- **Datasource**: Prometheus at `http://prometheus:9090` (auto-provisioned)
- **Dashboards**: loaded from `monitoring/grafana/dashboards/` (Compose) or `grafana-dashboards` ConfigMap (Helm)
- **Credentials**: externalized via environment variables (`GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`)

### Local development

Start Grafana alongside the rest of the stack:

```bash
docker compose up -d grafana
```

Access the Grafana UI at http://localhost:3000 (default credentials: `admin` / `admin`).

Override credentials via environment variables:

```bash
GRAFANA_ADMIN_USER=myuser GRAFANA_ADMIN_PASSWORD=mysecret docker compose up -d grafana
```

### Kubernetes

Enable Grafana in the Helm values:

```bash
helm upgrade --install ai-data-platform helm/ai-data-platform \
  --set grafana.enabled=true
```

Admin credentials are stored in a Kubernetes Secret (`grafana-credentials`). Override with `--set grafana.adminUser=<base64>` and `--set grafana.adminPassword=<base64>`.

Port-forward for local access:

```bash
kubectl port-forward svc/grafana 3000:3000 -n ai-data-platform
```

### Provisioning

Both Docker Compose and Helm use file-based provisioning:

- **Datasources** — `monitoring/grafana/datasources/prometheus.yml` (Compose) or `grafana-provisioning` ConfigMap (Helm)
- **Dashboard provider** — `monitoring/grafana/dashboards/dashboard.yml` (Compose) or `grafana-provisioning` ConfigMap (Helm)
- **Dashboard JSON** — `monitoring/grafana/dashboards/*.json` (Compose) or `grafana-dashboards` ConfigMap (Helm)

## Platform Dashboard (TASK-086)

The `platform-overview.json` dashboard provides a single-pane view of platform health.

### Panels

| Panel | Type | Key metrics |
|-------|------|-------------|
| Service Availability | stat | `up` |
| Service Event Rates | timeseries | `kafka_events_processed_total`, `kafka_events_consumed_total` |
| Error Rates | timeseries | `kafka_consumer_errors_total`, `kafka_processing_errors_total`, `kafka_dead_letter_events_total`, `events_invalid_total` |
| Processor Latency (avg) | timeseries | `processor_processing_seconds` (summary: sum/count) |
| Processor Throughput | stat | `processor_events_valid_total`, `processor_events_invalid_total` |
| API Request Rate | timeseries | `api_requests_total` |
| API Latency (avg) | timeseries | `api_request_duration_seconds` (summary: sum/count) |
| Source Freshness | timeseries | `source_freshness_age_seconds` |
| Source Fetch Success Rate | gauge | `source_fetch_success_total`, `source_fetch_attempts_total` |
| Ingestion Events | stat | `ingestion_events_total`, `ingestion_errors_total` |
| Source Fetch Latency (avg) | stat | `source_fetch_latency_seconds` (summary: sum/count) |

### Adding dashboards

1. Create a JSON file in `monitoring/grafana/dashboards/` (for Compose)
2. Copy the same file to `helm/ai-data-platform/dashboards/` (for Helm)
3. The dashboard provider auto-detects new JSON files on the next 30-second polling cycle

## Data Quality Dashboard (TASK-087)

The `data-quality.json` dashboard focuses on data-quality signals: validation outcomes, freshness, deduplication, failure rates, and source collection health.

### Panels

| Panel | Type | Key metrics |
|-------|------|-------------|
| Validation Pass Rate | gauge | `processor_events_valid_total`, `processor_events_invalid_total` |
| Source Freshness | timeseries | `source_freshness_age_seconds` |
| Source Fetch Success Rate | gauge | `source_fetch_success_total`, `source_fetch_attempts_total` |
| Invalid Event Rate | timeseries | `processor_events_invalid_total`, `events_invalid_total` |
| Deduplication Rate | timeseries | `processor_events_duplicate_total` |
| Processing Failure Rate | timeseries | `processor_events_failed_total`, `kafka_processing_errors_total` |
| Dead Letter Queue Rate | timeseries | `kafka_dead_letter_events_total` |
| Source Malformed Records | timeseries | `source_malformed_records_total` |
| Source Zero-Record Fetches | timeseries | `source_zero_record_fetches_total` |
| Source Partial Failures & Retries | timeseries | `source_partial_failures_total`, `source_retry_attempts_total` |
| Records Collected vs Emitted | timeseries | `source_records_collected_total`, `source_records_emitted_total` |
| Source Fetch Failure Rate | stat | `source_fetch_failure_total` |

## Kafka & Processing Dashboard (TASK-088)

The `kafka-processing.json` dashboard focuses on Kafka consumer throughput, lag indicators, error rates, and processing latency.

### Panels

| Panel | Type | Key metrics |
|-------|------|-------------|
| Consumer Throughput | timeseries | `kafka_events_consumed_total`, `kafka_events_processed_total` |
| Consumer Lag Indicator | timeseries | `kafka_consumer_lag` |
| Kafka Error Rates | timeseries | `kafka_consumer_errors_total`, `kafka_processing_errors_total` |
| Dead Letter Queue Rate | timeseries | `kafka_dead_letter_events_total` |
| Invalid Event Rate | timeseries | `events_invalid_total` |
| Lag Query Errors | stat | `kafka_lag_errors_total` |
| Processor Throughput | timeseries | `processor_events_processed_total`, `processor_events_valid_total`, `processor_events_invalid_total` |
| Processor Latency (avg) | timeseries | `processor_processing_seconds` (summary: sum/count) |
| Processor Batch Size (avg) | timeseries | `processor_batch_records_total`, `processor_batches_total` |
| Ingestion Rate | timeseries | `ingestion_events_total` |
| Ingestion Errors | stat | `ingestion_errors_total` |
| Processor Pipeline Health | gauge | `processor_events_valid_total` / `processor_events_processed_total` |

### Consumer Lag Metric

The `kafka_consumer_lag` gauge reports per-topic, per-partition consumer lag, sampled periodically by each consumer service (processor, raw-writer, lake-writer). Labels: `service`, `topic`, `partition`.

Lag is sampled every 50 consumer loop iterations via `KafkaConsumer.sample_lag()` and stored in `KafkaMetrics` for Prometheus scraping.

### Backlog Test Procedure

This procedure demonstrates the lag metric responding to a controlled backlog and subsequent recovery.

**Prerequisites**: Platform infrastructure running with Docker Compose (`docker compose up -d kafka prometheus grafana`), Grafana accessible at http://localhost:3000.

**Local development (Python processes):**

1. **Baseline**: Open the "Kafka & Processing" dashboard in Grafana. Verify the "Consumer Lag Indicator" panel shows near-zero lag across all partitions.

2. **Start producer**: Run the ingestion service to produce test events:
   ```bash
   python -m services.ingestion
   ```

3. **Create backlog**: Start the processor, then stop it (Ctrl+C) to allow messages to accumulate on `products.raw.v1`. Alternatively, do not start the processor at all while the ingestion service runs. Wait 2-3 minutes for lag to build.

4. **Observe lag increase**: The "Consumer Lag Indicator" panel should show rising `kafka_consumer_lag` values for the `products.raw.v1` topic. The "Consumer Throughput" panel will show consumption dropping to zero while production continues.

5. **Recover**: Restart the processor:
   ```bash
   python -m services.processor
   ```
   The processor will consume the backlog. Watch the lag panel decrease back toward zero as the processor catches up.

6. **Verify recovery**: Once lag returns to near-zero, confirm the "Consumer Throughput" panel shows consumption rate matching production rate again.

**Kubernetes:**

1. Scale down the processor deployment: `kubectl scale deployment processor --replicas=0 -n ai-data-platform`
2. Observe lag increase in Grafana
3. Scale back up: `kubectl scale deployment processor --replicas=1 -n ai-data-platform`
4. Observe lag decrease back to baseline

**Expected outcome**: Lag increases while processor is stopped, decreases after restart, returns to baseline. This validates the end-to-end lag metric pipeline: `KafkaConsumer.sample_lag()` → `KafkaMetrics.update_lag()` → Prometheus scrape → Grafana panel.
