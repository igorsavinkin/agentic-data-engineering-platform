# Пояснения к диаграммам архитектуры

## Как читать контейнерный вид (container-view.dot)

### Что показывает
Полную карту сервисов платформы, хранилищ данных, Kafka-топиков и границ
ответственности. Сплошные линии — реализованные компоненты (M0–M13,
TASK-001–TASK-115), пунктирные — проектное состояние (M14+).

### Порядок чтения
1. **Слева** — 5 внешних источников данных (эллипсы): FakeStore, BestBuy, eBay, Web Retailer, Difficult Retailer
2. **Ingestion** — адаптеры источников, изолирующие специфику API (5 реализованных адаптеров)
3. **Kafka** — 5 топиков: 3 продуктовых (raw, validated, invalid) + 2 операционных
4. **Processor** — валидация, нормализация, дедупликация, Polars-трансформации
5. **Data Lake** — два Parquet-слоя медальона (Bronze/Silver) + Gold как PostgreSQL-аналитические таблицы
6. **Warehouse** — Airflow (4 DAG), Warehouse Loader, PostgreSQL (8 таблиц)
7. **Serving** — FastAPI (M7, реализовано) и LangGraph-агент (M11, реализовано)

### Ключевые архитектурные ограничения, видимые на диаграмме
- Ingestion пишет **только в Kafka**, никогда напрямую в PostgreSQL
- Каждый сервис потребляет из **своей consumer group**
- Raw Writer владеет Bronze, Lake Writer — Silver, Airflow — Gold (аналитические таблицы)
- Агент имеет **только read-only** доступ к PostgreSQL
- DLQ (`products.invalid.v1`) содержит полный диагностический контекст
- Airflow DAGs читают из PostgreSQL и Bronze, пишут в Gold-таблицы

### Условные обозначения
| Форма | Значение |
|-------|----------|
| Прямоугольник | Сервис / контейнер |
| Компонент (двойная скобка) | Kafka-топик |
| Цилиндр | Хранилище данных |
| Эллипс | Внешний источник |
| Сплошная линия | Реализовано (M0–M13) |
| Пунктирная линия | Проектное состояние (M14+) |
| Точечная линия | Observability (метрики/трейсы) |

---

## Как читать поток данных (data-flow.dot)

### Что показывает
Линейное движение данных от внешнего источника до serving-слоя через все
уровни медальон-озера и Airflow-оркестрацию. Горизонтальная ориентация (LR)
подчёркивает последовательность трансформаций.

### Порядок чтения
Слева направо по потоку:

```
Источник → Adapter → Kafka (raw) → Raw Writer → Bronze
                                ↘ Processor → Kafka (validated) → Lake Writer → Silver
                                          ↘ Kafka (invalid/DLQ)

Silver → Warehouse Loader → PostgreSQL (base tables)
                                ↘ Airflow DAGs → Gold (PostgreSQL analytical tables)
Bronze → Airflow compaction → compacted Bronze

PostgreSQL → API / Agent (serving, реализовано M7/M11)
```

### Ключевые семантики на каждом переходе
| Переход | Семантика |
|---------|-----------|
| Source → Adapter | Сбор данных через 5 адаптеров (REST, OAuth, HTML, anti-bot) |
| Adapter → Kafka | Publish с partition key `source:external_id` |
| Kafka → Raw Writer | Консумирование, batch-аккумуляция |
| Raw Writer → Bronze | Parquet с детерминированными ключами (по event_id) |
| Kafka → Processor | Валидация (Pydantic), нормализация, дедупликация |
| Processor → validated | Успешные события после обработки |
| Processor → invalid | Проваленные события + диагностический контекст |
| Kafka (validated) → Lake Writer | Консумирование валидированных событий |
| Lake Writer → Silver | Parquet (нормализованный, дедуплицированный) |
| Silver → Warehouse Loader | Чтение Parquet, batch-загрузка |
| Warehouse Loader → PostgreSQL | Идемпотентный UPSERT по event_id |
| PostgreSQL → Airflow (quality) | 5 проверок: required fields, price, allowed values, duplicates, freshness |
| PostgreSQL → Airflow (metrics) |_daily aggregates: avg_price, unique_products, per-source counts |
| PostgreSQL → Airflow (health) | Source freshness, degradation detection |
| Bronze → Airflow (compaction) | Merge small Parquet files, deterministic keys |
| PostgreSQL → Agent | Read-only SQL через контролируемые инструменты |

