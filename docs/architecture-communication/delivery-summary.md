# Итоговая сводка коммуникационного пакета

## Что подготовлено

| Артефакт | Путь | Назначение |
|----------|------|------------|
| План коммуникации | `docs/architecture-communication/architecture-communication-plan.md` | Аудитория, контекст, иерархия сообщений |
| Контейнерный вид | `docs/architecture-communication/container-view.dot` | Graphviz DOT: сервисы, топики, хранилища, границы |
| Поток данных | `docs/architecture-communication/data-flow.dot` | Graphviz DOT: линейный поток через медальон-озеро + Airflow |
| Пояснения | `docs/architecture-communication/reading-notes.md` | Как читать диаграммы, evidence-ссылки, допущения |

Обновлено: 2026-09-18 (отражает состояние после TASK-062, Milestone 0–6)

## Для кого

Инженер / владелец проекта. Полный технический взгляд без упрощений.

## Как использовать

1. Открыть `.dot`-файлы в Graphviz-совместимом просмотрщике или Qoder Canvas
2. Прочитать `reading-notes.md` для контекста и evidence-ссылок
3. Использовать как базу для onboarding AI-агентов (Qwen, Claude)

## Текущее состояние платформы (кратко)

| Компонент | Статус | Milestone |
|-----------|--------|-----------|
| Kafka (KRaft, 5 topics) | Реализовано | M1 |
| Ingestion + 5 adapters | Реализовано | M1, M5, M5A–C |
| Processor (validate/transform/dedup) | Реализовано | M2 |
| Bronze (Raw Writer → Parquet) | Реализовано | M3 |
| Silver (Lake Writer → Parquet) | Реализовано | M3 |
| PostgreSQL (8 tables, 6 migrations) | Реализовано | M4 |
| Warehouse Loader (Silver → PG) | Реализовано | M4 |
| Airflow (4 DAGs) | Реализовано | M6 |
| Quality framework (5 checks) | Реализовано | M6 |
| Compaction (Parquet merge) | Реализовано | M6 |
| Daily metrics (Gold) | Реализовано | M6 |
| Ingestion health monitoring | Реализовано | M6 |
| Analytical queries (CTE, window) | Реализовано | M5 |
| FastAPI | M7 | Следующий |
| Kubernetes / Helm | M8–M9 | Roadmap |
| Observability (Prometheus/Grafana) | M10 | Roadmap |
| LangGraph Agent | M11 | Roadmap |
| Terraform + AWS | M14 | Roadmap |

## Следующие шаги

- M7: Реализовать FastAPI (products, analytics, pipeline, DQ endpoints)
- M8–M9: Kubernetes (kind) + Helm charts
- M10: Observability stack (Prometheus, Grafana, OTel)
- M11: LangGraph Agent (read-only SQL, controlled tools)
- Обновить диаграммы по мере реализации M7–M14 (пунктирные → сплошные)
- Добавить deployment-topology вид при реализации Kubernetes (M8–M9)
- Добавить trust-boundary вид при проработке security (M11, M14)

## Источник

Сформировано на основе evidence из кода, конфигурации, ADR-001,
`ai/PROJECT.md`, `ai/SPECIFICATION.md`, `ai/AGENTS.md`.
Первое издание: commit 1270500 (2026-09-12). Обновлено: 2026-09-18.
