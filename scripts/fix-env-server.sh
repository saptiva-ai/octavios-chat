#!/bin/bash
# ============================================================================
# SCRIPT DE CORRECCIÓN AUTOMÁTICA DE CONFIGURACIÓN
# ============================================================================
# Corrige automáticamente problemas comunes en .env de producción
# Usage: ./scripts/fix-env-server.sh [--dry-run]
#
# Cambios que aplica:
#   - Agrega/actualiza NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
#   - Verifica MAX_FILE_SIZE=52428800
#   - Elimina variables duplicadas
#   - Optimiza CORS para nginx proxy
#   - Valida formato del archivo

set -e

# Parse arguments
DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
    DRY_RUN=true
    echo "🔍 MODO DRY-RUN: No se harán cambios reales"
    echo ""
fi

# Detectar directorio
if [ ! -d "envs" ]; then
    echo "❌ Error: Ejecuta este script desde el directorio raíz del proyecto"
    echo "   cd /home/jf/copilotos-bridge && bash scripts/fix-env-server.sh"
    exit 1
fi

cd envs

# Determinar archivo a usar
if [ -f .env.prod ]; then
    ENV_FILE=.env.prod
elif [ -f .env ]; then
    ENV_FILE=.env
else
    echo "❌ Error: No se encontró archivo .env ni .env.prod"
    echo ""
    echo "Crea uno con:"
    echo "  cp .env.production.example .env.prod"
    echo "  vim .env.prod  # Edita valores"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 CORRECCIÓN AUTOMÁTICA DE CONFIGURACIÓN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Archivo: $ENV_FILE"
echo ""

if [ "$DRY_RUN" = false ]; then
    # BACKUP
    BACKUP_FILE="${ENV_FILE}.backup-$(date +%Y%m%d-%H%M%S)"
    cp "$ENV_FILE" "$BACKUP_FILE"
    echo "✓ Backup creado: $BACKUP_FILE"
else
    echo "⚠️  Dry-run: No se creará backup"
fi

# ============================================================================
# 1. AGREGAR/ACTUALIZAR NEXT_PUBLIC_MAX_FILE_SIZE_MB
# ============================================================================
echo ""
echo "[1/5] Verificando NEXT_PUBLIC_MAX_FILE_SIZE_MB..."

if grep -q "^NEXT_PUBLIC_MAX_FILE_SIZE_MB=" "$ENV_FILE"; then
    CURRENT_VALUE=$(grep "^NEXT_PUBLIC_MAX_FILE_SIZE_MB=" "$ENV_FILE" | cut -d= -f2)
    if [ "$CURRENT_VALUE" != "50" ]; then
        echo "  📝 Variable existe con valor $CURRENT_VALUE, actualizando a 50..."
        if [ "$DRY_RUN" = false ]; then
            sed -i 's/^NEXT_PUBLIC_MAX_FILE_SIZE_MB=.*/NEXT_PUBLIC_MAX_FILE_SIZE_MB=50/' "$ENV_FILE"
            echo "  ✓ Variable actualizada"
        else
            echo "  [DRY-RUN] sed -i 's/^NEXT_PUBLIC_MAX_FILE_SIZE_MB=.*/NEXT_PUBLIC_MAX_FILE_SIZE_MB=50/' $ENV_FILE"
        fi
    else
        echo "  ✓ Variable ya configurada correctamente (50)"
    fi
else
    echo "  📝 Variable no existe, agregando..."
    if [ "$DRY_RUN" = false ]; then
        # Agregar después de NEXT_PUBLIC_API_URL si existe
        if grep -q "^NEXT_PUBLIC_API_URL=" "$ENV_FILE"; then
            sed -i '/^NEXT_PUBLIC_API_URL=/a NEXT_PUBLIC_MAX_FILE_SIZE_MB=50' "$ENV_FILE"
            echo "  ✓ Variable agregada después de NEXT_PUBLIC_API_URL"
        else
            # Agregar en sección FRONTEND si existe
            if grep -q "^# FRONTEND" "$ENV_FILE"; then
                sed -i '/^# FRONTEND/a NEXT_PUBLIC_MAX_FILE_SIZE_MB=50' "$ENV_FILE"
                echo "  ✓ Variable agregada en sección FRONTEND"
            else
                # Agregar al final del archivo
                echo "" >> "$ENV_FILE"
                echo "# File upload limits" >> "$ENV_FILE"
                echo "NEXT_PUBLIC_MAX_FILE_SIZE_MB=50" >> "$ENV_FILE"
                echo "  ✓ Variable agregada al final del archivo"
            fi
        fi
    else
        echo "  [DRY-RUN] Agregaría NEXT_PUBLIC_MAX_FILE_SIZE_MB=50"
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
        echo "  📝 MAX_FILE_SIZE=$CURRENT, actualizando a 52428800..."
        if [ "$DRY_RUN" = false ]; then
            sed -i 's/^MAX_FILE_SIZE=.*/MAX_FILE_SIZE=52428800/' "$ENV_FILE"
            echo "  ✓ Variable actualizada"
        else
            echo "  [DRY-RUN] sed -i 's/^MAX_FILE_SIZE=.*/MAX_FILE_SIZE=52428800/' $ENV_FILE"
        fi
    else
        echo "  ✓ Ya configurado correctamente (52428800)"
    fi
