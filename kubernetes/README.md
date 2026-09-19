# kubernetes/

Kubernetes manifests for local kind deployment (Milestone 8). Cloud deployment topology is defined in `ai/SPECIFICATION.md`.

## Directory Structure

```text
kubernetes/
├── kind/
│   └── kind-config.yaml            # kind cluster configuration
├── namespaces/
│   └── platform-namespace.yaml      # Platform namespace definition
├── config/
│   ├── platform-config.yaml         # Shared infrastructure endpoints (TASK-078)
│   └── database-config.yaml         # PostgreSQL connection parameters (TASK-078)
├── secrets/
│   ├── minio-credentials.yaml       # MinIO access keys (TASK-078)
│   ├── database-credentials.yaml    # PostgreSQL password (TASK-078)
│   └── ingestion-api-keys.yaml      # Source API keys (TASK-078)
├── deployments/
│   ├── ingestion-deployment.yaml    # Ingestion service Deployment (TASK-071)
│   ├── processor-deployment.yaml    # Processor service Deployment (TASK-072)
│   ├── raw-writer-deployment.yaml   # Raw Writer service Deployment (TASK-073)
│   ├── lake-writer-deployment.yaml  # Lake Writer service Deployment (TASK-074)
│   ├── warehouse-loader-deployment.yaml # Warehouse Loader Deployment (TASK-075)
│   ├── api-deployment.yaml          # API service Deployment (TASK-076)
│   ├── api-service.yaml             # API ClusterIP Service (TASK-076)
│   ├── minio-service.yaml           # MinIO ClusterIP Service (TASK-078)
│   ├── postgresql-service.yaml      # PostgreSQL ClusterIP Service (TASK-078)
│   ├── kafka-deployment.yaml        # Kafka broker Deployment (TASK-077)
│   ├── kafka-service.yaml           # Kafka NodePort Service (TASK-077)
│   └── kafka-topics-job.yaml        # Kafka topic creation Job (TASK-077)
└── README.md                        # This file
```

## Prerequisites

- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/) (Kubernetes IN Docker)
- [kubectl](https://kubernetes.io/docs/reference/kubectl/)
- Docker (for building and loading images)

## Quick Start

### Create the cluster

```bash
bash scripts/kind-cluster.sh create
```

This creates a single-node kind cluster named `ai-data-platform` using the configuration in `kind/kind-config.yaml` and applies the platform namespace.

### Verify the cluster

```bash
bash scripts/kind-cluster.sh verify
```

Expected output: cluster info, one Ready node, and the `ai-data-platform` namespace.

### Delete the cluster

```bash
bash scripts/kind-cluster.sh delete
```

### Recreate from scratch

```bash
bash scripts/kind-cluster.sh recreate
```

### Load local Docker images

After building service images locally, load them into the kind cluster so pods can use them without a registry:

```bash
bash scripts/kind-cluster.sh load ai-data-platform/ingestion:dev
bash scripts/kind-cluster.sh load ai-data-platform/processor:dev
bash scripts/kind-cluster.sh load ai-data-platform/raw-writer:dev
bash scripts/kind-cluster.sh load ai-data-platform/lake-writer:dev
bash scripts/kind-cluster.sh load ai-data-platform/warehouse-loader:dev
bash scripts/kind-cluster.sh load ai-data-platform/api:dev
```

Multiple images can be loaded at once:

```bash
bash scripts/kind-cluster.sh load ai-data-platform/ingestion:dev ai-data-platform/processor:dev ai-data-platform/raw-writer:dev ai-data-platform/lake-writer:dev ai-data-platform/warehouse-loader:dev ai-data-platform/api:dev
```

## Manual Commands

The wrapper script is convenient but not required. You can use kind and kubectl directly:

```bash
# Create cluster
kind create cluster --name ai-data-platform --config kubernetes/kind/kind-config.yaml

# Apply namespaces
kubectl apply -f kubernetes/namespaces/platform-namespace.yaml

# Check cluster
kubectl cluster-info --context kind-ai-data-platform
kubectl get nodes
kubectl get namespaces

# Delete cluster
kind delete cluster --name ai-data-platform
```

## Namespace

All platform workloads run in the `ai-data-platform` namespace. This keeps them isolated from other local clusters and provides a consistent target for later deployment tasks.

```bash
kubectl get all -n ai-data-platform
```

## Configuration (TASK-078)

Application configuration is externalized into ConfigMaps and Secrets. Deployments reference these via `configMapKeyRef` and `secretKeyRef` rather than hardcoding values.

### ConfigMaps

ConfigMaps hold non-sensitive configuration that all services need:

| ConfigMap | Contents | Consumed By |
|---|---|---|
| `platform-config` | `APP_ENVIRONMENT`, `APP_KAFKA_BOOTSTRAP_SERVERS`, `APP_MINIO_ENDPOINT` | All services |
| `database-config` | `WAREHOUSE_DB_HOST`, `WAREHOUSE_DB_PORT`, `WAREHOUSE_DB_NAME`, `WAREHOUSE_DB_USER` | warehouse-loader, api |

```bash
kubectl apply -f kubernetes/config/
kubectl get configmaps -n ai-data-platform
kubectl describe configmap platform-config -n ai-data-platform
```

### Secrets

Secrets hold sensitive credentials. The YAML manifests in `secrets/` contain base64-encoded local development defaults. For local development, the helper script is preferred:

| Secret | Keys | Consumed By |
|---|---|---|
| `minio-credentials` | `minio-access-key`, `minio-secret-key` | raw-writer, lake-writer, warehouse-loader |
| `database-credentials` | `db-password` | warehouse-loader, api |
| `ingestion-api-keys` | `bestbuy-api-key` | ingestion |

#### Creating Secrets for local development

The recommended approach is the helper script, which uses `kubectl create secret` with `--dry-run=client` to generate and apply Secrets without editing YAML:

```bash
bash scripts/create-local-secrets.sh
```

Alternatively, apply the manifests directly (they contain local-dev placeholder values):

```bash
kubectl apply -f kubernetes/secrets/
```

Or create each Secret manually:

```bash
kubectl create secret generic minio-credentials \
  --namespace ai-data-platform \
  --from-literal=minio-access-key=minioadmin \
  --from-literal=minio-secret-key=minioadmin-local

kubectl create secret generic database-credentials \
  --namespace ai-data-platform \
  --from-literal=db-password=postgres

kubectl create secret generic ingestion-api-keys \
  --namespace ai-data-platform \
  --from-literal=bestbuy-api-key=YOUR_KEY_HERE
```

#### Secret design decisions

- **Shared Secrets**: MinIO credentials are shared across raw-writer, lake-writer, and warehouse-loader via a single `minio-credentials` Secret rather than per-service copies. Similarly, database credentials use one `database-credentials` Secret. This avoids duplication and simplifies rotation.
- **No real secrets in Git**: The YAML manifests contain only local development placeholder values. Production credentials must be injected through a proper secrets manager.
- **Helm-ready**: The ConfigMap/Secret split maps directly to Helm `values.yaml` and `templates/` patterns for TASK-080+.

### Service Discovery

Kubernetes provides in-cluster DNS based on Service names. Services reach each other using `<service-name>.<namespace>.svc.cluster.local` or simply `<service-name>` within the same namespace:

| Service | Type | Ports | Purpose |
|---|---|---|---|
| `kafka` | NodePort | 29092 (internal), 9092 (external) | Kafka broker — in-cluster and host access |
| `api` | ClusterIP | 8000 | FastAPI HTTP endpoint |
| `minio` | ClusterIP | 9000 (API), 9001 (console) | MinIO object storage |
| `postgresql` | ClusterIP | 5432 | PostgreSQL database |

Services that are Kafka consumers/producers only (ingestion, processor, raw-writer, lake-writer, warehouse-loader) do not expose inbound ports and therefore do not have their own Service resources.

## Deployments

Application service deployments live in `deployments/`. Each Deployment targets the `ai-data-platform` namespace and uses consistent `app.kubernetes.io` labels.

### Ingestion (TASK-071)

```bash
kubectl apply -f kubernetes/deployments/ingestion-deployment.yaml
kubectl get deployment ingestion -n ai-data-platform
kubectl logs deployment/ingestion -n ai-data-platform
```

The ingestion Deployment runs the source adapter fetch-publish loop. It does not expose inbound ports — it is a Kafka producer only. Configuration comes from `platform-config` ConfigMap; the BestBuy API key comes from the `ingestion-api-keys` Secret (optional).

### Processor (TASK-072)

```bash
kubectl apply -f kubernetes/deployments/processor-deployment.yaml
kubectl get deployment processor -n ai-data-platform
kubectl logs deployment/processor -n ai-data-platform
```

The processor Deployment consumes raw events from Kafka, validates and normalizes them, applies deduplication, and publishes valid records to the validated topic. Configuration comes from `platform-config` ConfigMap with service-specific settings (`APP_KAFKA_GROUP_ID`, `APP_KAFKA_AUTO_OFFSET_RESET`) as literals.

### Raw Writer (TASK-073)

```bash
kubectl apply -f kubernetes/deployments/raw-writer-deployment.yaml
kubectl get deployment raw-writer -n ai-data-platform
kubectl logs deployment/raw-writer -n ai-data-platform
```

The raw writer Deployment consumes raw events from Kafka and persists them to Bronze (MinIO) as Parquet files. Configuration comes from `platform-config` ConfigMap; MinIO credentials from the shared `minio-credentials` Secret.

### Lake Writer (TASK-074)

```bash
kubectl apply -f kubernetes/deployments/lake-writer-deployment.yaml
kubectl get deployment lake-writer -n ai-data-platform
kubectl logs deployment/lake-writer -n ai-data-platform
```

The lake writer Deployment consumes validated events from Kafka and persists them to Silver (MinIO) as Parquet files. Configuration comes from `platform-config` ConfigMap; MinIO credentials from the shared `minio-credentials` Secret.

### Warehouse Loader (TASK-075)

```bash
kubectl apply -f kubernetes/deployments/warehouse-loader-deployment.yaml
kubectl get deployment warehouse-loader -n ai-data-platform
kubectl logs deployment/warehouse-loader -n ai-data-platform
```

The warehouse loader Deployment reads Silver Parquet from MinIO and loads curated data into PostgreSQL with idempotent upserts. Configuration comes from `platform-config` and `database-config` ConfigMaps; credentials from `minio-credentials` and `database-credentials` Secrets. This deployment does not run Alembic migrations.

### API (TASK-076)

```bash
kubectl apply -f kubernetes/deployments/api-deployment.yaml
kubectl apply -f kubernetes/deployments/api-service.yaml
kubectl get deployment api -n ai-data-platform
kubectl get service api -n ai-data-platform
kubectl logs deployment/api -n ai-data-platform
```

The API Deployment runs the FastAPI application providing synchronous HTTP access to serving and analytics data. It is the only service that exposes inbound ports (port 8000) and has a corresponding ClusterIP Service for in-cluster access. Configuration comes from `platform-config` and `database-config` ConfigMaps; the database password from the `database-credentials` Secret.

Health and readiness probes target the established endpoints:
- **Liveness**: `GET /api/v1/health` — always returns 200 when the process is running
- **Readiness**: `GET /api/v1/ready` — returns 200 only when the database is reachable, 503 otherwise

To access the API locally via port-forward:

```bash
kubectl port-forward svc/api 8000:8000 -n ai-data-platform
curl http://localhost:8000/api/v1/health
```

### Kafka (TASK-077)

```bash
kubectl apply -f kubernetes/deployments/kafka-deployment.yaml
kubectl apply -f kubernetes/deployments/kafka-service.yaml
kubectl get deployment kafka -n ai-data-platform
kubectl get service kafka -n ai-data-platform
kubectl logs deployment/kafka -n ai-data-platform
```

Kafka runs in single-broker KRaft mode (combined broker + controller, no ZooKeeper) using the `apache/kafka:4.3.1` image. The NodePort Service exposes port 29092 for in-cluster pod-to-pod communication via `kafka:29092`, and maps host port 9092 via the kind port mapping (host 9092 → node 30092 → pod 9092 via PLAINTEXT_HOST listener).

After Kafka is ready, create the required topics:

```bash
kubectl apply -f kubernetes/deployments/kafka-topics-job.yaml
kubectl logs job/kafka-topics-setup -n ai-data-platform
```

The topics Job creates all five platform topics with correct partition counts and retention:
- `products.raw.v1` (3 partitions, 7-day retention)
- `products.validated.v1` (3 partitions, 7-day retention)
- `products.invalid.v1` (1 partition, 7-day retention)
- `pipeline.events.v1` (1 partition, 3-day retention)
- `data-quality.events.v1` (1 partition, 3-day retention)

To diagnose Kafka from inside the cluster:

```bash
kubectl exec deployment/kafka -n ai-data-platform -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:29092 --list
kubectl exec deployment/kafka -n ai-data-platform -- /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:29092
```

## Applying All Manifests

To deploy the full platform in the correct order:

```bash
# 1. Namespace
kubectl apply -f kubernetes/namespaces/

# 2. ConfigMaps and Secrets
kubectl apply -f kubernetes/config/
bash scripts/create-local-secrets.sh

# 3. Infrastructure services (Kafka, MinIO, PostgreSQL)
kubectl apply -f kubernetes/deployments/kafka-deployment.yaml
kubectl apply -f kubernetes/deployments/kafka-service.yaml
kubectl apply -f kubernetes/deployments/minio-service.yaml
kubectl apply -f kubernetes/deployments/postgresql-service.yaml

# 4. Kafka topics
kubectl apply -f kubernetes/deployments/kafka-topics-job.yaml

# 5. Application services
kubectl apply -f kubernetes/deployments/ingestion-deployment.yaml
kubectl apply -f kubernetes/deployments/processor-deployment.yaml
kubectl apply -f kubernetes/deployments/raw-writer-deployment.yaml
kubectl apply -f kubernetes/deployments/lake-writer-deployment.yaml
kubectl apply -f kubernetes/deployments/warehouse-loader-deployment.yaml
kubectl apply -f kubernetes/deployments/api-deployment.yaml
kubectl apply -f kubernetes/deployments/api-service.yaml
```

## Port Mappings

The kind config maps host ports to NodePort services inside the cluster, mirroring the Docker Compose layout:

| Host Port | Container Port | Service |
|-----------|---------------|---------|
| 9092 | 30092 | Kafka |
| 9000 | 30090 | MinIO API |
| 9001 | 30091 | MinIO Console |
| 8000 | 30080 | FastAPI |

## Troubleshooting

```bash
# Check kind is installed
kind version

# List existing clusters
kind get clusters

# Check kubectl context
kubectl config get-contexts

# View cluster events
kubectl get events -A --sort-by='.lastTimestamp'

# Describe a node for resource info
kubectl describe node kind-ai-data-platform-control-plane

# Verify ConfigMaps
kubectl get configmaps -n ai-data-platform
kubectl describe configmap platform-config -n ai-data-platform

# Verify Secrets
kubectl get secrets -n ai-data-platform
```
