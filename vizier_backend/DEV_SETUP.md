# Guia Completo de Setup em Desenvolvimento

Instruções passo a passo para executar o Vizier Med Backend em desenvolvimento local.

## 📋 Pré-requisitos

### Instalação Necessária

1. **Docker** (versão 20.10+)
   ```bash
   # Verificar instalação
   docker --version
   
   # Download: https://www.docker.com/products/docker-desktop
   ```

2. **Docker Compose** (versão 2.0+)
   ```bash
   # Verificar instalação
   docker-compose --version
   
   # Já vem com Docker Desktop
   ```

3. **Git** (para clonar/versionar)
   ```bash
   git --version
   ```

### Opcional (para desenvolvimento sem Docker)

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

## 🚀 Execução Rápida (5 minutos)

### 1. Extrair e Navegar

```bash
tar -xzf vizier_backend.tar.gz
cd vizier_backend
```

### 2. Copiar Arquivo de Ambiente

```bash
cp .env.example .env
```

### 3. Iniciar Serviços

```bash
# Com Makefile (recomendado)
make build
make up

# Ou com Docker Compose diretamente
docker-compose build
docker-compose up -d
```

### 4. Verificar Status

```bash
# Ver logs
make logs

# Ou diretamente
docker-compose logs -f web

# Verificar health
curl http://localhost:8000/api/health/
```

### 5. Acessar Aplicação

- **API**: http://localhost:8000
- **Health Check**: http://localhost:8000/api/health/
- **Admin**: http://localhost:8000/admin/ (sem credenciais por padrão)

## 🔐 Credenciais Necessárias

### 1. Variáveis de Ambiente Básicas

Edite o arquivo `.env` criado:

```bash
# Django
DEBUG=True
SECRET_KEY=dev-secret-key-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1,web

# Database (já configurado no docker-compose)
DATABASE_URL=postgresql://vizier_user:vizier_password@db:5432/vizier_med

# Redis (já configurado no docker-compose)
REDIS_URL=redis://redis:6379/0
```

### 2. AWS Cognito (Autenticação)

**Opção A: Desenvolvimento sem Cognito (Recomendado para começar)**

```bash
# No .env, deixe em branco ou com valores dummy
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_dummy
COGNITO_CLIENT_ID=dummy_client_id
```

A autenticação será desativada em modo desenvolvimento. Use `force_authenticate` nos testes.

**Opção B: Com Cognito Real (Produção)**

Se você já tem AWS Cognito configurado:

```bash
# 1. Ir para AWS Console
# https://console.aws.amazon.com/cognito/

# 2. Criar User Pool (se não tiver)
# - Nome: vizier-med
# - Configurar políticas de senha
# - Habilitar MFA (opcional)

# 3. Criar App Client
# - Nome: vizier-med-app
# - Anotar: User Pool ID e Client ID

# 4. Adicionar ao .env
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Como obter as credenciais:**

```bash
# AWS CLI
aws cognito-idp describe-user-pool --user-pool-id us-east-1_xxxxxxxxx --region us-east-1

# Ou via Console
# 1. AWS Console → Cognito
# 2. User Pools → Seu pool
# 3. General Settings → Pool ID
# 4. App Clients → Client ID
```

### 3. AWS S3 (Armazenamento)

**Opção A: Desenvolvimento Local (Recomendado)**

```bash
# No .env, deixe em branco
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=vizier-med-bucket-dev
```

Os arquivos serão salvos localmente em `/tmp/vizier-med/`.

**Opção B: Com S3 Real**

```bash
# 1. Criar bucket S3
aws s3 mb s3://vizier-med-bucket-dev --region us-east-1

# 2. Criar IAM User com permissões S3
# AWS Console → IAM → Users → Create User
# Adicionar policy: AmazonS3FullAccess

# 3. Gerar Access Key
# AWS Console → IAM → Users → Seu usuário → Security Credentials

