# 🔍 Auditoría y Mejora de Configuración del Servidor de Producción

**Fecha:** 2025-10-21
**Servidor:** jf@34.42.214.246
**Path:** /home/jf/copilotos-bridge/envs/

---

## 📊 Análisis de Configuración Actual

### 1. **Consistencia de Límites de Archivos (Multi-capa)**

La plataforma valida límites de tamaño de archivo en **4 capas diferentes**. Todas deben estar sincronizadas:

| Capa | Variable/Configuración | Valor Correcto | Ubicación |
|------|------------------------|----------------|-----------|
| **Nginx** | `client_max_body_size` | `50M` | `infra/nginx/nginx.conf:12` |
| **Backend (API)** | `MAX_FILE_SIZE` | `52428800` (50MB en bytes) | `envs/.env.prod` |
| **Frontend (Build)** | `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | `50` | `envs/.env.prod` (build arg) |
| **Frontend (Runtime)** | `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | `50` | `docker-compose.prod.yml:168` |

`★ Insight ─────────────────────────────────────`
**Por qué 4 capas:**
- **Nginx**: Primera validación (nivel HTTP) - rechaza requests grandes antes de llegar al backend
- **Backend**: Validación en FastAPI - protección contra archivos maliciosos
- **Frontend (Build)**: Compilado en el bundle JS - validación en el navegador ANTES de subir
- **Frontend (Runtime)**: Variables SSR - necesario para Next.js server-side rendering
`─────────────────────────────────────────────────`

### 2. **Problemas Detectados en .env.prod Local**

#### ✅ Correcto:
```bash
NEXT_PUBLIC_MAX_FILE_SIZE_MB=50        # ✓ Agregado correctamente
MAX_FILE_SIZE=52428800                  # ✓ 50MB en bytes
```

#### ⚠️ Problemas Potenciales:
```bash
# 1. NEXT_PUBLIC_API_URL apunta a IP sin HTTPS
NEXT_PUBLIC_API_URL=http://34.42.214.246:8001
# Problema: Tráfico sin cifrar, cookies inseguras
# Fix: Usar nginx como proxy reverso

# 2. CORS_ORIGINS permite HTTP
CORS_ORIGINS=["http://34.42.214.246:3000","http://34.42.214.246"]
# Problema: Mixed content warnings, CORS en producción
# Fix: Simplificar CORS cuando nginx maneja todo

# 3. Variables duplicadas
LOG_LEVEL=info   # línea 57
LOG_LEVEL=info   # línea 67
# Fix: Eliminar duplicado

# 4. Secrets hardcodeados
JWT_SECRET_KEY=prod-jwt-secret-2024-very-secure-32-chars-key
# Problema: Secret visible en git/logs
# Fix: Usar generador criptográfico
```

---

## 🛠️ Script de Validación del Servidor

Ejecuta esto en el servidor para validar la configuración:

