# 📤 Endpoint de Upload DICOM

Guia completo para usar o endpoint de upload de arquivos DICOM.

---

## 🎯 Endpoint

**URL:** `POST /api/studies/upload/`

**Base URL:** `http://localhost:8000`

**Full URL:** `http://localhost:8000/api/studies/upload/`

---

## 📋 Parâmetros

### Obrigatórios

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `dicom_zip` | File | Arquivo ZIP contendo arquivos DICOM |
| `npz_file` | File | Arquivo NPZ (alternativa ao ZIP) |
| `file` | File | Alias compatível (aceita .zip ou .npz) |
| `Authorization` | Header | Token de autenticação: `Bearer test-token` |

### Opcionais

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `category_id` | String | "1" | ID da categoria de análise |

---

## ✅ Exemplos

### 1. Com curl (Simples)

```bash
curl -X POST http://localhost:8000/api/studies/upload/ \
  -H "Authorization: Bearer test-token" \
  -F "dicom_zip=@seu_arquivo.zip"
```

### 2. Com curl (Com category_id)

```bash
curl -X POST http://localhost:8000/api/studies/upload/ \
  -H "Authorization: Bearer test-token" \
  -F "dicom_zip=@seu_arquivo.zip" \
  -F "category_id=1"
```

### 3. Com curl (Upload NPZ)

```bash
curl -X POST http://localhost:8000/api/studies/upload/ \
  -H "Authorization: Bearer test-token" \
  -F "npz_file=@seu_arquivo.npz" \
  -F "category_id=1"
```

### 4. Com curl (Verbose)

```bash
curl -v -X POST http://localhost:8000/api/studies/upload/ \
  -H "Authorization: Bearer test-token" \
  -F "dicom_zip=@seu_arquivo.zip" \
  | python -m json.tool
```

### 5. Com Python

```python
import requests

url = "http://localhost:8000/api/studies/upload/"
headers = {"Authorization": "Bearer test-token"}

with open("seu_arquivo.zip", "rb") as f:
    files = {"dicom_zip": f}
    data = {"category_id": "1"}
    response = requests.post(url, headers=headers, files=files, data=data)

print(response.json())
```

### 6. Com Postman

**Passo-a-passo:**
1. Método: `POST`
2. URL: `http://localhost:8000/api/studies/upload/`
3. Headers:
   - `Authorization: Bearer test-token`
4. Body → form-data:
   - Key: `file` → Type: `File` → Selecione arquivo
   - Key: `category_id` → Type: `Text` → Value: `1`
5. Clique "Send"

---

## 📊 Resposta Bem-Sucedida (201)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "clinic_id": "16bd4737-e71b-4c35-83b7-59b0db657d21",
  "owner": {
    "id": 1,
    "email": "dev@example.com",
    "full_name": "Dev User"
  },
  "category": "1",
  "status": "PROCESSING",
  "inference_job_id": "job_abc123def456",
  "s3_key": null,
  "created_at": "2026-02-11T20:00:00Z",
  "updated_at": "2026-02-11T20:00:00Z"
}
```

### Campos da Resposta

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUID | ID único do estudo |
| `clinic_id` | UUID | ID da clínica |
| `owner` | Object | Dados do proprietário |
| `category` | String | Categoria de análise |
| `status` | String | Status do estudo (PROCESSING, COMPLETED, FAILED) |
| `inference_job_id` | String | ID do job na API de inferência |
| `s3_key` | String | Chave do resultado em S3 (null até conclusão) |
| `created_at` | DateTime | Data de criação |
| `updated_at` | DateTime | Data de última atualização |

---

## ❌ Erros Comuns

### 401 - Não Autorizado

```json
{"detail": "Failed to validate token"}
```

**Causa:** Token inválido ou não fornecido

**Solução:**
```bash
# Verificar header
curl -H "Authorization: Bearer test-token" ...

# Ou iniciar Django
python manage.py runserver
```

### 400 - Requisição Inválida

```json
{"error": "No file provided"}
```

**Causa:** Arquivo não foi enviado

**Solução:**
```bash
# Verificar arquivo existe
ls -la seu_arquivo.zip

# Usar -F corretamente
curl -F "file=@seu_arquivo.zip" ...
```

### 400 - Usuário sem Clínica

```json
{"error": "User must belong to a clinic"}
```

**Causa:** Usuário não está vinculado a uma clínica

**Solução:** Em modo desenvolvimento, a clínica é criada automaticamente. Reinicie o servidor:
```bash
# Parar (Ctrl+C)

# Iniciar novamente
python manage.py runserver
```

### 413 - Arquivo Muito Grande

```json
{"detail": "File too large. Maximum size is 500MB."}
```

**Causa:** Arquivo maior que o limite

**Solução:** Aumentar limite em `settings.py`:
```python
DATA_UPLOAD_MAX_MEMORY_SIZE = 1000000000  # 1GB
FILE_UPLOAD_MAX_MEMORY_SIZE = 1000000000  # 1GB
```

### 500 - Erro Interno

```json
{"error": "..."}
```

**Causa:** Erro no processamento

**Solução:** Verificar logs:
```bash
# Ver logs do Django
docker-compose logs -f web

