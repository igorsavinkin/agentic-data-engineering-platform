# Data Engineering Glossary — памятка по проекту

Этот файл дополняет `APPLICATION_COMPONENTS-RU.md`: основной документ отвечает **«что делает каждый компонент?»**, а эта памятка — **«что означают термины и как они связаны?»**.

## Карта проекта

```text
External API
  ↓
Ingestion ── Producer
  ↓
Kafka: products.raw.v1
  ├→ Raw Writer → Bronze → Parquet → MinIO
  ↓
Processor ── Consumer + Producer
  ↓
Kafka: products.validated.v1
  ↓
Lake Writer ── Consumer / stream-to-lake sink
  ↓
Silver → Parquet → MinIO
  ↓
Warehouse Loader
  ↓
PostgreSQL ── Warehouse / Serving Layer
  ├→ FastAPI
  ├→ Airflow analytical transformations
  └→ LangGraph Agent
```

## Главное различие

```text
Bronze / Silver / Gold → КАКОЙ УРОВЕНЬ данных
Parquet                → В КАКОМ ФОРМАТЕ хранятся файлы
MinIO / S3             → ГДЕ файлы хранятся
Kafka                  → КАК события передаются
PostgreSQL             → ГДЕ структурированные данные доступны через SQL
Airflow                → КАК оркестрируются jobs
```

## Data Pipeline

**Data Pipeline** — весь путь данных от источника до использования:

```text
External API → Ingestion → Kafka → Processor → Lake Writer
→ Silver → Warehouse Loader → PostgreSQL → FastAPI/Airflow/Agent
```

Pipeline — не один сервис, а цепочка компонентов.

## Data Lake

**Data Lake** — хранилище больших объёмов данных, обычно в виде файлов/objects. В локальной архитектуре object storage для Data Lake — MinIO.

```text
MinIO
├── bronze/
├── silver/
└── gold/
```

Исторические данные можно хранить долго и при необходимости перерабатывать заново.

## Bronze

**Bronze** — логический слой данных, максимально близких к тому, что вошло в платформу.

```text
Ingestion → products.raw.v1 → Raw Writer → Bronze
```

Коротко: **Bronze = what arrived.**

Если позже найдена ошибка в обработке, сохранённый Bronze позволяет повторно обработать историю без повторного получения данных из источника.

## Silver

**Silver** — обработанные/валидированные данные, пригодные для downstream processing.

```text
products.raw.v1
  ↓
Processor
  ↓
products.validated.v1
  ↓
Lake Writer
  ↓
Silver
```

Коротко: **Silver = cleaned/validated data.**

В проекте Warehouse Loader читает Silver Parquet.

## Gold

**Gold** — производные данные, подготовленные для аналитики или конкретного use case.

В текущей реализации Gold не является обязательным Parquet-шагом перед Warehouse Loader:

```text
Silver / MinIO
  ↓
Warehouse Loader
  ↓
PostgreSQL: product_observations
  ↓
Airflow analytical transformations
  ↓
PostgreSQL analytical / Gold tables
```

Например: `daily_metrics`, quality/health analytical results.

## MinIO

**MinIO** — S3-compatible object storage.

```text
Local: MinIO ≈ Cloud: Amazon S3
```

Он хранит objects/files. Например:

```text
silver/
  source=fake_store/
    year=2026/month=09/day=24/
      observations.parquet
```

Не путать:

```text
MinIO   = storage
Silver  = data layer
Parquet = file format
```

## Parquet

**Apache Parquet** — бинарный columnar file format для табличных данных.

Логически:

```text
external_id | name     | price | currency
1           | Backpack | 109   | USD
2           | T-Shirt  | 22    | USD
```

В отличие от обычного CSV, Parquet организован для эффективного column-oriented чтения и хорошо подходит для Data Lake и аналитики.

## Object Storage

Object storage хранит данные как objects, обычно через bucket/key:

```text
bucket: silver
key: source=fake_store/year=2026/month=09/day=24/file.parquet
```

Примеры: **MinIO**, **Amazon S3**.

## Event

**Event** — сообщение о произошедшем факте. Например, product observation:

```json
{
  "event_id": "fake_store:1:...",
  "event_type": "product.observation",
  "source": "fake_store",
  "payload": {
    "external_id": "1",
    "price": "109.95",
    "currency": "USD"
  }
}
```

## Event Schema / Contract

Schema определяет ожидаемую структуру event: например `event_id`, `event_type`, `schema_version`, `source`, `produced_at`, `payload`.

Контракт нужен, чтобы Producer и Consumer одинаково понимали сообщение.

## Kafka

Kafka — event-streaming backbone между сервисами.

```text
Ingestion → Kafka → Processor
```

Ingestion не обязан напрямую вызывать Processor.

## Kafka Topic

**Topic** — именованный поток Kafka events.

В проекте:

