# Guia Completo: Execução em Desenvolvimento com Docker

Instruções passo-a-passo para executar o Vizier Med Backend em desenvolvimento usando Docker Compose.

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
   docker compose version
   
   # Já vem com Docker Desktop
   ```

3. **Git** (para clonar/versionar)
   ```bash
   git --version
   ```

### Requisitos de Sistema

- **RAM**: Mínimo 4GB (recomendado 8GB)
- **Disco**: Mínimo 5GB livres
- **CPU**: 2+ cores
- **SO**: Windows, macOS ou Linux

## 🚀 Execução Rápida (10 minutos)

### Passo 1: Extrair e Navegar

```bash
# Extrair arquivo
tar -xzf vizier_backend.tar.gz
cd vizier_backend

# Verificar arquivos Docker
ls -la Dockerfile docker-compose.yml .env.example
```

### Passo 2: Configurar Variáveis de Ambiente

```bash
# Copiar arquivo de exemplo
cp .env.example .env

# Editar arquivo (abrir com seu editor favorito)
# nano .env
# ou
# code .env
```

**Valores recomendados para desenvolvimento:**

```env
# ============ DJANGO ============
DEBUG=True
SECRET_KEY=dev-secret-key-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1,web

# ============ DATABASE ============
DATABASE_URL=postgresql://vizier_user:vizier_password@db:5432/vizier_med

# ============ REDIS ============
REDIS_URL=redis://redis:6379/0

# ============ COGNITO (deixe vazio para dev) ============
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=
COGNITO_CLIENT_ID=

# ============ AWS S3 (deixe vazio para dev) ============
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=vizier-med-bucket-dev

# ============ SUA API DE INFERÊNCIA ============
INFERENCE_API_URL=http://localhost:8001
INFERENCE_API_TIMEOUT=300

# ============ DICOM PROCESSING ============
DICOM_TARGET_HW=(512, 512)
DICOM_TARGET_SLICES=64
DICOM_WINDOW_CENTER=40
DICOM_WINDOW_WIDTH=400
```

### Passo 3: Build das Imagens

```bash
# Fazer build das imagens Docker
docker-compose build

# Saída esperada:
# Building db ... done
# Building redis ... done
# Building web ... done
```

### Passo 4: Iniciar Serviços

```bash
# Iniciar todos os serviços em background
docker-compose up -d

# Saída esperada:
# Creating vizier_db_1 ... done
# Creating vizier_redis_1 ... done
# Creating vizier_web_1 ... done
```

### Passo 5: Verificar Status

```bash
# Ver status dos containers
docker-compose ps

# Saída esperada:
# NAME            COMMAND                  SERVICE   STATUS
# vizier_db_1     "postgres"               db        Up 2 seconds
# vizier_redis_1  "redis-server"           redis     Up 2 seconds
# vizier_web_1    "python manage.py..."    web       Up 2 seconds
```

### Passo 6: Executar Migrations

```bash
# Rodar migrations do Django
docker-compose exec web python manage.py migrate

# Saída esperada:
# Operations to perform:
#   Apply all migrations: accounts, admin, audit, auth, ...
# Running migrations:
#   Applying accounts.0001_initial... OK
#   ...
```

### Passo 7: Acessar Aplicação

```bash
# Health check
curl http://localhost:8000/api/health/

# Resposta esperada:
# {"status":"healthy","service":"vizier-med-backend","version":"1.0.0"}

# Acessar no navegador
# API: http://localhost:8000
# Admin: http://localhost:8000/admin/
```

## 📊 Arquitetura Docker

```
┌─────────────────────────────────────────────────┐
│         Docker Compose (Desenvolvimento)        │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐  ┌──────────┐  ┌──────────┐  │
│  │   Django     │  │PostgreSQL│  │  Redis   │  │
│  │   (port 8000)│  │(port 5432)│ │(port 6379)│ │
│  │              │  │          │  │          │  │
│  │ • Hot reload │  │ • Data   │  │ • Cache  │  │
│  │ • Debug mode │  │ • Persist│  │ • Session│  │
│  │ • Logs       │  │          │  │          │  │
│  └──────────────┘  └──────────┘  └──────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

## 🔧 Comandos Úteis

### Iniciar/Parar Serviços

```bash
# Iniciar serviços
docker-compose up -d

# Parar serviços
docker-compose down

# Parar e remover volumes (CUIDADO: deleta dados!)
docker-compose down -v

# Reiniciar serviços
docker-compose restart

# Reiniciar serviço específico
docker-compose restart web
```

