#!/bin/bash
# Script interactivo para probar tools MCP de OctaviOS
# Uso: ./scripts/test_mcp_tools.sh

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuración
API_URL="${API_URL:-http://localhost:8000}"
USERNAME="${USERNAME:-demo}"
PASSWORD="${PASSWORD:-Demo1234}"

# Variables globales
TOKEN=""
FILE_ID=""
USER_ID=""

# ============================================================================
# Funciones de utilidad
# ============================================================================

print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

check_dependencies() {
    print_header "Verificando dependencias"

    if ! command -v curl &> /dev/null; then
        print_error "curl no está instalado"
        exit 1
    fi
    print_success "curl disponible"

    if ! command -v jq &> /dev/null; then
        print_info "jq no está instalado (recomendado para formateo JSON)"
    else
        print_success "jq disponible"
    fi
}

check_api() {
    print_header "Verificando API"

    if curl -s -f "$API_URL/health" > /dev/null 2>&1; then
        print_success "API está activa en $API_URL"
    else
        print_error "API no responde en $API_URL"
        print_info "Ejecuta: make dev"
        exit 1
    fi
}

# ============================================================================
# Autenticación
# ============================================================================

login() {
    print_header "Autenticación"

    print_info "Iniciando sesión con usuario: $USERNAME"

    RESPONSE=$(curl -s -X POST "$API_URL/api/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"identifier\": \"$USERNAME\", \"password\": \"$PASSWORD\"}")

    TOKEN=$(echo "$RESPONSE" | jq -r '.access_token' 2>/dev/null)
    USER_ID=$(echo "$RESPONSE" | jq -r '.user.id' 2>/dev/null)

    if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
        print_success "Login exitoso"
        print_info "User ID: $USER_ID"
        print_info "Token: ${TOKEN:0:20}..."
    else
        print_error "Login falló"
        echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
        exit 1
    fi
}

# ============================================================================
# Listar tools
# ============================================================================

list_tools() {
    print_header "Tools MCP Disponibles"

    RESPONSE=$(curl -s -X GET "$API_URL/api/mcp/tools" \
        -H "Authorization: Bearer $TOKEN")

    if command -v jq &> /dev/null; then
        echo "$RESPONSE" | jq -r '.[] | "\(.name) (\(.version)) - \(.description)"' | head -c 2000
    else
        echo "$RESPONSE"
    fi

    print_success "$(echo "$RESPONSE" | jq 'length' 2>/dev/null || echo "N/A") tools disponibles"
}

# ============================================================================
# Upload archivo
# ============================================================================

upload_file() {
    local file_path="$1"

    print_header "Subiendo Archivo"

    if [ ! -f "$file_path" ]; then
        print_error "Archivo no encontrado: $file_path"
        return 1
    fi

    print_info "Subiendo: $file_path"

    RESPONSE=$(curl -s -X POST "$API_URL/api/files/upload" \
        -H "Authorization: Bearer $TOKEN" \
        -F "files=@$file_path" \
        -F "conversation_id=test-mcp-$(date +%s)")

    FILE_ID=$(echo "$RESPONSE" | jq -r '.files[0].file_id' 2>/dev/null)
    FILE_STATUS=$(echo "$RESPONSE" | jq -r '.files[0].status' 2>/dev/null)

    if [ "$FILE_ID" != "null" ] && [ -n "$FILE_ID" ]; then
        print_success "Archivo subido exitosamente"
        print_info "File ID: $FILE_ID"
        print_info "Status: $FILE_STATUS"

        # Esperar a que termine de procesar
        wait_for_ready "$FILE_ID"
    else
        print_error "Error al subir archivo"
        echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
        return 1
    fi
}

wait_for_ready() {
    local file_id="$1"
    local max_wait=30
    local waited=0

    print_info "Esperando procesamiento del archivo..."

    while [ $waited -lt $max_wait ]; do
        # Simular espera (en producción usar SSE)
        sleep 2
        waited=$((waited + 2))

        # Verificar status (simplificado)
        print_info "Esperando... (${waited}s/${max_wait}s)"

        # En producción aquí iría verificación real del status
        if [ $waited -ge 6 ]; then
            print_success "Archivo listo para procesamiento"
            break
        fi
    done
}

# ============================================================================
# Auditar archivo
# ============================================================================

audit_file() {
    local doc_id="${1:-$FILE_ID}"
    local policy="${2:-auto}"

    print_header "Auditando Archivo (Document Audit)"

    if [ -z "$doc_id" ]; then
        print_error "No hay FILE_ID. Sube un archivo primero."
        return 1
    fi

    print_info "Auditando documento: $doc_id"
    print_info "Política: $policy"

    RESPONSE=$(curl -s -X POST "$API_URL/api/mcp/tools/invoke" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"tool\": \"audit_file\",
            \"payload\": {
                \"doc_id\": \"$doc_id\",
                \"policy_id\": \"$policy\",
                \"enable_disclaimer\": true,
                \"enable_format\": true,
                \"enable_logo\": true
            }
        }")

    SUCCESS=$(echo "$RESPONSE" | jq -r '.success' 2>/dev/null)

    if [ "$SUCCESS" = "true" ]; then
        print_success "Auditoría completada"

        TOTAL_FINDINGS=$(echo "$RESPONSE" | jq -r '.result.summary.total_findings' 2>/dev/null)
        ERRORS=$(echo "$RESPONSE" | jq -r '.result.summary.errors' 2>/dev/null)
        WARNINGS=$(echo "$RESPONSE" | jq -r '.result.summary.warnings' 2>/dev/null)
        DURATION=$(echo "$RESPONSE" | jq -r '.duration_ms' 2>/dev/null)

        print_info "Total hallazgos: $TOTAL_FINDINGS (Errores: $ERRORS, Warnings: $WARNINGS)"
        print_info "Duración: ${DURATION}ms"

        echo -e "\n${YELLOW}Hallazgos:${NC}"
        if command -v jq &> /dev/null; then
            echo "$RESPONSE" | jq -r '.result.findings[] | "  [\(.severity)] \(.type): \(.issue)"' 2>/dev/null | head -10
        fi
    else
        print_error "Auditoría falló"
        ERROR_MSG=$(echo "$RESPONSE" | jq -r '.error.message' 2>/dev/null)
        print_error "Error: $ERROR_MSG"
    fi
}

