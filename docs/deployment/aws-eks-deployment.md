# AWS EKS Deployment Guide

This guide deploys the complete AI Data Platform to AWS using Terraform and Helm.

## Architecture

```
AWS (eu-north-1)
├── VPC (10.0.0.0/16)
│   ├── Public subnets (NAT Gateway)
│   └── Private subnets (EKS, RDS)
│
├── EKS Cluster (1.35, public API endpoint)
│   ├── General node group (t3.medium, 1 node)
│   │   ├── ingestion, processor, raw-writer, lake-writer
│   │   └── warehouse-loader, api
│   └── Kafka node group (t3.medium, 1 node, tainted)
│       └── Strimzi Kafka (1 broker, JBOD 50Gi)
│
├── RDS PostgreSQL 16.4 (db.t3.small, 20GiB gp3)
├── S3 Data Lake (bronze/silver/gold prefixes)
└── ECR (7 repositories)
```

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| AWS CLI | 2.x | AWS authentication and EKS |
| Terraform | >= 1.5.0 | Infrastructure provisioning |
| kubectl | 1.31+ | Kubernetes management |
| Helm | 3.x | Chart deployment |
| Docker | 24+ | Container image builds |
| Python | 3.12+ | Verification scripts |

## Step 1: Bootstrap Terraform Backend

One-time setup for remote state storage (S3 + DynamoDB lock):

```bash
cd terraform/bootstrap
terraform init
terraform apply -var-file=dev.tfvars
```

This creates the S3 bucket and DynamoDB table for state management.

## Step 2: Provision AWS Infrastructure

```bash
# Review what will be created
./scripts/deploy-eks.sh plan

# Apply (requires RDS password)
export TF_VAR_rds_password="<strong-password>"
./scripts/deploy-eks.sh apply
```

The `apply` command performs these steps in order:

1. **Terraform apply** — creates VPC, EKS, RDS, S3, ECR, IAM
2. **Configure kubectl** — updates kubeconfig for the EKS cluster
3. **Build and push images** — Docker build + push to ECR for 6 services
4. **Install Strimzi operator** — Helm install from quay.io
5. **Deploy Strimzi Kafka** — 3-broker cluster on dedicated nodes
6. **Create Kafka topics** — 5 platform topics with replication factor 3
7. **Create Kubernetes secrets** — database credentials, API keys
8. **Deploy Helm chart** — all platform services with EKS values

### What Terraform Creates

| Resource | Module | Count |
|----------|--------|-------|
| VPC + subnets + IGW + NAT | networking | 1 |
| Security groups (eks-cluster, eks-nodes, rds) | networking | 3 |
| ECR repositories | ecr | 7 |
| S3 data lake bucket | s3 | 1 |
| RDS PostgreSQL instance | rds | 1 |
| EKS cluster + OIDC provider | eks | 1 |
| EKS node groups (general + kafka) | eks | 2 |
| IAM IRSA roles + policies | iam | 7 |

### Estimated Monthly Cost (dev)

| Resource | Approximate Cost |
|----------|-----------------|
| EKS cluster | $73 |
| General node (1x t3.medium) | $30 |
| Kafka node (1x t3.medium) | $30 |
| NAT Gateway | $32 |
| RDS (db.t3.small) | $29 |
| S3 (minimal data) | $1 |
| ECR (7 repos) | $1 |
| **Total** | **~$196/month** |

Costs vary with usage. The EKS cluster management fee and NAT Gateway are the largest fixed cost drivers.

## Step 3: Verify Deployment

```bash
# Quick status check
./scripts/deploy-eks.sh status

# Full E2E verification (bucket name from terraform output)
BUCKET=$(cd terraform && terraform output -raw s3_data_bucket)
python scripts/verify_eks_deployment.py --bucket-name "$BUCKET"
```

The verification script checks:
- All pods are running and ready
- API health endpoint responds
- Kafka topics exist with correct replication
- S3 bronze/ prefix accessible via raw-writer IRSA
- S3 silver/ prefix accessible via warehouse-loader IRSA
- PostgreSQL RDS connection works
- Data flows through the pipeline (raw + validated topics)
- Parquet objects exist in bronze/ and silver/
- Warehouse tables are loaded
- Agent `/api/v1/agent/ask` responds