### Logs

```bash
# Ver logs de todos os serviços
docker-compose logs

# Ver logs em tempo real
docker-compose logs -f

# Ver logs de serviço específico
docker-compose logs -f web
docker-compose logs -f db
docker-compose logs -f redis

# Ver últimas 100 linhas
docker-compose logs --tail=100 web
```

### Executar Comandos Django

```bash
# Migrations
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py makemigrations

# Criar superusuário
docker-compose exec web python manage.py createsuperuser

# Django shell
docker-compose exec web python manage.py shell

# Testes
docker-compose exec web python manage.py test

# Coletar static files
docker-compose exec web python manage.py collectstatic --noinput
```

### Acessar Containers

```bash
# Bash no container web
docker-compose exec web bash

# Bash no container db (PostgreSQL)
docker-compose exec db bash

# Bash no container redis
docker-compose exec redis bash

# Python shell no container web
docker-compose exec web python
```

### Banco de Dados

```bash
# Acessar PostgreSQL
docker-compose exec db psql -U vizier_user -d vizier_med

# Comandos SQL úteis:
# \dt                  - Listar tabelas
# \d accounts_user     - Descrever tabela
# SELECT * FROM accounts_user;  - Ver dados

# Fazer backup do banco
docker-compose exec db pg_dump -U vizier_user vizier_med > backup.sql

# Restaurar backup
docker-compose exec -T db psql -U vizier_user vizier_med < backup.sql
```

### Redis

```bash
# Acessar Redis CLI
docker-compose exec redis redis-cli

# Comandos úteis:
# KEYS *               - Listar todas as chaves
# GET chave            - Obter valor
# FLUSHALL             - Limpar tudo (CUIDADO!)
# INFO                 - Informações do Redis
```

## 🧪 Testando a API

### Health Check

```bash
curl http://localhost:8000/api/health/
```

**Resposta esperada:**
```json
{
  "status": "healthy",
  "service": "vizier-med-backend",
  "version": "1.0.0"
}
```

### Listar Clínicas

```bash
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/clinics/clinics/
```

**Resposta esperada:**
```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "...",
      "name": "Development Clinic",
      "cnpj": "00000000000191",
      "seat_limit": 5,
      "subscription_plan": "free",
      "active_doctors_count": 1,
      "created_at": "2026-02-11T...",
      "updated_at": "2026-02-11T..."
    }
  ]
}
```

### Listar Estudos

```bash
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/studies/studies/
```

### Testar com Postman

1. Importar coleção (se disponível)
2. Configurar variáveis:
   - `base_url`: http://localhost:8000
   - `token`: test-token
3. Executar requisições

## 🐛 Troubleshooting

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

### Erro: "Cannot connect to database"

```bash
# Verificar se PostgreSQL está rodando
docker-compose ps

# Ver logs do banco
docker-compose logs db

# Reiniciar banco
docker-compose restart db

# Aguardar health check passar
sleep 10
docker-compose exec web python manage.py migrate
```

### Erro: "Module not found"

```bash
# Reinstalar dependências
docker-compose exec web pip install -r requirements.txt

# Ou rebuild imagem
docker-compose build --no-cache
```

### Erro: "Permission denied"

```bash
# Verificar permissões
docker-compose exec web ls -la /app

# Corrigir (se necessário)
docker-compose exec -u root web chown -R appuser:appuser /app
```

### Erro: "Static files not found"

```bash
# Coletar static files
docker-compose exec web python manage.py collectstatic --noinput

# Verificar permissões
docker-compose exec web ls -la staticfiles/
```

### Erro: "DICOM processing failed"

```bash
# Verificar logs
docker-compose logs web | grep -i dicom

# Testar com arquivo DICOM válido
# Certifique-se que o ZIP contém pasta DICOM/ com arquivos .dcm
```

## 📝 Arquivo docker-compose.yml Explicado

```yaml
version: '3.8'

services:
  # Banco de dados PostgreSQL
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: vizier_med
      POSTGRES_USER: vizier_user
      POSTGRES_PASSWORD: vizier_password
    ports:
      - "5432:5432"  # Porta do banco (host:container)
    volumes:
      - postgres_data:/var/lib/postgresql/data  # Persistência
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vizier_user"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Cache Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"  # Porta do Redis
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Aplicação Django
  web:
    build:
      context: .
      dockerfile: Dockerfile
    command: >
      sh -c "python manage.py migrate &&
             python manage.py runserver 0.0.0.0:8000"
    environment:
      DEBUG: "True"
      DATABASE_URL: postgresql://vizier_user:vizier_password@db:5432/vizier_med
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: dev-secret-key-change-in-production
      ALLOWED_HOSTS: localhost,127.0.0.1,web
    ports:
      - "8000:8000"  # Porta da API (host:container)
    volumes:
      - .:/app  # Hot reload: mudanças locais refletem no container
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
```