```bash
#!/bin/bash
# validate-env-server.sh
# Validación completa de configuración de producción

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 AUDITORÍA DE CONFIGURACIÓN - Copilotos Bridge"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd /home/jf/copilotos-bridge

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# ============================================================================
# 1. VERIFICAR ARCHIVOS .ENV
# ============================================================================
echo -e "\n${BLUE}[1/6]${NC} Verificando archivos de configuración..."

if [ -f "envs/.env.prod" ]; then
    report_ok "Archivo envs/.env.prod existe"
    ENV_FILE="envs/.env.prod"
elif [ -f "envs/.env" ]; then
    report_warn "Usando envs/.env (falta .env.prod)"
    ENV_FILE="envs/.env"
else
    report_error "No se encontró archivo .env"
    exit 1
fi

# ============================================================================
# 2. VALIDAR LÍMITES DE ARCHIVOS
# ============================================================================
echo -e "\n${BLUE}[2/6]${NC} Validando límites de archivos (4 capas)..."

# Nginx
NGINX_LIMIT=$(grep -oP 'client_max_body_size\s+\K\d+' infra/nginx/nginx.conf || echo "0")
if [ "$NGINX_LIMIT" = "50" ]; then
    report_ok "Nginx: client_max_body_size = 50M"
else
    report_error "Nginx: client_max_body_size = ${NGINX_LIMIT}M (debe ser 50M)"
fi

# Backend
BACKEND_LIMIT=$(grep -oP '^MAX_FILE_SIZE=\K\d+' "$ENV_FILE" || echo "0")
EXPECTED_BYTES=52428800
if [ "$BACKEND_LIMIT" = "$EXPECTED_BYTES" ]; then
    report_ok "Backend: MAX_FILE_SIZE = 52428800 bytes (50MB)"
else
    report_error "Backend: MAX_FILE_SIZE = ${BACKEND_LIMIT} (debe ser 52428800)"
fi

# Frontend Build Arg
FRONTEND_LIMIT=$(grep -oP '^NEXT_PUBLIC_MAX_FILE_SIZE_MB=\K\d+' "$ENV_FILE" || echo "0")
if [ "$FRONTEND_LIMIT" = "50" ]; then
    report_ok "Frontend: NEXT_PUBLIC_MAX_FILE_SIZE_MB = 50"
else
    report_error "Frontend: NEXT_PUBLIC_MAX_FILE_SIZE_MB = ${FRONTEND_LIMIT} (debe ser 50)"
fi

# ============================================================================
# 3. VALIDAR URLs Y ENDPOINTS
# ============================================================================
echo -e "\n${BLUE}[3/6]${NC} Validando URLs y endpoints..."

API_URL=$(grep -oP '^NEXT_PUBLIC_API_URL=\K.*' "$ENV_FILE" | tr -d '"' || echo "")
if [[ "$API_URL" =~ ^https:// ]]; then
    report_ok "NEXT_PUBLIC_API_URL usa HTTPS: $API_URL"
elif [[ "$API_URL" =~ ^http://.*:8001$ ]]; then
    report_warn "NEXT_PUBLIC_API_URL usa HTTP: $API_URL (recomienda proxy reverso)"
else
    report_error "NEXT_PUBLIC_API_URL mal configurado: $API_URL"
fi

# ============================================================================
# 4. VERIFICAR VARIABLES CRÍTICAS
# ============================================================================
echo -e "\n${BLUE}[4/6]${NC} Verificando variables críticas..."

check_var() {
    local var_name=$1
    local min_length=$2
    local value=$(grep -oP "^${var_name}=\K.*" "$ENV_FILE" | tr -d '"' || echo "")

    if [ -z "$value" ]; then
        report_error "$var_name no está configurado"
    elif [ ${#value} -lt $min_length ]; then
        report_error "$var_name muy corto (${#value} chars, mínimo $min_length)"
    elif [[ "$value" == *"CHANGE_ME"* ]] || [[ "$value" == *"dev-"* ]]; then
        report_error "$var_name contiene valor de ejemplo/dev: ${value:0:20}..."
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
echo -e "\n${BLUE}[5/6]${NC} Detectando problemas comunes..."

# Variables duplicadas
DUPLICATES=$(sort "$ENV_FILE" | grep -v '^#' | grep -v '^$' | cut -d= -f1 | uniq -d)
if [ -n "$DUPLICATES" ]; then
    report_warn "Variables duplicadas encontradas:"
    echo "$DUPLICATES" | while read dup; do
        echo "  - $dup"
    done
else
    report_ok "No hay variables duplicadas"
fi

# CORS permite localhost en producción
if grep -q "localhost" "$ENV_FILE"; then
    report_warn "CORS_ORIGINS contiene 'localhost' (no necesario en producción)"
fi

# ============================================================================
# 6. VERIFICAR IMÁGENES DOCKER
# ============================================================================
echo -e "\n${BLUE}[6/6]${NC} Verificando imágenes Docker..."

if docker image inspect copilotos-web:latest &> /dev/null; then
    BUILD_DATE=$(docker image inspect copilotos-web:latest --format='{{.Created}}' | cut -d'T' -f1)
    report_ok "Imagen copilotos-web:latest existe (build: $BUILD_DATE)"

    # Verificar si la imagen tiene la variable embebida
    # (esto requiere inspeccionar el bundle, difícil de automatizar)
else
    report_error "Imagen copilotos-web:latest no encontrada (requiere rebuild)"
fi

if docker image inspect copilotos-api:latest &> /dev/null; then
    report_ok "Imagen copilotos-api:latest existe"
else
    report_error "Imagen copilotos-api:latest no encontrada"
fi

# ============================================================================
# RESUMEN
# ============================================================================
echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📋 RESUMEN DE AUDITORÍA${NC}"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}OK:${NC}       $OK"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "${RED}Errores:${NC}  $ERRORS"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}⚠️  ACCIÓN REQUERIDA: Hay $ERRORS errores críticos${NC}"
    echo "Ejecuta: ./scripts/fix-env-server.sh para corregir automáticamente"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Hay $WARNINGS advertencias (no críticas)${NC}"
    exit 0
else
    echo -e "${GREEN}✅ Configuración correcta. Sistema listo para operar.${NC}"
    exit 0
fi
```

