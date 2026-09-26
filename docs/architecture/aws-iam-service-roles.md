# AWS IAM — Service Roles and IRSA

## Overview

The IAM module implements least-privilege IAM roles for each platform service,
mapped to Kubernetes service accounts via IRSA (IAM Roles for Service Accounts).
Each role uses an OIDC trust policy that restricts `sts:AssumeRoleWithWebIdentity`
to a specific namespace and service account.

## IAM Topology

```text
EKS OIDC Provider
├── Trust: sts:AssumeRoleWithWebIdentity
├── Condition: aud = sts.amazonaws.com
└── Condition: sub = system:serviceaccount:ai-data-platform:<service-account>

Service Roles (one per pod identity):
├── ingestion        → CloudWatch Logs, ECR pull
├── processor        → CloudWatch Logs, ECR pull
├── raw-writer       → CloudWatch Logs, ECR pull, S3 bronze/* write
├── lake-writer      → CloudWatch Logs, ECR pull, S3 silver/* write
├── warehouse-loader → CloudWatch Logs, ECR pull, S3 silver/* read, Secrets Manager
├── api              → CloudWatch Logs, ECR pull, Secrets Manager
└── agent            → CloudWatch Logs, ECR pull, Secrets Manager

Shared Policies:
├── ecr-pull         → All services (ECR BatchGetImage, GetDownloadUrlForLayer)
├── secrets-read     → warehouse-loader, api, agent (Secrets Manager GetSecretValue)
└── Per-service      → CloudWatch Logs, S3 write/read scoped to prefix
```

## Least-Privilege Design

| Service | S3 | Secrets Manager | ECR | CloudWatch Logs |
|---------|----|-----------------|-----|-----------------|
| ingestion | — | — | Pull | /aws/eks/\<cluster\>/\* |
| processor | — | — | Pull | /aws/eks/\<cluster\>/\* |
| raw-writer | bronze/\* write | — | Pull | /aws/eks/\<cluster\>/\* |
| lake-writer | silver/\* write | — | Pull | /aws/eks/\<cluster\>/\* |
| warehouse-loader | silver/\* read | GetSecretValue | Pull | /aws/eks/\<cluster\>/\* |
| api | — | GetSecretValue | Pull | /aws/eks/\<cluster\>/\* |
| agent | — | GetSecretValue | Pull | /aws/eks/\<cluster\>/\* |

## IRSA Trust Policy

Each role's trust policy restricts assumption to a single Kubernetes service
account:

```json
{
  "Effect": "Allow",
  "Principal": { "Federated": "<oidc-provider-arn>" },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "<oidc-provider-url>:aud": "sts.amazonaws.com",
      "<oidc-provider-url>:sub": "system:serviceaccount:ai-data-platform:<sa-name>"
    }
  }
}
```

## Variables

| Variable | Description |
|----------|-------------|
| `eks_oidc_provider_url` | OIDC issuer URL (without `https://`) for trust conditions |
| `data_bucket_arn` | S3 data lake bucket ARN for S3 policy scoping |
| `ecr_repository_arns` | Map of ECR repository ARNs for pull policy scoping |
| `service_accounts` | Map of K8s service account names per service |

## Outputs

| Output | Description |
|--------|-------------|
| `service_role_arns` | Map of IAM role ARNs keyed by service name |
| `ecr_pull_policy_arn` | Shared ECR pull policy ARN |
| `secrets_read_policy_arn` | Secrets Manager read policy ARN |

## Security

- No wildcard permissions except `ecr:GetAuthorizationToken` (AWS requires `*` resource)
- S3 policies scoped to specific prefixes (bronze, silver)
- Secrets Manager scoped to `${name_prefix}-*` ARN pattern
- CloudWatch Logs scoped to the EKS cluster log group
- No credentials, access keys, or secrets in Terraform configuration
