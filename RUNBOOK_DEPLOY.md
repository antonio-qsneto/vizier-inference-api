# Runbook Deploy AWS (Dev/Prod)

## Escopo
Este runbook cobre deploy do stack alvo:
- Frontend no Amplify.
- Django API + worker em ECS/Fargate.
- BiomedParse em ECS EC2 GPU (capacity provider).
- S3 + SQS/DLQ + RDS PostgreSQL + Secrets Manager.
- CI/CD GitHub Actions com OIDC.

## Pré-requisitos
1. Terraform state remoto já criado (bucket S3 + lock table opcional).
2. Role OIDC (`AWS_ROLE_ARN`) com permissão para Terraform e deploy.
3. GitHub Environments `development` e `production` configurados.
4. Variáveis/segredos definidos conforme [GITHUB_SECRETS.md](/home/antonio/medIA/development/vizier-inference-api/GITHUB_SECRETS.md).
5. `TF_VAR_rds_password` e `TF_VAR_django_secret_key` válidos.

## Fluxo padrão de deploy
1. `main` recebe push.
2. Workflow `deploy-dev.yml`:
   - garante ECR,
   - build/push imagem backend,
   - `terraform apply` em `envs/dev`,
   - roda migrations (`run_ecs_migrate.sh`),
   - bootstrap opcional (`run_bootstrap.sh`),
   - smoke test (`smoke_api.sh`).
3. Promoção para produção:
   - workflow manual `deploy-prod.yml`,
   - informar `image_tag` validada em dev e `source_commit_sha` com CI verde,
   - aprovar ambiente `production`.

## Primeiro bootstrap manual (se necessário)
```bash
export AWS_REGION=us-east-1
export ECS_CLUSTER=<terraform output ecs_gpu_cluster_name>
export TASK_DEFINITION_ARN=<terraform output ecs_fargate_django_task_definition_arn>
export SUBNET_IDS=<subnet-1,subnet-2>
export SECURITY_GROUP_IDS=<sg-id>
export BOOTSTRAP_CONTAINER_NAME=<terraform output ecs_fargate_django_service_name>
export BOOTSTRAP_ADMIN_EMAIL=<admin@empresa.com>
export BOOTSTRAP_CREATE_USER_IF_MISSING=1
export BOOTSTRAP_MAKE_SUPERUSER=1
./scripts/deploy/run_bootstrap.sh
```

## Rollback
1. Identificar tag anterior estável no ECR.
2. Executar `deploy-prod.yml` com `image_tag=<tag_anterior>` e `source_commit_sha=<sha-com-ci-success>`.
3. Confirmar smoke e métricas de erro.
4. Se necessário, reduzir `desired_count` do worker para conter retries.

## Diagnóstico de falhas

### API indisponível no ALB
1. Verificar alarmes:
   - `alb-5xx`,
   - `alb-unhealthy-targets`.
2. Conferir logs:
   - `/ecs/vizier-django-api-<env>`.
3. Validar SG:
   - ALB -> porta `8000` no SG das tasks.

### Jobs presos em fila
1. Checar `ApproximateNumberOfMessagesVisible` na fila principal.
2. Verificar serviço worker:
   - desired/running tasks.
3. Ver logs:
   - `/ecs/vizier-inference-worker-<env>`.

### Mensagens na DLQ
1. Inspecionar payload da DLQ (job_id, tenant_id, correlation_id).
2. Corrigir causa raiz (input inválido, timeout GPU, permissão S3/ECS).
3. Reenfileirar manualmente para fila principal após correção.

### Task GPU falhando
1. Confirmar capacity provider e ASG:
   - `ecs_gpu_capacity_provider`,
   - `ecs_gpu_asg_name`.
2. Ver logs da task:
   - `/ecs/vizier-biomedparse-<env>`.
3. Validar imagem/tag do BiomedParse e variáveis de task override.

## Operação da janela GPU
Parâmetro padrão:
- Timezone: `America/Sao_Paulo`.
- Up: `07:00` (`min=1`, `desired=1`).
- Down: `18:00` (`min=0`, `desired=0`).

Fora da janela, tasks pendentes ainda escalam por managed scaling do capacity provider.

## Pós-deploy checklist
1. `GET /api/health/` responde 200.
2. Create job + upload S3 + upload-complete.
3. Worker consome SQS e dispara task GPU.
4. Outputs no S3:
   - `output/<tenant>/<job>/original_image.nii.gz`,
   - `output/<tenant>/<job>/mask.nii.gz`,
   - `output/<tenant>/<job>/summary.json`.
5. Endpoint de outputs retorna presigned GET válido.
