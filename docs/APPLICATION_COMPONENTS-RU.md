# Компоненты приложения 
## Что делает каждый компонент приложения и почему Kubernetes показывает Deployment / StatefulSet / Job.

Ваша текущая цепочка выглядит так:

```text
External API
    │
    ▼
┌─────────────┐
│  Ingestion  │
└──────┬──────┘
       │ ProductObservation
       ▼
┌──────────────────────┐
│        Kafka         │
│ products.raw.v1      │
└──────────┬───────────┘
           │
           ▼
┌─────────────┐
│  Processor  │
└──────┬──────┘
       │ validated events
       ▼
┌──────────────────────────┐
│ Kafka                    │
│ products.validated.v1    │
└────────────┬─────────────┘
             │
             ▼
┌──────────────┐
│ Lake Writer  │
└───────┬──────┘
        │ Parquet
        ▼
┌─────────────────┐
│ MinIO           │
│ Silver data lake│
└─────────────────┘

                 PostgreSQL
                     ▲
                     │
           будет использоваться позже
```

### `ingestion` — получение исходных данных

```text
ingestion-56d454ff6f-ql2vp   1/1 Running
```

Это вход в pipeline. Он обращается к внешним источникам, например Fake Store и Best Buy, преобразует полученные данные в ваш единый `ProductObservation` event и публикует его в Kafka:

```text
Fake Store API
      ↓
   ingestion
      ↓
products.raw.v1
```

Мы это уже реально проверили. Например:

```json
{
  "event_id": "fake_store:1:...",
  "event_type": "product.observation",
  "source": "fake_store",
  "payload": {
    "external_id": "1",
    "name": "Fjallraven...",
    "price": "109.95",
    "currency": "USD"
  }
}
```

То есть ingestion — это **Extract + начало Normalize**.

---

### `kafka` — транспорт событий

```text
kafka-798c456747-wvlmz   1/1 Running
```

Kafka — это центральная event-streaming система между сервисами.

Вместо прямой связи:

```text
Ingestion → Processor
```

у вас:

```text
Ingestion → Kafka → Processor
```

Это важное архитектурное различие. Ingestion не обязан знать, где находится Processor и работает ли он прямо сейчас.

У вас уже есть, среди прочих, два ключевых topic:

```text
products.raw.v1
products.validated.v1
```

Первый содержит сырые canonical observations:

```text
Ingestion
   ↓
products.raw.v1
```

Второй — события, прошедшие Processor:

```text
Processor
   ↓
products.validated.v1
```

Поэтому Kafka фактически является **event backbone** платформы.

---

### `processor` — проверка и обработка данных

```text
processor-7cd699cd54-4zrxg   1/1 Running
```

Он читает:

```text
products.raw.v1
```

и занимается validation/processing/deduplication согласно логике проекта.

Мы уже видели:

```text
processor_batch_complete
valid: 1
invalid: 0
duplicates: 0
conflicts: 0
```

После успешной обработки событие отправляется в:

```text
products.validated.v1
```

Поэтому:

```text
Kafka raw
   ↓
Processor
   ↓
Kafka validated
```

Это важный Data Engineering boundary: downstream-компонентам уже не обязательно работать непосредственно с сырыми событиями.

---

### `lake-writer` — Kafka → Data Lake

```text
lake-writer-6d8bc8c984-bcbmz   1/1 Running
```

Он читает:

```text
products.validated.v1
```

и превращает поток событий в файлы Data Lake, в вашем случае **Parquet**.

Мы уже увидели реальную запись:

```text
bucket: silver

silver/
  source=fake_store/
    year=2026/
      month=09/
        day=22/
          fake_store_4_....parquet
```

То есть:

```text
Kafka events
      ↓
 Lake Writer
      ↓
   Parquet
      ↓
    MinIO
```

`lake-writer` — это фактически **stream-to-lake sink**.

---

### `minio` — ваш локальный S3 / Data Lake

```text
minio-0   1/1 Running
```

MinIO предоставляет S3-compatible object storage.

В локальной среде он играет примерно ту роль, которую позже в AWS будет выполнять **Amazon S3**:

```text
Local                     AWS later

MinIO       ≈             Amazon S3
  │                           │
  ├── Bronze                  ├── Bronze
  ├── Silver                  ├── Silver
  └── Gold                    └── Gold
```

В отличие от PostgreSQL, это не обычная relational database. Там хранятся объекты — например Parquet-файлы.

Уже доказано:

```text
Lake Writer
    ↓
MinIO
    ↓
Silver/*.parquet   ✓
```

---

### `postgresql` — аналитическая relational database

```text
postgresql-0   1/1 Running
```

PostgreSQL находится дальше по pipeline.

Текущая реализованная архитектура downstream-потока:

```text
Silver (Parquet в MinIO)
   ↓
Warehouse Loader
   ↓
PostgreSQL: product_observations
   ↓
   ├──────────────→ FastAPI
   │
   ├──────────────→ LangGraph Agent
   │
   └→ Airflow transformations
          ↓
      PostgreSQL analytical / Gold tables
      (например daily_metrics, quality_results, health_results)
```

Важно: **Airflow transformations идут после Warehouse Loader и PostgreSQL** для тех DAG'ов, которые строят аналитические результаты из warehouse-таблиц. Например, `build_daily_metrics` читает `product_observations` из PostgreSQL и записывает рассчитанные `daily_metrics` обратно в PostgreSQL.

