environment = "dev"
aws_region  = "eu-west-1"

vpc_cidr = "10.0.0.0/16"

availability_zones = ["eu-west-1a", "eu-west-1b", "eu-west-1c"]

eks_cluster_version = "1.31"
rds_instance_class  = "db.t3.medium"
rds_db_name         = "dataplatform"
rds_username        = "platform_admin"

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