### Семантика доставки
- **At-least-once** с идемпотентной обработкой (никогда exactly-once)
- Офсеты коммитятся **только после** успешной обработки
- При сбое/рестарте необработанные записи доставляются повторно
- RetryPolicy: 1-10 попыток, линейный backoff 0-5с
- Только `TransientProcessingError` подвержен ретраю
- Warehouse Loader использует `event_id` для UPSERT идемпотентности
- Airflow DAGs используют `logical_date` для replay-safe идемпотентности

---

## Реализованные компоненты (M0–M13)

### Milestone 0 — Repository Foundation (TASK-001–005)
- Структура репозитория, pyproject.toml, CI base

### Milestone 1 — Event Platform (TASK-006–012)
- Kafka KRaft (single-node), MinIO, topic management (ADR-001)
- Event contracts (ProductObservationEvent), Kafka producer/consumer libs

### Milestone 2 — Processing Pipeline (TASK-013–019)
- Processor service: Pydantic validation, Polars transforms, schema normalization
- Deduplication, DLQ with diagnostic context, error classification

### Milestone 3 — Data Lake (TASK-020–026)
- Bronze layer: Raw Writer service, Parquet with deterministic keys
- Silver layer: Lake Writer service, validated Parquet
- Partition key strategy, Parquet schema definitions

### Milestone 4 — PostgreSQL Warehouse (TASK-027–033)
- PostgreSQL 17, Alembic migrations (001–006), 8 tables
- Warehouse Loader: idempotent Parquet → PostgreSQL
- Strategic indexes, event_id unique constraint

### Milestone 5 — E2E Vertical Slice + Sources (TASK-034–055)
- FakeStore + BestBuy adapters (REST)
- eBay adapter (OAuth, marketplace models, normalizer)
- Web Retailer adapter (HTML scraping, selectolax)
- Difficult Retailer adapter (anti-bot, rate limiting, pagination)
- Analytical queries (CTE, window functions, rolling averages)

### Milestone 6 — Data Quality + Airflow (TASK-056–062)
- Airflow 2.10 deployment (Docker Compose: scheduler + webserver)
- Quality framework: 5 checks, runner, PostgreSQL persistence
- 4 DAGs: ingestion_health, daily_data_quality, parquet_compaction, build_daily_metrics
- Observability libs: health assessment/evaluation, source/processor/Kafka metrics

### Milestone 7 — FastAPI (TASK-063–069)
- `services/api/`, 13+ endpoints (products, analytics, pipelines, quality, agent)
- Health/readiness probes, Prometheus `/metrics` endpoint
- Read-only PostgreSQL access via SQLAlchemy ORM

### Milestone 8 — Kubernetes (TASK-070–079)
- `kubernetes/` manifests: 7 Deployments, 2 StatefulSets, 2 Jobs
- kind local cluster, liveness/readiness probes, ConfigMaps, Secrets

### Milestone 9 — Helm (TASK-080–083)
- `helm/ai-data-platform/` chart with values.yaml, values-local.yaml, values-production.yaml
- All Kubernetes resources templated, conditional monitoring, HPA, Ingress, NetworkPolicy

### Milestone 10 — Observability (TASK-084–091)
- Prometheus (scrape configs, 30+ metrics), Grafana (3 dashboards, 35 panels)
- OpenTelemetry Collector (OTLP gRPC/HTTP), Jaeger backend
- Active span instrumentation in 4 services (ingestion, processor, raw-writer, lake-writer)

### Milestone 11 — LangGraph Agent (TASK-092–100)
- `services/agent/`, 4 read-only tools, deterministic keyword classifier
- Graph routing: classify → execute → compose; read-only SQL enforcement
- Deployed within API service process (not a separate container)

### Milestone 12 — Failure Engineering (TASK-101–107)
- `tests/test_failure_replay.py`, `tests/test_duplicate_replay.py`
- At-least-once semantics verified, crash recovery, duplicate delivery handling
- Recovery documentation

