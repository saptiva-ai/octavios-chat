#!/bin/bash
# ============================================================================
# SCRIPT DE VALIDACIÓN DE CONFIGURACIÓN DEL SERVIDOR
# ============================================================================
# Ejecutar en el servidor de producción para auditar la configuración
# Usage: ./scripts/validate-env-server.sh
#
# Exit codes:
#   0 - Todo OK
#   1 - Errores críticos encontrados
#   2 - Solo warnings (no críticos)

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 AUDITORÍA DE CONFIGURACIÓN - Copilotos Bridge"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Detectar si estamos en el directorio correcto
if [ ! -d "infra" ] || [ ! -d "envs" ]; then
    echo "❌ Error: Ejecuta este script desde el directorio raíz del proyecto"
    echo "   cd /home/jf/octavios-bridge && bash scripts/validate-env-server.sh"
    exit 1
fi

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Contadores
ERRORS=0
WARNINGS=0
OK=0

# Función para reportar
report_ok() {
    echo -e "${GREEN}✓${NC} $1"
    ((OK++))
}

report_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

report_error() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

report_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

# ============================================================================
# 1. VERIFICAR ARCHIVOS .ENV
# ============================================================================
echo -e "\n${BLUE}[1/7]${NC} Verificando archivos de configuración..."

if [ -f "envs/.env.prod" ]; then
    report_ok "Archivo envs/.env.prod existe"
    ENV_FILE="envs/.env.prod"
elif [ -f "envs/.env" ]; then
    report_warn "Usando envs/.env (recomendado: .env.prod para producción)"
    ENV_FILE="envs/.env"
else
    report_error "No se encontró archivo .env ni .env.prod"
    echo ""
    echo "Crea uno con: cp envs/.env.production.example envs/.env.prod"
    exit 1
fi

report_info "Usando: $ENV_FILE"

# ============================================================================
# 2. VALIDAR LÍMITES DE ARCHIVOS (4 CAPAS)
# ============================================================================
echo -e "\n${BLUE}[2/7]${NC} Validando límites de archivos (multi-capa)..."

# Capa 1: Nginx
if [ -f "infra/nginx/nginx.conf" ]; then
    NGINX_LIMIT=$(grep -oP 'client_max_body_size\s+\K\d+' infra/nginx/nginx.conf 2>/dev/null || echo "0")
    if [ "$NGINX_LIMIT" = "50" ]; then
        report_ok "Nginx: client_max_body_size = 50M"
    else
        report_error "Nginx: client_max_body_size = ${NGINX_LIMIT}M (debe ser 50M)"
        report_info "Fix: sed -i 's/client_max_body_size [0-9]*M/client_max_body_size 50M/' infra/nginx/nginx.conf"
    fi
else
    report_warn "Nginx config no encontrado (infra/nginx/nginx.conf)"
fi

# Capa 2: Backend
BACKEND_LIMIT=$(grep -oP '^MAX_FILE_SIZE=\K\d+' "$ENV_FILE" 2>/dev/null || echo "0")
EXPECTED_BYTES=52428800
if [ "$BACKEND_LIMIT" = "$EXPECTED_BYTES" ]; then
    report_ok "Backend: MAX_FILE_SIZE = 52428800 bytes (50MB)"
elif [ "$BACKEND_LIMIT" = "0" ]; then
    report_error "Backend: MAX_FILE_SIZE no configurado"
    report_info "Fix: echo 'MAX_FILE_SIZE=52428800' >> $ENV_FILE"
else
    report_error "Backend: MAX_FILE_SIZE = ${BACKEND_LIMIT} (debe ser 52428800)"
    report_info "Fix: sed -i 's/^MAX_FILE_SIZE=.*/MAX_FILE_SIZE=52428800/' $ENV_FILE"
fi

# Capa 3 y 4: Frontend (Build + Runtime)
FRONTEND_LIMIT=$(grep -oP '^NEXT_PUBLIC_MAX_FILE_SIZE_MB=\K\d+' "$ENV_FILE" 2>/dev/null || echo "0")
if [ "$FRONTEND_LIMIT" = "50" ]; then
    report_ok "Frontend: NEXT_PUBLIC_MAX_FILE_SIZE_MB = 50"
elif [ "$FRONTEND_LIMIT" = "0" ]; then
    report_error "Frontend: NEXT_PUBLIC_MAX_FILE_SIZE_MB no configurado"
    report_info "Fix: Ejecuta scripts/fix-env-server.sh"
