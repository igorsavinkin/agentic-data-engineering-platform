output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = aws_eks_cluster.this.endpoint
}

output "oidc_provider_arn" {
  description = "OIDC identity provider ARN for IRSA"
  value       = aws_iam_openid_connect_provider.cluster.arn
}

output "oidc_provider_url" {
  description = "OIDC issuer URL (without https://)"
  value       = replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
}

output "cluster_security_group_id" {
  description = "EKS cluster security group ID (from networking module input)"
  value       = var.cluster_security_group_id
}

output "node_role_arn" {
  description = "IAM role ARN assigned to the managed node groups"
  value       = aws_iam_role.nodes.arn
}

output "cluster_certificate_authority" {
  description = "Base64-encoded cluster CA certificate"
  value       = aws_eks_cluster.this.certificate_authority[0].data
}