else
    echo "  📝 Variable no existe, agregando..."
    if [ "$DRY_RUN" = false ]; then
        # Agregar en sección PERFORMANCE si existe
        if grep -q "^# PERFORMANCE" "$ENV_FILE"; then
            sed -i '/^# PERFORMANCE/a MAX_FILE_SIZE=52428800  # 50MB in bytes' "$ENV_FILE"
            echo "  ✓ Variable agregada en sección PERFORMANCE"
        else
            # Agregar junto con NEXT_PUBLIC_MAX_FILE_SIZE_MB
            if grep -q "^NEXT_PUBLIC_MAX_FILE_SIZE_MB=" "$ENV_FILE"; then
                sed -i '/^NEXT_PUBLIC_MAX_FILE_SIZE_MB=/a MAX_FILE_SIZE=52428800  # 50MB in bytes' "$ENV_FILE"
                echo "  ✓ Variable agregada junto a NEXT_PUBLIC_MAX_FILE_SIZE_MB"
            else
                echo "MAX_FILE_SIZE=52428800" >> "$ENV_FILE"
                echo "  ✓ Variable agregada al final del archivo"
            fi
        fi
    else
        echo "  [DRY-RUN] Agregaría MAX_FILE_SIZE=52428800"
    fi
fi

# ============================================================================
# 3. ELIMINAR VARIABLES DUPLICADAS
# ============================================================================
echo ""
echo "[3/5] Eliminando duplicados..."

# Contar duplicados antes
DUPES_BEFORE=$(grep -v '^#' "$ENV_FILE" | grep -v '^$' | cut -d= -f1 | sort | uniq -d | wc -l)

if [ "$DUPES_BEFORE" -gt 0 ]; then
    echo "  📝 Encontrados $DUPES_BEFORE variables duplicadas"

    if [ "$DRY_RUN" = false ]; then
        # Estrategia: Mantener la ÚLTIMA ocurrencia de cada variable
        # (asumiendo que las correcciones están al final)

        # 1. Extraer comentarios y líneas vacías
        grep '^#\|^$' "$ENV_FILE" > "${ENV_FILE}.comments"

        # 2. Extraer variables (sin duplicados, última ocurrencia gana)
        grep -v '^#' "$ENV_FILE" | grep -v '^$' | tac | awk -F= '!seen[$1]++' | tac > "${ENV_FILE}.vars"

        # 3. Reconstruir archivo manteniendo estructura
        # (esto es simplificado, mezcla comentarios con variables ordenadas)
        cat "${ENV_FILE}.vars" > "${ENV_FILE}.tmp"

        # 4. Reemplazar archivo original
        mv "${ENV_FILE}.tmp" "$ENV_FILE"
        rm -f "${ENV_FILE}.comments" "${ENV_FILE}.vars"

        echo "  ✓ Duplicados eliminados (última ocurrencia preservada)"
    else
        echo "  [DRY-RUN] Eliminaría $DUPES_BEFORE duplicados"
        grep -v '^#' "$ENV_FILE" | grep -v '^$' | cut -d= -f1 | sort | uniq -d | while read dup; do
            echo "    • $dup"
        done
    fi
else
    echo "  ✓ No hay duplicados"
fi

# ============================================================================
# 4. OPTIMIZAR CORS PARA NGINX PROXY (Opcional)
# ============================================================================
echo ""
echo "[4/5] Verificando configuración CORS..."

if grep -q "CORS_ORIGINS=.*localhost.*3000" "$ENV_FILE"; then
    echo "  ⚠️  CORS incluye localhost:3000 (innecesario con nginx proxy)"
    echo "  ℹ️  Saltando optimización (requiere validación manual)"
    # No hacemos cambios automáticos aquí porque puede ser intencional
else
    echo "  ✓ CORS configurado apropiadamente"
fi

# ============================================================================
# 5. VALIDAR FORMATO
# ============================================================================
echo ""
echo "[5/5] Validando formato del archivo..."

if [ "$DRY_RUN" = false ]; then
    # Eliminar líneas vacías duplicadas (máximo 2 consecutivas)
    cat -s "$ENV_FILE" > "${ENV_FILE}.tmp"
    mv "${ENV_FILE}.tmp" "$ENV_FILE"

    # Eliminar espacios al final de líneas
    sed -i 's/[[:space:]]*$//' "$ENV_FILE"

    # Asegurar nueva línea al final del archivo
    if [ -n "$(tail -c 1 "$ENV_FILE")" ]; then
        echo "" >> "$ENV_FILE"
    fi

    echo "  ✓ Formato validado"
else
    echo "  [DRY-RUN] Validaría formato (eliminar espacios, líneas vacías, etc.)"
fi

# ============================================================================
# MOSTRAR CAMBIOS
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 VERIFICACIÓN DE VARIABLES CRÍTICAS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "Límites de archivos:"
grep -E "^(NEXT_PUBLIC_MAX_FILE_SIZE_MB|MAX_FILE_SIZE)=" "$ENV_FILE" | while read line; do
    echo "  ✓ $line"
done

echo ""
echo "URLs y endpoints:"
grep -E "^(NEXT_PUBLIC_API_URL|DOMAIN)=" "$ENV_FILE" | while read line; do
    echo "  • $line"
done

# ============================================================================
# RESUMEN
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$DRY_RUN" = true ]; then
    echo "✅ DRY-RUN COMPLETADO"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Para aplicar los cambios, ejecuta sin --dry-run:"
    echo "  bash scripts/fix-env-server.sh"
else
    echo "✅ CORRECCIÓN COMPLETADA"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Cambios aplicados a: $ENV_FILE"
    echo "Backup disponible en: $BACKUP_FILE"
    echo ""
    echo "Siguiente paso:"
    echo "  1. Validar: bash scripts/validate-env-server.sh"
    echo "  2. Rebuild imagen web (desde máquina local):"
    echo "     cd /home/jazielflo/Proyects/copilotos-bridge"
    echo "     make deploy-tar"
    echo ""
fi
