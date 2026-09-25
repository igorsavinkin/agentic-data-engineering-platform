# API Latency Measurement

**TASK-114** — Systematic API latency measurement during load tests.

## Overview

The API latency probe measures HTTP response times for key FastAPI endpoints
while the pipeline is under load.  It runs as a background monitor thread
inside the load-test harness, sending periodic GET requests to configured
endpoints and recording per-endpoint latency distributions.

## Architecture

```
LoadTestRunner
    │
    ├── producer workers ──► Kafka
    │
    ├── PG latency monitor ──► processing_latency report
    │
    └── API latency monitor ──► api_latency report
            │
            ├── GET /api/v1/health
            ├── GET /api/v1/products
            ├── GET /api/v1/analytics/price-changes
            └── GET /api/v1/quality/summary
```

The probe uses `urllib.request` to avoid adding external HTTP dependencies.
Each probe cycle hits every configured endpoint once and records the
round-trip latency measured with `time.perf_counter()`.

## Components

| Module | Role |
|---|---|
| `libs/load_test/api_latency_collector.py` | Thread-safe collector storing per-endpoint latency samples and computing percentile distributions |
| `libs/load_test/api_latency_probe.py` | Factory that creates an HTTP probe function for the configured endpoints |
| `libs/load_test/runner.py` | Runner integration via `_start_api_latency_monitor` background thread |
| `libs/load_test/config.py` | `api_base_url`, `api_endpoints`, `api_latency_poll_interval_sec`, `api_latency_timeout_sec` settings |
| `scripts/run_load_test.py` | CLI flags `--api-url`, `--api-endpoints`, `--api-latency-interval` |

## Configuration

### CLI

```bash
python scripts/run_load_test.py \
    --rate 100 --duration 30 \
    --api-url http://localhost:8000 \
    --api-endpoints /api/v1/health /api/v1/products /api/v1/analytics/price-changes \
    --api-latency-interval 5
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_API_BASE_URL` | `""` (disabled) | Base URL of the API service |
| `APP_API_ENDPOINTS` | `/api/v1/health`, `/api/v1/products`, `/api/v1/analytics/price-changes`, `/api/v1/quality/summary` | Endpoint paths to probe |
| `APP_API_LATENCY_POLL_INTERVAL_SEC` | `5.0` | Seconds between probe cycles |
| `APP_API_LATENCY_TIMEOUT_SEC` | `10.0` | HTTP request timeout in seconds |

## Report Format

The API latency section appears in the JSON report under `"api_latency"`:

```json
{
  "api_latency": {
    "total_samples": 24,
    "endpoint_count": 4,
    "overall_latency_ms": {
      "min": 2.1,
      "p50": 8.5,
      "p95": 45.2,
      "p99": 120.0,
      "max": 250.3,
      "mean": 12.4
    },
    "endpoints": {
      "/api/v1/analytics/price-changes": {
        "sample_count": 6,
        "latency_ms": { "min": 15.0, "p50": 35.0, "p95": 80.0, "p99": 120.0, "max": 150.0, "mean": 42.0 },
        "status_codes": { "200": 6 }
      },
      "/api/v1/health": {
        "sample_count": 6,
        "latency_ms": { "min": 1.0, "p50": 3.0, "p95": 8.0, "p99": 12.0, "max": 15.0, "mean": 4.5 },
        "status_codes": { "200": 6 }
      }
    }
  }
}
```

Each endpoint reports:
- `sample_count` — number of probe requests
- `latency_ms` — percentile distribution (min, p50, p95, p99, max, mean)
- `status_codes` — count of each HTTP status code observed

## Identifying Slow Queries

Compare percentile distributions across endpoints to identify which
endpoints degrade under load:

- **p99 >> p50** indicates high variance; the endpoint has occasional slow responses
- **Analytics endpoints** (`/analytics/price-changes`) typically show higher latency than health checks due to complex SQL queries
- **Status code distribution** reveals error rates under stress (5xx responses)

## Limitations

- The probe measures client-side latency including network overhead, not server-side processing time
- The probe uses `urllib.request` (synchronous); probe cycles are sequential per endpoint
- The probe does not authenticate; it only measures unauthenticated endpoints
- Probe requests add minimal load to the API; they are not a substitute for dedicated load testing tools