# 4. Adicionar ao .env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=vizier-med-bucket-dev
```

### 4. API de Inferência (Seu Serviço)

**Configurar Endereço da API:**

```bash
# No .env
INFERENCE_API_URL=http://localhost:8001
INFERENCE_API_TIMEOUT=300
```

**Onde colocar:**

1. **Arquivo `.env`** (mais fácil):
   ```env
   INFERENCE_API_URL=http://seu-servidor:porta
   INFERENCE_API_TIMEOUT=300
   ```

2. **Variável de ambiente**:
   ```bash
   export INFERENCE_API_URL=http://seu-servidor:porta
   docker-compose up
   ```

3. **docker-compose.yml** (editar diretamente):
   ```yaml
   environment:
     INFERENCE_API_URL: http://seu-servidor:porta
   ```

**Exemplo com diferentes APIs:**

```bash
# API local em outra porta
INFERENCE_API_URL=http://localhost:8001

# API em servidor remoto
INFERENCE_API_URL=https://api.seu-dominio.com

# API em container Docker (mesmo network)
INFERENCE_API_URL=http://inference-api:8001

# API em AWS
INFERENCE_API_URL=https://inference-api.us-east-1.amazonaws.com
```

## 📝 Arquivo .env Completo para Desenvolvimento

```bash
# ==================== DJANGO ====================
DEBUG=True
SECRET_KEY=dev-secret-key-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1,web

# ==================== DATABASE ====================
# Já configurado no docker-compose.yml
DATABASE_URL=postgresql://vizier_user:vizier_password@db:5432/vizier_med

# ==================== REDIS ====================
REDIS_URL=redis://redis:6379/0

# ==================== AWS COGNITO ====================
# Deixe em branco para desenvolvimento sem autenticação
# Ou configure com valores reais
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx

# ==================== AWS S3 ====================
# Deixe em branco para desenvolvimento local
# Ou configure com valores reais
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=vizier-med-bucket-dev

# ==================== INFERENCE API ====================
# Seu serviço de inferência
INFERENCE_API_URL=http://localhost:8001
INFERENCE_API_TIMEOUT=300

# ==================== DICOM PROCESSING ====================
DICOM_TARGET_HW=(512, 512)
DICOM_TARGET_SLICES=64
DICOM_WINDOW_CENTER=40
DICOM_WINDOW_WIDTH=400
```

## 🔌 Conectando sua API de Inferência

### 1. Entender o Fluxo

```
Django Backend
    ↓
Recebe DICOM ZIP
    ↓
Converte para NPZ
    ↓
Envia para sua API (INFERENCE_API_URL)
    ↓
Sua API processa
    ↓
Django faz polling de status
    ↓
Baixa resultados
    ↓
Converte para NIfTI
    ↓
Salva em S3
    ↓
Retorna URL assinada
```

### 2. Endpoints Esperados da Sua API

Sua API deve ter estes endpoints:

**POST /jobs/submit**
```bash
# Request
curl -X POST http://seu-servidor:porta/jobs/submit \
  -F "file=@estudo.npz"

# Response
{
  "job_id": "job-123-abc",
  "status": "SUBMITTED"
}
```

**GET /jobs/{job_id}/status**
```bash
# Request
curl http://seu-servidor:porta/jobs/job-123-abc/status

# Response
{
  "job_id": "job-123-abc",
  "status": "PROCESSING",
  "progress": 45
}

# Ou quando completo
{
  "job_id": "job-123-abc",
  "status": "COMPLETED",
  "progress": 100
}
```

**GET /jobs/{job_id}/results**
```bash
# Request
curl http://seu-servidor:porta/jobs/job-123-abc/results \
  --output resultado.npz

# Response: arquivo binário NPZ
```

### 3. Exemplo: API Local em Python

Se você quer testar com uma API local:

**mock_inference_api.py**
```python
from flask import Flask, request, jsonify
import uuid
import time

app = Flask(__name__)
jobs = {}

@app.route('/jobs/submit', methods=['POST'])
def submit_job():
    file = request.files['file']
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'PROCESSING',
        'progress': 0,
        'file': file.read()
    }
    return jsonify({'job_id': job_id, 'status': 'SUBMITTED'})

@app.route('/jobs/<job_id>/status', methods=['GET'])
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Not found'}), 404
    
    job = jobs[job_id]
    # Simular progresso
    job['progress'] = min(100, job['progress'] + 10)
    if job['progress'] >= 100:
        job['status'] = 'COMPLETED'
    
    return jsonify({
        'job_id': job_id,
        'status': job['status'],
        'progress': job['progress']
    })