При этом Airflow в проекте выполняет не только Gold-трансформации: отдельные DAG'и отвечают за ingestion health, data quality и Parquet compaction. Поэтому Airflow — это orchestration/analytics layer, а не обязательный линейный шаг между Silver и Warehouse Loader.

То есть MinIO и PostgreSQL имеют разные роли.

**MinIO**

```text
large analytical datasets
Parquet
historical data
Bronze/Silver/Gold
cheap object storage
```

**PostgreSQL**

```text
tables
SQL
indexes
queries
API-serving layer
agent queries
```

Warehouse Loader читает **Silver Parquet** и загружает нормализованные наблюдения в warehouse-таблицы PostgreSQL (в частности `product_observations` и связанные таблицы `sources`, `products`, `source_products`).

После этого Airflow может читать warehouse-данные и строить производные аналитические результаты. Например:

```text
Silver / MinIO
      ↓
Warehouse Loader
      ↓
PostgreSQL
  product_observations
      ↓
Airflow: build_daily_metrics
      ↓
PostgreSQL
  daily_metrics
```

То есть в текущей реализации **Gold — это не обязательный Parquet-слой перед Warehouse Loader**. Часть Gold/analytical результатов хранится в PostgreSQL и создаётся Airflow уже после загрузки Silver в warehouse.

FastAPI затем может выполнять SQL-запросы к serving/warehouse-таблицам, например:

```sql
SELECT *
FROM products
WHERE category = 'electronics';
```

---

## А почему одни называются Deployment, другие StatefulSet?

Вот это тоже важно понимать в Kubernetes.

У вас:

```text
DEPLOYMENTS
ingestion
kafka
lake-writer
processor
```

Deployment означает примерно:

> Kubernetes, запусти мне N экземпляров этого приложения и следи, чтобы они продолжали работать.

Например:

```text
deployment/processor
        ↓
ReplicaSet
        ↓
processor-7cd699cd54-4zrxg
```

Если этот Pod умрёт, Kubernetes создаст новый.

Поэтому:

```text
READY   1/1
```

означает:

```text
desired replicas = 1
ready replicas   = 1
```

---

У MinIO и PostgreSQL:

```text
STATEFULSETS

minio
postgresql
```

StatefulSet используется потому, что этим приложениям важно **состояние и persistent storage**.

Например:

```text
postgresql-0
     │
     ▼
PersistentVolumeClaim
     │
     ▼
PostgreSQL data
```

Pod можно пересоздать:

```text
postgresql-0 dies
       ↓
new postgresql-0
       ↓
same persistent storage
       ↓
data remains
```

Именно поэтому для database/storage StatefulSet логичнее обычного Deployment.

---

Наконец:

```text
job.batch/kafka-topics-setup
STATUS Complete
```

Это совсем другой тип workload.

`Job` должен **выполнить задачу один раз и закончить работу**.

В вашем случае:

```text
Kafka starts
     ↓
kafka-topics-setup Job
     ↓
create/check topics
     ↓
products.raw.v1
products.validated.v1
products.invalid.v1
pipeline.events.v1
data-quality.events.v1
     ↓
Job exits successfully
```

Поэтому:

```text
0/1 Completed
```

для Job — **нормальное и желаемое состояние**. Он не должен постоянно быть `Running`.

---

### Итого

| Component              | Роль                                                         |
| ---------------------- | ------------------------------------------------------------ |
| **ingestion**          | получает данные из внешних источников и публикует raw events |
| **Kafka**              | передаёт и буферизует события между сервисами                |
| **processor**          | validates/processes/deduplicates raw observations            |
| **lake-writer**        | превращает validated Kafka events в Parquet                  |
| **MinIO**              | локальный S3-compatible Data Lake                            |
| **PostgreSQL**         | SQL warehouse/serving layer; хранит observations и analytical/Gold tables |
| **Warehouse Loader**   | читает Silver Parquet и idempotent UPSERT'ит данные в PostgreSQL |
| **Airflow**            | orchestration: health/data-quality jobs, compaction и analytical/Gold transformations |
| **FastAPI**            | предоставляет API поверх warehouse/analytical данных          |
| **LangGraph Agent**    | использует данные/инструменты поверх serving layer            |
| **kafka-topics-setup** | один раз создаёт/проверяет Kafka topics                       |
| **warehouse-migration** | применяет Alembic migrations к PostgreSQL перед использованием warehouse schema |

И самое ценное сейчас в нашем ручном E2E — это не просто наличие этих Pod'ов. Мы уже своими руками доказали реальный поток:

```text
Fake Store API
      │
      ▼
  Ingestion ✓
      │
      ▼
 Kafka raw ✓
      │
      ▼
 Processor ✓
      │
      ▼
Kafka validated ✓
      │
      ▼
 Lake Writer ✓
      │
      ▼
MinIO / Silver Parquet ✓

      ↓ NEXT

Warehouse Loader → PostgreSQL → Airflow analytical/Gold transformations
                         ├→ FastAPI
                         └→ LangGraph Agent
```

Именно такое понимание компонентов намного полезнее для Kubernetes/Data Engineering, чем просто уметь выполнить `kubectl apply`.
