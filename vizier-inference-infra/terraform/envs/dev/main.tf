provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  tags = {
    Project = var.project_name
    Env     = var.environment
  }

  resolved_artifacts_bucket_name = coalesce(
    var.s3_artifacts_bucket_name,
    lower("${var.project_name}-${var.environment}-${data.aws_caller_identity.current.account_id}-artifacts")
  )

  backend_ecr_name     = "${var.backend_ecr_repo_name}-${var.environment}"
  biomedparse_ecr_name = "${var.biomedparse_ecr_repo_name}-${var.environment}"
}

module "network" {
  source = "../../modules/network"

  vpc_cidr              = var.vpc_cidr
  public_subnet_cidr    = var.public_subnet_cidr
  public_subnet_cidr_b  = var.public_subnet_cidr_b
  private_subnet_cidr   = var.private_subnet_cidr
  private_subnet_cidr_b = var.private_subnet_cidr_b
  enable_nat_gateway    = var.enable_nat_gateway
  enable_vpc_endpoints  = var.enable_vpc_endpoints
  availability_zone     = var.availability_zone
  availability_zone_b   = var.availability_zone_b
  single_az_mode        = var.single_az_mode
}

module "s3" {
  source = "../../modules/s3"

  bucket_name          = local.resolved_artifacts_bucket_name
  kms_key_arn          = var.s3_kms_key_arn
  cors_allowed_origins = var.frontend_upload_allowed_origins
  tags                 = local.tags
}

module "sqs" {
  source = "../../modules/sqs"

  name     = var.jobs_queue_name
  dlq_name = var.jobs_dlq_name
  tags     = local.tags
}

module "ecr_backend" {
  count  = var.manage_backend_ecr_repository ? 1 : 0
  source = "../../modules/ecr"

  name         = local.backend_ecr_name
  force_delete = var.ecr_force_delete
  tags         = local.tags
}

module "ecr_biomedparse" {
  count  = var.manage_biomedparse_ecr_repository ? 1 : 0
  source = "../../modules/ecr"

  name         = local.biomedparse_ecr_name
  force_delete = var.ecr_force_delete
  tags         = local.tags
}

module "iam_github" {
  source = "../../modules/iam-github"

  github_repo         = var.github_repo
  github_branch       = var.github_branch
  github_environments = ["development", "production"]
  aws_region          = var.aws_region
}

module "rds_postgres" {
  source = "../../modules/rds-postgres"

  name                       = var.rds_instance_identifier
  vpc_id                     = module.network.vpc_id
  subnet_ids                 = module.network.private_subnet_ids
  ingress_security_group_ids = [aws_security_group.fargate_app.id]
  db_name                    = var.rds_db_name
  username                   = var.rds_username
  password                   = var.rds_password
  instance_class             = var.rds_instance_class
  allocated_storage          = var.rds_allocated_storage
  backup_retention_period    = var.rds_backup_retention_days
  skip_final_snapshot        = var.rds_skip_final_snapshot
  final_snapshot_identifier  = trimspace(var.rds_final_snapshot_identifier) != "" ? var.rds_final_snapshot_identifier : null
  deletion_protection        = var.rds_deletion_protection
  apply_immediately          = true
  multi_az                   = false
  tags                       = local.tags
}

locals {
  django_database_url            = "postgresql://${var.rds_username}:${var.rds_password}@${module.rds_postgres.endpoint}:${module.rds_postgres.port}/${var.rds_db_name}?sslmode=require"
  backend_ecr_repository_url     = var.manage_backend_ecr_repository ? module.ecr_backend[0].repository_url : coalesce(trimspace(var.external_backend_ecr_repository_url) != "" ? trimspace(var.external_backend_ecr_repository_url) : null, "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${local.backend_ecr_name}")
  biomedparse_ecr_repository_url = var.manage_biomedparse_ecr_repository ? module.ecr_biomedparse[0].repository_url : coalesce(trimspace(var.external_biomedparse_ecr_repository_url) != "" ? trimspace(var.external_biomedparse_ecr_repository_url) : null, "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${local.biomedparse_ecr_name}")
  backend_image                  = "${local.backend_ecr_repository_url}:${var.backend_image_tag}"
  biomedparse_image              = var.biomedparse_image_override != "" ? var.biomedparse_image_override : "${local.biomedparse_ecr_repository_url}:${var.biomedparse_image_tag}"
  stripe_allowed_redirect_origins_csv = join(
    ",",
    length(var.stripe_allowed_redirect_origins) > 0
    ? var.stripe_allowed_redirect_origins
    : var.frontend_upload_allowed_origins
  )
}

