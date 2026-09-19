# kubernetes/

Kubernetes manifests for local kind deployment (Milestone 8). Cloud deployment topology is defined in `ai/SPECIFICATION.md`.

## Directory Structure

```text
kubernetes/
├── kind/
│   └── kind-config.yaml       # kind cluster configuration
├── namespaces/
│   └── platform-namespace.yaml # Platform namespace definition
├── deployments/
│   ├── ingestion-deployment.yaml   # Ingestion service Deployment (TASK-071)
│   ├── processor-deployment.yaml   # Processor service Deployment (TASK-072)
│   ├── raw-writer-deployment.yaml  # Raw Writer service Deployment (TASK-073)
│   ├── lake-writer-deployment.yaml # Lake Writer service Deployment (TASK-074)
│   ├── warehouse-loader-deployment.yaml # Warehouse Loader Deployment (TASK-075)
│   ├── api-deployment.yaml         # API service Deployment (TASK-076)
│   ├── api-service.yaml            # API service ClusterIP Service (TASK-076)
│   ├── kafka-deployment.yaml       # Kafka broker Deployment (TASK-077)
│   ├── kafka-service.yaml          # Kafka NodePort Service (TASK-077)
│   └── kafka-topics-job.yaml       # Kafka topic creation Job (TASK-077)
└── README.md                   # This file
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

All platform workloads run in the `ai-data-platform` namespace. This keeps them isolated from other local clusters and provides a consistent target for later deployment tasks (TASK-071 through TASK-079).

```bash
kubectl get all -n ai-data-platform
```

## Deployments

Application service deployments live in `deployments/`. Each Deployment targets the `ai-data-platform` namespace and uses consistent `app.kubernetes.io` labels.

### Ingestion (TASK-071)

```bash
kubectl apply -f kubernetes/deployments/ingestion-deployment.yaml
kubectl get deployment ingestion -n ai-data-platform
kubectl logs deployment/ingestion -n ai-data-platform
```

The ingestion Deployment runs the source adapter fetch-publish loop. It does not expose inbound ports — it is a Kafka producer only. Configuration is externalized via environment variables; `BESTBUY_API_KEY` references a Secret (optional until TASK-078 creates it).

### Processor (TASK-072)

```bash
kubectl apply -f kubernetes/deployments/processor-deployment.yaml
kubectl get deployment processor -n ai-data-platform
kubectl logs deployment/processor -n ai-data-platform
```

The processor Deployment consumes raw events from Kafka, validates and normalizes them, applies deduplication, and publishes valid records to the validated topic. Invalid records are routed to the invalid topic with diagnostic context. Like ingestion, it does not expose inbound ports — it is a Kafka consumer/producer only. Configuration uses `APP_KAFKA_GROUP_ID` to identify the consumer group.

### Raw Writer (TASK-073)

```bash
kubectl apply -f kubernetes/deployments/raw-writer-deployment.yaml
kubectl get deployment raw-writer -n ai-data-platform
kubectl logs deployment/raw-writer -n ai-data-platform
```

The raw writer Deployment consumes raw events from Kafka and persists them to Bronze (MinIO) as Parquet files. It implements at-least-once delivery with idempotent processing. MinIO credentials (`APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY`) are sourced from a Secret (optional until TASK-078 creates it).

### Lake Writer (TASK-074)

```bash
kubectl apply -f kubernetes/deployments/lake-writer-deployment.yaml
kubectl get deployment lake-writer -n ai-data-platform
kubectl logs deployment/lake-writer -n ai-data-platform
```

The lake writer Deployment consumes validated events from Kafka and persists them to Silver (MinIO) as Parquet files. It implements at-least-once delivery with idempotent processing using deterministic S3 keys derived from `event_id`. MinIO credentials (`APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY`) are sourced from a Secret (optional until TASK-078 creates it).

### Warehouse Loader (TASK-075)

```bash
kubectl apply -f kubernetes/deployments/warehouse-loader-deployment.yaml
kubectl get deployment warehouse-loader -n ai-data-platform
kubectl logs deployment/warehouse-loader -n ai-data-platform
```

The warehouse loader Deployment reads Silver Parquet from MinIO and loads curated data into PostgreSQL with idempotent upserts. Unlike the Kafka-consuming services, it connects to PostgreSQL and object storage only. Database credentials (`WAREHOUSE_DB_PASSWORD`) and MinIO credentials (`APP_MINIO_ACCESS_KEY`, `APP_MINIO_SECRET_KEY`) are sourced from a Secret (optional until TASK-078 creates it). This deployment does not run Alembic migrations.

### API (TASK-076)

```bash
kubectl apply -f kubernetes/deployments/api-deployment.yaml
kubectl apply -f kubernetes/deployments/api-service.yaml
kubectl get deployment api -n ai-data-platform
kubectl get service api -n ai-data-platform
kubectl logs deployment/api -n ai-data-platform
```

The API Deployment runs the FastAPI application providing synchronous HTTP access to serving and analytics data. It is the only service that exposes inbound ports (port 8000) and has a corresponding ClusterIP Service for in-cluster access. Database password (`WAREHOUSE_DB_PASSWORD`) is sourced from a Secret (optional until TASK-078 creates it).

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

## Port Mappings

The kind config maps host ports to NodePort services inside the cluster, mirroring the Docker Compose layout:

| Host Port | Container Port | Service |
|-----------|---------------|---------|
| 9092 | 30092 | Kafka |
| 9000 | 30090 | MinIO API |
| 9001 | 30091 | MinIO Console |
| 8000 | 30080 | FastAPI |

These are configured for later tasks. No services are deployed by TASK-070.

## What TASK-070 Does NOT Do

- Does not deploy any application services (TASK-071+)
- Does not deploy Kafka, MinIO, or PostgreSQL (TASK-077+)
- Does not configure Helm (TASK-080+)
- Does not set up ConfigMaps, Secrets, or health probes (TASK-078, TASK-079)

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
```
