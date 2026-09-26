variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "eks_cluster_name" {
  description = "EKS cluster name for IAM trust policies"
  type        = string
}

variable "eks_oidc_provider_arn" {
  description = "EKS OIDC provider ARN for IRSA roles"
  type        = string
}

variable "eks_oidc_provider_url" {
  description = "EKS OIDC issuer URL (without https://) for IRSA trust conditions"
  type        = string
}

variable "data_bucket_arn" {
  description = "ARN of the S3 data lake bucket"
  type        = string
}

variable "ecr_repository_arns" {
  description = "Map of ECR repository ARNs keyed by service name"
  type        = map(string)
  default     = {}
}

variable "service_accounts" {
  description = "Map of Kubernetes service account names keyed by service name"
  type        = map(string)
  default = {
    ingestion        = "ingestion"
    processor        = "processor"
    raw-writer       = "raw-writer"
    lake-writer      = "lake-writer"
    warehouse-loader = "warehouse-loader"
    api              = "api"
    agent            = "agent"
  }
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
