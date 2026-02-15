# 🐳 Guia: Testar Docker Localmente

Como o sandbox tem limitações de iptables, este guia mostra como testar o Docker Compose **na sua máquina local**.

## ✅ Pré-requisitos

- ✅ Docker Desktop instalado (Windows/macOS)
- ✅ Ou Docker + Docker Compose (Linux)
- ✅ Projeto Vizier Med Backend extraído

## 🚀 Passo-a-Passo

### 1. Preparar Projeto

```bash
# Extrair
tar -xzf vizier_backend.tar.gz
cd vizier_backend

# Verificar arquivos
ls -la Dockerfile docker-compose.yml .env.example
```

### 2. Configurar Ambiente

```bash
# Copiar .env
cp .env.example .env

# Editar (abrir com seu editor)
# nano .env
# ou
# code .env

# Valores para desenvolvimento:
# DEBUG=True
# COGNITO_USER_POOL_ID=  (deixar vazio)
# COGNITO_CLIENT_ID=     (deixar vazio)
# AWS_ACCESS_KEY_ID=     (deixar vazio)
# AWS_SECRET_ACCESS_KEY= (deixar vazio)
# INFERENCE_API_URL=http://localhost:8001
```

### 3. Build das Imagens

```bash
# Build (vai baixar ~500MB de imagens)
docker-compose build

# Saída esperada:
# [+] Building 45.2s (12/12) FINISHED
# => [web] exporting to image
# => => writing image sha256:abc123...
# => => naming to docker.io/library/vizier_backend-web:latest
```

**Tempo esperado:** 5-10 minutos (primeira vez)

### 4. Iniciar Serviços

```bash
# Iniciar em background
docker-compose up -d

# Ver status
docker-compose ps

# Saída esperada:
# NAME            COMMAND                  SERVICE   STATUS
# vizier_db_1     "postgres"               db        Up 10 seconds
# vizier_redis_1  "redis-server"           redis     Up 10 seconds
# vizier_web_1    "python manage.py..."    web       Up 10 seconds
```

### 5. Executar Migrations

```bash
# Rodar migrations
docker-compose exec web python manage.py migrate

# Saída esperada:
# Operations to perform:
#   Apply all migrations: accounts, admin, audit, auth, ...
# Running migrations:
#   Applying accounts.0001_initial... OK
#   Applying audit.0001_initial... OK
#   Applying health.0001_initial... OK
#   Applying studies.0001_initial... OK
#   Applying tenants.0001_initial... OK
#   ...
```

### 6. Testar Health Check

```bash
# Health check
curl http://localhost:8000/api/health/

# Resposta esperada:
# {"status":"healthy","service":"vizier-med-backend","version":"1.0.0"}
```

### 7. Testar Endpoints

```bash
# Listar clínicas
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/clinics/clinics/

# Resposta esperada:
# {
#   "count": 1,
#   "next": null,
#   "previous": null,
#   "results": [
#     {
#       "id": "...",
#       "name": "Development Clinic",
#       "cnpj": "00000000000191",
#       ...
#     }
#   ]
# }

# Listar estudos
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/studies/studies/

# Resposta esperada:
# {
#   "count": 0,
#   "next": null,
#   "previous": null,
#   "results": []
# }
```

### 8. Ver Logs

```bash
# Logs em tempo real
docker-compose logs -f web

# Logs do banco
docker-compose logs -f db

# Logs do Redis
docker-compose logs -f redis

# Últimas 100 linhas
docker-compose logs --tail=100 web
```

## 🧪 Testes Completos

### Teste 1: Health Check

```bash
curl -v http://localhost:8000/api/health/

# Esperado:
# HTTP/1.1 200 OK
# Content-Type: application/json
# {"status":"healthy","service":"vizier-med-backend","version":"1.0.0"}
```

### Teste 2: Autenticação

```bash
# Sem token (deve retornar erro)
curl http://localhost:8000/api/clinics/clinics/
# Resposta: {"detail":"As credenciais de autenticação não foram fornecidas."}

# Com token (deve funcionar)
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/clinics/clinics/
# Resposta: {"count": 1, "results": [...]}
```

### Teste 3: Banco de Dados

