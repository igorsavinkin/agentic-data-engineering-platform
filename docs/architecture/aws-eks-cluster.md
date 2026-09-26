# AWS EKS Cluster Configuration

**Implementation:** TASK-121

## Overview

The platform runs on an AWS EKS cluster provisioned by Terraform (`terraform/modules/eks/`).
The cluster hosts all platform services and a Strimzi-based Kafka deployment.

## Cluster Architecture

| Component | Details |
|---|---|
| Kubernetes version | 1.31 (configurable via `eks_cluster_version`) |
| API endpoint | Private by default; public access optional via `eks_cluster_public_endpoint` |
| Service CIDR | 172.20.0.0/16 (configurable via `eks_service_cidr`) |
| Control plane logs | api, audit, authenticator, controllerManager, scheduler |
| Log retention | 30 days (configurable via `cluster_log_retention_days`) |

## Node Groups

### General-Purpose Node Group

Runs platform services: ingestion, processor, raw-writer, lake-writer, warehouse-loader, API, agent.

| Parameter | Default | Variable |
|---|---|---|
| Instance type | t3.medium | `eks_general_node_instance_types` |
| Desired | 2 | `eks_general_node_desired_size` |
| Min | 1 | `eks_general_node_min_size` |
| Max | 4 | `eks_general_node_max_size` |
| Label | `role=general` | |

### Kafka Node Group

Dedicated pool for Strimzi Kafka brokers and ZooKeeper. Uses a taint (`dedicated=kafka:NoSchedule`)
so only Kafka pods with matching tolerations are scheduled here.

| Parameter | Default | Variable |
|---|---|---|
| Instance type | t3.large | `eks_kafka_node_instance_types` |
| Desired | 3 | `eks_kafka_node_desired_size` |
| Min | 3 | `eks_kafka_node_min_size` |
| Max | 5 | `eks_kafka_node_max_size` |
| Label | `role=kafka` | |
| Taint | `dedicated=kafka:NoSchedule` | |

## Networking

The cluster is deployed in private subnets. The EKS control plane security group
allows inbound HTTPS (443) from the VPC CIDR. Node-to-node communication and
kubelet access from the control plane are configured in the networking module.

Kafka is reachable from ingestion and processor services within the cluster
via the Strimzi bootstrap service (`platform-cluster-kafka-bootstrap.strimzi.svc:9092`).

## IRSA (IAM Roles for Service Accounts)

The module creates an OIDC identity provider from the cluster's issuer URL.
The IAM module (TASK-122) uses this OIDC provider to create per-service IAM roles
that Kubernetes service accounts assume via IRSA.

## Strimzi Kafka

Kafka runs inside EKS using Strimzi, not Amazon MSK. The Strimzi operator manages
a 3-broker Kafka cluster with 3 ZooKeeper nodes in the `strimzi` namespace.

Key manifests:
- `kubernetes/namespaces/strimzi-namespace.yaml` — namespace
- `kubernetes/deployments/strimzi-kafka-eks.yaml` — Kafka CR targeting the kafka node group

The Kafka CR uses:
- 3 replicas with replication factor 3 for durability
- JBOD storage with 50Gi persistent volumes per broker
- Node selectors and tolerations for the dedicated kafka node group
- Internal listeners on ports 9092 (plaintext) and 9093 (TLS)

## Terraform Variables

All EKS-related variables are prefixed with `eks_` at the root level:

```
eks_cluster_version          — Kubernetes version
eks_cluster_public_endpoint  — public API access toggle
eks_service_cidr             — Kubernetes service CIDR
eks_general_node_*           — general node group sizing
eks_kafka_node_*             — kafka node group sizing
```

## Outputs

| Output | Description |
|---|---|
| `eks_cluster_name` | Cluster name |
| `eks_cluster_endpoint` | API server URL |
| `eks_oidc_provider_arn` | OIDC provider for IRSA |
