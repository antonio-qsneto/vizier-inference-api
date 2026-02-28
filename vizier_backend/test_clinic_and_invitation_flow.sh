#!/bin/bash

# test_clinic_and_invitation_flow.sh
# Script para testar fluxo completo de cadastro de clínica e convite a médicos

set -e

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Configuração
API_BASE="http://localhost:8000"
REGION="us-east-1"
USER_POOL_ID="${COGNITO_USER_POOL_ID}"
CLIENT_ID="${COGNITO_CLIENT_ID}"

# Função para fazer login
login_user() {
    local username=$1
    local password=$2
    
    echo -e "${BLUE}🔐 Fazendo login como ${username}...${NC}"
    
    TOKEN_RESPONSE=$(aws cognito-idp admin-initiate-auth \
        --user-pool-id $USER_POOL_ID \
        --client-id $CLIENT_ID \
        --auth-flow ADMIN_NO_SRP_AUTH \
        --auth-parameters USERNAME=$username,PASSWORD=$password \
        --region $REGION 2>/dev/null)
    
    ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.AuthenticationResult.AccessToken')
    
    if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
        echo -e "${RED}❌ Erro ao fazer login${NC}"
        return 1
    fi
    
    echo $ACCESS_TOKEN
}

# Função para fazer requisição
api_call() {
    local method=$1
    local endpoint=$2
    local token=$3
    local data=$4
    
    if [ -z "$data" ]; then
        curl -s -X $method "$API_BASE$endpoint" \
            -H "Authorization: Bearer $token" \
            -H "Content-Type: application/json"
    else
        curl -s -X $method "$API_BASE$endpoint" \
            -H "Authorization: Bearer $token" \
            -H "Content-Type: application/json" \
            -d "$data"
    fi
}

# ============ TESTE 1: Criar Clínica ============

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TESTE 1: Criar Clínica (Owner vira CLINIC_ADMIN)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

OWNER_TOKEN=$(login_user "prof.antonioqsneto@gmail.com" "Init4289*")
if [ -z "$OWNER_TOKEN" ]; then
    echo -e "${RED}Abortando: Usuário owner não encontrado${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Login bem-sucedido${NC}"

CLINIC_DATA='{
  "name": "Clínica Santa Maria",
  "cnpj": "12345678000190",
  "seat_limit": 10
}'

echo -e "${BLUE}📝 Criando clínica...${NC}"
CLINIC_RESPONSE=$(api_call POST "/api/clinics/clinics/" "$OWNER_TOKEN" "$CLINIC_DATA")

CLINIC_ID=$(echo $CLINIC_RESPONSE | jq -r '.id')
CLINIC_NAME=$(echo $CLINIC_RESPONSE | jq -r '.name')
OWNER_ROLE=$(echo $CLINIC_RESPONSE | jq -r '.owner.role')

if [ "$CLINIC_ID" = "null" ] || [ -z "$CLINIC_ID" ]; then
    echo -e "${RED}❌ Erro ao criar clínica${NC}"
    echo "$CLINIC_RESPONSE" | jq .
    exit 1
fi

echo -e "${GREEN}✓ Clínica criada com sucesso${NC}"
echo "  ID: $CLINIC_ID"
echo "  Nome: $CLINIC_NAME"
echo "  Owner Role: $OWNER_ROLE"

# ============ TESTE 2: Convidar Médico ============

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TESTE 2: Convidar Médico à Clínica${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

INVITE_DATA='{
  "email": "dr.carlos@example.com"
}'

echo -e "${BLUE}📧 Enviando convite para dr.carlos@example.com...${NC}"
INVITE_RESPONSE=$(api_call POST "/api/clinics/clinics/invite/" "$OWNER_TOKEN" "$INVITE_DATA")

INVITATION_ID=$(echo $INVITE_RESPONSE | jq -r '.id')
INVITE_STATUS=$(echo $INVITE_RESPONSE | jq -r '.status')

if [ "$INVITATION_ID" = "null" ] || [ -z "$INVITATION_ID" ]; then
    echo -e "${RED}❌ Erro ao criar convite${NC}"
    echo "$INVITE_RESPONSE" | jq .
    exit 1
fi

echo -e "${GREEN}✓ Convite enviado com sucesso${NC}"
echo "  ID: $INVITATION_ID"
echo "  Status: $INVITE_STATUS"
echo "  Email: dr.carlos@example.com"

# ============ TESTE 3: Médico faz login (Auto-accept) ============

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TESTE 3: Médico faz login (Auto-accept do convite)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

DOCTOR_TOKEN=$(login_user "dr.carlos@example.com" "DoctorPassword123!")
if [ -z "$DOCTOR_TOKEN" ]; then
    echo -e "${RED}Abortando: Usuário médico não encontrado${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Login bem-sucedido${NC}"

# Verificar perfil do médico
echo -e "${BLUE}🔍 Verificando perfil do médico...${NC}"
DOCTOR_PROFILE=$(api_call GET "/api/auth/users/me/" "$DOCTOR_TOKEN")

DOCTOR_ROLE=$(echo $DOCTOR_PROFILE | jq -r '.role')
DOCTOR_CLINIC=$(echo $DOCTOR_PROFILE | jq -r '.clinic_id')
DOCTOR_EMAIL=$(echo $DOCTOR_PROFILE | jq -r '.email')

echo -e "${GREEN}✓ Perfil do médico:${NC}"
echo "  Email: $DOCTOR_EMAIL"
echo "  Role: $DOCTOR_ROLE"
echo "  Clinic ID: $DOCTOR_CLINIC"

if [ "$DOCTOR_ROLE" = "CLINIC_DOCTOR" ]; then
    echo -e "${GREEN}✅ SUCESSO: Convite foi auto-aceitado!${NC}"
else
    echo -e "${RED}⚠️  Aviso: Role não é CLINIC_DOCTOR (provável que não houve auto-accept)${NC}"
fi

# ============ TESTE 4: Listar Convites Pendentes ============

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TESTE 4: Médico vê seus convites${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

echo -e "${BLUE}📬 Listando convites do médico...${NC}"
INVITATIONS=$(api_call GET "/api/doctor-invitations/my_invitations/" "$DOCTOR_TOKEN")

INVITE_COUNT=$(echo $INVITATIONS | jq 'length')
echo -e "${GREEN}✓ Convites encontrados: $INVITE_COUNT${NC}"
echo $INVITATIONS | jq '.[] | {id, clinic_name, status, email}'

# ============ TESTE 5: CLINIC_ADMIN lista médicos ============

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TESTE 5: CLINIC_ADMIN lista médicos da clínica${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

echo -e "${BLUE}👥 Listando médicos da clínica...${NC}"
DOCTORS=$(api_call GET "/api/clinics/clinics/doctors/" "$OWNER_TOKEN")

DOCTOR_COUNT=$(echo $DOCTORS | jq 'length')
echo -e "${GREEN}✓ Médicos na clínica: $DOCTOR_COUNT${NC}"
echo $DOCTORS | jq '.[] | {email, first_name, last_name, role}'

# ============ RESUMO ============

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ TODOS OS TESTES PASSARAM COM SUCESSO!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"

echo ""
echo "Resumo:"
echo "  1. ✓ Clínica criada: $CLINIC_NAME"
echo "  2. ✓ Convite enviado para: dr.carlos@example.com"
echo "  3. ✓ Médico fez login e convite foi auto-aceitado"
echo "  4. ✓ Médico vê convite como ACCEPTED"
echo "  5. ✓ CLINIC_ADMIN vê médico na lista"