# Ou sem Docker
# Ver terminal onde Django está rodando
```

---

## 🔄 Fluxo Completo

### 1. Upload do Arquivo

```bash
curl -X POST http://localhost:8000/api/studies/upload/ \
  -H "Authorization: Bearer test-token" \
  -F "file=@seu_arquivo.zip"
```

**Resposta:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "inference_job_id": "job_abc123"
}
```

### 2. Verificar Status

```bash
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/studies/550e8400-e29b-41d4-a716-446655440000/status/
```

**Resposta:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "job": {
    "status": "RUNNING",
    "progress": 45
  }
}
```

### 3. Obter Resultado

Quando `status` = "COMPLETED":

```bash
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/studies/550e8400-e29b-41d4-a716-446655440000/result/
```

**Resposta:**
```json
{
  "study_id": "550e8400-e29b-41d4-a716-446655440000",
  "image_url": "https://s3.amazonaws.com/...",
  "mask_url": "https://s3.amazonaws.com/...",
  "expires_in": 3600,
  "image_file_name": "study_550e8400-e29b-41d4-a716-446655440000_image.nii.gz",
  "mask_file_name": "study_550e8400-e29b-41d4-a716-446655440000_mask.nii.gz"
}
```

---

## 🧪 Script de Teste Completo

```bash
#!/bin/bash

# Configuração
API_URL="http://localhost:8000"
TOKEN="test-token"
FILE="seu_arquivo.zip"

echo "📤 Iniciando upload..."

# 1. Upload
RESPONSE=$(curl -s -X POST "$API_URL/api/studies/upload/" \
  -H "Authorization: Bearer $TOKEN" \
  -F "dicom_zip=@$FILE")

STUDY_ID=$(echo $RESPONSE | python -c "import sys, json; print(json.load(sys.stdin)['id'])")

echo "✅ Upload concluído!"
echo "📋 Study ID: $STUDY_ID"

# 2. Verificar status
echo ""
echo "⏳ Aguardando processamento..."

for i in {1..10}; do
  STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "$API_URL/api/studies/$STUDY_ID/status/" | \
    python -c "import sys, json; print(json.load(sys.stdin)['status'])")
  
  echo "  Status: $STATUS"
  
  if [ "$STATUS" = "COMPLETED" ]; then
    echo "✅ Processamento concluído!"
    break
  fi
  
  sleep 5
done

# 3. Obter resultado
echo ""
echo "📥 Obtendo resultado..."

RESULT=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_URL/api/studies/$STUDY_ID/result/")

IMAGE_URL=$(echo $RESULT | python -c "import sys, json; print(json.load(sys.stdin)['image_url'])")
MASK_URL=$(echo $RESULT | python -c "import sys, json; print(json.load(sys.stdin)['mask_url'])")

echo "✅ Resultado pronto!"
echo "🖼️ Image URL: $IMAGE_URL"
echo "🎭 Mask URL: $MASK_URL"
```

---

## 📊 Categorias Disponíveis

As categorias definem o tipo de análise a ser realizada:

| ID | Categoria | Descrição |
|----|-----------|-----------|
| 1 | Lung Cancer Detection | Detecção de câncer de pulmão |
| 2 | Liver Segmentation | Segmentação de fígado |
| 3 | Brain Tumor Detection | Detecção de tumor cerebral |
| ... | ... | ... |

**Nota:** Consulte `/api/clinics/categories/` para lista completa.

---

## 🔐 Segurança

### Autenticação

- ✅ Token Bearer obrigatório
- ✅ Validação de usuário
- ✅ Isolamento por clínica

### Validação

- ✅ Arquivo obrigatório
- ✅ Limite de tamanho
- ✅ Validação de formato

### Logging

- ✅ Todos os uploads são registrados
- ✅ Audit trail completo
- ✅ LGPD compliant

---

## 🚀 Próximos Passos

1. **Upload do arquivo** ← Você está aqui
2. **Verificar status** → `/api/studies/{id}/status/`
3. **Obter resultado** → `/api/studies/{id}/result/`
4. **Download do arquivo** → URL assinada do S3

---

## 📞 Troubleshooting

### Arquivo não é aceito

```bash
# Verificar se é um ZIP válido
file seu_arquivo.zip

# Ou tentar com um arquivo de teste
zip test.zip test.dcm
```

### Processamento muito lento

```bash
# Verificar se a API de inferência está rodando
curl http://localhost:8001/health/

# Ou verificar logs
docker-compose logs -f web
```

### Resultado não aparece

```bash
# Aguardar mais tempo
sleep 30

# Ou verificar status
curl -H "Authorization: Bearer test-token" \
  http://localhost:8000/api/studies/{id}/status/
```

---

**Pronto para fazer upload!** 📤✅
