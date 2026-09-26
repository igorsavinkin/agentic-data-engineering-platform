# Networking module — VPC, subnets, internet gateway, NAT gateway, route tables, security groups.
# Implementation: TASK-117

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
