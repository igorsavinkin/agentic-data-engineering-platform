# Backend resources are provisioned separately via terraform/bootstrap/.
# The bucket and DynamoDB table names must be supplied at init time with
# -backend-config flags (see terraform/bootstrap/README.md).
terraform {
  backend "s3" {
    # bucket         = overridden via -backend-config="bucket=..."
    # key            = overridden via -backend-config="key=..."
    # region         = overridden via -backend-config="region=..."
    # dynamodb_table = overridden via -backend-config="dynamodb_table=..."
    encrypt = true
  }
}
