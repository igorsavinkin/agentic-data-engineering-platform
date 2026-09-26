# Data Engineering Platform --- Bash / Kubernetes Cheat Sheet

> Практическая памятка для `agentic-data-engineering-platform`: Windows
> 11 + Git Bash, Docker Desktop, kind и namespace `ai-data-platform`.

## Git и worktree

### Проверить текущую ветку и состояние

**Описание:** перед любой TASK убедиться, что работа идёт в правильной
ветке/worktree.

``` bash
git branch --show-current
git status
git log --oneline --graph --decorate -10
git worktree list
```

### Обновить main

``` bash
git switch main
git pull origin main
```

### Создать branch + worktree

**Синтаксис:**

``` bash
git worktree add <path> -b <branch> <base>
```

**Пример:**

``` bash
git worktree add ../agentic-data-platform-task-134 \
  -b feature/TASK-134-airflow-kubernetes-runtime \
  main
```

### Удалить worktree после merge

``` bash
git worktree remove ../agentic-data-platform-task-134
git branch -d feature/TASK-134-airflow-kubernetes-runtime
```

------------------------------------------------------------------------

## kind и Kubernetes context

### Кластеры kind

``` bash
kind get clusters
```

### Текущий context

``` bash
kubectl config current-context
```

Для проекта ожидается:

``` text
kind-ai-data-platform
```

Переключение:

``` bash
kubectl config use-context kind-ai-data-platform
```

------------------------------------------------------------------------

## Kubernetes --- основные ресурсы проекта

### Pods

**Описание:** реальные запущенные экземпляры workload/container.

``` bash
kubectl -n ai-data-platform get pods
kubectl -n ai-data-platform get pods -o wide
kubectl -n ai-data-platform get pods -w
```

### Deployments

**Описание:** управляют stateless Pod replicas и rollout.

``` bash
kubectl -n ai-data-platform get deployments
kubectl -n ai-data-platform describe deployment <name>
```

### StatefulSets

**Описание:** управляют stateful workloads со стабильной
identity/storage, например PostgreSQL.

``` bash
kubectl -n ai-data-platform get statefulsets
kubectl -n ai-data-platform describe statefulset <name>
```

### Services

**Описание:** дают стабильный network endpoint/DNS для доступа к Pod'ам.

``` bash
kubectl -n ai-data-platform get services
kubectl -n ai-data-platform get svc
kubectl -n ai-data-platform describe service <name>
```

### Основные ресурсы вместе

``` bash
kubectl -n ai-data-platform get pods,deployments,statefulsets,services
```

``` bash
kubectl -n ai-data-platform get all
```

`get all` не означает буквально все Kubernetes resource types.
ConfigMaps, Secrets и PVC удобно проверять отдельно.

------------------------------------------------------------------------

## ConfigMaps, Secrets и storage

``` bash
kubectl -n ai-data-platform get configmaps
kubectl -n ai-data-platform get secrets
kubectl -n ai-data-platform get pvc
```

Не выводите содержимое Secrets без необходимости и не сохраняйте
реальные credentials в task reports.

------------------------------------------------------------------------

## Диагностика Pod

### Состояние и Events

``` bash
kubectl -n ai-data-platform describe pod <pod-name>
```

Обратите внимание на `State`, `Last State`, `Reason`, `Restart Count`,
`Events`.

### Логи

``` bash
kubectl -n ai-data-platform logs <pod-name>
kubectl -n ai-data-platform logs -f <pod-name>
kubectl -n ai-data-platform logs <pod-name> --previous
```

`--previous` особенно полезен после crash/restart.

Для Pod с несколькими containers:

``` bash
kubectl -n ai-data-platform logs <pod-name> -c <container-name>
```

### Shell внутри Pod

``` bash
kubectl -n ai-data-platform exec -it <pod-name> -- bash
```

или:

``` bash
kubectl -n ai-data-platform exec -it <pod-name> -- sh
```

------------------------------------------------------------------------

## PostgreSQL в Kubernetes

### Найти PostgreSQL Pod

``` bash
kubectl -n ai-data-platform get pods | grep postgres
```

### Открыть psql