---

## 🔧 Script de Corrección Automática

Guarda esto como `scripts/fix-env-server.sh`:

```bash
#!/bin/bash
# fix-env-server.sh
# Corrige automáticamente problemas comunes en .env de producción

set -e

cd /home/jf/copilotos-bridge/envs/

# Determinar archivo a usar
if [ -f .env.prod ]; then
    ENV_FILE=.env.prod
elif [ -f .env ]; then
    ENV_FILE=.env
else
    echo "❌ Error: No se encontró archivo .env"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 CORRECCIÓN AUTOMÁTICA DE CONFIGURACIÓN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Archivo: $ENV_FILE"
echo ""

# BACKUP
BACKUP_FILE="${ENV_FILE}.backup-$(date +%Y%m%d-%H%M%S)"
cp "$ENV_FILE" "$BACKUP_FILE"
echo "✓ Backup creado: $BACKUP_FILE"

# ============================================================================
# 1. AGREGAR/ACTUALIZAR NEXT_PUBLIC_MAX_FILE_SIZE_MB
# ============================================================================
echo ""
echo "[1/5] Verificando NEXT_PUBLIC_MAX_FILE_SIZE_MB..."

if grep -q "^NEXT_PUBLIC_MAX_FILE_SIZE_MB=" "$ENV_FILE"; then
    # Ya existe, actualizar valor
    sed -i 's/^NEXT_PUBLIC_MAX_FILE_SIZE_MB=.*/NEXT_PUBLIC_MAX_FILE_SIZE_MB=50/' "$ENV_FILE"
    echo "  ✓ Variable actualizada a 50"
else
    # No existe, agregar después de NEXT_PUBLIC_API_URL
    if grep -q "^NEXT_PUBLIC_API_URL=" "$ENV_FILE"; then
        sed -i '/^NEXT_PUBLIC_API_URL=/a NEXT_PUBLIC_MAX_FILE_SIZE_MB=50' "$ENV_FILE"
        echo "  ✓ Variable agregada"
    else
        # Agregar en sección FRONTEND
        sed -i '/^# FRONTEND CONFIGURATION/a NEXT_PUBLIC_MAX_FILE_SIZE_MB=50' "$ENV_FILE"
        echo "  ✓ Variable agregada (sección FRONTEND)"
    fi
fi

# ============================================================================
# 2. VERIFICAR MAX_FILE_SIZE BACKEND
# ============================================================================
echo ""
echo "[2/5] Verificando MAX_FILE_SIZE (backend)..."

if grep -q "^MAX_FILE_SIZE=" "$ENV_FILE"; then
    CURRENT=$(grep "^MAX_FILE_SIZE=" "$ENV_FILE" | cut -d= -f2)
    if [ "$CURRENT" != "52428800" ]; then
        sed -i 's/^MAX_FILE_SIZE=.*/MAX_FILE_SIZE=52428800/' "$ENV_FILE"
        echo "  ✓ Actualizado de $CURRENT a 52428800"
    else
        echo "  ✓ Ya configurado correctamente"
    fi
else
    # Agregar en sección PERFORMANCE
    if grep -q "^# PERFORMANCE" "$ENV_FILE"; then
        sed -i '/^# PERFORMANCE/a MAX_FILE_SIZE=52428800' "$ENV_FILE"
    else
        echo "MAX_FILE_SIZE=52428800" >> "$ENV_FILE"
    fi
    echo "  ✓ Variable agregada"
fi

# ============================================================================
# 3. ELIMINAR VARIABLES DUPLICADAS
# ============================================================================
echo ""
echo "[3/5] Eliminando duplicados..."

# Crear archivo temporal sin duplicados (mantiene primera ocurrencia)
awk '!seen[$0]++' "$ENV_FILE" > "${ENV_FILE}.tmp"
mv "${ENV_FILE}.tmp" "$ENV_FILE"
echo "  ✓ Duplicados eliminados"

# ============================================================================
# 4. OPTIMIZAR CORS PARA NGINX PROXY
# ============================================================================
echo ""
echo "[4/5] Optimizando CORS..."

# Si nginx maneja todo, CORS puede ser más simple
if grep -q "CORS_ORIGINS=.*localhost" "$ENV_FILE"; then
    # Comentar CORS con localhost en producción
    sed -i 's/^CORS_ORIGINS=.*localhost.*/# CORS_ORIGINS (manejado por nginx proxy)/' "$ENV_FILE"
    echo "  ✓ CORS simplificado (nginx proxy)"
fi

# ============================================================================
# 5. VALIDAR FORMATO
# ============================================================================
echo ""
echo "[5/5] Validando formato..."

# Eliminar líneas vacías duplicadas
sed -i '/^$/N;/^\n$/d' "$ENV_FILE"

# Eliminar espacios al final de líneas
sed -i 's/[[:space:]]*$//' "$ENV_FILE"

echo "  ✓ Formato validado"

# ============================================================================
# MOSTRAR CAMBIOS
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 CAMBIOS APLICADOS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "Variables de límites de archivos:"
grep -E "^(NEXT_PUBLIC_MAX_FILE_SIZE_MB|MAX_FILE_SIZE)=" "$ENV_FILE" || echo "  (no encontradas)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ CORRECCIÓN COMPLETADA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Siguiente paso:"
echo "  cd /home/jf/copilotos-bridge"
echo "  docker-compose -f infra/docker-compose.prod.yml down"
echo "  # Esperar nuevo deploy con imagen reconstruida"
echo ""
echo "Backup disponible en: $BACKUP_FILE"
```

