output "repository_urls" {
  description = "ECR repository URLs keyed by service name"
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}

output "repository_arns" {
  description = "ECR repository ARNs keyed by service name"
  value       = { for name, repo in aws_ecr_repository.this : name => repo.arn }
}

output "repository_names" {
  description = "ECR repository names keyed by service name"
  value       = { for name, repo in aws_ecr_repository.this : name => repo.name }
}