``` bash
kubectl -n ai-data-platform exec -it postgresql-0 -- \
  psql -U postgres -d warehouse
```

### Выполнить SQL без interactive shell

``` bash
kubectl -n ai-data-platform exec postgresql-0 -- \
  psql -U postgres -d warehouse \
  -c "SELECT COUNT(*) FROM product_observations;"
```

``` bash
kubectl -n ai-data-platform exec postgresql-0 -- \
  psql -U postgres -d warehouse \
  -c "SELECT COUNT(*) FROM daily_metrics;"
```

Внутри `psql`:

``` text
\l    -- databases
\dt   -- tables
\q    -- exit
```

------------------------------------------------------------------------

## Port-forward

**Синтаксис:**

``` bash
kubectl -n <namespace> port-forward <resource> <local-port>:<remote-port>
```

Пример:

``` bash
kubectl -n ai-data-platform port-forward service/postgresql 15432:5432
```

После этого локальный процесс обращается к `localhost:15432`.

Port-forward удобен для диагностики. Целевой TASK-134 runtime Airflow
должен использовать Kubernetes Service DNS без зависимости от
port-forward.

------------------------------------------------------------------------

## Docker

``` bash
docker ps
docker ps -a
docker images
docker logs <container>
docker logs -f <container>
docker exec -it <container> bash
```

Если `bash` отсутствует:

``` bash
docker exec -it <container> sh
```

------------------------------------------------------------------------

## Airflow --- временная Docker verification

Эта команда иллюстрирует прежнюю verification topology: Airflow в
Docker, DAGs/libs из репозитория, warehouse через `host.docker.internal`
и host port-forward.

``` bash
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd)/airflow/dags\:/opt/airflow/dags\:ro" \
  -v "$(pwd)/libs\:/opt/airflow/libs\:ro" \
  -e AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="sqlite:////tmp/airflow\.db" \
  -e AIRFLOW__CORE__EXECUTOR="SequentialExecutor" \
  -e AIRFLOW__CORE__LOAD_EXAMPLES="false" \
  -e AIRFLOW__CORE__DAGS_FOLDER="/opt/airflow/dags" \
  -e AIRFLOW__WEBSERVER__SECRET_KEY="test-verification-key" \
  -e WAREHOUSE_DB_HOST="host.docker.internal" \
  -e WAREHOUSE_DB_PORT="15432" \
  -e WAREHOUSE_DB_NAME="warehouse" \
  -e WAREHOUSE_DB_USER="postgres" \
  -e WAREHOUSE_DB_PASSWORD="" \
  -e PYTHONPATH="/opt/airflow" \
  apache/airflow:2.10.4-python3.12 \
  bash -c "
    pip install polars --quiet &&
    airflow db migrate > /dev/null 2>&1 &&
    airflow dags list &&
    airflow tasks test build_daily_metrics compute_daily_metrics 2026-09-23
  "
```

### Что означает

-   `MSYS_NO_PATHCONV=1` --- не даёт Git Bash/MSYS нежелательно
    преобразовывать Docker paths.
-   `-v` --- mount локальных DAGs/libs в container.
-   `-e` --- environment variable.
-   `SequentialExecutor` --- verification configuration, не
    автоматически целевой Kubernetes executor.
-   `WAREHOUSE_DB_*` --- environment contract runtime-кода.
-   `host.docker.internal:15432` --- временный Docker → host →
    Kubernetes port-forward путь.
-   `pip install polars` --- verification workaround; TASK-134 должен
    bake dependency в custom image.

------------------------------------------------------------------------

## Airflow CLI

``` bash
airflow dags list
airflow dags list-import-errors
airflow tasks list build_daily_metrics
```

**Тест task:**

``` bash
airflow tasks test <dag-id> <task-id> <logical-date>
```

Пример:

``` bash
airflow tasks test \
  build_daily_metrics \
  compute_daily_metrics \
  2026-09-23
```

------------------------------------------------------------------------

## Kubernetes DNS

Внутри namespace Service обычно доступен по имени:

``` text
<service-name>:<port>
```

Концептуально:

``` text
postgresql:5432
minio:9000
```

Полная форма:

``` text
<service>.<namespace>.svc.cluster.local
```