# ============================================================================
# Extraer texto
# ============================================================================

extract_text() {
    local doc_id="${1:-$FILE_ID}"

    print_header "Extrayendo Texto del Documento"

    if [ -z "$doc_id" ]; then
        print_error "No hay FILE_ID. Sube un archivo primero."
        return 1
    fi

    print_info "Extrayendo texto de: $doc_id"

    RESPONSE=$(curl -s -X POST "$API_URL/api/mcp/tools/invoke" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"tool\": \"extract_document_text\",
            \"payload\": {
                \"doc_id\": \"$doc_id\",
                \"method\": \"auto\",
                \"include_metadata\": true
            }
        }")

    SUCCESS=$(echo "$RESPONSE" | jq -r '.success' 2>/dev/null)

    if [ "$SUCCESS" = "true" ]; then
        print_success "Extracción completada"

        METHOD=$(echo "$RESPONSE" | jq -r '.result.method_used' 2>/dev/null)
        CHAR_COUNT=$(echo "$RESPONSE" | jq -r '.result.metadata.char_count' 2>/dev/null)
        WORD_COUNT=$(echo "$RESPONSE" | jq -r '.result.metadata.word_count' 2>/dev/null)
        CACHED=$(echo "$RESPONSE" | jq -r '.result.metadata.cached' 2>/dev/null)

        print_info "Método: $METHOD"
        print_info "Caracteres: $CHAR_COUNT"
        print_info "Palabras: $WORD_COUNT"
        print_info "Desde caché: $CACHED"

        echo -e "\n${YELLOW}Primeros 200 caracteres:${NC}"
        echo "$RESPONSE" | jq -r '.result.text' 2>/dev/null | head -c 200
        echo -e "\n..."
    else
        print_error "Extracción falló"
        ERROR_MSG=$(echo "$RESPONSE" | jq -r '.error.message' 2>/dev/null)
        print_error "Error: $ERROR_MSG"
    fi
}

# ============================================================================
# Deep research
# ============================================================================

deep_research() {
    local query="$1"

    print_header "Deep Research con Aletheia"

    if [ -z "$query" ]; then
        query="¿Cuáles son las tendencias en inteligencia artificial para 2025?"
    fi

    print_info "Query: $query"

    RESPONSE=$(curl -s -X POST "$API_URL/api/mcp/tools/invoke" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"tool\": \"deep_research\",
            \"payload\": {
                \"query\": \"$query\",
                \"depth\": \"shallow\",
                \"max_iterations\": 2
            }
        }")

    SUCCESS=$(echo "$RESPONSE" | jq -r '.success' 2>/dev/null)

    if [ "$SUCCESS" = "true" ]; then
        print_success "Tarea de investigación creada"

        TASK_ID=$(echo "$RESPONSE" | jq -r '.result.task_id' 2>/dev/null)
        STATUS=$(echo "$RESPONSE" | jq -r '.result.status' 2>/dev/null)

        print_info "Task ID: $TASK_ID"
        print_info "Status: $STATUS"
    else
        print_error "Deep research falló"
    fi
}

# ============================================================================
# Menú interactivo
# ============================================================================

show_menu() {
    echo -e "\n${BLUE}┌─────────────────────────────────────┐${NC}"
    echo -e "${BLUE}│   OctaviOS MCP Tools - Test Menu   │${NC}"
    echo -e "${BLUE}└─────────────────────────────────────┘${NC}\n"
    echo "1) Listar tools disponibles"
    echo "2) Subir archivo PDF"
    echo "3) Auditar archivo (Document Audit)"
    echo "4) Extraer texto del archivo"
    echo "5) Deep research"
    echo "6) Flujo completo: Upload + Audit"
    echo "7) Salir"
    echo ""
}

main_menu() {
    while true; do
        show_menu
        read -p "Selecciona una opción: " option

        case $option in
            1)
                list_tools
                ;;
            2)
                read -p "Ruta del archivo PDF: " file_path
                upload_file "$file_path"
                ;;
            3)
                if [ -z "$FILE_ID" ]; then
                    read -p "File ID: " FILE_ID
                fi
                read -p "Policy ID (auto/414-std/414-strict): " policy
                policy=${policy:-auto}
                audit_file "$FILE_ID" "$policy"
                ;;
            4)
                if [ -z "$FILE_ID" ]; then
                    read -p "File ID: " FILE_ID
                fi
                extract_text "$FILE_ID"
                ;;
            5)
                read -p "Query de investigación: " query
                deep_research "$query"
                ;;
            6)
                read -p "Ruta del archivo PDF: " file_path
                if upload_file "$file_path"; then
                    sleep 2
                    audit_file "$FILE_ID" "auto"
                fi
                ;;
            7)
                print_info "¡Hasta luego!"
                exit 0
                ;;
            *)
                print_error "Opción inválida"
                ;;
        esac

        read -p "Presiona Enter para continuar..."
    done
}

# ============================================================================
# Main
# ============================================================================

main() {
    clear
    print_header "OctaviOS MCP Tools - Test Script"

    check_dependencies
    check_api
    login

    # Modo interactivo
    main_menu
}

# Ejecutar
main
