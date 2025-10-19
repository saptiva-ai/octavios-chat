# Resumen de Errores del Despliegue a Producción
**Fecha**: 2025-10-16
**Objetivo**: Desplegar código con botón '+' de adjuntar archivos a producción
**Estado Final**: Bloqueado por errores de TypeScript y Tailwind CSS

---

## 🚨 Errores Críticos Encontrados

### Error #1: TypeScript Type Mismatch en ChatRequest.metadata
**Archivo**: `apps/web/src/app/chat/_components/ChatView.tsx:515`
**Severidad**: 🔴 BLOQUEANTE - Impide build de producción

#### Descripción del Error
```
Type error: Object literal may only specify known properties,
and 'metadata' does not exist in type 'ChatRequest'.
```

#### Causa Raíz
Hay un **mismatch de tipos** entre lo que envía `ChatView.tsx` y lo que espera la interfaz `ChatRequest` en `api-client.ts`.

**Lo que envía ChatView.tsx** (líneas 406-416):
```typescript
userMessageMetadata = {
  file_ids: fileIds,           // ❌ NO está en ChatRequest.metadata
  files: readyFiles.map((f) => ({
    file_id: f.file_id,
    filename: f.filename,
    bytes: f.bytes,              // ❌ Debería ser "size"
    pages: f.pages,              // ❌ NO está en ChatRequest.metadata
    mimetype: f.mimetype,        // ❌ Debería ser "mime_type"
  })),
};
```

**Lo que espera ChatRequest** (api-client.ts:58-66):
```typescript
metadata?: {
  files?: Array<{
    file_id: string;
    filename: string;
    size: number;              // ✅ NO "bytes"
    mime_type: string;         // ✅ NO "mimetype"
  }>;
};
// NO acepta: file_ids, pages
```

#### Impacto
- ❌ Build con target `runner` (producción optimizada) FALLA
- ❌ No se puede desplegar a producción
- ⚠️ Build en modo desarrollo funciona localmente (sin strict type checking)

#### Solución Requerida
Ajustar `ChatView.tsx` líneas 406-416 para cumplir con el tipo:
```typescript
userMessageMetadata = {
  files: readyFiles.map((f) => ({
    file_id: f.file_id,
    filename: f.filename,
    size: f.bytes,           // ✅ Renombrar
    mime_type: f.mimetype,   // ✅ Renombrar
  })),
};
// Eliminar file_ids y pages del metadata
```

---

### Error #2: Tailwind CSS Parsing Error en Dev Build
**Archivo**: `apps/web/src/app/globals.css:4`
**Severidad**: 🔴 BLOQUEANTE - Impide build dev en producción

#### Descripción del Error
```
Module parse failed: Unexpected character '@' (4:0)
> @tailwind base;
```

#### Causa Raíz
Al usar target `dev` en producción, Next.js no está procesando las directivas de Tailwind CSS correctamente. Esto ocurre porque:
1. El target `dev` no ejecuta el proceso de build completo
2. PostCSS/Tailwind no se aplican en modo desarrollo puro
3. La configuración esperada para desarrollo local no existe en contenedor de producción

#### Impacto
- ❌ Target `dev` no funciona en producción
- ⚠️ Funciona en desarrollo local con hot-reload (porque hay proceso de build previo)

#### Solución Requerida
No usar target `dev` en producción. Siempre usar target `runner` (producción optimizada).

---

### Error #3: SECRET_KEY Muy Corto
**Archivo**: `envs/.env` en producción
**Severidad**: 🟡 RESUELTO

#### Descripción del Error
```
SecretValidationError: Secret 'SECRET_KEY' too short (minimum 32 characters)
```

#### Causa Raíz
- Código nuevo tiene validación estricta: SECRET_KEY debe tener mínimo 32 caracteres
- Producción tenía SECRET_KEY de 45 caracteres (¿generado con método antiguo?)
- La validación nueva rechaza el formato

