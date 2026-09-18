# План коммуникации архитектуры — AI Data Platform

## Аудитория

Инженер / владелец проекта. Глубокое техническое понимание, необходимость
видеть полную картину: сервисы, потоки данных, границы ответственности,
статус реализации.

## Решенческий контекст

- Понимание текущего состояния платформы (M0–M6 реализованы)
- Планирование следующих milestone'ов (M7+: FastAPI, K8s, Agent)
- Проверка архитектурной целостности: соблюдены ли заявленные границы сервисов
- Ориентир для onboarding новых AI-агентов и разработчиков

## Иерархия сообщений

1. **Что платформа делает** — event-driven конвейер конкурентной разведки
   e-commerce с медальон-озером (Bronze/Silver), PostgreSQL serving-слоем
   с Gold-аналитическими таблицами и Airflow-оркестрацией.
2. **Как устроена** — 4 сервиса (ingestion, processor, raw-writer, lake-writer),
   5 Kafka-топиков, 2 Parquet-слоя + Gold PostgreSQL, 5 source-адаптеров,
   4 Airflow DAG, PostgreSQL (8 таблиц), аналитические запросы.
3. **Что реализовано** — Milestone 0–6 (TASK-001–TASK-062): foundation,
   event platform, processing, data lake, warehouse, all 5 sources,
   Airflow quality/metrics/health/compaction.
4. **Что в roadmap** — M7: FastAPI, M8–M9: Kubernetes/Helm, M10: Observability,
   M11: LangGraph Agent, M12–M14: Failure/Performance/AWS.
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

- Реализованы Milestone 0–6 (TASK-001–TASK-062)
- Gold-слой реализован как PostgreSQL-аналитические таблицы (не Gold Parquet)
- Airflow читает из PostgreSQL и Bronze, пишет в Gold-таблицы
- 5 source-адаптеров реализованы (FakeStore, BestBuy, eBay, WebRetailer, DifficultRetailer)
- Observability libs реализованы; Prometheus/Grafana/OTel — M10
- Kubernetes, Helm, Terraform — placeholder-директории