## Step 4: Access Services

```bash
# API — via LoadBalancer
kubectl get svc api -n ai-data-platform
# Use the EXTERNAL-IP from the output

# Grafana — via port-forward
kubectl port-forward svc/grafana 3000:3000 -n ai-data-platform
# Open http://localhost:3000 (admin/admin)

# Prometheus — via port-forward
kubectl port-forward svc/prometheus 9090:9090 -n ai-data-platform
```

## Step 5: Trigger Ingestion

```bash
# Trigger a manual ingestion cycle
kubectl exec -n ai-data-platform deploy/ingestion -- \
    python -c "from services.ingestion import main; main()"

# Check raw events in Kafka
kubectl exec -n strimzi $(kubectl get pod -n strimzi -l strimzi.io/name=platform-cluster-kafka -o jsonpath='{.items[0].metadata.name}') -- \
    /opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic products.raw.v1 \
    --from-beginning \
    --max-messages 5
```

## Tear Down

```bash
# Destroy everything (requires confirmation)
./scripts/deploy-eks.sh destroy
```

This removes in this order:
1. Helm release (all platform workloads)
2. Strimzi Kafka cluster and operator
3. Terraform resources (EKS, RDS, S3, ECR, VPC, IAM)

**Warning:** With `enable_deletion_protection = false` (dev default), RDS and S3 are deleted permanently. Set to `true` for staging/production.

## Incremental Updates

### Update application images only

```bash
export IMAGE_TAG=v1.2.0
./scripts/deploy-eks.sh images
./scripts/deploy-eks.sh helm
```

### Update infrastructure

```bash
# Edit terraform/envs/dev.tfvars or module files
./scripts/deploy-eks.sh plan   # review changes
./scripts/deploy-eks.sh apply  # apply changes
```

### Update Helm values

```bash
# Edit helm/ai-data-platform/values-eks.yaml
./scripts/deploy-eks.sh helm
```

## Troubleshooting

### Pods stuck in ImagePullBackOff

```bash
# Check ECR login on the node
kubectl describe pod <pod-name> -n ai-data-platform
# Verify the IAM role has ECR pull access
aws iam list-attached-role-policies --role-name <role-name>
```

### Kafka connection refused

```bash
# Check Strimzi Kafka pods
kubectl get pods -n strimzi
kubectl logs -n strimzi -l strimzi.io/name=platform-cluster-kafka --tail=50

# Verify bootstrap service
kubectl get svc -n strimzi platform-cluster-kafka-bootstrap
```

### RDS connection timeout

```bash
# Check RDS is accessible from the VPC
kubectl exec -n ai-data-platform deploy/warehouse-loader -- \
    python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('<rds-endpoint>', 5432)); print('OK'); s.close()"

# Verify security group allows port 5432 from EKS nodes
aws ec2 describe-security-groups --group-ids <rds-sg-id>
```

### S3 permission denied

```bash
# Verify IRSA annotation on the service account
kubectl get sa raw-writer -n ai-data-platform -o yaml
# Check the annotation: eks.amazonaws.com/role-arn

# Test S3 access from the pod (uses prefix-scoped ListBucket)
kubectl exec -n ai-data-platform deploy/raw-writer -- \
    python -c "import boto3; s3=boto3.client('s3'); r=s3.list_objects_v2(Bucket='<bucket>', Prefix='bronze/', MaxKeys=1); print(r.get('KeyCount', 0))"
```

## Security Notes

- No credentials or secrets are committed to Git
- RDS password is passed via `TF_VAR_rds_password` environment variable
- Kubernetes secrets are created from environment variables at deploy time
- IRSA provides per-service AWS credentials (no static AWS keys)
- All S3 buckets have public access blocked
- RDS is in private subnets (no public endpoint)
- EKS API server endpoint is private by default
- NetworkPolicy restricts pod-to-pod traffic