---

## 🔐 Mejoras de Seguridad Recomendadas

### 1. **Regenerar Secrets con Crypto Seguro**

Los secrets actuales son predecibles. Ejecuta en el servidor:

```bash
cd /home/jf/copilotos-bridge

# Generar nuevos secrets
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "MONGODB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=')"
echo "REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=')"

# Copiar estos valores a envs/.env.prod manualmente
# IMPORTANTE: Después de cambiar MONGODB/REDIS passwords, hay que:
#   1. Detener servicios
#   2. Limpiar volúmenes: docker volume rm copilotos-mongodb-data copilotos-redis-data
#   3. Reiniciar servicios (recreará DBs con nuevas passwords)
```

### 2. **Simplificar CORS con Nginx Proxy**

Si nginx escucha en el puerto 80/443 y hace proxy a web:3000 y api:8001, el navegador solo ve un origen (`http://34.42.214.246`). CORS no es necesario.

**Configuración recomendada:**

```bash
# En envs/.env.prod
CORS_ORIGINS=["http://34.42.214.246","https://34.42.214.246"]  # Solo la IP pública
ALLOWED_HOSTS=["34.42.214.246","api","web","localhost"]

# Frontend debe apuntar al proxy, no al API directamente
NEXT_PUBLIC_API_URL=http://34.42.214.246/api  # ← Sin :8001, nginx hace proxy
```

