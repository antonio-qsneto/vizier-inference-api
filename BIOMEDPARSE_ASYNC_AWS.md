# BiomedParse Async Inference on AWS

## Resumo

O contrato operacional passou a ser:

- `1 input.npz -> 1 output.npz`
- `1 job assíncrono por arquivo`
- integração entre API e worker por `S3 + SQS + DynamoDB`
- sem diretório compartilhado entre API e worker

## O que foi removido do desenho antigo

Foi removido o uso de:

- EFS/shared volume entre API e worker para payloads de inferência
- `JOB_BASE_DIR`
- `status.txt` em filesystem compartilhado
- pastas `input/` e `output/` como mecanismo de integração
- cópia de artefatos via mount compartilhado
- execução baseada em `predict.sh` como contrato principal do serviço

## Arquitetura atual

1. A API recebe um `.npz` por upload ou por referência a `s3://...`.
2. A API gera `job_id`, grava `input.npz` no bucket de artefatos, persiste o status em DynamoDB e publica a mensagem na SQS.
3. O worker ECS consome a mensagem e dispara uma task GPU do BiomedParse.
4. A task GPU usa storage efêmero local em `/tmp/jobs/<job_id>/`.
5. A task baixa `input.npz`, executa:

```bash
python /opt/BiomedParse/inference.py \
  --input-file /tmp/jobs/<job_id>/input.npz \
  --output-file /tmp/jobs/<job_id>/output.npz \
  --device cuda \
  --summary-file /tmp/jobs/<job_id>/summary.json
```

6. A task sobe `output.npz` e `summary.json` para S3.
7. O worker atualiza o status do job em DynamoDB para `succeeded` ou `failed`.

## Recursos AWS

- `S3`: bucket único de artefatos
- `SQS`: fila principal de jobs
- `SQS DLQ`: fila de dead-letter para falhas repetidas
- `DynamoDB`: tabela de status dos jobs
- `CloudWatch Logs`: logs da API, worker e task GPU
- `ECS EC2`: plataforma preservada

## Estrutura de artefatos

Prefixo padrão: `jobs/<job_id>/`

- `jobs/<job_id>/input.npz`
- `jobs/<job_id>/output.npz`
- `jobs/<job_id>/summary.json`

## Status do job

- `pending`
- `running`
- `succeeded`
- `failed`

## Endpoints da API

### Criar job por upload

`POST /jobs/submit`

Exemplo:

```bash
curl -X POST "$API_URL/jobs/submit" \
  -H "Idempotency-Key: upload-001" \
  -F "file=@/path/input.npz" \
  -F "requested_device=cuda" \
  -F "slice_batch_size=4"
```

Resposta:

```json
{
  "job_id": "4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d",
  "status": "pending",
  "created_at": "2026-03-03T14:08:31.942021Z",
  "updated_at": "2026-03-03T14:08:31.942021Z",
  "started_at": null,
  "completed_at": null,
  "requested_device": "cuda",
  "slice_batch_size": 4,
  "attempt_count": 0,
  "request_id": "upload-001",
  "correlation_id": "upload-001",
  "error_message": null,
  "error_type": null,
  "result": {
    "input_s3_uri": "s3://bucket/jobs/4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d/input.npz",
    "output_s3_uri": "s3://bucket/jobs/4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d/output.npz",
    "summary_s3_uri": "s3://bucket/jobs/4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d/summary.json"
  }
}
```

### Criar job por referência a S3

`POST /jobs`

Payload:

```json
{
  "input_s3_uri": "s3://vizier-inference-dev-123456789012-artifacts/jobs/preloaded/input.npz",
  "requested_device": "cuda",
  "slice_batch_size": 4,
  "request_id": "ref-001",
  "correlation_id": "study-abc"
}
```

Observação:

- a referência precisa apontar para o bucket de artefatos configurado pela stack

### Consultar status

`GET /jobs/{job_id}/status`

Resposta:

```json
{
  "job_id": "4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d",
  "status": "running",
  "created_at": "2026-03-03T14:08:31.942021Z",
  "updated_at": "2026-03-03T14:09:11.102422Z",
  "started_at": "2026-03-03T14:09:11.102422Z",
  "completed_at": null,
  "attempt_count": 1,
  "requested_device": "cuda",
  "slice_batch_size": 4,
  "error_message": null,
  "error_type": null,
  "request_id": "upload-001",
  "correlation_id": "upload-001"
}
```

### Obter metadados/localização do resultado

`GET /jobs/{job_id}`

Quando o job está em `succeeded`, a resposta inclui:

- `result.input_s3_uri`
- `result.output_s3_uri`
- `result.summary_s3_uri`
- `result.output_download_url`
- `result.summary_download_url`

### Baixar o resultado binário

`GET /jobs/{job_id}/results`

Retorna o `output.npz` como stream binário.

