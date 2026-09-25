# Итоговая сводка коммуникационного пакета

## Что подготовлено

| Артефакт | Путь | Назначение |
|----------|------|------------|
| План коммуникации | `docs/architecture-communication/architecture-communication-plan.md` | Аудитория, контекст, иерархия сообщений |
| Контейнерный вид | `docs/architecture-communication/container-view.dot` | Graphviz DOT: сервисы, топики, хранилища, границы |
| Поток данных | `docs/architecture-communication/data-flow.dot` | Graphviz DOT: линейный поток через медальон-озеро + Airflow |
| Пояснения | `docs/architecture-communication/reading-notes.md` | Как читать диаграммы, evidence-ссылки, допущения |

Обновлено: 2026-09-25 (отражает состояние после TASK-115, Milestone 0–13;
скорректировано по `docs/architecture/platform-inventory-m13.md`)

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
| FastAPI (13+ endpoints) | Реализовано | M7 |
| Kubernetes (kind, 7 Deployments) | Реализовано | M8 |
| Helm charts | Реализовано | M9 |
| Observability (Prometheus/Grafana/OTel/Jaeger) | Реализовано | M10 |
| LangGraph Agent (read-only SQL) | Реализовано | M11 |
| Failure engineering (replay tests) | Реализовано | M12 |
| Performance testing (load benchmarks) | Реализовано | M13 |
| Terraform + AWS | M14 | Roadmap |
| Production Polish | M15 | Roadmap |

## Следующие шаги

- M14: Terraform/AWS (VPC, ECR, S3, RDS, EKS, IAM, CI/CD)
- M15: Production Polish (documentation, ADRs, security review, demo)
- Обновить диаграммы по мере реализации M14–M15 (пунктирные → сплошные)
- Добавить trust-boundary вид при проработке security (M14, M15)

## Источник

Сформировано на основе evidence из кода, конфигурации, ADR-001,
`ai/PROJECT.md`, `ai/SPECIFICATION.md`, `ai/AGENTS.md`.
Первое издание: commit 1270500 (2026-09-12). Обновлено: 2026-09-18.
Скорректировано: 2026-09-25 (M13 reconciliation по `docs/architecture/platform-inventory-m13.md`).
