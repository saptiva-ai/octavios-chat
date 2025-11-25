# ⚠️ ANÁLISIS CRÍTICO - Diferencias de Nombrado

**Fecha:** 2025-11-24
**Prioridad:** 🔴 CRÍTICA

---

## 🚨 Problema Detectado

### Nombres de Contenedores Actuales (Producción)
```
client-project-chat-api
client-project-chat-web
client-project-chat-nginx
client-project-chat-mongodb
client-project-chat-minio
client-project-chat-redis
client-project-chat-languagetool
```

### Nombres Esperados por Docker Compose (Código Nuevo)
```
octavios-chat-client-project-api
octavios-chat-client-project-web
octavios-chat-client-project-nginx
octavios-chat-client-project-mongodb
octavios-chat-client-project-minio
octavios-chat-client-project-redis
octavios-chat-client-project-languagetool
octavios-chat-client-project-qdrant  # NUEVO
```

**Diferencia:** El prefijo cambió de `client-project-chat` a `octavios-chat-client-project`

---

## 💥 Impacto

### 1. Volúmenes Docker
Los volúmenes están asociados al nombre del proyecto de Compose:

**Producción actual:**
```bash
client-project-chat_mongodb_data
client-project-chat_redis_data
client-project-chat_minio_data
```

**Esperado por código nuevo:**
```bash
octavios-chat-client-project_mongodb_data
octavios-chat-client-project_redis_data
octavios-chat-client-project_minio_data
octavios-chat-client-project_qdrant_data      # NUEVO
octavios-chat-client-project_qdrant_snapshots # NUEVO
```

### 2. Red de Docker
```bash
# Actual
client-project-chat_octavios-network

# Esperado
octavios-chat-client-project_octavios-network
```

### 3. Scripts y Referencias
Todos los scripts que referencian nombres de contenedores fallarán.

---

## ✅ Solución: Mantener Nombre del Proyecto

### Opción 1: Modificar docker-compose.yml (RECOMENDADO)

Forzar el nombre del proyecto en el docker-compose:

```yaml
# En infra/docker-compose.yml (línea 1)
name: client-project-chat  # <-- AGREGAR ESTA LÍNEA

services:
  mongodb:
    container_name: ${COMPOSE_PROJECT_NAME:-client-project-chat}-mongodb
    # ...
```

O configurar en el servidor:

```bash
# En el servidor, en envs/.env
COMPOSE_PROJECT_NAME=client-project-chat
```

### Opción 2: Renombrar Volúmenes Durante Deploy

Crear aliases de volúmenes en docker-compose.yml:

```yaml
volumes:
  mongodb_data:
    name: client-project-chat_mongodb_data
    external: true
  redis_data:
    name: client-project-chat_redis_data
    external: true
  minio_data:
    name: client-project-chat_minio_data
    external: true
```

### Opción 3: Migrar Datos a Nuevos Volúmenes

**Pasos:**
1. Backup de volúmenes actuales
2. Crear nuevos volúmenes con nombres correctos
3. Copiar datos entre volúmenes
4. Deploy con nuevos nombres

**Tiempo:** +30 minutos
**Riesgo:** Medio (requiere copia de datos)

---

## 📋 Plan de Acción Recomendado

### PASO 1: Verificar Variable de Entorno en Servidor

```bash
# Conectar al servidor
ssh jf@34.172.67.93

# Verificar qué está definido
cd /home/jf/client-project-chat
grep COMPOSE_PROJECT_NAME envs/.env

# Si no existe o está mal, agregar/corregir:
echo "COMPOSE_PROJECT_NAME=client-project-chat" >> envs/.env
```

### PASO 2: Modificar docker-compose.yml Localmente

```bash
# Agregar al inicio de infra/docker-compose.yml
name: client-project-chat
```

### PASO 3: Actualizar Scripts de Backup

Los scripts ya tienen esta variable:
```bash
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-octavios-chat-client-project}"
```

Cambiar a:
```bash
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-client-project-chat}"
```

**Archivos a modificar:**
- `scripts/audit-production-state.sh` ✅ (ya tiene variable)
- `scripts/backup-docker-volumes.sh` (cambiar default)
- `scripts/db-manager.sh` (cambiar default)

### PASO 4: Verificar Antes del Deploy

```bash
# En el servidor, verificar nombres actuales
ssh jf@34.172.67.93 'docker ps --format "{{.Names}}"'

# Verificar volúmenes
ssh jf@34.172.67.93 'docker volume ls --filter name=client-project'
```

---

## 🎯 Resultado Esperado Después del Deploy

Con el fix aplicado, los nuevos contenedores se llamarán:

```
client-project-chat-api            (existente, será reemplazado)
client-project-chat-web            (existente, será reemplazado)
client-project-chat-nginx          (existente, será reemplazado)
client-project-chat-mongodb        (existente, será reemplazado)
client-project-chat-minio          (existente, será reemplazado)
client-project-chat-redis          (existente, será reemplazado)
client-project-chat-languagetool   (existente, será reemplazado)
client-project-chat-qdrant         (NUEVO ✨)
```

**Volúmenes:**
```
client-project-chat_mongodb_data         (REUTILIZADO ✅)
client-project-chat_redis_data           (REUTILIZADO ✅)
client-project-chat_minio_data           (REUTILIZADO ✅)
client-project-chat_qdrant_data          (NUEVO ✨)
client-project-chat_qdrant_snapshots     (NUEVO ✨)
```

---

## ⚠️ Riesgos si NO se Corrige

1. **Datos perdidos**: Los nuevos contenedores crearán volúmenes vacíos
2. **Usuarios desaparecen**: MongoDB nuevo no verá datos antiguos
3. **Sesiones perdidas**: Redis nuevo estará vacío
4. **Archivos desaparecen**: MinIO nuevo no tendrá archivos subidos

**Severidad:** 🔴 CRÍTICA - Deploy fallará o perderá datos

---

## 📝 Checklist Pre-Deploy

Antes de ejecutar deploy:

- [ ] Verificar `COMPOSE_PROJECT_NAME=client-project-chat` en `envs/.env` del servidor
- [ ] Agregar `name: client-project-chat` al inicio de `docker-compose.yml`
- [ ] Commit y push cambios
- [ ] Ejecutar auditoría de nuevo para confirmar nombres
- [ ] Proceder con deploy

---

**ACCIÓN INMEDIATA REQUERIDA:** Aplicar fix antes del deploy
