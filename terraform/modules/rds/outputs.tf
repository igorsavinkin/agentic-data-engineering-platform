output "endpoint" {
  description = "RDS PostgreSQL connection endpoint"
  value       = aws_db_instance.this.endpoint
}

output "port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "PostgreSQL database name"
  value       = aws_db_instance.this.db_name
}

output "instance_id" {
  description = "RDS instance identifier"
  value       = aws_db_instance.this.id
}
