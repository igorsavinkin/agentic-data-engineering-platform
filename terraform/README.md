# Terraform Infrastructure — AI Data Platform

AWS infrastructure for the AI Data Platform, provisioned with Terraform.

## Structure

```text
terraform/
├── main.tf           # Root module — composes child modules
├── variables.tf      # Root input variables
├── outputs.tf        # Root outputs
├── versions.tf       # Terraform and provider version constraints
├── providers.tf      # AWS provider configuration
├── backend.tf        # S3 remote state backend
├── envs/             # Environment-specific variable files
│   ├── dev.tfvars
│   └── staging.tfvars
└── modules/          # Reusable child modules
    ├── networking/   # VPC, subnets, gateways, route tables (TASK-117)
    ├── ecr/          # Container repositories (TASK-118)
    ├── s3/           # Data lake storage (TASK-119)
    ├── rds/          # PostgreSQL warehouse (TASK-120)
    ├── eks/          # Kubernetes cluster (TASK-121)
    └── iam/          # Service roles and policies (TASK-122)
```

## Prerequisites

- Terraform >= 1.5.0
- AWS CLI configured with appropriate credentials
- S3 bucket `ai-data-platform-terraform` for state storage
- DynamoDB table `ai-data-platform-terraform-locks` for state locking

## Usage

Initialize with an environment — each environment requires its own state key:

```bash
cd terraform

# Initialize with environment-specific state isolation
terraform init -backend-config="key=envs/dev/terraform.tfstate"

terraform plan -var-file=envs/dev.tfvars -var="rds_password=CHANGE_ME"
terraform apply -var-file=envs/dev.tfvars -var="rds_password=CHANGE_ME"
```

## Environment Separation

Each environment uses its own `.tfvars` file under `envs/` and a separate
state key. Always initialize with the environment-specific backend config:

```bash
# Dev
terraform init -backend-config="key=envs/dev/terraform.tfstate"
terraform plan -var-file=envs/dev.tfvars -var="rds_password=CHANGE_ME"

# Staging
terraform init -backend-config="key=envs/staging/terraform.tfstate"
terraform plan -var-file=envs/staging.tfvars -var="rds_password=CHANGE_ME"
```

## Security

- Credentials are never committed to Git.
- Sensitive variables (e.g., `rds_password`) are passed at plan/apply time.
- State is encrypted at rest in S3.
- State locking uses DynamoDB to prevent concurrent modifications.

## Network Topology

The networking module provisions a multi-AZ VPC with public and private tiers:

```text
VPC (var.vpc_cidr, default 10.0.0.0/16)
├── Public subnets (one per AZ, /24 each)
│   ├── NAT Gateway (first AZ)
│   └── Internet Gateway → default route 0.0.0.0/0
├── Private subnets (one per AZ, /24 each)
│   ├── EKS worker nodes
│   └── RDS PostgreSQL instances
└── Security groups
    ├── eks-cluster — API port 443 from VPC CIDR
    ├── eks-nodes   — self-referencing node-to-node, kubelet from cluster SG
    └── rds         — port 5432 from eks-nodes SG only
```

- Public subnets carry `kubernetes.io/role/elb` tags for external load balancers.
- Private subnets carry `kubernetes.io/role/internal-elb` tags for internal load balancers.
- RDS ingress is restricted to the EKS node security group (no direct VPC CIDR access).
- All outbound traffic is permitted; inbound is scoped per security group.

## Container Registries

The ECR module creates one repository per platform service with:

- **Immutable tags** — prevents accidental overwrites
- **Scan on push** — automatic vulnerability scanning
- **AES256 encryption** — at-rest encryption enabled
- **Lifecycle policies** — expire untagged images after 7 days
- **EKS pull access** — granted via node IAM role (TASK-122)

Services: ingestion, processor, raw-writer, lake-writer, warehouse-loader, api, agent.

## Data Lake Storage

The S3 module creates a single bucket (`{project}-{env}-data-lake`) with prefix-based
separation for the three Parquet layers:

