terraform {
  backend "s3" {
    bucket         = "ai-data-platform-terraform"
    key            = "infrastructure/terraform.tfstate"
    region         = "eu-west-1"
    encrypt        = true
    dynamodb_table = "ai-data-platform-terraform-locks"
  }
}
