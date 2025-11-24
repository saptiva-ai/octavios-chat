# ⚠️ ANÁLISIS CRÍTICO - Diferencias de Nombrado

**Fecha:** 2025-11-24
**Prioridad:** 🔴 CRÍTICA

---

## 🚨 Problema Detectado

### Nombres de Contenedores Actuales (Producción)
```
capital414-chat-api
capital414-chat-web
capital414-chat-nginx
capital414-chat-mongodb
capital414-chat-minio
capital414-chat-redis
capital414-chat-languagetool
```

### Nombres Esperados por Docker Compose (Código Nuevo)
```
octavios-chat-capital414-api
octavios-chat-capital414-web
octavios-chat-capital414-nginx
octavios-chat-capital414-mongodb
octavios-chat-capital414-minio
octavios-chat-capital414-redis
octavios-chat-capital414-languagetool
octavios-chat-capital414-qdrant  # NUEVO
```

**Diferencia:** El prefijo cambió de `capital414-chat` a `octavios-chat-capital414`

---

## 💥 Impacto

### 1. Volúmenes Docker
Los volúmenes están asociados al nombre del proyecto de Compose:

**Producción actual:**
```bash
capital414-chat_mongodb_data
capital414-chat_redis_data
capital414-chat_minio_data
```

**Esperado por código nuevo:**
```bash
octavios-chat-capital414_mongodb_data
octavios-chat-capital414_redis_data
octavios-chat-capital414_minio_data
octavios-chat-capital414_qdrant_data      # NUEVO
octavios-chat-capital414_qdrant_snapshots # NUEVO
```

### 2. Red de Docker
```bash
# Actual
capital414-chat_octavios-network

# Esperado
octavios-chat-capital414_octavios-network
```

### 3. Scripts y Referencias
Todos los scripts que referencian nombres de contenedores fallarán.

---

## ✅ Solución: Mantener Nombre del Proyecto

### Opción 1: Modificar docker-compose.yml (RECOMENDADO)

Forzar el nombre del proyecto en el docker-compose:

```yaml
# En infra/docker-compose.yml (línea 1)
name: capital414-chat  # <-- AGREGAR ESTA LÍNEA

services:
  mongodb:
    container_name: ${COMPOSE_PROJECT_NAME:-capital414-chat}-mongodb
    # ...
```

O configurar en el servidor:

```bash
# En el servidor, en envs/.env
COMPOSE_PROJECT_NAME=capital414-chat
```

### Opción 2: Renombrar Volúmenes Durante Deploy

Crear aliases de volúmenes en docker-compose.yml:

```yaml
volumes:
  mongodb_data:
    name: capital414-chat_mongodb_data
    external: true
  redis_data:
    name: capital414-chat_redis_data
    external: true
  minio_data:
    name: capital414-chat_minio_data
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
cd /home/jf/capital414-chat
grep COMPOSE_PROJECT_NAME envs/.env

# Si no existe o está mal, agregar/corregir:
echo "COMPOSE_PROJECT_NAME=capital414-chat" >> envs/.env
```

### PASO 2: Modificar docker-compose.yml Localmente

```bash
# Agregar al inicio de infra/docker-compose.yml
name: capital414-chat
```

### PASO 3: Actualizar Scripts de Backup

Los scripts ya tienen esta variable:
```bash
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-octavios-chat-capital414}"
```

Cambiar a:
```bash
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-capital414-chat}"
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
ssh jf@34.172.67.93 'docker volume ls --filter name=capital414'
```

---

## 🎯 Resultado Esperado Después del Deploy

Con el fix aplicado, los nuevos contenedores se llamarán:

```
capital414-chat-api            (existente, será reemplazado)
capital414-chat-web            (existente, será reemplazado)
capital414-chat-nginx          (existente, será reemplazado)
capital414-chat-mongodb        (existente, será reemplazado)
capital414-chat-minio          (existente, será reemplazado)
capital414-chat-redis          (existente, será reemplazado)
capital414-chat-languagetool   (existente, será reemplazado)
capital414-chat-qdrant         (NUEVO ✨)
```

**Volúmenes:**
```
capital414-chat_mongodb_data         (REUTILIZADO ✅)
capital414-chat_redis_data           (REUTILIZADO ✅)
capital414-chat_minio_data           (REUTILIZADO ✅)
capital414-chat_qdrant_data          (NUEVO ✨)
capital414-chat_qdrant_snapshots     (NUEVO ✨)
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

- [ ] Verificar `COMPOSE_PROJECT_NAME=capital414-chat` en `envs/.env` del servidor
- [ ] Agregar `name: capital414-chat` al inicio de `docker-compose.yml`
- [ ] Commit y push cambios
- [ ] Ejecutar auditoría de nuevo para confirmar nombres
- [ ] Proceder con deploy

---

**ACCIÓN INMEDIATA REQUERIDA:** Aplicar fix antes del deploy
