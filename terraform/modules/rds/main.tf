# RDS module — PostgreSQL for serving and analytical queries.
# Implementation: TASK-120

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# ------------------------------------------------------------------------------
# DB subnet group — places RDS in private subnets
# ------------------------------------------------------------------------------

resource "aws_db_subnet_group" "this" {
  name        = "${local.name_prefix}-rds"
  subnet_ids  = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${local.name_prefix}-rds-subnet-group"
  })
}

# ------------------------------------------------------------------------------
# RDS instance — PostgreSQL
#
# Instance sizing: db.t3.medium is the default for dev/staging.
# 2 vCPU, 4 GiB RAM — sufficient for analytical query workloads at
# portfolio scale. Production should scale to db.r6g.large or larger
# based on measured query performance and connection count.
#
# Credentials are passed as variables. In production, these should come
# from AWS Secrets Manager (TASK-122 IAM module wires service access).
# ------------------------------------------------------------------------------

resource "aws_db_instance" "this" {
  identifier = "${local.name_prefix}-postgresql"

  engine         = "postgres"
  engine_version = "16.4"
  instance_class = var.instance_class

  db_name  = var.db_name
  username = var.username
  password = var.password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  backup_retention_period = var.backup_retention_days
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  deletion_protection       = var.enable_deletion_protection
  skip_final_snapshot       = !var.enable_deletion_protection
  final_snapshot_identifier = var.enable_deletion_protection ? "${local.name_prefix}-final" : null

  tags = merge(var.tags, {
    Name      = "${local.name_prefix}-postgresql"
    Component = "warehouse"
  })
}
