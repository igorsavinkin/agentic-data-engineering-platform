# Итоговая сводка коммуникационного пакета

## Что подготовлено

| Артефакт | Путь | Назначение |
|----------|------|------------|
| План коммуникации | `docs/architecture-communication/architecture-communication-plan.md` | Аудитория, контекст, иерархия сообщений |
| Контейнерный вид | `docs/architecture-communication/container-view.dot` | Графviz DOT: сервисы, топики, хранилища, границы |
| Поток данных | `docs/architecture-communication/data-flow.dot` | Графviz DOT: линейный поток через медальон-озеро |
| Пояснения | `docs/architecture-communication/reading-notes.md` | Как читать диаграммы, evidence-ссылки, допущения |

## Для кого

Инженер / владелец проекта. Полный технический взгляд без упрощений.

## Как использовать

1. Открыть `.dot`-файлы в Graphviz-совместимом просмотрщике или Qoder Canvas
2. Прочитать `reading-notes.md` для контекста и evidence-ссылок
3. Использовать как базу для onboarding AI-агентов (Qwen, Claude)

## Следующие шаги

- Обновить диаграммы по мере реализации Milestone 4-15 (пунктирные → сплошные)
- Добавить deployment-topology вид при реализации Kubernetes (M8-M9)
- Добавить trust-boundary вид при проработке security (M11, M14)

## Источник

Сформировано skill `architecture-communicator` на основе evidence из кода,
конфигурации, ADR-001, `ai/PROJECT.md`, `ai/SPECIFICATION.md`, `ai/AGENTS.md`.
