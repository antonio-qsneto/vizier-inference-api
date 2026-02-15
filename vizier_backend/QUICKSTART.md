# 🚀 Quick Start - 5 Minutos

Comece a desenvolver em 5 minutos com Docker.

## 1️⃣ Pré-requisitos (1 minuto)

```bash
# Verificar Docker
docker --version
docker compose version

# Se não tiver, instale:
# https://www.docker.com/products/docker-desktop
```

## 2️⃣ Preparar Projeto (1 minuto)

```bash
# Extrair
tar -xzf vizier_backend.tar.gz
cd vizier_backend

# Configurar
cp .env.example .env
```

## 3️⃣ Build (2 minutos)

```bash
# Build das imagens
docker-compose build

# Aguarde completar...
```

## 4️⃣ Iniciar (1 minuto)

```bash
# Iniciar serviços
docker-compose up -d

# Rodar migrations
docker-compose exec web python manage.py migrate

# Pronto!
```

## ✅ Verificar

```bash
# Health check
curl http://localhost:8000/api/health/

# Esperado:
# {"status":"healthy","service":"vizier-med-backend","version":"1.0.0"}
```

## 📍 Acessar

- **API**: http://localhost:8000
- **Admin**: http://localhost:8000/admin/
- **Health**: http://localhost:8000/api/health/

## 🔧 Comandos Úteis

```bash
# Ver logs
docker-compose logs -f web

# Parar
docker-compose down

# Reiniciar
docker-compose restart

# Bash no container
docker-compose exec web bash

# Django shell
docker-compose exec web python manage.py shell
```

## 🧪 Testar API

```bash
# Listar clínicas
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/clinics/clinics/

# Listar estudos
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/studies/studies/
```

## ⚙️ Configurar Sua API

Editar `.env`:

```env
INFERENCE_API_URL=http://seu-servidor:porta
```

## 📚 Documentação Completa

Veja `DOCKER_DEV_GUIDE.md` para guia detalhado.

---

**Pronto!** 🎉 Comece a desenvolver!
