#!/bin/bash
# ============================================================================
# DIAGNÓSTICO DE ERROR 413 (Content Too Large)
# ============================================================================
# Ejecutar en el servidor para identificar qué nginx rechaza archivos
# Usage: bash scripts/diagnose-nginx-413.sh

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 DIAGNÓSTICO ERROR 413 - Nginx Content Too Large"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================================
# 1. IDENTIFICAR TODOS LOS NGINX CORRIENDO
# ============================================================================
echo -e "\n${BLUE}[1/6]${NC} Identificando procesos Nginx..."

NGINX_PROCESSES=$(ps aux | grep nginx | grep -v grep || echo "")

if [ -z "$NGINX_PROCESSES" ]; then
    echo -e "${RED}✗${NC} No hay procesos nginx corriendo"
    echo "   Esto es extraño si recibes error 413..."
else
    echo -e "${GREEN}✓${NC} Nginx procesos encontrados:"
    echo "$NGINX_PROCESSES" | while read line; do
        echo "  • $line"
    done
fi

# Contar nginx
SYSTEM_NGINX=$(ps aux | grep '/usr/sbin/nginx\|/usr/bin/nginx' | grep -v grep | wc -l)
DOCKER_NGINX=$(docker ps --filter "name=nginx" --format '{{.Names}}' | wc -l)

echo ""
echo "Resumen:"
echo "  • Nginx del sistema (APT/YUM): $SYSTEM_NGINX proceso(s)"
echo "  • Nginx en Docker: $DOCKER_NGINX contenedor(es)"

# ============================================================================
# 2. VERIFICAR NGINX DEL SISTEMA (/etc/nginx/)
# ============================================================================
echo -e "\n${BLUE}[2/6]${NC} Verificando Nginx del sistema..."