```text
products.raw.v1
products.validated.v1
products.invalid.v1
pipeline.events.v1
data-quality.events.v1
```

Topic — не PostgreSQL table и не Parquet file.

## Producer

**Producer** публикует events:

```text
Ingestion → products.raw.v1
```

Processor одновременно может быть Consumer и Producer:

```text
products.raw.v1 → Processor → products.validated.v1
```

## Consumer

**Consumer** читает Kafka events.

```text
products.validated.v1 → Lake Writer
```

Важно: Warehouse Loader — **не Kafka consumer**. Он работает:

```text
Silver Parquet → Warehouse Loader → PostgreSQL
```

## Consumer Group

Kafka Consumer Group позволяет нескольким consumers совместно обрабатывать partitions topic.

```text
partition 0 → consumer A
partition 1 → consumer B
partition 2 → consumer C
```

## Offset

**Offset** — позиция сообщения внутри Kafka partition.

```text
offset 100 → event A
offset 101 → event B
offset 102 → event C
```

Offsets помогают отслеживать прогресс consumer.

## ACK — Acknowledgement

**ACK** = acknowledgement = подтверждение операции.

```text
Producer ──event──→ Kafka
Producer ←──ACK──── Kafka
```

ACK — не новое business event. Это подтверждение записи согласно конфигурации producer/broker.

## Synchronous vs Asynchronous

Synchronous:

```text
send event 1 → wait ACK → send event 2 → wait ACK
```

Asynchronous:

```text
send 1 ─┐
send 2 ─┼→ Kafka
send 3 ─┘
         ← ACKs arrive later
```

Это критично для performance testing: synchronous ожидание может ограничить сам load generator.

## Batch

**Batch** — группа данных, обрабатываемая вместе:

```text
event + event + event + event → batch → processing/write
```

Batching уменьшает overhead по сравнению с отдельной дорогой операцией на каждый event.

## Raw Writer

Raw Writer сохраняет raw Kafka events в Bronze:

```text
products.raw.v1 → Raw Writer → Bronze
```

## Processor

Processor выполняет processing/validation/deduplication:

```text
products.raw.v1 → Processor → products.validated.v1
```

Это граница между raw и validated data.

## Lake Writer

Lake Writer — **Kafka consumer + stream-to-lake sink**:

```text
products.validated.v1 → Lake Writer → Parquet → MinIO/Silver
```

Его ответственность — превратить validated event stream в persistent Data Lake files.

## Warehouse

Data Warehouse — структурированное хранилище для SQL queries, analytics и serving. В проекте эту роль выполняет PostgreSQL.

```text
sources
products
source_products
product_observations
analytical tables
```

## Warehouse Loader

Warehouse Loader переносит данные:

```text
Silver Parquet → Warehouse Loader → PostgreSQL
```

Это batch Parquet→PostgreSQL loader, а не Kafka consumer.

## Serving Layer

Serving Layer предоставляет данные приложениям:

```text
PostgreSQL → FastAPI → HTTP client
```

В проекте уже проверены product list/detail/history и health/readiness API paths.

## ETL / ELT

ETL:

```text
Extract → Transform → Load
```

ELT:

```text
Extract → Load → Transform
```

Проект содержит streaming ingestion, validation, Data Lake, batch loading и downstream transformations, поэтому полезнее описывать фактический flow, чем насильно сводить всю архитектуру к одной аббревиатуре.

## Orchestration

**Orchestration** — управление выполнением и зависимостями data jobs. В проекте эту роль выполняет Airflow.

```text
PostgreSQL product_observations
  ↓
Airflow: build_daily_metrics
  ↓
PostgreSQL daily_metrics
```

Airflow также используется для health/data-quality jobs и Parquet compaction.

## At-least-once delivery

At-least-once означает, что event может быть доставлен повторно. Система предпочитает возможный replay риску silent data loss.

Поэтому downstream должен безопасно обрабатывать duplicates.

## Idempotency

Операция idempotent, если повторное выполнение не создаёт нежелательного дополнительного эффекта:

```text
process X
process X again
→ logically safe result
```

Это особенно важно при replay/recovery.

## Deduplication

Deduplication обнаруживает/обрабатывает повторы:

```text
at-least-once → possible replay → deduplication/idempotency → safe processing
```

Deduplication и idempotency связаны, но не идентичны.

## DLQ — Dead Letter Queue

DLQ хранит события, которые не удалось нормально обработать:

```text
malformed event
  ↓
failure
  ↓
products.invalid.v1
```

Diagnostic context может включать `error_type`, raw value, topic, partition, offset и consumer group. Это помогает избежать silent data loss и расследовать ошибку.

## Retry

Retry — повторная попытка операции. Retry полезен для transient failures, но бессмысленен бесконечно для заведомо malformed data. Поэтому retries обычно сочетаются с backoff, limits и DLQ/recovery strategy.