```bash
# Acessar PostgreSQL
docker-compose exec db psql -U vizier_user -d vizier_med

# Comandos SQL:
\dt                           # Listar tabelas
SELECT * FROM accounts_user;  # Ver usuários
SELECT * FROM tenants_clinic; # Ver clínicas
\q                            # Sair
```

### Teste 4: Redis

```bash
# Acessar Redis
docker-compose exec redis redis-cli

# Comandos:
KEYS *                        # Listar chaves
INFO                          # Informações
FLUSHALL                      # Limpar (CUIDADO!)
exit                          # Sair
```

### Teste 5: Django Shell

```bash
# Acessar Django shell
docker-compose exec web python manage.py shell

# Comandos Python:
from apps.accounts.models import User
from apps.tenants.models import Clinic

# Ver usuários
User.objects.all()

# Ver clínicas
Clinic.objects.all()

# Sair
exit()
```

## 📊 Verificar Tudo Está Funcionando

```bash
# Verificar containers
docker-compose ps

# Verificar logs
docker-compose logs

# Verificar health
curl http://localhost:8000/api/health/

# Verificar banco
docker-compose exec db pg_isready

# Verificar Redis
docker-compose exec redis redis-cli ping
```

**Tudo deve estar "Up" e respondendo.**

## 🔧 Comandos Úteis

### Parar Serviços

```bash
# Parar (mantém dados)
docker-compose down

# Parar e remover volumes (CUIDADO: deleta dados!)
docker-compose down -v

# Parar apenas um serviço
docker-compose stop web
```

### Reiniciar

```bash
# Reiniciar tudo
docker-compose restart

# Reiniciar um serviço
docker-compose restart web

# Rebuild e restart
docker-compose up -d --build
```

### Logs

```bash
# Logs completos
docker-compose logs

# Logs em tempo real
docker-compose logs -f

# Logs de um serviço
docker-compose logs -f web

# Últimas N linhas
docker-compose logs --tail=50 web

# Salvar logs
docker-compose logs > logs.txt
```

### Executar Comandos

```bash
# Django manage.py
docker-compose exec web python manage.py <comando>

# Exemplos:
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
docker-compose exec web python manage.py test
docker-compose exec web python manage.py shell

# Bash
docker-compose exec web bash

# Python
docker-compose exec web python
```

## 🐛 Troubleshooting

### Erro: "Port already in use"

```bash
# Encontrar processo
lsof -i :8000

# Matar processo
kill -9 <PID>

# Ou mudar porta em docker-compose.yml:
# ports:
#   - "8001:8000"
```

### Erro: "Cannot connect to database"

```bash
# Verificar logs
docker-compose logs db

# Reiniciar banco
docker-compose restart db

# Aguardar e tentar migrations novamente
sleep 10
docker-compose exec web python manage.py migrate
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

### Erro: "Health check failed"

```bash
# Ver logs
docker-compose logs web

# Verificar se servidor está rodando
curl http://localhost:8000/api/health/

# Reiniciar
docker-compose restart web
```

## 📈 Monitoramento

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
# Ver status
docker-compose ps

# Ou verificar manualmente
curl http://localhost:8000/api/health/
docker-compose exec db pg_isready
docker-compose exec redis redis-cli ping
```

## 🎯 Checklist de Teste

- [ ] Docker e Docker Compose instalados
- [ ] Projeto extraído
- [ ] `.env` configurado
- [ ] `docker-compose build` completou com sucesso
- [ ] `docker-compose up -d` iniciou todos os serviços
- [ ] `docker-compose ps` mostra todos "Up"
- [ ] Migrations executadas
- [ ] Health check retorna 200 OK
- [ ] Endpoints respondendo com autenticação
- [ ] Banco de dados acessível
- [ ] Redis acessível
- [ ] Logs sem erros críticos

## 🚀 Próximos Passos

1. **Testar endpoints** via curl ou Postman
2. **Conectar sua API** de inferência
3. **Fazer upload de DICOM** para testar pipeline
4. **Configurar Cognito** (se necessário)
5. **Configurar S3** (se necessário)
6. **Deploy em produção**

## 📚 Referências

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Django Documentation](https://docs.djangoproject.com/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

**Tudo pronto para testar!** 🐳✅