Перед использованием проверьте реальные names:

``` bash
kubectl -n ai-data-platform get svc
```

------------------------------------------------------------------------

## Helm

### Releases

``` bash
helm list -n ai-data-platform
```

### Render без установки

``` bash
helm template <release-name> <chart-path> -n ai-data-platform
```

### Install/upgrade

``` bash
helm upgrade --install <release-name> <chart-path> \
  -n ai-data-platform
```

Путь к chart и values всегда сверяйте с текущей структурой репозитория.

------------------------------------------------------------------------

## Rollout / restart

``` bash
kubectl -n ai-data-platform rollout status deployment/<name>
kubectl -n ai-data-platform rollout restart deployment/<name>
kubectl -n ai-data-platform rollout status statefulset/<name>
```

------------------------------------------------------------------------

# Pods vs Deployments vs StatefulSets vs Services

## Pod

**Pod --- реально запущенный экземпляр workload.**

``` text
Pod
└── container(s)
```

Pod может быть удалён и создан заново; его IP обычно не следует
использовать как постоянный endpoint.

## Deployment

**Deployment управляет stateless Pod'ами.**

``` text
Deployment: processor
       │
       ├── Pod 1
       ├── Pod 2
       └── Pod 3
```

Если Pod умер, Deployment/ReplicaSet создаёт replacement. Подходит для
API, processors, ingestion services и других взаимозаменяемых instances.

## StatefulSet

**StatefulSet управляет stateful Pod'ами со стабильной
identity/storage.**

``` text
StatefulSet: postgresql
       │
       └── postgresql-0
              │
              └── PersistentVolume
```

Имена вроде `postgresql-0`, `postgresql-1` стабильны. Это подходит для
databases и других workloads, где важны identity, storage или ordered
lifecycle.

## Service

**Service не запускает приложение. Он предоставляет стабильный network
endpoint к Pod'ам.**

``` text
Service: postgresql:5432
              │
              ▼
         postgresql-0
```

Для replicas:

``` text
             Service
                │
        ┌───────┼───────┐
        ▼       ▼       ▼
      Pod 1   Pod 2   Pod 3
```

Pod IP может измениться, Service DNS остаётся стабильным.

## Связь ресурсов

Stateless:

``` text
Deployment
    │ creates/manages
    ▼
ReplicaSet
    │
    ▼
   Pods
    ▲
    │ routes
 Service
    ▲
    │
 clients
```

Stateful:

``` text
StatefulSet
    │ creates/manages
    ▼
stable Pods ── PersistentVolumeClaims
    ▲
    │ routes
 Service
    ▲
    │
 clients
```

- **Pod** — это место, где реально работают контейнеры. Например, postgresql-0 — конкретный работающий Pod.

- **Deployment** — контроллер для преимущественно stateless-приложений. Например, если задано 3 replicas Processor и один Pod погиб, Kubernetes создаст новый:
```
Deployment: processor
        ↓
   ReplicaSet
        ↓
 ┌──────┼──────┐
 ▼      ▼      ▼
Pod    Pod     Pod
```
- **StatefulSet** — похож на Deployment, но предназначен для stateful workloads, где важны стабильная identity и storage (data):
```
StatefulSet: postgresql
        ↓
   postgresql-0
        ↓
      PVC
        ↓
 persistent data
``` 
Поэтому имя **postgresql-0** не случайно: *-0* — ordinal instance StatefulSet.

- **PVC** — это PersistentVolumeClaim (запрос на постоянное хранилище) в Kubernetes.

Расшифровка:

- Persistent — постоянный, сохраняемый.

- Volume — том/хранилище.

- Claim — заявка/запрос.

Простыми словами: PVC — это заявка Pod’а на диск, который должен сохраниться даже после перезапуска или удаления Pod’а.

В твоей схеме выше это значит:

- StatefulSet создаёт Pod с предсказуемым именем, например postgresql-0.

- Для этого Pod’а создаётся PVC — например data-postgresql-0.

- PVC запрашивает у Kubernetes хранилище нужного размера, например 10 Gi.

- Kubernetes связывает PVC с PV — PersistentVolume, то есть с реальным диском.