```text
ai-data-platform-dev-data-lake/
├── bronze/   ← Raw Writer (products.raw.v1)
├── silver/   ← Lake Writer (products.validated.v1)
└── gold/     ← Airflow batch transformations
```

Bucket configuration:

- **Versioning** — enabled for rollback and noncurrent-version lifecycle
- **Encryption** — AES-256 (SSE-S3) with bucket key
- **Public access** — all four public access blocks enabled
- **Lifecycle policies**:
  - Bronze: STANDARD_IA after 30 days, expire after 90 days (replayable from Kafka)
  - Silver: STANDARD_IA after 60 days, expire after 180 days
  - Gold: STANDARD_IA after 90 days, no expiration (permanent analytical data)
  - Noncurrent versions: cleaned up per layer (7/14/30 days)
  - Incomplete multipart uploads: aborted after 7 days

IAM access for raw-writer, lake-writer, and Airflow is granted by the IAM module (TASK-122).

## PostgreSQL Warehouse

The RDS module provisions a managed PostgreSQL instance for the serving and
analytical query layer:

- **Engine**: PostgreSQL 16.4
- **Instance class**: `db.t3.medium` (dev/staging default; 2 vCPU, 4 GiB RAM)
- **Storage**: 20 GiB gp3, auto-scaling to 100 GiB, encrypted at rest
- **Placement**: private subnets via DB subnet group (no public accessibility)
- **Security**: ingress restricted to the EKS node security group (port 5432)
- **Backups**: automated, 7-day retention (configurable), backup window 03:00-04:00 UTC
- **Maintenance**: Monday 04:00-05:00 UTC
- **Deletion protection**: controlled by `enable_deletion_protection` variable; final snapshot taken when enabled

Credentials are passed as variables at plan/apply time and never committed to Git.
Secrets Manager integration for runtime credential injection is handled by the IAM module (TASK-122).

## EKS Cluster

The EKS module provisions a managed Kubernetes cluster for all platform services and Kafka:

- **Cluster**: EKS 1.31, private API endpoint by default, control-plane logging (api, audit, authenticator, controllerManager, scheduler)
- **Node groups**: general-purpose (t3.medium, 1–4 nodes) and dedicated Kafka (t3.large, 3–5 nodes, tainted `dedicated=kafka:NoSchedule`)
- **IRSA**: OIDC identity provider created from the cluster issuer for IAM Roles for Service Accounts
- **Kafka**: Strimzi-based deployment targeting the dedicated Kafka node group (see `kubernetes/deployments/strimzi-kafka-eks.yaml`)

Full cluster documentation: [`docs/architecture/aws-eks-cluster.md`](../docs/architecture/aws-eks-cluster.md).

## IAM Service Roles

The IAM module creates least-privilege IRSA roles for each platform service:

- **IRSA roles**: one per service (ingestion, processor, raw-writer, lake-writer, warehouse-loader, api, agent), each with an OIDC trust policy scoped to a specific Kubernetes service account
- **CloudWatch Logs**: per-service policy for `/aws/eks/<cluster>/*` log groups
- **ECR pull**: shared policy granting BatchGetImage/GetDownloadUrlForLayer on platform repositories
- **S3 write**: raw-writer → bronze/\*, lake-writer → silver/\*
- **S3 read**: warehouse-loader → silver/\*
- **Secrets Manager**: warehouse-loader, api, agent → GetSecretValue on `${name_prefix}-*`

Full IAM documentation: [`docs/architecture/aws-iam-service-roles.md`](../docs/architecture/aws-iam-service-roles.md).

## Implementation Progress

| Module     | Task     | Status      |
|------------|----------|-------------|
| networking | TASK-117 | Complete    |
| ecr        | TASK-118 | Complete    |
| s3         | TASK-119 | Complete    |
| rds        | TASK-120 | Complete    |
| eks        | TASK-121 | Complete    |
| iam        | TASK-122 | Complete    |