## Load-testing Harness

**Harness** = тестовый стенд/обвязка.

Load-testing harness:

```text
generate controlled load
  ↓
send it to System Under Test
  ↓
measure results
```

Harness **не является самим pipeline**.

```text
Load Generator / Harness → System Under Test
```

## Target Rate vs Actual Rate

Настройка:

```text
target = 100 events/sec
```

не доказывает, что generator реально отправил 100/sec.

В TASK-109:

```text
Target:             100 events/sec
Actual throughput:   18.86 events/sec
Produced:          1,132
Duration:             60 sec
Errors:                0
Mean latency:       52.8 ms
```

Поэтому этот запуск выявил ограничение synchronous single-worker generator; он ещё не доказал производительность pipeline при фактических 100 events/sec.

## Throughput

**Throughput** отвечает: **сколько?**

```text
1132 / 60 ≈ 18.86 events/sec
```

## Latency

**Latency** отвечает: **как долго?**

```text
send → ... → ACK
       52.8 ms
```

Не путать:

```text
throughput = events/sec
latency    = time per operation
```

## p50 / p95 / p99

Percentiles описывают распределение latency.

- **p50** — медиана;
- **p95** — примерно 95% измерений не превышают значение;
- **p99** — примерно 99% измерений не превышают значение.

p99 помогает увидеть медленный «хвост», который среднее может скрывать.

## Consumer Lag

Consumer lag показывает, насколько Kafka consumer отстал:

```text
Producer latest offset: 10000
Consumer offset:         8500
Lag:                     1500
```

Растущий lag может означать, что downstream обрабатывает события медленнее, чем они поступают.

## Bottleneck

**Bottleneck** — компонент, ограничивающий производительность рассматриваемой системы.

В TASK-109:

```text
target 100/sec
  ↓
synchronous single-worker harness
  ↓
actual ~18.86/sec
  ↓
pipeline
```

Поэтому нельзя автоматически объявлять pipeline bottleneck: сначала нужно обеспечить требуемую фактическую нагрузку.

## Benchmark

Benchmark — воспроизводимое измерение производительности при известных условиях.

Нужно фиксировать:

```text
environment
configuration
target load
actual load
duration
throughput
latency
errors
limitations
```

Главное правило: **не придумывать benchmark numbers — записывать реально измеренное.**

## System Under Test (SUT)

SUT — система, которую тестируют:

```text
Harness → System Under Test
```

Если bottleneck в harness, SUT ещё не получил запрошенную нагрузку.

## Observability

Observability помогает понимать состояние системы через:

```text
metrics
logs
traces
```

Metrics отвечают «сколько/как меняется», logs помогают понять конкретное событие/ошибку, traces показывают путь и время операции через компоненты.

## Source of Truth

Source of Truth — авторитетный источник конкретной информации. Для архитектуры документация должна соответствовать реальной реализации.

Например, нельзя писать:

```text
Kafka → Warehouse Loader
```

если фактический flow:

```text
Silver Parquet → Warehouse Loader → PostgreSQL
```

## Что с чем не путать

| Термин | Что означает |
|---|---|
| Bronze / Silver / Gold | логический уровень данных |
| Parquet | формат файла |
| MinIO / S3 | object storage |
| Kafka | event-streaming backbone |
| Topic | именованный поток Kafka events |
| Producer | пишет events |
| Consumer | читает events |
| ACK | подтверждение операции |
| Offset | позиция сообщения в partition |
| Batch | группа данных для совместной обработки |
| PostgreSQL | SQL warehouse/serving storage |
| Airflow | orchestration |
| FastAPI | API/serving interface |
| DLQ | хранилище проблемных сообщений |
| Throughput | сколько операций за время |
| Latency | сколько времени занимает операция |
| Consumer Lag | насколько consumer отстал |
| Harness | чем создаём/измеряем тестовую нагрузку |
| Pipeline / SUT | что тестируем |
| Idempotency | безопасное повторное выполнение |
| Deduplication | обнаружение/обработка повторов |

## Две схемы для интервью

### Data Engineering

```text
Bronze / Silver / Gold → WHAT LEVEL of data
Parquet                → WHAT FILE FORMAT
MinIO / S3             → WHERE files are stored
Kafka                  → HOW events move
PostgreSQL             → HOW structured data is queried/served
Airflow                → HOW jobs are orchestrated
```

### Performance Engineering

```text
Harness
  │ target load
  ▼
Producer
  │ actual load
  ▼
System Under Test
  ├→ throughput → HOW MUCH?
  ├→ latency    → HOW LONG?
  ├→ errors     → WHAT FAILED?
  └→ lag        → IS DOWNSTREAM FALLING BEHIND?
```

Перед выводом о производительности всегда проверить:

> **Действительно ли load generator создал ту нагрузку, которую мы собирались тестировать?**
