# IAM module — Service roles, IRSA, and least-privilege policies.
# Implementation: TASK-122

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
