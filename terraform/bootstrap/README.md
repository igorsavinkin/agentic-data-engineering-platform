# Terraform Backend Bootstrap

One-time provisioning of the S3 bucket and DynamoDB table required by the main
Terraform remote backend. This configuration uses the `local` backend (no
remote state) so it can create the very resources the main configuration needs
before it exists.

## Prerequisites

- Terraform >= 1.5.0
- AWS CLI configured with the `data-platform` profile
- A globally unique bucket name (S3 bucket names are globally unique)

## Usage

### 1. Choose a bucket name

Pick a name that includes a unique suffix (account ID, team initials, or random
string). Example:

```bash
export TF_STATE_BUCKET="ai-data-platform-terraform-dev-abc123"
```

### 2. Initialize

```bash
cd terraform/bootstrap

terraform init
```

### 3. Plan

```bash
terraform plan \
  -var="bucket_name=${TF_STATE_BUCKET}" \
  -var="environment=dev"
```

### 4. Apply

```bash
terraform apply \
  -var="bucket_name=${TF_STATE_BUCKET}" \
  -var="environment=dev"
```

### 5. Configure the main backend

After apply, use the `backend_config_snippet` output to configure the root
Terraform backend. Either copy the values into `terraform/backend.tf` or pass
them at init time:

```bash
cd ../

terraform init \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="key=envs/dev/terraform.tfstate" \
  -backend-config="region=eu-north-1" \
  -backend-config="dynamodb_table=ai-data-platform-terraform-locks" \
  -backend-config="encrypt=true"
```

## Teardown

Bootstrap resources have `prevent_destroy` lifecycle guards. To tear down:

```bash
# Remove the lifecycle guards first (edit main.tf), then:
terraform destroy \
  -var="bucket_name=${TF_STATE_BUCKET}" \
  -var="environment=dev"
```

WARNING: destroying the state bucket deletes all Terraform state. Ensure no
environments depend on it before proceeding.

## Variables

| Variable            | Default                              | Description                                    |
|---------------------|--------------------------------------|------------------------------------------------|
| `aws_region`        | `eu-north-1`                         | AWS region for backend resources               |
| `bucket_name`       | (required)                           | Globally unique S3 bucket name for state       |
| `dynamodb_table_name` | `ai-data-platform-terraform-locks` | DynamoDB table for state locking               |
| `environment`       | `dev`                                | Environment tag                                |
| `project_name`      | `ai-data-platform`                   | Project name for tagging                       |
