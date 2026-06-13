terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

provider "aws" {
  region = var.region
}

# Networking ---------------------------------------------------------------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.project}-vpc"
  cidr = "10.42.0.0/16"

  azs             = ["${var.region}a", "${var.region}b"]
  public_subnets  = ["10.42.1.0/24", "10.42.2.0/24"]
  private_subnets = ["10.42.11.0/24", "10.42.12.0/24"]

  enable_nat_gateway   = !var.public_subnets_only
  single_nat_gateway   = var.single_nat
  enable_dns_hostnames = true
}

# ECR ---------------------------------------------------------------------

resource "aws_ecr_repository" "app" {
  name                 = "${var.project}-app"
  image_tag_mutability = "IMMUTABLE"
  encryption_configuration { encryption_type = "AES256" }
  image_scanning_configuration { scan_on_push = true }
}

# Postgres ----------------------------------------------------------------

resource "aws_db_subnet_group" "this" {
  name       = "${var.project}-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "db" {
  name   = "${var.project}-db"
  vpc_id = module.vpc.vpc_id
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.project}-pg"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = var.db_instance_class
  allocated_storage       = 20
  storage_encrypted       = true
  username                = "agentic_admin"
  password                = var.db_password
  db_name                 = "agentic_bank"
  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.db.id]
  skip_final_snapshot     = true
  publicly_accessible     = false
  backup_retention_period = 7
  deletion_protection     = false
  apply_immediately       = true
}

# Secrets Manager ---------------------------------------------------------

resource "aws_secretsmanager_secret" "jwt_private" { name = "${var.project}/jwt-private" }
resource "aws_secretsmanager_secret" "jwt_public"  { name = "${var.project}/jwt-public"  }
resource "aws_secretsmanager_secret" "audit_hmac"  { name = "${var.project}/audit-hmac"  }
resource "aws_secretsmanager_secret" "db_dek"      { name = "${var.project}/db-dek"      }

# ECS, ALB, services live in modules in the same directory; omitted here for brevity
# to keep the portfolio reviewable. See infra/ecs/README.md for the full task definitions.

output "alb_dns_name"  { value = "see infra/ecs/README.md — populate after applying app module" }
output "ecr_repo_url"  { value = aws_ecr_repository.app.repository_url }
output "db_endpoint"   { value = aws_db_instance.postgres.address }