## 🔌 Conectar sua API de Inferência

### Opção 1: API Local em Outra Porta

```bash
# Terminal 1: Vizier Med Backend
docker-compose up -d

# Terminal 2: Sua API de Inferência
python seu_api.py --port 8001

# No .env, configure:
INFERENCE_API_URL=http://localhost:8001
```

### Opção 2: API em Container Docker

**Criar docker-compose.override.yml:**

```yaml
version: '3.8'

services:
  inference-api:
    build: ../seu-projeto-api
    ports:
      - "8001:8001"
    environment:
      PORT: 8001

  web:
    environment:
      INFERENCE_API_URL: http://inference-api:8001
    depends_on:
      - inference-api
```

**Executar:**
```bash
docker-compose up -d
```

### Opção 3: API Remota

```env
# .env
INFERENCE_API_URL=https://seu-servidor.com/api
INFERENCE_API_TIMEOUT=300
```

## 📊 Monitoramento

### Ver Uso de Recursos

```bash
# CPU, memória, rede
docker stats

# Saída:
# CONTAINER ID   NAME           CPU %     MEM USAGE
# abc123...      vizier_web_1   0.5%      150MiB
# def456...      vizier_db_1    1.2%      200MiB
```

### Verificar Health Checks

```bash
# Ver status dos health checks
docker-compose ps

# Ou verificar manualmente
curl http://localhost:8000/api/health/
```

### Logs Estruturados

```bash
# Ver logs com timestamp
docker-compose logs --timestamps

# Ver logs de erro
docker-compose logs web | grep ERROR

# Exportar logs
docker-compose logs > logs.txt
```

## 🔒 Segurança em Desenvolvimento

### Não Fazer em Produção

- ❌ DEBUG=True
- ❌ Deixar SECRET_KEY como padrão
- ❌ Deixar Cognito vazio
- ❌ Deixar AWS credentials em branco
- ❌ Usar senha padrão do banco

### Boas Práticas

- ✅ Usar .env para variáveis sensíveis
- ✅ Nunca commitar .env
- ✅ Usar volumes para dados persistentes
- ✅ Manter imagens atualizadas
- ✅ Usar redes isoladas

## 🚀 Deploy em Produção

Quando estiver pronto para produção:

1. **Usar Dockerfile.prod** (multi-stage build otimizado)
2. **Usar docker-compose.prod.yml** (com Nginx, SSL, etc)
3. **Configurar variáveis reais** (Cognito, AWS, etc)
4. **Usar AWS ECS/Fargate** (ao invés de docker-compose)
5. **Ativar HTTPS** (certificados SSL)
6. **Configurar backups** (RDS, S3)

Veja `DOCKER.md` para instruções completas de produção.

## 📚 Referências

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Django in Docker](https://docs.djangoproject.com/en/5.0/howto/deployment/wsgi/gunicorn/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Redis Documentation](https://redis.io/documentation)

## ✅ Checklist de Setup

- [ ] Docker e Docker Compose instalados
- [ ] Arquivo `.env` criado e configurado
- [ ] `docker-compose build` executado com sucesso
- [ ] `docker-compose up -d` iniciou todos os serviços
- [ ] `docker-compose ps` mostra todos os containers "Up"
- [ ] Health check retorna status "healthy"
- [ ] Migrations executadas com sucesso
- [ ] API respondendo em http://localhost:8000
- [ ] Banco de dados acessível
- [ ] Redis acessível

## 🎯 Próximos Passos

1. **Testar endpoints** via curl ou Postman
2. **Conectar sua API** de inferência
3. **Fazer upload de DICOM** para testar pipeline
4. **Configurar Cognito** (se necessário)
5. **Configurar S3** (se necessário)

---

**Pronto para começar!** 🚀

Se tiver dúvidas, consulte:
- `README.md` - Instruções gerais
- `DEV_SETUP.md` - Setup sem Docker
- `DOCKER.md` - Guia avançado de Docker
- `ARCHITECTURE.md` - Arquitetura do projeto