module "app_secrets" {
  source = "../../modules/secrets-manager"

  name        = "vizier/${var.environment}/django-app"
  description = "Django app runtime secrets"
  secret_string = jsonencode({
    DATABASE_URL               = local.django_database_url
    DJANGO_SECRET_KEY          = var.django_secret_key
    INFERENCE_API_BEARER_TOKEN = var.inference_api_bearer_token
    STRIPE_SECRET_KEY          = var.stripe_secret_key
    STRIPE_WEBHOOK_SECRET      = var.stripe_webhook_secret
  })
  tags = local.tags
}

module "iam_runtime" {
  source = "../../modules/iam-runtime"

  sqs_queue_arn        = module.sqs.queue_arn
  artifacts_bucket_arn = module.s3.bucket_arn
  app_secret_arns      = [module.app_secrets.secret_arn]
  name_prefix          = "vizier-${var.environment}"
  tags                 = local.tags
}

module "ecs_gpu" {
  source = "../../modules/ecs-gpu"

  cluster_name          = "vizier-${var.environment}-gpu"
  private_subnet_ids    = module.network.private_runtime_subnet_ids
  ecs_sg_id             = module.network.ecs_security_group_id
  instance_profile_name = module.iam_runtime.ecs_instance_profile_name

  gpu_ami_id                 = var.gpu_ami_id
  instance_type              = var.gpu_instance_type
  asg_min                    = var.gpu_asg_min
  asg_desired                = var.gpu_asg_desired
  asg_max                    = var.gpu_asg_max
  biomedparse_image          = local.biomedparse_image
  biomedparse_log_group_name = "/ecs/vizier-biomedparse-${var.environment}"

  enable_business_hours_schedule  = var.gpu_enable_business_hours_schedule
  business_hours_time_zone        = var.gpu_business_hours_time_zone
  business_hours_scale_up_cron    = var.gpu_business_hours_scale_up_cron
  business_hours_scale_down_cron  = var.gpu_business_hours_scale_down_cron
  business_hours_min_size         = var.gpu_business_hours_min_size
  business_hours_desired_capacity = var.gpu_business_hours_desired_capacity

  worker_task_execution_role_arn = module.iam_runtime.ecs_task_execution_role_arn
  worker_task_role_arn           = module.iam_runtime.worker_task_role_arn
  aws_region                     = var.aws_region

  tags = local.tags
}

module "alb" {
  source = "../../modules/alb"

  name              = "vizier-${var.environment}-api"
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  ingress_cidrs     = var.alb_ingress_cidrs
  target_port       = 8000
  health_check_path = "/api/health/"
  tags              = local.tags
}

module "api_cloudfront" {
  source = "../../modules/api-cloudfront"

  name               = "vizier-${var.environment}-api-edge"
  origin_domain_name = module.alb.alb_dns_name
  tags               = local.tags
}