**Ajuste en nginx.conf:**

```nginx
# Línea 77-85, cambiar:
location /api/ {
    limit_req zone=api burst=20 nodelay;

    # Remover el trailing slash del proxy_pass para preservar el /api/ prefix
    proxy_pass http://api;  # ← Correcto
    # NO usar: proxy_pass http://api/; (elimina /api del path)

    # ... resto igual
}
```

### 3. **Habilitar HTTPS (Let's Encrypt)**

Actualmente todo es HTTP sin cifrado. Recomendado para producción:

```bash
# En el servidor
sudo apt update && sudo apt install -y certbot

# Obtener certificado (requiere dominio, no funciona con IP)
# Si tienes dominio:
sudo certbot certonly --standalone -d tu-dominio.com

# Descomentar bloque HTTPS en nginx.conf y actualizar paths:
# ssl_certificate /etc/letsencrypt/live/tu-dominio.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/tu-dominio.com/privkey.pem;
```

---

## 📦 Checklist Post-Corrección

Después de ejecutar los scripts, verifica:

```bash
# 1. Validar configuración
./scripts/validate-env-server.sh

# 2. Verificar servicios funcionando
docker ps | grep copilotos

# 3. Test de upload de archivo (HPE.pdf = 2.3MB)
# Desde el navegador o:
curl -X POST http://34.42.214.246/api/documents/upload \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@tests/data/pdf/HPE.pdf"

# 4. Verificar logs no muestran errores de tamaño
docker logs copilotos-web-prod --tail 50 | grep -i "size\|limit"
docker logs copilotos-api-prod --tail 50 | grep -i "size\|limit"
docker logs copilotos-nginx --tail 50 | grep -i "413\|size"
```

---

## 🎯 Resumen de Cambios Necesarios

| # | Cambio | Prioridad | Script | Manual |
|---|--------|-----------|--------|--------|
| 1 | Agregar `NEXT_PUBLIC_MAX_FILE_SIZE_MB=50` | 🔴 Crítico | ✅ | ❌ |
| 2 | Verificar `MAX_FILE_SIZE=52428800` | 🔴 Crítico | ✅ | ❌ |
| 3 | Regenerar secrets con OpenSSL | 🟡 Importante | ❌ | ✅ |
| 4 | Simplificar CORS para nginx proxy | 🟡 Importante | ⚠️ Parcial | ✅ |
| 5 | Habilitar HTTPS (requiere dominio) | 🟢 Opcional | ❌ | ✅ |
| 6 | Eliminar duplicados de variables | 🟡 Importante | ✅ | ❌ |

---

## 🚀 Flujo de Deployment Post-Fix

```bash
# EN EL SERVIDOR (jf@34.42.214.246)
cd /home/jf/copilotos-bridge/envs/

# 1. Ejecutar fix automático
bash ../scripts/fix-env-server.sh

# 2. Validar configuración
bash ../scripts/validate-env-server.sh

# EN TU MÁQUINA LOCAL
cd /home/jazielflo/Proyects/copilotos-bridge

# 3. Rebuild y deploy (usa scripts actualizados con build args)
make deploy-tar

# Esto hará:
#   - Build local con --build-arg NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
#   - Export a tar
#   - Transfer a servidor
#   - Load en servidor
#   - Restart servicios

# 4. Verificar que HPE.pdf (2.3MB) ahora se acepta
# Navegar a http://34.42.214.246:3000 y probar upload
```

---

## 📚 Referencias

- **Dockerfile Build Args:** `apps/web/Dockerfile:91-96`
- **Nginx Config:** `infra/nginx/nginx.conf:12` (client_max_body_size)
- **Backend Validation:** `apps/api/src/core/config.py:330` (MAX_FILE_SIZE)
- **Frontend Validation:** `apps/web/src/types/files.ts:107-111`
- **Deploy Scripts:** `scripts/deploy-with-tar.sh:176-193`

---

**Última actualización:** 2025-10-21 02:30 UTC-6
**Estado:** ✅ Scripts listos para ejecutar