## Mensagem publicada na fila

```json
{
  "job_id": "4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d",
  "input_s3_uri": "s3://bucket/jobs/4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d/input.npz",
  "output_s3_uri": "s3://bucket/jobs/4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d/output.npz",
  "summary_s3_uri": "s3://bucket/jobs/4d7dbf14-f8d8-6e4a-c4ce-6b5c0f3dbf7d/summary.json",
  "requested_device": "cuda",
  "slice_batch_size": 4,
  "request_id": "upload-001",
  "correlation_id": "upload-001"
}
```

## Execução do worker

O worker ECS não usa filesystem compartilhado. Ele:

1. consome a mensagem da fila
2. gera URLs pré-assinadas para download/upload dos artefatos
3. dispara uma task GPU por job
4. estende a visibilidade da mensagem enquanto a task está rodando
5. valida a existência de `output.npz` e `summary.json`
6. marca o job como `succeeded` ou `failed`

Equivalente lógico da task GPU:

```bash
mkdir -p /tmp/jobs/<job_id>
curl -o /tmp/jobs/<job_id>/input.npz "$INPUT_DOWNLOAD_URL"
python /opt/BiomedParse/inference.py \
  --input-file /tmp/jobs/<job_id>/input.npz \
  --output-file /tmp/jobs/<job_id>/output.npz \
  --device cuda \
  --summary-file /tmp/jobs/<job_id>/summary.json
curl -X PUT --data-binary @/tmp/jobs/<job_id>/output.npz "$OUTPUT_UPLOAD_URL"
curl -X PUT --data-binary @/tmp/jobs/<job_id>/summary.json "$SUMMARY_UPLOAD_URL"
rm -rf /tmp/jobs/<job_id>
```

Na implementação real, o download/upload é feito dentro da task via Python stdlib para não depender de `aws cli` ou `boto3` na imagem do BiomedParse.

## Idempotência

- opcional via header `Idempotency-Key`
- a API deriva um `job_id` estável a partir dessa chave
- o mesmo `Idempotency-Key` retorna o mesmo job

## Retry e tolerância a falhas

- a fila principal usa DLQ
- o worker só apaga a mensagem quando o job conclui com artefatos válidos
- em falha, o status vai para `failed` com `error_message` e `error_type`
- se o retry reencontrar `output.npz` e `summary.json` já publicados, o worker reconcilia o estado e conclui o job sem reprocessar

## Logs

- API e worker registram eventos estruturados em stdout
- stdout/stderr da task GPU vão para CloudWatch Logs
- `summary.json` fica persistido no S3 por job

## Deploy

### Terraform

```bash
cd vizier-inference-infra/terraform/envs/dev
terraform init
terraform plan \
  -var="api_image=<api-image>" \
  -var="worker_image=<worker-image>" \
  -var="biomedparse_image=<biomedparse-image>"
terraform apply \
  -var="api_image=<api-image>" \
  -var="worker_image=<worker-image>" \
  -var="biomedparse_image=<biomedparse-image>"
```

Outputs relevantes apos o apply:

- `artifacts_bucket_name`
- `jobs_table_name`
- `jobs_queue_url`
- `jobs_dlq_url`

Variáveis úteis adicionais:

- `jobs_queue_name`
- `jobs_dlq_name`
- `jobs_table_name`
- `s3_artifacts_bucket_name`
- `job_artifacts_prefix`
- `s3_kms_key_arn` e `dynamodb_kms_key_arn` (opcionais)

### Build local das imagens de controle

```bash
docker build -t vizier-api:latest app/api
docker build -t vizier-worker:latest app/worker
```

## Teste rápido

### Verificação estática

```bash
python -m compileall app/api app/worker vizier_backend
```

### Testes Django relevantes ao novo formato de saída

```bash
cd vizier_backend
python manage.py test apps.studies.tests
```

### Smoke test da API

```bash
curl http://<api-host>/health
curl -X POST http://<api-host>/jobs/submit -F "file=@/tmp/input.npz"
curl http://<api-host>/jobs/<job_id>/status
curl http://<api-host>/jobs/<job_id>
curl http://<api-host>/jobs/<job_id>/results --output output.npz
```

## Tradeoffs

1. Foi preservado o modelo atual de `worker ECS CPU -> task GPU por job`, porque isso evita reescrever a plataforma de execução.
2. DynamoDB foi usado para status no lugar de filesystem porque é o menor delta coerente para AWS e elimina estado local compartilhado.
3. URLs pré-assinadas foram usadas entre worker e task GPU para não exigir mudanças na imagem do BiomedParse além do próprio contrato `--input-file/--output-file`.
4. O serviço do worker continuou com `desired_count = 1`, porque não existia autoscaling prévio no repositório. Escalonamento por profundidade de fila pode ser adicionado depois sem mudar o contrato do job.