- Данные PostgreSQL лежат на этом диске и не пропадают при перезапуске Pod’а.

Более точно схема выглядит так:

```text
StatefulSet: postgresql
        ↓
   Pod: postgresql-0
        ↓
   PVC: data-postgresql-0
        ↓
   PV: persistent volume
        ↓
   Реальный диск: SSD/HDD/NFS/cloud disk
        ↓
   persistent data
```

- **Service** вообще не запускает приложение. Его задача — дать стабильный сетевой адрес для Pod'ов:
```
Airflow
   │
   │ postgresql:5432
   ▼
Service: postgresql
   │
   ▼
postgresql-0
```

---

| Resource    | Роль                                           | Типичный вопрос                                      |
|-------------|------------------------------------------------|------------------------------------------------------|
| Pod         | Запускает container(s)                         | «Процесс работает?»                                  |
| Deployment  | Управляет stateless replicas/rollout           | «Сколько API/processor instances должно быть?»       |
| StatefulSet | Управляет stateful instances и identity/storage | «Как держать PostgreSQL с постоянными данными?»      |
| Service     | Даёт стабильный DNS/network endpoint           | «По какому адресу Airflow найдёт PostgreSQL?»        |


------------------------------------------------------------------------

## Что значит mount / mounted

Это очень важное понятие Linux/Docker/Kubernetes.

**Mount** = подключить одно хранилище к определённому каталогу файловой системы.

Например, PostgreSQL внутри контейнера видит:

`/var/lib/postgresql/data`

Но физически данные могут находиться на persistent volume.

Можно представить:
```
Persistent Volume
┌────────────────────────────┐
│                            │
│ PostgreSQL files           │
│                            │
│ tables                     │
│ indexes                    │
│ WAL                        │
│ ...                        │
└──────────────┬─────────────┘
               │
               │ mount
               ▼
     /var/lib/postgresql/data
               ▲
               │
        PostgreSQL container
```
PostgreSQL ничего особенного про Kubernetes знать не обязан. Для него это просто каталог:

`/var/lib/postgresql/data`

Он делает условно:

`write("/var/lib/postgresql/data/...")`

Но Kubernetes сделал этот каталог точкой монтирования (mount point) persistent storage.

Поэтому запись фактически идёт:
```
PostgreSQL
     │
     ▼
/var/lib/postgresql/data
     │
     │ mounted volume
     ▼
    PVC
     │
     ▼
    PV
     │
     ▼
persistent storage
```
**mount** — действие:

подключить volume к каталогу.

**mounted** — состояние:

volume уже подключён к каталогу.

Например:

The volume is mounted at /var/lib/postgresql/data.

означает:

Том подключён к /var/lib/postgresql/data.

И твой эксперимент теперь можно описать именно через это понятие:
```
OLD POD
postgresql-0
     │
     └── /var/lib/postgresql/data
                  │
                  │ mounted
                  ▼
                 PVC
                  │
                  ▼
                 PV
                  │
               [DATA]


kubectl delete pod postgresql-0
             ↓

        Pod уничтожен
        PV НЕ уничтожен


NEW POD                         AGE 9s
postgresql-0
     │
     └── /var/lib/postgresql/data
                  │
                  │ mounted AGAIN
                  ▼
             тот же PVC
                  │
                  ▼
              тот же PV
                  │
               [DATA]
                  ↑
           данные сохранились
```

Это очень хороший практический пример разницы между **compute lifecycle (Pod)** и **storage lifecycle (PVC/PV)**: Pod временный, а persistent storage имеет независимый жизненный цикл.

-----------------------------------

## Быстрая диагностика

``` bash
kubectl config current-context

kubectl -n ai-data-platform get pods
kubectl -n ai-data-platform get deployments
kubectl -n ai-data-platform get statefulsets
kubectl -n ai-data-platform get services

kubectl -n ai-data-platform get configmaps
kubectl -n ai-data-platform get pvc
```

Затем:

``` bash
kubectl -n ai-data-platform describe pod <pod-name>
kubectl -n ai-data-platform logs <pod-name>
kubectl -n ai-data-platform logs <pod-name> --previous
```