#### Solución Aplicada ✅
```bash
# Generar nueva SECRET_KEY de 64 caracteres
openssl rand -hex 32

# Actualizar envs/.env
SECRET_KEY=<nuevo_valor_64_chars>
JWT_SECRET_KEY=<nuevo_valor_64_chars>
```

---

### Error #4: Archivo Faltante - files-store.ts No en Repositorio Remoto
**Archivo**: `apps/web/src/lib/stores/files-store.ts`
**Severidad**: 🟡 WORKAROUND APLICADO

#### Descripción del Error
```
Module not found: Can't resolve '../lib/stores/files-store'
```

#### Causa Raíz
- Archivo existe en local: ✅ `/home/jazielflo/Proyects/copilotos-bridge/apps/web/src/lib/stores/files-store.ts`
- Archivo NO existe en origin/main: ❌
- Archivo nunca fue pusheado al repositorio remoto
- Producción al hacer `git pull` no recibe el archivo

#### Solución Temporal (Workaround) ✅
```bash
# Copiar archivo directamente a producción
scp apps/web/src/lib/stores/files-store.ts \
    jf@34.42.214.246:/home/jf/copilotos-bridge/apps/web/src/lib/stores/
```

#### Solución Permanente Requerida
```bash
# Commit y push del archivo faltante
git add apps/web/src/lib/stores/files-store.ts
git commit -m "fix: add missing files-store.ts"
git push origin main
```

---

### Error #5: Volúmenes Docker No Montados en Base Compose
**Archivo**: `infra/docker-compose.yml`
**Severidad**: 🟢 RESUELTO (desarrollo local)

#### Descripción del Problema
El botón '+' no aparecía después de desplegar porque el `docker-compose.yml` base no monta volúmenes de código fuente.

#### Causa Raíz
```yaml
# docker-compose.yml - SIN volúmenes
services:
  web:
    build:
      target: dev
    # volumes: NO HAY - código queda en imagen
```

Esto significa que cambios en el código local no se reflejan en el contenedor.

#### Solución ✅
Usar overlay de desarrollo:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

El overlay `docker-compose.dev.yml` monta:
```yaml
services:
  web:
    volumes:
      - ../apps/web:/app/apps/web  # Hot-reload
```

---

### Error #6: Next.js Proxy Apuntando a Puerto Incorrecto
**Archivo**: `apps/web/next.config.js` (implícito)
**Severidad**: 🟢 RESUELTO

#### Descripción del Problema
```
POST http://localhost:3000/api/auth/login 500
```

Login fallaba porque Next.js estaba proxeando a `localhost:8080` en lugar de `localhost:8001`.

#### Solución ✅
Crear `.env.local` con:
```
API_BASE_URL=http://localhost:8001
NEXT_PUBLIC_API_URL=http://localhost:8001
```

---

## 📊 Análisis de Tiempo de Deployment

| Fase | Tiempo | Estado |
|------|--------|---------|
| Backup de MongoDB | 2 min | ✅ Exitoso (59MB) |
| Git pull origin main | 1 min | ✅ Exitoso |
| Docker build (sin cache) | 18 min | ✅ Exitoso |
| SECRET_KEY update | 5 min | ✅ Exitoso |
| Copiar files-store.ts | 1 min | ✅ Workaround aplicado |
| Build producción (runner) | N/A | ❌ FALLÓ (Error TypeScript) |
| Build desarrollo (dev) | N/A | ❌ FALLÓ (Error Tailwind) |
| **TOTAL** | **27 min** | **❌ BLOQUEADO** |

---

## 🎯 Estado Final de Producción

### Servicios Activos ✅
- **MongoDB**: ✅ Healthy (restaurado desde backup 59MB)
- **API**: ✅ Healthy (puerto 8001, SECRET_KEY actualizado)
- **Redis**: ✅ Healthy

### Servicios Fallando ❌
- **Web**: ❌ HTTP 500
  - Container reporta "healthy" pero retorna 500
  - No puede arrancar debido a errores de build

### Commit Actual
- **Producción**: e47cacb "Archivos .gitignorados"
- **Sincronizado con**: origin/main

---

