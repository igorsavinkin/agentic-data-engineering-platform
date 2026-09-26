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

Initialize with an environment:

```bash
cd terraform
terraform init
terraform plan -var-file=envs/dev.tfvars -var="rds_password=CHANGE_ME"
terraform apply -var-file=envs/dev.tfvars -var="rds_password=CHANGE_ME"
```

## Environment Separation

Each environment uses its own `.tfvars` file under `envs/`. State is isolated
by configuring the backend key per environment at init time:

```bash
terraform init -backend-config="key=envs/dev/terraform.tfstate"
```

## Security

- Credentials are never committed to Git.
- Sensitive variables (e.g., `rds_password`) are passed at plan/apply time.
- State is encrypted at rest in S3.
- State locking uses DynamoDB to prevent concurrent modifications.

## Implementation Progress

| Module     | Task     | Status      |
|------------|----------|-------------|
| networking | TASK-117 | Pending     |
| ecr        | TASK-118 | Pending     |
| s3         | TASK-119 | Pending     |
| rds        | TASK-120 | Pending     |
| eks        | TASK-121 | Pending     |
| iam        | TASK-122 | Pending     |
