variable "project" {
  type    = string
  default = "agentic-bank"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "single_nat" {
  description = "Single NAT gateway. Cheaper, not HA."
  type        = bool
  default     = true
}

variable "public_subnets_only" {
  description = "Skip NAT entirely. Tasks run in public subnets with security groups."
  type        = bool
  default     = false
}
