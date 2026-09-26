variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for EKS node placement"
  type        = list(string)
}

variable "cluster_security_group_id" {
  description = "Security group ID for the EKS cluster control plane"
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
}

variable "cluster_public_endpoint" {
  description = "Whether to expose the EKS API endpoint publicly"
  type        = bool
  default     = false
}

variable "service_cidr" {
  description = "IPv4 CIDR block for Kubernetes services"
  type        = string
  default     = "172.20.0.0/16"
}

variable "cluster_log_retention_days" {
  description = "CloudWatch log retention for EKS control plane logs"
  type        = number
  default     = 30
}

variable "general_node_instance_types" {
  description = "Instance types for the general-purpose node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "general_node_desired_size" {
  description = "Desired number of general-purpose nodes"
  type        = number
  default     = 2
}

variable "general_node_min_size" {
  description = "Minimum number of general-purpose nodes"
  type        = number
  default     = 1
}

variable "general_node_max_size" {
  description = "Maximum number of general-purpose nodes"
  type        = number
  default     = 4
}

variable "kafka_node_instance_types" {
  description = "Instance types for the Kafka (Strimzi) node group"
  type        = list(string)
  default     = ["t3.large"]
}

variable "kafka_node_desired_size" {
  description = "Desired number of Kafka nodes"
  type        = number
  default     = 3
}

variable "kafka_node_min_size" {
  description = "Minimum number of Kafka nodes"
  type        = number
  default     = 3
}

variable "kafka_node_max_size" {
  description = "Maximum number of Kafka nodes"
  type        = number
  default     = 5
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
