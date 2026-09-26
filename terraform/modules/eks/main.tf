# EKS module — Kubernetes cluster for platform services.
# Implementation: TASK-121

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
