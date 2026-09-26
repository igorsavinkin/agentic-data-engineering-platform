module "networking" {
  source = "./modules/networking"

  project_name       = var.project_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = var.tags
}

module "ecr" {
  source = "./modules/ecr"

  project_name  = var.project_name
  environment   = var.environment
  service_names = var.ecr_service_names
  tags          = var.tags
}

module "s3" {
  source = "./modules/s3"

  project_name               = var.project_name
  environment                = var.environment
  enable_deletion_protection = var.enable_deletion_protection
  tags                       = var.tags
}

module "rds" {
  source = "./modules/rds"

  project_name               = var.project_name
  environment                = var.environment
  private_subnet_ids         = module.networking.private_subnet_ids
  security_group_id          = module.networking.rds_security_group_id
  instance_class             = var.rds_instance_class
  db_name                    = var.rds_db_name
  username                   = var.rds_username
  password                   = var.rds_password
  enable_deletion_protection = var.enable_deletion_protection
  tags                       = var.tags
}

module "eks" {
  source = "./modules/eks"

  project_name            = var.project_name
  environment             = var.environment
  private_subnet_ids      = module.networking.private_subnet_ids
  cluster_security_group_id = module.networking.eks_cluster_security_group_id
  cluster_version         = var.eks_cluster_version
  cluster_public_endpoint = var.eks_cluster_public_endpoint
  service_cidr            = var.eks_service_cidr
  general_node_instance_types = var.eks_general_node_instance_types
  general_node_desired_size   = var.eks_general_node_desired_size
  general_node_min_size       = var.eks_general_node_min_size
  general_node_max_size       = var.eks_general_node_max_size
  kafka_node_instance_types   = var.eks_kafka_node_instance_types
  kafka_node_desired_size     = var.eks_kafka_node_desired_size
  kafka_node_min_size         = var.eks_kafka_node_min_size
  kafka_node_max_size         = var.eks_kafka_node_max_size
  tags                        = var.tags
}

module "iam" {
  source = "./modules/iam"

  project_name          = var.project_name
  environment           = var.environment
  eks_cluster_name      = module.eks.cluster_name
  eks_oidc_provider_arn = module.eks.oidc_provider_arn
  eks_oidc_provider_url = module.eks.oidc_provider_url
  data_bucket_arn       = module.s3.data_bucket_arn
  ecr_repository_arns   = module.ecr.repository_arns
  tags                  = var.tags
}