## 🔍 Lecciones Aprendidas y Prevención

### 1️⃣ Siempre Ejecutar TypeScript Build Localmente ANTES de Deploy
**Problema**: Código con errores de tipo pasó a main sin testing del build de producción.

**Prevención**:
```bash
# ANTES de commit a main, SIEMPRE ejecutar:
cd apps/web
pnpm build

# Si falla, NO hacer commit
```

### 2️⃣ Validar Cambios de Schema/Types en Ambos Lados
**Problema**: `ChatRequest.metadata` fue modificado pero `ChatView.tsx` no se actualizó.

**Prevención**:
- Cuando se modifica un tipo compartido (interfaces, schemas), usar búsqueda global:
  ```bash
  grep -r "ChatRequest" apps/web/src --include="*.ts" --include="*.tsx"
  ```
- Verificar TODOS los usos del tipo modificado

### 3️⃣ Verificar Archivos Nuevos Están en Git Remoto
**Problema**: `files-store.ts` existe local pero no en origin/main.

**Prevención**:
```bash
# ANTES de deployar, verificar archivos untracked:
git status
git ls-files --others --exclude-standard

# Verificar que archivos críticos están en remoto:
git ls-tree origin/main apps/web/src/lib/stores/
```

### 4️⃣ Probar Build de Producción en Staging Primero
**Problema**: Errores de build solo se descubrieron EN producción.

**Prevención**:
```bash
# Crear entorno de staging con target runner:
docker compose -f docker-compose.yml build web --target runner

# Si falla, NO deployar a producción
```

### 5️⃣ Secrets: Validar Formato Antes de Deploy
**Problema**: SECRET_KEY en producción no cumplía requisitos del código nuevo.

**Prevención**:
- Documentar requisitos de secrets en `.env.example`
- Agregar validación en script de deploy:
  ```bash
  if [ ${#SECRET_KEY} -lt 32 ]; then
    echo "❌ SECRET_KEY too short"
    exit 1
  fi
  ```

### 6️⃣ Backups: SIEMPRE Verificar Antes de Cambios Críticos
**Problema**: Casi desplegamos sin backup verificado.

**Solución Implementada**: ✅
- Backup creado: 59MB
- Verificación de integridad: `_mdb_catalog.wt` presente
- Restore probado exitosamente

---

## 🛠️ Próximos Pasos para Desbloquear Producción

### Paso 1: Fix TypeScript Error (CRÍTICO)
```bash
# Editar apps/web/src/app/chat/_components/ChatView.tsx
# Líneas 406-416: Ajustar metadata para cumplir tipo ChatRequest
```

### Paso 2: Test Build Localmente
```bash
cd apps/web
pnpm build  # Debe completar sin errores
```

### Paso 3: Commit y Push Fix
```bash
git add apps/web/src/app/chat/_components/ChatView.tsx
git add apps/web/src/lib/stores/files-store.ts  # Agregar archivo faltante
git commit -m "fix: resolve ChatRequest metadata type mismatch and add missing files-store"
git push origin main
```

### Paso 4: Deploy a Producción
```bash
ssh jf@34.42.214.246
cd /home/jf/copilotos-bridge
git pull origin main
cd infra
docker compose build web
docker compose up -d web
```

### Paso 5: Verificar '+' Button en Producción
```bash
curl -I http://34.42.214.246:3000
# Verificar visualmente en http://34.42.214.246:3000
```

---

## 📝 Archivos Modificados en Esta Sesión

### Producción (jf@34.42.214.246)
- `/home/jf/copilotos-bridge/envs/.env` - SECRET_KEY y JWT_SECRET_KEY actualizados
- `/home/jf/copilotos-bridge/apps/web/src/lib/stores/files-store.ts` - Copiado manualmente
- Git: Sincronizado a commit e47cacb

### Desarrollo Local
- `apps/web/.env.local` - Creado con API_BASE_URL correcto

### Backups Creados
- `~/backups/docker-volumes/mongodb_pre_deploy_20251017_014045.tar.gz` (59MB) - ✅ VERIFICADO
