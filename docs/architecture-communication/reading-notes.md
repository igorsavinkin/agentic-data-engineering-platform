# Пояснения к диаграммам архитектуры

## Как читать контейнерный вид (container-view.dot)

### Что показывает
Полную карту сервисов платформы, хранилищ данных, Kafka-топиков и границ
ответственности. Сплошные линии — реализованные компоненты, пунктирные —
проектное состояние (target state из roadmap).

### Порядок чтения
1. **Слева** — внешние источники данных (эллипсы)
2. **Ingestion** — адаптеры источников, изолирующие специфику API
3. **Kafka** — 5 топиков: 3 продуктовых (raw, validated, invalid) + 2 операционных
4. **Processor** — валидация, нормализация, дедупликация
5. **Data Lake** — три слоя медальона (Bronze/Silver/Gold)
6. **Warehouse** — Airflow для Gold-конструкции, Loader для загрузки в PostgreSQL
7. **Serving** — FastAPI для HTTP-запросов, LangGraph-агент для AI

### Ключевые архитектурные ограничения, видимые на диаграмме
- Ingestion пишет **только в Kafka**, никогда напрямую в PostgreSQL
- Каждый сервис потребляет из **своей consumer group**
- Raw Writer владеет Bronze, Lake Writer — Silver, Airflow — Gold
- Агент имеет **только read-only** доступ к PostgreSQL
- DLQ (`products.invalid.v1`) содержит полный диагностический контекст

### Условные обозначения
| Форма | Значение |
|-------|----------|
| Прямоугольник | Сервис / контейнер |
| Компонент (двойная скобка) | Kafka-топик |
| Цилиндр | Хранилище данных |
| Эллипс | Внешний источник |
| Сплошная линия | Реализовано (high confidence) |
| Пунктирная линия | Проектное состояние (target) |
| Точечная линия | Observability (метрики/трейсы) |

---

## Как читать поток данных (data-flow.dot)

### Что показывает
Линейное движение данных от внешнего источника до serving-слоя через все
уровни медальон-озера. Горизонтальная ориентация (LR) подчёркивает
последовательность трансформаций.

### Порядок чтения
Слева направо по потоку:

```
Источник → Adapter → Kafka (raw) → Raw Writer → Bronze
                                ↘ Processor → Kafka (validated) → Lake Writer → Silver
                                          ↘ Kafka (invalid/DLQ)
Silver → Airflow → Gold → Warehouse Loader → PostgreSQL → API / Agent
```

### Ключевые семантики на каждом переходе
| Переход | Семантика |
|---------|-----------|
| Source → Adapter | Сбор данных, нормализация в канонический формат |
| Adapter → Kafka | Publish с partition key `source:external_id` |
| Kafka → Raw Writer | Консумирование, batch-аккумуляция |
| Raw Writer → Bronze | Parquet с детерминированными ключами (по event_id) |
| Kafka → Processor | Валидация (Pydantic), нормализация, дедупликация |
| Processor → validated | Успешные события после обработки |
| Processor → invalid | Проваленные события + диагностический контекст |
| Silver → Airflow | Batch-трансформации: quality, compaction, Gold |
| Gold → PostgreSQL | Идемпотентный UPSERT по event_id |
| PostgreSQL → Agent | Read-only SQL через контролируемые инструменты |

### Семантика доставки
- **At-least-once** с идемпотентной обработкой (никогда exactly-once)
- Офсеты коммитятся **только после** успешной обработки
- При сбое/рестарте необработанные записи доставляются повторно
- RetryPolicy: 1-10 попыток, линейный backoff 0-5с
- Только `TransientProcessingError` подвержен ретраю

---

## Evidence-ссылки на код

| Компонент | Путь в репозитории |
|-----------|-------------------|
| Event contract | `libs/event_contracts/product_observation.py` |
| Kafka producer | `libs/common/kafka_producer.py` |
| Kafka consumer | `libs/common/kafka_consumer.py` |
| MinIO storage | `libs/common/minio_storage.py` |
| Config system | `libs/common/config.py` |
| Processor pipeline | `services/processor/pipeline.py` |
| Bronze writer | `libs/raw_writer/bronze_writer.py` |
| Raw Writer consumer | `services/raw-writer/consumer.py` |
| Topic management | `scripts/manage_kafka_topics.py` |
| ADR-001 (топики) | `docs/adr/ADR-001-kafka-topic-configuration.md` |
| Docker Compose | `docker-compose.yml` |

## Ограничения и допущения

1. Диаграммы отражают **архитектурное намерение** из `ai/PROJECT.md` и
   `ai/SPECIFICATION.md`, а не только текущее состояние кода
2. Реализованы Milestone 0-3 (TASK-001 — TASK-026)
3. Компоненты Silver/Gold, API, Agent, Airflow — проектное состояние
4. Observability (Prometheus/Grafana/OTel) — placeholder-директории
5. Kubernetes/Terraform — placeholder, реализация в Milestone 8-14
