# Deployment

This guide takes you from `git clone` to a running stack on (a) your laptop and (b) AWS ECS Fargate.

## A. Local

Prereqs: Docker Desktop or Colima, GNU Make, Python 3.12 (only for `make keys`).

```bash
git clone <your-fork> agentic-bank
cd agentic-bank
cp .env.example .env
make keys      # generates secrets/ — local only, never commit
make up        # builds image, starts Postgres, Ollama, Jaeger, Prometheus, Grafana, app
# wait ~30s for the Ollama model pull to finish; check `make logs`
make seed      # creates demo users
make demo      # walks through the full scenario
```

Open:
- API docs: <http://localhost:8000/docs>
- Jaeger (agent traces): <http://localhost:16686>
- Grafana: <http://localhost:3000> (admin / admin)

## B. AWS ECS Fargate

The Terraform under `infra/terraform/` provisions a minimum-viable footprint.

### What gets created

- **VPC** (3 public subnets, single NAT — cost-conscious; HA upgrade is a single variable flip).
- **ECS cluster** with two services:
  - `app` — FastAPI behind an ALB on port 443 (ACM cert), 0.5 vCPU / 1 GB.
  - `ollama` — internal-only on port 11434 (security-group-restricted to `app`'s SG).
- **RDS Postgres 16** (db.t4g.small, encrypted EBS).
- **ElastiCache Redis** (single-node, encrypted in-transit).
- **Secrets Manager** entries for JWT keys + audit HMAC + DB DEK; rotation Lambdas optional.
- **CloudWatch Logs** for both services.
- **AWS X-Ray** as the OTLP destination (alternatively keep Jaeger in a sidecar — see `infra/ecs/observability.md`).

### Deploy steps

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit: domain_name, certificate_arn, db_password, region, etc.
terraform init
terraform plan
terraform apply
```

After apply, the ALB DNS is in `terraform output alb_dns_name`. Push the image:

```bash
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URL
docker build -f infra/docker/Dockerfile -t agentic-bank:0.1.0 .
docker tag agentic-bank:0.1.0 $ECR_URL/agentic-bank:0.1.0
docker push $ECR_URL/agentic-bank:0.1.0

aws ecs update-service --cluster agentic-bank --service app --force-new-deployment
```

Run migrations once (one-shot ECS task; see `infra/terraform/run_migrations.tf`).

### Stay within the AWS free tier

Out of the box, this design exceeds the free tier (NAT alone is ~$32/month). To stay free:

1. Set `single_nat = false` and `public_subnets_only = true` — drops NAT entirely.
2. Replace RDS with the same Postgres-in-ECS container locally — cheap but not durable; fine for a demo.
3. Use `t4g.micro` (free-tier eligible) or run the API on a single `t3.micro` EC2 + Docker compose.

A pure-EC2 single-instance variant for portfolio demos is provided at `infra/terraform/single_ec2/` — about $0/month for the first 12 months.

## C. Image hardening notes

- Base image: `python:3.12-slim` pinned; rebuild monthly to pick up security patches.
- Non-root user `app` (uid 10001).
- `tini` as PID 1 to handle signal propagation.
- Read-only root filesystem (set `readonly_root_filesystem = true` in the task definition).
- No build tools in the runtime image; multi-stage cuts ~200 MB.
- Trivy in CI fails on HIGH/CRITICAL OS or library CVEs.

## D. Operational runbook (excerpt)

| Symptom | Triage | Fix |
|---|---|---|
| `/health` 200 but agent calls hang | Ollama not ready / model not pulled | `docker exec ollama ollama list`; re-pull with `ollama pull <model>` |
| 401 on every request | JWT keys rotated but app still has old | Restart app task to reload secrets |
| Audit chain fails verification | Tampering or bad migration | Run `python scripts/audit_verify.py` with admin DB user; bisect by id |
| Ollama OOM on 8 GB host | Model too large | Switch `LLM_MODEL` to `qwen2.5:3b` |
