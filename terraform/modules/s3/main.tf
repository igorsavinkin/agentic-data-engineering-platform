# S3 module — Data lake storage (Bronze/Silver/Gold Parquet layers).
# Implementation: TASK-119

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