else
    report_error "Frontend: NEXT_PUBLIC_MAX_FILE_SIZE_MB = ${FRONTEND_LIMIT} (debe ser 50)"
    report_info "Fix: sed -i 's/^NEXT_PUBLIC_MAX_FILE_SIZE_MB=.*/NEXT_PUBLIC_MAX_FILE_SIZE_MB=50/' $ENV_FILE"
fi

# ============================================================================
# 3. VALIDAR URLs Y ENDPOINTS
# ============================================================================
echo -e "\n${BLUE}[3/7]${NC} Validando URLs y endpoints..."

API_URL=$(grep -oP '^NEXT_PUBLIC_API_URL=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "")
if [[ "$API_URL" =~ ^https:// ]]; then
    report_ok "NEXT_PUBLIC_API_URL usa HTTPS: $API_URL"
elif [[ "$API_URL" =~ ^http://.*:8001$ ]]; then
    report_warn "NEXT_PUBLIC_API_URL apunta directo al API: $API_URL"
    report_info "Recomendado: Usar nginx proxy (http://IP/api en vez de http://IP:8001)"
elif [[ "$API_URL" =~ ^http://.*/api$ ]]; then
    report_ok "NEXT_PUBLIC_API_URL usa nginx proxy: $API_URL"
else
    report_error "NEXT_PUBLIC_API_URL mal configurado: $API_URL"
fi

DOMAIN=$(grep -oP '^DOMAIN=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "")
if [ -n "$DOMAIN" ]; then
    report_ok "DOMAIN configurado: $DOMAIN"
else
    report_warn "DOMAIN no configurado (opcional)"
fi

# ============================================================================
# 4. VERIFICAR VARIABLES CRÍTICAS
# ============================================================================
echo -e "\n${BLUE}[4/7]${NC} Verificando secrets y credenciales..."

check_var() {
    local var_name=$1
    local min_length=$2
    local value=$(grep -oP "^${var_name}=\K.*" "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "")

    if [ -z "$value" ]; then
        report_error "$var_name no está configurado"
    elif [ ${#value} -lt $min_length ]; then
        report_error "$var_name muy corto (${#value} chars, mínimo $min_length)"
    elif [[ "$value" == *"CHANGE_ME"* ]] || [[ "$value" == *"change_me"* ]]; then
        report_error "$var_name contiene valor de ejemplo: ${value:0:30}..."
        report_info "Fix: openssl rand -hex 32"
    elif [[ "$value" == *"dev-"* ]] && [[ "$ENV_FILE" == *".prod"* ]]; then
        report_error "$var_name contiene prefijo 'dev-' en producción"
        report_info "Fix: openssl rand -hex 32"
    else
        report_ok "$var_name configurado (${#value} chars)"
    fi
}

check_var "JWT_SECRET_KEY" 32
check_var "SECRET_KEY" 32
check_var "MONGODB_PASSWORD" 16
check_var "REDIS_PASSWORD" 16
check_var "SAPTIVA_API_KEY" 40

# ============================================================================
# 5. DETECTAR PROBLEMAS COMUNES
# ============================================================================
echo -e "\n${BLUE}[5/7]${NC} Detectando problemas comunes..."

# Variables duplicadas
DUPLICATES=$(grep -v '^#' "$ENV_FILE" | grep -v '^$' | cut -d= -f1 | sort | uniq -d)
if [ -n "$DUPLICATES" ]; then
    report_warn "Variables duplicadas encontradas:"
    echo "$DUPLICATES" | while read dup; do
        LINE_NUMBERS=$(grep -n "^${dup}=" "$ENV_FILE" | cut -d: -f1 | tr '\n' ',' | sed 's/,$//')
        echo "  ${YELLOW}•${NC} $dup (líneas: $LINE_NUMBERS)"
    done
    report_info "Fix: scripts/fix-env-server.sh eliminará duplicados automáticamente"
else
    report_ok "No hay variables duplicadas"
fi

# CORS permite localhost en producción
if grep -q "localhost" "$ENV_FILE" && [[ "$ENV_FILE" == *".prod"* ]]; then
    CORS_LINE=$(grep -n "localhost" "$ENV_FILE" | head -1)
    report_warn "Configuración contiene 'localhost' (innecesario en producción)"
    echo "  ${YELLOW}•${NC} $CORS_LINE"
fi

# LOG_LEVEL en producción
LOG_LEVEL=$(grep -oP '^LOG_LEVEL=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "info")
if [ "$LOG_LEVEL" = "debug" ] && [[ "$ENV_FILE" == *".prod"* ]]; then
    report_warn "LOG_LEVEL=debug en producción (performance impact)"
    report_info "Recomendado: LOG_LEVEL=info o LOG_LEVEL=warning"
else
    report_ok "LOG_LEVEL=$LOG_LEVEL"
fi

# ============================================================================
# 6. VERIFICAR IMÁGENES DOCKER
# ============================================================================
echo -e "\n${BLUE}[6/7]${NC} Verificando imágenes Docker..."

# Determinar nombres de contenedores según COMPOSE_PROJECT_NAME
PROJECT_NAME=$(grep -oP '^COMPOSE_PROJECT_NAME=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "octavios")

check_image() {
    local image_name=$1
    local container_name="${PROJECT_NAME}-${image_name}"

    if docker image inspect "${PROJECT_NAME}-${image_name}:latest" &> /dev/null; then
        BUILD_DATE=$(docker image inspect "${PROJECT_NAME}-${image_name}:latest" --format='{{.Created}}' 2>/dev/null | cut -d'T' -f1)
        report_ok "Imagen ${PROJECT_NAME}-${image_name}:latest existe (build: $BUILD_DATE)"

        # Verificar si el contenedor está corriendo
        if docker ps --filter "name=${container_name}" --format '{{.Names}}' | grep -q "${container_name}"; then
            report_ok "Contenedor ${container_name} está corriendo"
        else
            report_warn "Contenedor ${container_name} no está corriendo"
        fi
    else
        report_error "Imagen ${PROJECT_NAME}-${image_name}:latest no encontrada"
        report_info "Requiere deployment con imagen reconstruida"
    fi
}

check_image "web"
check_image "api"

# ============================================================================
# 7. VERIFICAR SERVICIOS DEPENDIENTES
# ============================================================================
echo -e "\n${BLUE}[7/7]${NC} Verificando servicios dependientes..."

# MongoDB
if docker ps --filter "name=mongodb" --format '{{.Names}}' | grep -q "mongodb"; then
    report_ok "MongoDB está corriendo"

    # Test de conexión
    MONGO_USER=$(grep -oP '^MONGODB_USER=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "")
    if [ -n "$MONGO_USER" ]; then
        if docker exec -it $(docker ps --filter "name=mongodb" --format '{{.Names}}' | head -1) mongosh --eval "db.runCommand('ping')" &> /dev/null; then
            report_ok "MongoDB responde a ping"
        else
            report_warn "MongoDB no responde (puede estar iniciando)"
        fi
    fi
else
    report_error "MongoDB no está corriendo"
fi

# Redis
if docker ps --filter "name=redis" --format '{{.Names}}' | grep -q "redis"; then
    report_ok "Redis está corriendo"

    REDIS_PASS=$(grep -oP '^REDIS_PASSWORD=\K.*' "$ENV_FILE" 2>/dev/null | tr -d '"' || echo "")
    if [ -n "$REDIS_PASS" ]; then
        if docker exec $(docker ps --filter "name=redis" --format '{{.Names}}' | head -1) redis-cli -a "$REDIS_PASS" ping &> /dev/null; then
            report_ok "Redis responde a PING"
        else
            report_warn "Redis no responde (verificar password)"
        fi
    fi
else
    report_error "Redis no está corriendo"
fi

# Nginx
if docker ps --filter "name=nginx" --format '{{.Names}}' | grep -q "nginx"; then
    report_ok "Nginx está corriendo"
else
    report_warn "Nginx no está corriendo (opcional si no se usa proxy)"
fi

# ============================================================================
# RESUMEN FINAL
# ============================================================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📋 RESUMEN DE AUDITORÍA${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}OK:${NC}       $OK checks pasaron"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS advertencias"
echo -e "${RED}Errores:${NC}  $ERRORS errores críticos"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}⚠️  ACCIÓN REQUERIDA: Hay $ERRORS errores críticos${NC}"
    echo ""
    echo "Opciones para corregir:"
    echo "  1. Automático: bash scripts/fix-env-server.sh"
    echo "  2. Manual: Edita $ENV_FILE según las recomendaciones arriba"
    echo ""
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}ℹ️  Hay $WARNINGS advertencias (no críticas)${NC}"
    echo "El sistema puede funcionar, pero se recomienda revisar los warnings."
    echo ""
    exit 2
else
    echo -e "${GREEN}✅ Configuración correcta. Sistema listo para operar.${NC}"
    echo ""
    echo "Siguiente paso:"
    echo "  • Prueba upload de HPE.pdf: curl -F file=@tests/data/pdf/HPE.pdf http://DOMAIN/api/documents/upload"
    echo ""
    exit 0
fi
