variable "aws_region" {
  description = "AWS region for backend resources"
  type        = string
  default     = "eu-north-1"
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Bucket name must be 3-63 characters, lowercase letters, numbers, hyphens, and periods."
  }
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for Terraform state locking"
  type        = string
  default     = "ai-data-platform-terraform-locks"
}

variable "environment" {
  description = "Environment tag for backend resources"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name used for resource tagging"
  type        = string
  default     = "ai-data-platform"
}
