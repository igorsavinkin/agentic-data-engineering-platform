# S3 module — Data lake storage (Bronze/Silver/Gold Parquet layers).
# Implementation: TASK-119

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  bucket_name = "${local.name_prefix}-data-lake"
}

# ------------------------------------------------------------------------------
# S3 bucket
# ------------------------------------------------------------------------------

resource "aws_s3_bucket" "data_lake" {
  bucket = local.bucket_name

  tags = merge(var.tags, {
    Name      = local.bucket_name
    Component = "data-lake"
  })
}

# ------------------------------------------------------------------------------
# Versioning — enables rollback and noncurrent-version lifecycle management
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  versioning_configuration {
    status = "Enabled"
  }
}

# ------------------------------------------------------------------------------
# Encryption — AES-256 at rest (SSE-S3)
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# ------------------------------------------------------------------------------
# Public access block
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ------------------------------------------------------------------------------
# Lifecycle rules — per-layer storage transitions and version management
#
# Bronze: raw events replayable from Kafka → aggressive expiration.
# Silver: validated records → moderate transition to IA.
# Gold:   curated analytical datasets → long retention, no expiration.
# Noncurrent versions and incomplete uploads are cleaned up globally.
# ------------------------------------------------------------------------------

resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "bronze-layer"
    status = "Enabled"

    filter {
      prefix = "bronze/"
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  rule {
    id     = "silver-layer"
    status = "Enabled"

    filter {
      prefix = "silver/"
    }

    transition {
      days          = 60
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 180
    }

    noncurrent_version_expiration {
      noncurrent_days = 14
    }
  }

  rule {
    id     = "gold-layer"
    status = "Enabled"

    filter {
      prefix = "gold/"
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
