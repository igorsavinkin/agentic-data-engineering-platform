# Отчёт о пройденной E2E-проверке Agentic Data Engineering Platform

**Дата проверки:** 23--24 сентября 2026\
**Среда:** локальный Kubernetes-кластер `kind` (`ai-data-platform`)\
**Namespace:** `ai-data-platform`\
**Статус:** частичная E2E-проверка успешно пройдена до PostgreSQL
включительно

## 1. Цель проверки

Цель текущего этапа E2E-тестирования --- подтвердить реальное
прохождение данных через основные компоненты платформы, а не только
успешность unit/integration tests.

Проверяемый путь:

``` text
Fake Store
    ↓
Ingestion
    ↓
Kafka: products.raw.v1
    ├────────────→ Raw Writer → Bronze / MinIO
    │
    └→ Processor
          ↓
       products.validated.v1
          ↓
       Lake Writer
          ↓
       Silver / MinIO
          ↓
       Warehouse Loader
          ↓
       PostgreSQL
```

FastAPI, Airflow analytical transformations и LangGraph Agent пока не
входят в уже подтверждённую часть E2E.

------------------------------------------------------------------------

## 2. Kubernetes-инфраструктура

Во время проверки существующий `kind`-кластер не пересоздавался.

Подтверждено рабочее состояние следующих компонентов:

-   Kafka
-   MinIO
-   PostgreSQL
-   Ingestion
-   Processor
-   Raw Writer
-   Lake Writer
-   Warehouse Loader
-   warehouse migration Job

PVC для MinIO и PostgreSQL находились в состоянии `Bound`, поэтому
данные сохранялись между этапами тестирования.

------------------------------------------------------------------------

## 3. Source → Ingestion

В качестве реально работающего источника использовался **Fake Store**.

Best Buy adapter также запускался, однако возвращал HTTP 403 из-за
placeholder API key. Это не рассматривалось как blocker E2E, поскольку
Fake Store успешно публиковал реальные события.

Лог Ingestion подтвердил успешную публикацию:

``` text
ingestion_cycle_complete
total_published: 10
total_malformed: 0
total_errors: 4
```

**Результат:** PASS.

------------------------------------------------------------------------

## 4. Ingestion → Kafka

Содержимое Kafka topic `products.raw.v1` было проверено напрямую через
`kafka-console-consumer`.

Подтверждено наличие реального события Fake Store, включая observation с
идентификатором:

``` text
fake_store:1
```

Таким образом, путь:

``` text
Fake Store → Ingestion → products.raw.v1
```

подтверждён фактическим сообщением Kafka.

**Результат:** PASS.

------------------------------------------------------------------------

## 5. Kafka → Processor → Validated Topic

Processor был загружен в `kind` и успешно запущен.

Логи подтвердили обработку события:

``` text
processor_batch_complete
valid: 1
invalid: 0
duplicates: 0
conflicts: 0
```

После этого `products.validated.v1` был прочитан напрямую. В topic
присутствовало соответствующее событие `fake_store:1`.

Подтверждён путь:

``` text
products.raw.v1
    ↓
Processor
    ↓
products.validated.v1
```

**Результат:** PASS.

------------------------------------------------------------------------

## 6. Raw Writer → Bronze

Raw Writer работал как отдельный Kafka consumer и записал raw/canonical
event в Bronze layer MinIO.

Лог подтвердил создание Parquet object вида:

``` text
bronze/source=fake_store/year=2026/month=09/day=22/...parquet
```

Подтверждён путь:

``` text
products.raw.v1
    ↓
Raw Writer
    ↓
Bronze / MinIO / Parquet
```

**Результат:** PASS.

------------------------------------------------------------------------

## 7. Lake Writer → Silver

Lake Writer получил validated event и записал его в Silver layer.

Пример подтверждённого объекта:

``` text
silver/source=fake_store/year=2026/month=09/day=22/...parquet
```

Подтверждён путь:

``` text
products.validated.v1
    ↓
Lake Writer
    ↓
Silver / MinIO / Parquet
```

**Результат:** PASS.

------------------------------------------------------------------------

## 8. Обнаруженный E2E blocker: PostgreSQL schema

При первом запуске Warehouse Loader данные из Silver успешно
обнаруживались и читались, однако загрузка в PostgreSQL завершалась
ошибкой:

``` text
relation "sources" does not exist
```

До ошибки Loader обнаружил:

``` text
file_count=18880
row_count=18880
```

Это показало, что связь:

``` text
Silver → Warehouse Loader
```

работает, но Kubernetes deployment не имел воспроизводимого механизма
применения warehouse migrations.

Для исправления был создан corrective task:

``` text
TASK-K8S-FIX-003
```

------------------------------------------------------------------------

## 9. TASK-K8S-FIX-003 --- PostgreSQL migrations

В рамках исправления был добавлен отдельный migration image и Kubernetes
migration Job.

Migration image:

``` text
ai-data-platform/warehouse-migrations:dev
```

Он был успешно:

1.  собран локально;
2.  загружен в существующий `kind` cluster;
3.  использован Kubernetes Job `warehouse-migration`.

Job завершился успешно:

``` text
warehouse-migration   Complete   1/1
```

Alembic выполнил всю цепочку:

``` text
-> 001
001 -> 002
002 -> 003
003 -> 004
004 -> 005
005 -> 006
```

Финальный лог:

``` text
Upgraded to head
```

------------------------------------------------------------------------

## 10. Проверка PostgreSQL schema

Состояние Alembic было проверено непосредственно в PostgreSQL:

``` text
version_num
-----------
006
```

Фактически существовали 9 таблиц:

``` text
alembic_version
daily_metrics
data_quality_results
ingestion_health_results
pipeline_runs
product_observations
products
source_products
sources
```

