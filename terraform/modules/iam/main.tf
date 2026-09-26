# IAM module — Service roles, IRSA, and least-privilege policies.
# Implementation: TASK-122

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  namespace   = "ai-data-platform"
  account_id  = data.aws_caller_identity.current.account_id

  s3_services_with_write = {
    raw-writer  = "bronze"
    lake-writer = "silver"
  }

  s3_services_with_read = {
    warehouse-loader = "silver"
  }

  db_services = toset(["warehouse-loader", "api", "agent"])
}

# ------------------------------------------------------------------------------
# Data sources for ARN scoping
# ------------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# ------------------------------------------------------------------------------
# IRSA roles — one per platform service
# ------------------------------------------------------------------------------

resource "aws_iam_role" "service" {
  for_each = var.service_accounts

  name = "${local.name_prefix}-${each.key}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.eks_oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.eks_oidc_provider_url}:aud" = "sts.amazonaws.com"
          "${var.eks_oidc_provider_url}:sub" = "system:serviceaccount:${local.namespace}:${each.value}"
        }
      }
    }]
  })

  tags = merge(var.tags, {
    "service" = each.key
  })
}

# ------------------------------------------------------------------------------
# CloudWatch Logs — all services
# ------------------------------------------------------------------------------

resource "aws_iam_policy" "cloudwatch_logs" {
  for_each = var.service_accounts

  name        = "${local.name_prefix}-${each.key}-logs"
  description = "CloudWatch Logs access for ${each.key}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
      ]
      Resource = "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/eks/${var.eks_cluster_name}/*"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "cloudwatch_logs" {
  for_each = var.service_accounts

  role       = aws_iam_role.service[each.key].name
  policy_arn = aws_iam_policy.cloudwatch_logs[each.key].arn
}

# ------------------------------------------------------------------------------
# ECR pull — all services
# ------------------------------------------------------------------------------

resource "aws_iam_policy" "ecr_pull" {
  name        = "${local.name_prefix}-ecr-pull"
  description = "ECR pull access for platform repositories"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
        ]
        Resource = values(var.ecr_repository_arns)
      },
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecr_pull" {
  for_each = var.service_accounts

  role       = aws_iam_role.service[each.key].name
  policy_arn = aws_iam_policy.ecr_pull.arn
}

# ------------------------------------------------------------------------------
# S3 write — raw-writer (bronze), lake-writer (silver)
# ------------------------------------------------------------------------------

resource "aws_iam_policy" "s3_write" {
  for_each = local.s3_services_with_write

  name        = "${local.name_prefix}-${each.key}-s3-write"
  description = "S3 write access to ${each.value} prefix for ${each.key}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:ListBucket"]
        Resource = [var.data_bucket_arn]
        Condition = {
          StringLike = {
            "s3:prefix" = "${each.value}/*"
          }
        }
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = ["${var.data_bucket_arn}/${each.value}/*"]
      },
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "s3_write" {
  for_each = local.s3_services_with_write

  role       = aws_iam_role.service[each.key].name
  policy_arn = aws_iam_policy.s3_write[each.key].arn
}

# ------------------------------------------------------------------------------
# S3 read — warehouse-loader (silver)
# ------------------------------------------------------------------------------

resource "aws_iam_policy" "s3_read" {
  for_each = local.s3_services_with_read

  name        = "${local.name_prefix}-${each.key}-s3-read"
  description = "S3 read access to ${each.value} prefix for ${each.key}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:ListBucket"]
        Resource = [var.data_bucket_arn]
        Condition = {
          StringLike = {
            "s3:prefix" = "${each.value}/*"
          }
        }
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = ["${var.data_bucket_arn}/${each.value}/*"]
      },
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "s3_read" {
  for_each = local.s3_services_with_read

  role       = aws_iam_role.service[each.key].name
  policy_arn = aws_iam_policy.s3_read[each.key].arn
}

# ------------------------------------------------------------------------------
# Secrets Manager read — warehouse-loader, api, agent
# ------------------------------------------------------------------------------

resource "aws_iam_policy" "secrets_read" {
  name        = "${local.name_prefix}-secrets-read"
  description = "Secrets Manager read access for database credentials"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
      ]
      Resource = "arn:aws:secretsmanager:${var.aws_region}:${local.account_id}:secret:${local.name_prefix}-*"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "secrets_read" {
  for_each = local.db_services

  role       = aws_iam_role.service[each.key].name
  policy_arn = aws_iam_policy.secrets_read.arn
}
