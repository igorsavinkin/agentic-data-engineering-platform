# E2E Test Report — PostgreSQL → FastAPI

**Date:** 2026-09-24  
**Scope:** PostgreSQL warehouse → FastAPI read API  
**Status:** PASS

## Objective

Verify that FastAPI connects to the PostgreSQL warehouse and exposes real product and observation data through HTTP.

This report covers only:

```text
PostgreSQL → FastAPI → HTTP client
```

The upstream path is documented separately in `E2E-SOURCE-TO-POSTGRESQL-2026-09-24.md`.

## Kubernetes and readiness

The API deployment rolled out successfully. The API pod reached `1/1 Running`, and the ClusterIP service exposed port 8000.

Application logs confirmed successful startup and successful probes:

```text
Application startup complete.
Uvicorn running on http://0.0.0.0:8000
GET /api/v1/health HTTP/1.1 200 OK
GET /api/v1/ready HTTP/1.1 200 OK
```

Health response:

```json
{"status":"healthy","service":"api","version":"0.1.0"}
```

Readiness response:

```json
{"status":"ready","service":"api","version":"0.1.0","database":"connected"}
```

**Result: PASS.**

## PostgreSQL verification

Direct PostgreSQL inspection showed a live, growing warehouse. At one snapshot:

```text
products | min_id | max_id
2499     | 1      | 2499
```

Canonical product `id=1`:

```text
SanDisk SSD PLUS 1TB Internal SSD - SATA III 6 Gb/s
category: electronics
```

Counts continued increasing while the pipeline was running, so later API totals differ from earlier database snapshots.

## Product list

Request:

```bash
curl -s "http://localhost:8000/api/v1/products?page_size=5" | python -m json.tool
```

The API returned five canonical products:

```json
{
  "total": 2553,
  "page": 1,
  "page_size": 5
}
```

First item:

```json
{
  "id": 1,
  "canonical_name": "SanDisk SSD PLUS 1TB Internal SSD - SATA III 6 Gb/s",
  "category": "electronics",
  "latest_name": "SanDisk SSD PLUS 1TB Internal SSD - SATA III 6 Gb/s",
  "latest_price": 109.0,
  "latest_currency": "USD",
  "latest_availability": "in_stock",
  "latest_collected_at": "2026-09-24T06:21:56.099624+00:00"
}
```

**Result: PASS.**

## Product detail

Request:

```bash
curl -s "http://localhost:8000/api/v1/products/1" | python -m json.tool
```

Response included:

```json
{
  "id": 1,
  "canonical_name": "SanDisk SSD PLUS 1TB Internal SSD - SATA III 6 Gb/s",
  "category": "electronics",
  "source_count": 1,
  "latest_price": 109.0,
  "latest_currency": "USD",
  "latest_availability": "in_stock",
  "latest_collected_at": "2026-09-24T06:11:42.404489+00:00",
  "latest_source": "fake_store",
  "latest_url": "https://fakestoreapi.com/products/10"
}
```

**Result: PASS.**

## Product history

Request:

```bash
curl -s "http://localhost:8000/api/v1/products/1/history?page_size=5" | python -m json.tool
```

The response reported:

```json
{"total":2444,"page":1,"page_size":5}
```

Latest tested observation:

```json
{
  "id": 1132422,
  "name": "SanDisk SSD PLUS 1TB Internal SSD - SATA III 6 Gb/s",
  "price": 109.0,
  "currency": "USD",
  "availability": "in_stock",
  "collected_at": "2026-09-24T06:11:42.404489+00:00",
  "source": "fake_store",
  "url": "https://fakestoreapi.com/products/10"
}
```

The next returned observation IDs were `1132421`, `1132420`, `1132419`, and `1132418`.

**Result: PASS.**

## ID semantics

The test clarified two ID domains:

```text
GET /products
    item.id = products.id

GET /products/{product_id}/history
    history item.id = product_observations.id
```

Therefore:

```text
Product ID:     1
Observation ID: 1132422
```

`GET /products/1` is valid, while `/products/1132422` returns `PRODUCT_NOT_FOUND` because the latter is an observation ID.

## Pagination

The endpoint uses `page` and `page_size`. The verified request is:

```text
/api/v1/products?page_size=5
```

An earlier `limit=5` request did not represent the endpoint's pagination contract.

## Verification matrix

| Check | Result |
|---|---|
| API Kubernetes rollout | PASS |
| API pod Ready 1/1 | PASS |
| `/api/v1/health` | PASS |
| `/api/v1/ready` | PASS |
| PostgreSQL connection | PASS |
| Product list | PASS |
| Canonical product detail | PASS |
| Observation history | PASS |
| `fake_store` source traceability | PASS |
| `page_size` pagination | PASS |

## Conclusion

**PostgreSQL → FastAPI E2E: PASS**

The API successfully reads warehouse data from PostgreSQL and exposes canonical products, latest product state, source traceability, and historical observations over HTTP.

Together with `E2E-SOURCE-TO-POSTGRESQL-2026-09-24.md`, the verified happy path is:

```text
Fake Store
    ↓
Ingestion
    ↓
Kafka — products.raw.v1
    ├──→ Raw Writer → Bronze
    ↓
Processor
    ↓
Kafka — products.validated.v1
    ↓
Lake Writer
    ↓
Silver
    ↓
Warehouse Loader
    ↓
PostgreSQL
    ↓
FastAPI
    ↓
HTTP API
```

Next planned validation area: failure engineering/reliability, beginning with TASK-104 (duplicate/replay behavior).
