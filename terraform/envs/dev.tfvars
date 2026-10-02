environment = "dev"

vpc_cidr = "10.0.0.0/16"

aws_region = "eu-north-1"

availability_zones = [
  "eu-north-1a",
  "eu-north-1b",
  "eu-north-1c"
]

# EKS — K8s 1.35 is in standard support until Mar 27, 2027.
# Strimzi 0.45.0 supports K8s 1.25+.
eks_cluster_version            = "1.35"
eks_cluster_public_endpoint    = true
eks_cluster_log_retention_days = 7

# Dev-sized node groups — single nodes per pool.
eks_general_node_instance_types = ["t3.medium"]
eks_general_node_desired_size   = 1
eks_general_node_min_size       = 1
eks_general_node_max_size       = 2

eks_kafka_node_instance_types = ["t3.medium"]
eks_kafka_node_desired_size   = 1
eks_kafka_node_min_size       = 1
eks_kafka_node_max_size       = 1

# RDS — db.t3.small (2 vCPU, 2 GiB) is sufficient for dev workloads.
rds_instance_class = "db.t3.small"
rds_db_name        = "dataplatform"
rds_username       = "platform_admin"

enable_deletion_protection = false

ecr_service_names = [
  "ingestion",
  "processor",
  "raw-writer",
  "lake-writer",
  "warehouse-loader",
  "api",
  "agent",
]

tags = {
  CostCenter = "development"
}

