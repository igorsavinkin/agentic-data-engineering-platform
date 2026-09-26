output "service_role_arns" {
  description = "IAM role ARNs keyed by service name"
  value       = { for name, role in aws_iam_role.service : name => role.arn }
}

output "ecr_pull_policy_arn" {
  description = "Shared ECR pull policy ARN"
  value       = aws_iam_policy.ecr_pull.arn
}

output "secrets_read_policy_arn" {
  description = "Secrets Manager read policy ARN"
  value       = aws_iam_policy.secrets_read.arn
}