resource "aws_security_group" "fargate_app" {
  name        = "vizier-${var.environment}-fargate-app-sg"
  description = "Security group for Django API and worker tasks"
  vpc_id      = module.network.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [module.alb.alb_security_group_id]
    description     = "Allow HTTP from ALB only"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

module "cognito" {
  source = "../../modules/cognito"

  project_name      = var.project_name
  environment       = var.environment
  callback_urls     = var.cognito_callback_urls
  logout_urls       = var.cognito_logout_urls
  mfa_configuration = var.cognito_mfa_configuration
  ses_source_arn    = var.cognito_ses_source_arn
  tags              = local.tags
}

module "ecs_fargate_django" {
  source = "../../modules/ecs-fargate-service"

  name                              = "vizier-django-api-${var.environment}"
  cluster_name                      = module.ecs_gpu.cluster_name
  execution_role_arn                = module.iam_runtime.ecs_task_execution_role_arn
  task_role_arn                     = module.iam_runtime.api_task_role_arn
  container_image                   = local.backend_image
  container_port                    = 8000
  desired_count                     = var.api_desired_count
  cpu                               = var.api_cpu
  memory                            = var.api_memory
  subnet_ids                        = module.network.private_runtime_subnet_ids
  security_group_ids                = [aws_security_group.fargate_app.id]
  aws_region                        = var.aws_region
  log_group_name                    = "/ecs/vizier-django-api-${var.environment}"
  target_group_arn                  = module.alb.api_target_group_arn
  health_check_grace_period_seconds = 120
  environment = merge(
    {
      DEBUG                           = "False"
      SECURE_SSL_REDIRECT             = "false"
      SESSION_COOKIE_SECURE           = "false"
      CSRF_COOKIE_SECURE              = "false"
      USE_X_FORWARDED_HOST            = "true"
      AWS_REGION                      = var.aws_region
      S3_BUCKET                       = module.s3.bucket_name
      INFERENCE_ASYNC_S3_ENABLED      = "true"
      INFERENCE_JOBS_QUEUE_URL        = module.sqs.queue_url
      ALLOWED_HOSTS                   = var.django_allowed_hosts
      CORS_ALLOWED_ORIGINS            = join(",", var.frontend_upload_allowed_origins)
      LOG_JSON                        = "true"
      ENABLE_STRIPE_BILLING           = tostring(var.enable_stripe_billing)
      STRIPE_ALLOWED_REDIRECT_ORIGINS = local.stripe_allowed_redirect_origins_csv
      COGNITO_REGION                  = var.aws_region
      COGNITO_USER_POOL_ID            = module.cognito.user_pool_id
      COGNITO_CLIENT_ID               = module.cognito.user_pool_client_id
      COGNITO_DOMAIN                  = "${module.cognito.user_pool_domain}.auth.${var.aws_region}.amazoncognito.com"
      BIO_ECS_CLUSTER                 = module.ecs_gpu.cluster_name
      BIO_ECS_TASK_DEFINITION         = module.ecs_gpu.biomedparse_task_def_arn
      BIO_ECS_CAPACITY_PROVIDER       = module.ecs_gpu.capacity_provider_name
      BIO_ECS_SUBNETS                 = join(",", module.network.private_runtime_subnet_ids)
      BIO_ECS_SECURITY_GROUPS         = module.network.ecs_security_group_id
      BIO_ECS_CONTAINER_NAME          = "biomedparse"
      BIO_ECS_TASK_POLL_SECONDS       = tostring(var.bio_ecs_task_poll_seconds)
      BIO_ECS_TASK_TIMEOUT_SECONDS    = tostring(var.bio_ecs_task_timeout_seconds)
    },
    var.stripe_product_id != "" ? { STRIPE_PRODUCT_ID = var.stripe_product_id } : {},
    var.stripe_price_id_individual_monthly != "" ? { STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY = var.stripe_price_id_individual_monthly } : {},
    var.stripe_price_id_individual_annual != "" ? { STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL = var.stripe_price_id_individual_annual } : {},
    var.stripe_price_lookup_key_individual_monthly != "" ? { STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_MONTHLY = var.stripe_price_lookup_key_individual_monthly } : {},
    var.stripe_price_lookup_key_individual_annual != "" ? { STRIPE_PRICE_LOOKUP_KEY_INDIVIDUAL_ANNUAL = var.stripe_price_lookup_key_individual_annual } : {}
  )
  secrets = [
    { name = "DATABASE_URL", valueFrom = "${module.app_secrets.secret_arn}:DATABASE_URL::" },
    { name = "DJANGO_SECRET_KEY", valueFrom = "${module.app_secrets.secret_arn}:DJANGO_SECRET_KEY::" },
    { name = "INFERENCE_API_BEARER_TOKEN", valueFrom = "${module.app_secrets.secret_arn}:INFERENCE_API_BEARER_TOKEN::" },
    { name = "STRIPE_SECRET_KEY", valueFrom = "${module.app_secrets.secret_arn}:STRIPE_SECRET_KEY::" },
    { name = "STRIPE_WEBHOOK_SECRET", valueFrom = "${module.app_secrets.secret_arn}:STRIPE_WEBHOOK_SECRET::" },
  ]
  tags = local.tags
}

module "ecs_fargate_worker" {
  source = "../../modules/ecs-fargate-service"

  name               = "vizier-inference-worker-${var.environment}"
  cluster_name       = module.ecs_gpu.cluster_name
  execution_role_arn = module.iam_runtime.ecs_task_execution_role_arn
  task_role_arn      = module.iam_runtime.worker_task_role_arn
  container_image    = local.backend_image
  command            = ["python", "manage.py", "run_inference_worker"]
  desired_count      = var.worker_desired_count
  cpu                = var.worker_cpu
  memory             = var.worker_memory
  subnet_ids         = module.network.private_runtime_subnet_ids
  security_group_ids = [aws_security_group.fargate_app.id]
  aws_region         = var.aws_region
  log_group_name     = "/ecs/vizier-inference-worker-${var.environment}"
  environment = {
    DEBUG                        = "False"
    AWS_REGION                   = var.aws_region
    S3_BUCKET                    = module.s3.bucket_name
    INFERENCE_ASYNC_S3_ENABLED   = "true"
    INFERENCE_JOBS_QUEUE_URL     = module.sqs.queue_url
    LOG_JSON                     = "true"
    BIO_ECS_CLUSTER              = module.ecs_gpu.cluster_name
    BIO_ECS_TASK_DEFINITION      = module.ecs_gpu.biomedparse_task_def_arn
    BIO_ECS_CAPACITY_PROVIDER    = module.ecs_gpu.capacity_provider_name
    BIO_ECS_SUBNETS              = join(",", module.network.private_runtime_subnet_ids)
    BIO_ECS_SECURITY_GROUPS      = module.network.ecs_security_group_id
    BIO_ECS_CONTAINER_NAME       = "biomedparse"
    BIO_ECS_TASK_POLL_SECONDS    = tostring(var.bio_ecs_task_poll_seconds)
    BIO_ECS_TASK_TIMEOUT_SECONDS = tostring(var.bio_ecs_task_timeout_seconds)
  }
  secrets = [
    { name = "DATABASE_URL", valueFrom = "${module.app_secrets.secret_arn}:DATABASE_URL::" },
    { name = "DJANGO_SECRET_KEY", valueFrom = "${module.app_secrets.secret_arn}:DJANGO_SECRET_KEY::" },
    { name = "INFERENCE_API_BEARER_TOKEN", valueFrom = "${module.app_secrets.secret_arn}:INFERENCE_API_BEARER_TOKEN::" },
  ]
  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "vizier-${var.environment}-alb-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_ELB_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  dimensions = {
    LoadBalancer = module.alb.alb_arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "alb_target_unhealthy" {
  alarm_name          = "vizier-${var.environment}-alb-unhealthy-targets"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions = {
    LoadBalancer = module.alb.alb_arn_suffix
    TargetGroup  = module.alb.api_target_group_arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "sqs_queue_depth" {
  alarm_name          = "vizier-${var.environment}-sqs-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 20
  treat_missing_data  = "notBreaching"
  dimensions = {
    QueueName = module.sqs.queue_name
  }
}

resource "aws_cloudwatch_metric_alarm" "sqs_dlq_depth" {
  alarm_name          = "vizier-${var.environment}-sqs-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  dimensions = {
    QueueName = module.sqs.dlq_name
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "vizier-${var.environment}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  dimensions = {
    DBInstanceIdentifier = module.rds_postgres.instance_id
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_low_storage" {
  alarm_name          = "vizier-${var.environment}-rds-low-storage"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 21474836480
  treat_missing_data  = "notBreaching"
  dimensions = {
    DBInstanceIdentifier = module.rds_postgres.instance_id
  }
}

resource "aws_cloudwatch_metric_alarm" "rds_connections_high" {
  alarm_name          = "vizier-${var.environment}-rds-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 120
  treat_missing_data  = "notBreaching"
  dimensions = {
    DBInstanceIdentifier = module.rds_postgres.instance_id
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_api_cpu_high" {
  alarm_name          = "vizier-${var.environment}-ecs-api-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  dimensions = {
    ClusterName = module.ecs_gpu.cluster_name
    ServiceName = module.ecs_fargate_django.service_name
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_api_memory_high" {
  alarm_name          = "vizier-${var.environment}-ecs-api-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  dimensions = {
    ClusterName = module.ecs_gpu.cluster_name
    ServiceName = module.ecs_fargate_django.service_name
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_worker_cpu_high" {
  alarm_name          = "vizier-${var.environment}-ecs-worker-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  dimensions = {
    ClusterName = module.ecs_gpu.cluster_name
    ServiceName = module.ecs_fargate_worker.service_name
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_worker_memory_high" {
  alarm_name          = "vizier-${var.environment}-ecs-worker-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  dimensions = {
    ClusterName = module.ecs_gpu.cluster_name
    ServiceName = module.ecs_fargate_worker.service_name
  }
}