### Milestone 13 — Performance Testing (TASK-108–115)
- `scripts/run_load_test.py`, 3 benchmark reports (100/500/1000 eps targets)
- Producer-side throughput measured; bottleneck documented (synchronous produce-wait loop)
- Linux in-cluster verification: 95.55 eps at 100 target (95.6%)

---

## Evidence-ссылки на код

### Ядро платформы
| Компонент | Путь в репозитории |
|-----------|-------------------|
| Event contract | `libs/event_contracts/product_observation.py` |
| Kafka producer | `libs/common/kafka_producer.py` |
| Kafka consumer | `libs/common/kafka_consumer.py` |
| MinIO storage | `libs/common/minio_storage.py` |
| Config system | `libs/common/config.py` |
| Topic management | `scripts/manage_kafka_topics.py` |
| ADR-001 (топики) | `docs/adr/ADR-001-kafka-topic-configuration.md` |
| Docker Compose | `docker-compose.yml` |

### Сервисы
| Компонент | Путь в репозитории |
|-----------|-------------------|
| Ingestion runner | `services/ingestion/runner.py` |
| Processor pipeline | `services/processor/pipeline.py` |
| Raw Writer consumer | `services/raw-writer/consumer.py` |
| Lake Writer consumer | `services/lake-writer/consumer.py` |
| Bronze writer lib | `libs/raw_writer/bronze_writer.py` |
| Silver writer lib | `libs/lake_writer/silver_writer.py` |

### Source Adapters
| Адаптер | Путь в репозитории |
|---------|-------------------|
| Fake Store | `libs/adapters/fake_store/` |
| Best Buy | `libs/adapters/best_buy/` |
| eBay | `libs/adapters/ebay/` |
| Web Retailer | `libs/adapters/web_retailer/` |
| Difficult Retailer | `libs/adapters/difficult_retailer/` |
| Adapter protocol | `libs/adapters/protocol.py` |

### Warehouse & Analytics
| Компонент | Путь в репозитории |
|-----------|-------------------|
| Schema DDL | `warehouse/schema/init.sql` |
| Schema design | `warehouse/schema/SCHEMA_DESIGN.md` |
| Migrations | `warehouse/migrations/versions/001–006` |
| Batch loader | `warehouse/loader/batch_loader.py` |
| Analytical queries | `warehouse/analytics/queries.py` |

### Airflow DAGs & Libs
| Компонент | Путь в репозитории |
|-----------|-------------------|
| ingestion_health DAG | `airflow/dags/ingestion_health_dag.py` |
| daily_data_quality DAG | `airflow/dags/daily_data_quality_dag.py` |
| parquet_compaction DAG | `airflow/dags/parquet_compaction_dag.py` |
| build_daily_metrics DAG | `airflow/dags/build_daily_metrics_dag.py` |
| Quality framework | `libs/quality/` (checks, runner, persistence, models) |
| Compaction lib | `libs/compaction/compactor.py` |
| Metrics calculator | `libs/metrics/calculator.py` |
| Health evaluation | `libs/observability/health_evaluation.py` |
| Health persistence | `libs/observability/health_persistence.py` |

---

## Проектное состояние (M14+, не реализовано)

| Компонент | Milestone | Описание |
|-----------|-----------|----------|
| Terraform + AWS | M14 (TASK-116–124) | AWS infrastructure as code (VPC, ECR, S3, RDS, EKS, IAM) |
| Production Polish | M15 (TASK-125–133) | Documentation, ADRs, security review, demo |

## Ограничения и допущения

1. Диаграммы отражают **реализованное состояние** (M0–M13) + проектное (M14+)
2. Gold-слой реализован как PostgreSQL-аналитические таблицы, а не Gold Parquet
3. Warehouse Loader читает из Silver Parquet, а не из Gold
4. Airflow DAGs читают из PostgreSQL base tables и Bronze Parquet
5. Observability полностью реализована: Prometheus, Grafana (3 dashboards), OpenTelemetry, Jaeger (M10)
6. Kubernetes (M8) и Helm (M9) реализованы; Terraform (M14) — проектное состояние
7. 5 source adapters реализованы, Amazon/сложные источники — в roadmap
8. Авторитетный снимок архитектуры: `docs/architecture/platform-inventory-m13.md`
