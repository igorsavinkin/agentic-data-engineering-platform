# ECR module — Container repositories for each platform service.
# Implementation: TASK-118

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
