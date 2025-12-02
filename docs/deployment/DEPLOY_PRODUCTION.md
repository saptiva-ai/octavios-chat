# Guía de Deploy a Producción - SAFE UPDATE

**⚠️ IMPORTANTE: Este deploy NO borra datos de usuarios. Solo actualiza código y reconstruye contenedores.**

## Pre-requisitos

- Servidor: `${PROD_SERVER_USER}@${PROD_SERVER_IP}` (configurado en `.env.prod`)
- Deploy anterior ya existente
- Docker y Docker Compose instalados
- Acceso SSH configurado

## Paso 1: Conectar al Servidor

```bash
# Configurar variables (si no están en tu .bashrc/.zshrc)
export PROD_SERVER_USER="your_user"
export PROD_SERVER_IP="your_server_ip"

ssh ${PROD_SERVER_USER}@${PROD_SERVER_IP}
```

## Paso 2: Navegar al Directorio del Proyecto

```bash
cd /path/to/octavios-chat-bajaware_invex
# (Ajustar la ruta según donde esté instalado)
```

## Paso 3: Backup de Configuración (Opcional pero Recomendado)

```bash
# Backup de archivos .env
cp envs/.env.prod envs/.env.prod.backup.$(date +%Y%m%d_%H%M%S)

# Verificar volúmenes activos (NO los borraremos)
docker volume ls | grep octavios
```

## Paso 4: Detener Servicios (SIN borrar datos)

```bash
# Detener contenedores pero MANTENER volúmenes
docker-compose -f infra/docker-compose.yml down
```

**✅ IMPORTANTE: NO usar `docker-compose down -v` porque borraría los volúmenes con datos**

## Paso 5: Pull del Código Actualizado

```bash
# Asegurarse de estar en main
git checkout main

# Pull de los últimos cambios
git pull origin main
```

## Paso 6: Verificar Variables de Entorno

```bash
# Revisar que las variables de producción estén correctas
cat envs/.env.prod

# Variables críticas que deben estar:
# - SAPTIVA_API_KEY
# - POSTGRES_PASSWORD
# - Database credentials
# - NEXT_PUBLIC_FEATURE_BANK_ADVISOR=true
```

## Paso 7: Reconstruir Contenedores (SAFE - mantiene datos)

```bash
# Reconstruir solo las imágenes que cambiaron
docker-compose -f infra/docker-compose.yml build --no-cache bank-advisor backend web

# Levantar todos los servicios
docker-compose -f infra/docker-compose.yml up -d
```

## Paso 8: Verificar Deploy

```bash
# Verificar que todos los contenedores estén corriendo
docker-compose -f infra/docker-compose.yml ps

# Verificar logs de bank-advisor
docker-compose -f infra/docker-compose.yml logs -f bank-advisor

# Verificar health endpoint
curl http://localhost:8002/health

# Verificar backend
curl http://localhost:8000/health
```

## Paso 9: Verificar Datos Preservados

```bash
# Verificar que la base de datos tiene datos
docker exec -it octavios-chat-bajaware_invex-postgres psql -U octavios -d bankadvisor -c "SELECT COUNT(*) FROM monthly_kpis;"

# Debe devolver ~3660 filas o más

# Verificar que los usuarios existen
docker exec -it octavios-chat-bajaware_invex-postgres psql -U postgres -d chat_db -c "SELECT COUNT(*) FROM users;"
```

## Paso 10: Test Funcional

Desde tu máquina local, accede a:
```
http://${PROD_SERVER_IP}:3000
```

Prueba:
1. ✅ Login con usuario existente
2. ✅ Chat normal funciona
3. ✅ Bank Advisor está activado (ícono visible)
4. ✅ Query: "IMOR de consumo últimos 3 meses"
5. ✅ Verificar que la gráfica aparece sin refresh

## Rollback (Si es necesario)

```bash
# Detener servicios
docker-compose -f infra/docker-compose.yml down

# Volver al commit anterior
git log --oneline -5  # Ver commits recientes
git checkout <commit-anterior>

# Reconstruir y levantar
docker-compose -f infra/docker-compose.yml build --no-cache
docker-compose -f infra/docker-compose.yml up -d
```

## Notas Importantes

### ✅ Lo que SE PRESERVA (SEGURO):
- Base de datos PostgreSQL (usuarios, conversaciones, mensajes)
- Datos de Bank Advisor (monthly_kpis, métricas)
- Archivos subidos por usuarios (MinIO)
- Configuración de Qdrant (embeddings)

### ⚠️ Lo que SE ACTUALIZA:
- Código de backend (Python/FastAPI)
- Código de frontend (Next.js/React)
- Código de Bank Advisor MCP
- Librerías y dependencias

### ❌ Lo que NO se toca:
- Volúmenes Docker (datos persisten)
- Variables de entorno existentes
- Configuración de networking

## Nuevas Funcionalidades en este Deploy

1. **Fix IMOR/ICOR + Segmento**: Queries como "IMOR consumo" ahora funcionan correctamente
2. **LLM Redirect Fix**: QuerySpecParser con LLM ahora funciona sin error 307
3. **Frontend Charts**: Gráficas aparecen inmediatamente sin necesidad de refresh
4. **VizRecommender**: Detección inteligente de tipo de visualización
5. **5 Nuevos Métodos**: Análisis de segmentos (consumo, automotriz, empresas, vivienda)

## Monitoreo Post-Deploy

```bash
# Ver logs en tiempo real
docker-compose -f infra/docker-compose.yml logs -f

# Verificar uso de recursos
docker stats

# Verificar errores en bank-advisor
docker-compose logs bank-advisor | grep -i error

# Verificar conexiones a base de datos
docker exec octavios-chat-bajaware_invex-postgres psql -U octavios -d bankadvisor -c "SELECT count(*) FROM pg_stat_activity;"
```

## Contacto

Si hay problemas durante el deploy:
- **Branch estable**: `main` (commit `d388779b`)
- **Logs**: Revisar con `docker-compose logs -f [servicio]`
- **Rollback**: Seguir instrucciones de rollback arriba

---

**Última actualización**: 2025-12-02
**Deploy seguro**: ✅ Preserva datos de usuarios
**Tiempo estimado**: 10-15 minutos
