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

## Implementation Progress

| Module     | Task     | Status      |
|------------|----------|-------------|
| networking | TASK-117 | Complete    |
| ecr        | TASK-118 | Complete    |
| s3         | TASK-119 | Pending     |
| rds        | TASK-120 | Pending     |
| eks        | TASK-121 | Pending     |
| iam        | TASK-122 | Pending     |