if [ -d "/etc/nginx" ]; then
    echo -e "${GREEN}✓${NC} Directorio /etc/nginx existe (nginx del sistema instalado)"

    # Buscar configuración principal
    if [ -f "/etc/nginx/nginx.conf" ]; then
        echo ""
        echo "Configuración principal: /etc/nginx/nginx.conf"

        # Buscar client_max_body_size
        MAIN_LIMIT=$(grep -r "client_max_body_size" /etc/nginx/nginx.conf 2>/dev/null || echo "")
        if [ -n "$MAIN_LIMIT" ]; then
            echo -e "${CYAN}▸${NC} Encontrado en nginx.conf:"
            echo "$MAIN_LIMIT" | while read line; do
                echo "    $line"
            done
        else
            echo -e "${YELLOW}⚠${NC} client_max_body_size NO encontrado en nginx.conf"
            echo "    (default: 1M)"
        fi
    fi

    # Buscar en sites-enabled
    if [ -d "/etc/nginx/sites-enabled" ]; then
        echo ""
        echo "Sitios habilitados:"
        for site in /etc/nginx/sites-enabled/*; do
            if [ -f "$site" ]; then
                SITE_NAME=$(basename "$site")
                echo ""
                echo "  📄 $SITE_NAME"

                # Verificar si es para octavios.saptiva.com
                if grep -q "octavios\.saptiva\.com\|server_name.*saptiva" "$site" 2>/dev/null; then
                    echo -e "    ${GREEN}✓${NC} Configuración para octavios.saptiva.com"

                    # Buscar client_max_body_size
                    SITE_LIMIT=$(grep "client_max_body_size" "$site" 2>/dev/null || echo "")
                    if [ -n "$SITE_LIMIT" ]; then
                        echo -e "    ${CYAN}▸${NC} client_max_body_size configurado:"
                        echo "$SITE_LIMIT" | sed 's/^/      /'
                    else
                        echo -e "    ${RED}✗${NC} client_max_body_size NO configurado (usa default: 1M)"
                        echo -e "    ${YELLOW}↳ ESTE ES PROBABLEMENTE EL PROBLEMA${NC}"
                    fi

                    # Mostrar proxy_pass para entender la arquitectura
                    echo ""
                    echo "    Proxy configuration:"
                    grep -E "location|proxy_pass" "$site" | sed 's/^/      /'
                fi
            fi
        done
    fi

    # Buscar en conf.d
    if [ -d "/etc/nginx/conf.d" ]; then
        echo ""
        echo "Configuraciones adicionales (/etc/nginx/conf.d/):"

        CONF_FILES=$(find /etc/nginx/conf.d -name "*.conf" 2>/dev/null || echo "")
        if [ -n "$CONF_FILES" ]; then
            echo "$CONF_FILES" | while read conf; do
                CONF_NAME=$(basename "$conf")
                echo ""
                echo "  📄 $CONF_NAME"

                CONF_LIMIT=$(grep "client_max_body_size" "$conf" 2>/dev/null || echo "")
                if [ -n "$CONF_LIMIT" ]; then
                    echo -e "    ${CYAN}▸${NC} $CONF_LIMIT"
                fi
            done
        else
            echo "  (vacío)"
        fi
    fi

else
    echo -e "${YELLOW}⚠${NC} /etc/nginx no existe (nginx del sistema no instalado)"
fi

# ============================================================================
# 3. VERIFICAR NGINX DE DOCKER
# ============================================================================
echo -e "\n${BLUE}[3/6]${NC} Verificando Nginx en Docker..."

DOCKER_NGINX_CONTAINERS=$(docker ps --filter "name=nginx" --format '{{.Names}}' || echo "")

if [ -n "$DOCKER_NGINX_CONTAINERS" ]; then
    echo "$DOCKER_NGINX_CONTAINERS" | while read container; do
        echo ""
        echo -e "${GREEN}✓${NC} Contenedor: $container"

        # Verificar configuración dentro del contenedor
        echo "  Buscando client_max_body_size..."

        DOCKER_LIMIT=$(docker exec "$container" grep -r "client_max_body_size" /etc/nginx/ 2>/dev/null || echo "")
        if [ -n "$DOCKER_LIMIT" ]; then
            echo "$DOCKER_LIMIT" | sed 's/^/    /'
        else
            echo -e "    ${YELLOW}⚠${NC} No encontrado (default: 1M)"
        fi
    done
else
    echo -e "${YELLOW}⚠${NC} No hay contenedores nginx corriendo"
fi

# ============================================================================
# 4. VERIFICAR PUERTOS Y ARQUITECTURA
# ============================================================================
echo -e "\n${BLUE}[4/6]${NC} Verificando puertos y arquitectura..."

echo ""
echo "Puertos escuchando:"

# Puerto 80 (HTTP)
PORT_80=$(ss -tlnp 2>/dev/null | grep ':80 ' || netstat -tlnp 2>/dev/null | grep ':80 ' || echo "")
if [ -n "$PORT_80" ]; then
    echo -e "  ${GREEN}✓${NC} Puerto 80 (HTTP):"
    echo "$PORT_80" | sed 's/^/    /'
else
    echo -e "  ${YELLOW}⚠${NC} Puerto 80 no escucha"
fi

# Puerto 443 (HTTPS)
PORT_443=$(ss -tlnp 2>/dev/null | grep ':443 ' || netstat -tlnp 2>/dev/null | grep ':443 ' || echo "")
if [ -n "$PORT_443" ]; then
    echo -e "  ${GREEN}✓${NC} Puerto 443 (HTTPS):"
    echo "$PORT_443" | sed 's/^/    /'
else
    echo -e "  ${YELLOW}⚠${NC} Puerto 443 no escucha"
fi

# Puerto 3000 (Next.js)
PORT_3000=$(ss -tlnp 2>/dev/null | grep ':3000 ' || netstat -tlnp 2>/dev/null | grep ':3000 ' || echo "")
if [ -n "$PORT_3000" ]; then
    echo -e "  ${CYAN}ℹ${NC} Puerto 3000 (Next.js):"
    echo "$PORT_3000" | sed 's/^/    /'
fi

# Puerto 8001 (FastAPI)
PORT_8001=$(ss -tlnp 2>/dev/null | grep ':8001 ' || netstat -tlnp 2>/dev/null | grep ':8001 ' || echo "")
if [ -n "$PORT_8001" ]; then
    echo -e "  ${CYAN}ℹ${NC} Puerto 8001 (FastAPI):"
    echo "$PORT_8001" | sed 's/^/    /'
fi

# ============================================================================
# 5. TEST DE UPLOAD
# ============================================================================
echo -e "\n${BLUE}[5/6]${NC} Probando límites de tamaño..."

# Crear archivo de prueba de 2MB
TEST_FILE="/tmp/test-2mb.bin"
dd if=/dev/zero of="$TEST_FILE" bs=1M count=2 2>/dev/null
echo -e "${GREEN}✓${NC} Archivo de prueba creado: 2MB"

# Test directo al backend (sin nginx)
echo ""
echo "Test 1: Directo al backend (puerto 8001, sin nginx)..."
BACKEND_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -F "file=@${TEST_FILE}" \
    http://localhost:8001/api/files/upload 2>/dev/null || echo "000")

if [ "$BACKEND_RESPONSE" = "401" ] || [ "$BACKEND_RESPONSE" = "403" ]; then
    echo -e "  ${GREEN}✓${NC} Backend acepta archivo (error $BACKEND_RESPONSE es por auth, no por tamaño)"
elif [ "$BACKEND_RESPONSE" = "413" ]; then
    echo -e "  ${RED}✗${NC} Backend rechaza por tamaño (413)"
elif [ "$BACKEND_RESPONSE" = "000" ]; then
    echo -e "  ${YELLOW}⚠${NC} Backend no responde (puede estar en Docker network)"
else
    echo -e "  ${CYAN}ℹ${NC} Backend responde: $BACKEND_RESPONSE"
fi

# Test a través de nginx (puerto 80)
echo ""
echo "Test 2: A través de nginx (puerto 80/443)..."
NGINX_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -F "file=@${TEST_FILE}" \
    http://localhost/api/files/upload 2>/dev/null || echo "000")

if [ "$NGINX_RESPONSE" = "413" ]; then
    echo -e "  ${RED}✗${NC} Nginx rechaza archivo: 413 Content Too Large"
    echo -e "  ${YELLOW}↳ CONFIRMADO: client_max_body_size < 2MB${NC}"
elif [ "$NGINX_RESPONSE" = "401" ] || [ "$NGINX_RESPONSE" = "403" ]; then
    echo -e "  ${GREEN}✓${NC} Nginx acepta archivo (error $NGINX_RESPONSE es por auth)"
elif [ "$NGINX_RESPONSE" = "502" ] || [ "$NGINX_RESPONSE" = "504" ]; then
    echo -e "  ${YELLOW}⚠${NC} Nginx acepta pero backend no responde ($NGINX_RESPONSE)"
else
    echo -e "  ${CYAN}ℹ${NC} Nginx responde: $NGINX_RESPONSE"
fi

# Cleanup
rm -f "$TEST_FILE"

# ============================================================================
# 6. RECOMENDACIONES
# ============================================================================
echo -e "\n${BLUE}[6/6]${NC} Recomendaciones..."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${YELLOW}🔧 ACCIONES RECOMENDADAS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -f "/etc/nginx/sites-enabled/octavios" ] || grep -rl "octavios\.saptiva\.com" /etc/nginx/ 2>/dev/null | grep -q .; then
    echo ""
    echo "1. Actualizar nginx del sistema:"
    echo "   sudo nano /etc/nginx/sites-enabled/octavios"
    echo ""
    echo "   Agregar dentro del bloque 'server':"
    echo "   ${CYAN}client_max_body_size 50M;${NC}"
    echo ""
    echo "2. Validar configuración:"
    echo "   sudo nginx -t"
    echo ""
    echo "3. Recargar nginx:"
    echo "   sudo systemctl reload nginx"
    echo ""
elif [ -d "/etc/nginx" ]; then
    echo ""
    echo "1. Buscar configuración de octavios.saptiva.com:"
    echo "   grep -rl 'octavios' /etc/nginx/"
    echo ""
    echo "2. Editar el archivo encontrado y agregar:"
    echo "   ${CYAN}client_max_body_size 50M;${NC}"
    echo ""
    echo "3. Recargar nginx:"
    echo "   sudo systemctl reload nginx"
    echo ""
else
    echo ""
    echo "⚠️  Nginx del sistema no detectado"
    echo "   El problema puede estar en configuración de Docker"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