@app.route('/jobs/<job_id>/results', methods=['GET'])
def get_results(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Not found'}), 404
    
    return jobs[job_id]['file'], 200, {'Content-Type': 'application/octet-stream'}

if __name__ == '__main__':
    app.run(port=8001, debug=True)
```

**Executar:**
```bash
pip install flask
python mock_inference_api.py

# Em outro terminal
export INFERENCE_API_URL=http://localhost:8001
make up
```

### 4. Testar Conexão

```bash
# Verificar se API está acessível
curl http://seu-servidor:porta/jobs/test/status

# Ou via Django shell
docker-compose exec web python manage.py shell

# No shell Python
>>> from apps.inference.client import InferenceClient
>>> client = InferenceClient()
>>> client.get_status('test-job-id')
```

## 🧪 Comandos Úteis de Desenvolvimento

### Makefile Commands

```bash
# Build e start
make build
make up

# Logs
make logs
make logs-db
make logs-redis

# Database
make migrate
make migrations
make createsuperuser

# Testes
make test
make coverage
make lint
make format

# Shell
make shell
make bash

# Parar
make down
```

### Docker Compose Direto

```bash
# Build
docker-compose build

# Start
docker-compose up -d

# Logs
docker-compose logs -f web

# Executar comando
docker-compose exec web python manage.py migrate

# Shell
docker-compose exec web python manage.py shell

# Parar
docker-compose down
```

## 🐛 Troubleshooting

### Erro: "Cannot connect to database"

```bash
# Verificar se PostgreSQL está rodando
docker-compose ps

# Ver logs do banco
docker-compose logs db

# Reiniciar
docker-compose restart db
```

### Erro: "Port already in use"

```bash
# Encontrar processo na porta
lsof -i :8000

# Matar processo
kill -9 <PID>

# Ou mudar porta no docker-compose.yml
# ports:
#   - "8001:8000"  # Mudar 8000 para 8001
```

### Erro: "Module not found"

```bash
# Reinstalar dependências
docker-compose exec web pip install -r requirements.txt

# Ou rebuild
docker-compose build --no-cache
```

### Erro: "Permission denied"

```bash
# Verificar permissões
docker-compose exec web ls -la /app

# Corrigir (se necessário)
docker-compose exec -u root web chown -R appuser:appuser /app
```

### Erro: "DICOM processing failed"

```bash
# Verificar logs
docker-compose logs web | grep -i dicom

# Testar com arquivo DICOM válido
# Certifique-se que o ZIP contém pasta DICOM/ com arquivos .dcm
```

## 🔍 Verificação de Setup

### Health Check

```bash
# Verificar se tudo está rodando
curl http://localhost:8000/api/health/

# Resposta esperada:
# {"status": "healthy", "database": "connected", "redis": "connected"}
```

### Listar Endpoints

```bash
# Ver todas as rotas disponíveis
docker-compose exec web python manage.py show_urls

# Ou acessar documentação
# http://localhost:8000/api/schema/swagger/
# http://localhost:8000/api/schema/redoc/
```

### Testar Autenticação

```bash
# Sem Cognito (desenvolvimento)
curl -H "Authorization: Bearer dummy-token" \
  http://localhost:8000/api/auth/users/

# Com Cognito (produção)
# Obter token via Cognito
# Usar token no header
```

## 📚 Próximos Passos

1. **Configurar .env** com suas credenciais
2. **Executar `make up`** para iniciar
3. **Testar endpoints** via Postman ou curl
4. **Conectar sua API** de inferência
5. **Fazer upload de DICOM** para testar pipeline

## 🎯 Checklist de Setup

- [ ] Docker e Docker Compose instalados
- [ ] Arquivo `.env` criado e configurado
- [ ] `make build` executado com sucesso
- [ ] `make up` iniciou todos os serviços
- [ ] Health check retorna status "healthy"
- [ ] API de inferência está acessível
- [ ] Credenciais AWS configuradas (se usar S3 real)
- [ ] Cognito configurado (se usar autenticação real)

## 📞 Suporte

Se tiver dúvidas:

1. Verificar logs: `make logs`
2. Consultar documentação: `README.md`, `ARCHITECTURE.md`
3. Testar com curl: `curl http://localhost:8000/api/health/`
4. Abrir issue no GitHub

---

**Pronto para começar!** 🚀
