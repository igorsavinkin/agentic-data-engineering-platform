# kubernetes/

Kubernetes manifests for local kind deployment (Milestone 8). Cloud deployment topology is defined in `ai/SPECIFICATION.md`.

## Directory Structure

```text
kubernetes/
├── kind/
│   └── kind-config.yaml       # kind cluster configuration
├── namespaces/
│   └── platform-namespace.yaml # Platform namespace definition
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
```

Multiple images can be loaded at once:

```bash
bash scripts/kind-cluster.sh load ai-data-platform/ingestion:dev ai-data-platform/processor:dev
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
