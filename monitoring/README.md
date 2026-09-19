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

All metrics carry a `service` label. Source metrics also carry a `source` label.

### Implementation

- `libs/observability/prometheus_exporter.py` — bridges snapshot-based metrics to Prometheus
- `libs/observability/metrics_http_server.py` — HTTP server for background services
- `services/api/routes/v1/metrics.py` — FastAPI `/metrics` endpoint

## Planned

- OpenTelemetry integration (TASK-090+)

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
| Consumer Lag Indicator | timeseries | consumed rate - processed rate (gap indicator) |
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