До повторного запуска Warehouse Loader:

``` text
product_observations = 0
```

Это дало чистую baseline-точку для проверки последующей загрузки.

**Результат migration acceptance:** PASS.

------------------------------------------------------------------------

## 11. Silver → Warehouse Loader → PostgreSQL

После применения migrations Warehouse Loader был снова запущен.

На этот момент Silver layer содержал уже:

``` text
file_count = 20140
partition_count = 2
```

Рост с 18,880 до 20,140 файлов произошёл потому, что
ingestion/processing pipeline продолжал работать во время исправления
migration blocker.

Финальный batch:

``` text
processing_batch
batch_start: 20000
batch_end: 20140
batch_size: 140
```

Commit batch:

``` text
batch_committed
sources: 0
products: 1
source_products: 1
observations: 140
```

Главный результат load cycle:

``` text
Load cycle complete: read=20140 loaded=20140 failed=0
```

Предыдущая ошибка:

``` text
relation "sources" does not exist
```

больше не возникла.

**Результат:** PASS.

------------------------------------------------------------------------

## 12. Независимая SQL-проверка результата

После завершения Warehouse Loader состояние PostgreSQL было проверено
непосредственно через `psql`.

Результат:

  Entity                       Rows
  ------------------------ --------
  `sources`                       1
  `products`                     40
  `source_products`              10
  `product_observations`     20,140

Особенно важна проверка:

``` text
BEFORE Warehouse Loader:
product_observations = 0

AFTER Warehouse Loader:
product_observations = 20140
```

Количество observations совпало с:

``` text
read=20140
loaded=20140
failed=0
```

из лога Warehouse Loader.

Это подтверждает фактическую загрузку данных из Silver в PostgreSQL.

**Результат:** PASS.

------------------------------------------------------------------------

## 13. Итог подтверждённого E2E-пути

На текущем этапе фактически подтверждён следующий путь:

``` text
Fake Store
    ↓
Ingestion ✓
    ↓
Kafka: products.raw.v1 ✓
    │
    ├──────────────→ Raw Writer ✓
    │                    ↓
    │              Bronze / Parquet ✓
    │
    └→ Processor ✓
          ↓
       products.validated.v1 ✓
          ↓
       Lake Writer ✓
          ↓
       Silver / Parquet ✓
          ↓
       Warehouse Loader ✓
          ↓
       PostgreSQL ✓
          ↓
       product_observations = 20,140
```

Таким образом, основной **write/data path от внешнего источника до
warehouse PostgreSQL успешно прошёл E2E-проверку**.

------------------------------------------------------------------------

## 14. TASK-K8S-FIX-003 Manual Acceptance

Все пункты manual acceptance A--I выполнены:

  Check                               Result
  ----------------------------------- --------
  A. Build migration image            PASS
  B. Load migration image into kind   PASS
  C. PostgreSQL readiness             PASS
  D. Run migration Job                PASS
  E. Migration Job Completed          PASS
  F. Alembic head + expected tables   PASS
  G. Start Warehouse Loader           PASS
  H. Load without `UndefinedTable`    PASS
  I. `product_observations > 0`       PASS

**TASK-K8S-FIX-003: MANUALLY ACCEPTED.**

------------------------------------------------------------------------

## 15. Наблюдение по производительности

Во время E2E был обнаружен потенциально важный performance
characteristic.

Warehouse Loader работал с очень большим количеством маленьких
Parquet-файлов:

``` text
18,880 files — предыдущий запуск
20,140 files — финальный запуск
```

При этом операции partition/file discovery и lazy Parquet scan занимали
заметное время.

Это **не считается доказанным performance defect или benchmark result**.
Однако наблюдение следует сохранить для будущих задач performance
milestone, в частности анализа bottlenecks и Parquet compaction.

Необходимо измерять это отдельно под контролируемой нагрузкой, а не
выводить benchmark из текущего E2E.

------------------------------------------------------------------------

## 16. Что ещё не проверено

Текущая проверка не является полной E2E-проверкой всей платформы.

Ещё предстоит подтвердить:

``` text
PostgreSQL
    ├→ FastAPI
    ├→ LangGraph Agent
    └→ Airflow analytical transformations
           ↓
       analytical / Gold tables
```

Особенно Airflow требует отдельной проверки, поскольку существующая
конфигурация ориентирована на Docker Compose service names, а Kubernetes
deployment Airflow на текущем этапе E2E ещё не подтверждён.

------------------------------------------------------------------------

## 17. Следующий этап

Рекомендуемая следующая граница E2E:

``` text
PostgreSQL
    ↓
FastAPI
    ↓
real API query / response
```

Это позволит подтвердить полный пользовательский read path:

``` text
External Source
    ↓
Ingestion
    ↓
Kafka
    ↓
Processing
    ↓
Data Lake
    ↓
Warehouse
    ↓
FastAPI
    ↓
API Consumer
```

После FastAPI следует отдельно проверить Airflow analytical
transformations и затем LangGraph Agent.

------------------------------------------------------------------------

## Conclusion

Текущий этап E2E успешно подтвердил, что платформа способна провести
реальные данные через распределённый ingestion/data-engineering
pipeline:

**Fake Store → Kafka → Bronze/Silver Parquet → PostgreSQL.**

Проверка выявила реальный infrastructure gap --- отсутствие
воспроизводимого применения PostgreSQL migrations в Kubernetes --- и
этот gap был исправлен через `TASK-K8S-FIX-003`.

После исправления:

``` text
20,140 rows read
20,140 rows loaded
0 failed
20,140 product_observations verified directly in PostgreSQL
```

Следующий этап E2E начинается с проверки **PostgreSQL → FastAPI**.
