# План коммуникации архитектуры — AI Data Platform

## Аудитория

Инженер / владелец проекта. Глубокое техническое понимание, необходимость
видеть полную картину: сервисы, потоки данных, границы ответственности,
статус реализации.

## Решенческий контекст

- Понимание текущего состояния платформы (M0–M13 реализованы)
- Планирование следующих milestone'ов (M14+: Terraform/AWS, Production Polish)
- Проверка архитектурной целостности: соблюдены ли заявленные границы сервисов
- Ориентир для onboarding новых AI-агентов и разработчиков

## Иерархия сообщений

1. **Что платформа делает** — event-driven конвейер конкурентной разведки
   e-commerce с медальон-озером (Bronze/Silver), PostgreSQL serving-слоем
   с Gold-аналитическими таблицами и Airflow-оркестрацией.
2. **Как устроена** — 7 сервисов (ingestion, processor, raw-writer, lake-writer,
   warehouse-loader, api, agent), 5 Kafka-топиков, 2 Parquet-слоя + Gold PostgreSQL,
   5 source-адаптеров, 4 Airflow DAG, PostgreSQL (8 таблиц), FastAPI (13+ endpoints),
   LangGraph-агент, аналитические запросы.
3. **Что реализовано** — Milestone 0–13 (TASK-001–TASK-115): foundation,
   event platform, processing, data lake, warehouse, all 5 sources,
   Airflow quality/metrics/health/compaction, FastAPI, Kubernetes, Helm,
   Observability (Prometheus/Grafana/OTel), LangGraph Agent, failure engineering,
   performance testing.
4. **Что в roadmap** — M14: Terraform/AWS, M15: Production Polish.
5. **Ключевые ограничения** — at-least-once + идемпотентность, ingestion
   пишет только в Kafka, агент не пишет в БД, Gold = PostgreSQL tables.

## Выбранные виды

| Вид | Формат | Назначение |
|-----|--------|------------|
| Контейнерный вид | Graphviz DOT | Сервисы, хранилища, топики, границы ответственности |
| Поток данных | Graphviz DOT | Движение данных от источников до serving-слоя |

## Глубина объяснения

L2 (контейнеры/сервисы) с элементами L3 (модули внутри сервисов) для
ключевых компонентов. Технические термины без упрощений.

## Допущения и ограничения

- Реализованы Milestone 0–13 (TASK-001–TASK-115)
- Gold-слой реализован как PostgreSQL-аналитические таблицы (не Gold Parquet)
- Airflow читает из PostgreSQL и Bronze, пишет в Gold-таблицы
- 5 source-адаптеров реализованы (FakeStore, BestBuy, eBay, WebRetailer, DifficultRetailer)
- Observability полностью реализована: Prometheus, Grafana (3 dashboards), OpenTelemetry, Jaeger (M10)
- Kubernetes (M8) и Helm (M9) реализованы; Terraform (M14) — проектное состояние
- Авторитетный снимок архитектуры: `docs/architecture/platform-inventory-m13.md`
