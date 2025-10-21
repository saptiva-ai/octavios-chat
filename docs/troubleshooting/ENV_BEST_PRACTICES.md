# 🎯 Mejores Prácticas para Configuración de Entornos

**Última actualización:** 2025-10-21

---

## 📚 Tabla de Contenidos

1. [Consistencia Multi-capa](#consistencia-multi-capa)
2. [Gestión de Secrets](#gestión-de-secrets)
3. [Variables Build-time vs Runtime](#variables-build-time-vs-runtime)
4. [CORS y Proxy Reverso](#cors-y-proxy-reverso)
5. [Optimización de Nginx](#optimización-de-nginx)
6. [Checklist de Deployment](#checklist-de-deployment)

---

## 🔗 Consistencia Multi-capa

### Problema

El límite de tamaño de archivo debe configurarse en **4 capas diferentes**. Si una capa tiene un límite menor, rechazará archivos válidos.

### Configuración Correcta (50MB)

| Capa | Variable/Config | Valor | Archivo |
|------|-----------------|-------|---------|
| **Nginx** | `client_max_body_size` | `50M` | `infra/nginx/nginx.conf` |
| **Backend** | `MAX_FILE_SIZE` | `52428800` | `envs/.env.prod` |
| **Frontend (Build)** | `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | `50` | `envs/.env.prod` + Dockerfile ARG |
| **Frontend (Runtime)** | `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | `50` | `docker-compose.prod.yml` |

`★ Insight ─────────────────────────────────────`
**Flujo de validación:**
1. **Nginx**: Rechaza HTTP request > 50M (antes de llegar al backend)
2. **Frontend (Browser)**: Valida tamaño ANTES de subir (ahorra bandwidth)
3. **Backend**: Validación final de seguridad (archivos maliciosos, etc.)
`─────────────────────────────────────────────────`

### Script de Verificación

```bash
# En el servidor
bash scripts/validate-env-server.sh

# Si hay errores, corregir automáticamente:
bash scripts/fix-env-server.sh
```

---

## 🔐 Gestión de Secrets

### ❌ MAL (Secrets predecibles)

```bash
# envs/.env.prod
JWT_SECRET_KEY=prod-jwt-secret-2024-very-secure-32-chars-key
SECRET_KEY=prod-session-secret-2024-very-secure-32-chars
MONGODB_PASSWORD=ProdMongo2024!SecurePass
```

**Problemas:**
- Patrones predecibles (`prod-`, `2024`, palabras comunes)
- Podrían estar en git/logs/documentación
- Fáciles de adivinar con fuerza bruta

### ✅ BIEN (Generados criptográficamente)

```bash
# Generar secrets seguros
openssl rand -hex 32   # Para JWT_SECRET_KEY, SECRET_KEY
openssl rand -base64 32 | tr -d '/+='  # Para passwords (MongoDB, Redis)

# Ejemplo de salida:
# JWT_SECRET_KEY=a7f2c8e1b3d4f5e6a7f2c8e1b3d4f5e6a7f2c8e1b3d4f5e6a7f2c8e1b3d4f5e6
# MONGODB_PASSWORD=x8K2mP9vL5nQ3wR7tY4uZ1iO6aS8dF3gH7jK2lM9nB5vC
```

### Rotación de Secrets

```bash
# 1. Generar nuevos secrets
NEW_JWT=$(openssl rand -hex 32)
NEW_MONGO_PASS=$(openssl rand -base64 32 | tr -d '/+=')
NEW_REDIS_PASS=$(openssl rand -base64 32 | tr -d '/+=')

# 2. Actualizar .env.prod
echo "JWT_SECRET_KEY=$NEW_JWT"
echo "MONGODB_PASSWORD=$NEW_MONGO_PASS"
echo "REDIS_PASSWORD=$NEW_REDIS_PASS"

# 3. Detener servicios
docker-compose -f infra/docker-compose.prod.yml down

# 4. IMPORTANTE: Eliminar volúmenes de bases de datos
docker volume rm copilotos-mongodb-prod-data
docker volume rm copilotos-redis-prod-data

# 5. Reiniciar con nuevos secrets
docker-compose -f infra/docker-compose.prod.yml up -d
```

`★ Insight ─────────────────────────────────────`
**Por qué eliminar volúmenes:**
MongoDB y Redis almacenan passwords hasheados en sus volúmenes de datos.
Cambiar la password en .env NO actualiza la DB existente.
Debes recrear los volúmenes para que usen las nuevas passwords.
`─────────────────────────────────────────────────`

---

## ⏱️ Variables Build-time vs Runtime

### El Problema de `NEXT_PUBLIC_*`

Next.js tiene dos tipos de variables de entorno:

| Tipo | Prefijo | Cuándo se usa | Dónde vive |
|------|---------|---------------|------------|
| **Servidor** | Cualquiera | Server-side rendering | Solo en el contenedor Node.js |
| **Cliente** | `NEXT_PUBLIC_*` | Browser JavaScript | Embebido en el bundle compilado |

`★ Insight ─────────────────────────────────────`
**Variables `NEXT_PUBLIC_*` son especiales:**
- Se compilan **DENTRO** del bundle JavaScript durante `next build`
- El valor que existe durante `docker build` es el que queda embebido
- Cambiar la variable en docker-compose **NO** afecta código ya compilado
- Debes pasar como `ARG` en el Dockerfile para que esté disponible en build time
`─────────────────────────────────────────────────`

### ✅ Configuración Correcta

#### 1. Dockerfile (Build Args)

```dockerfile
# apps/web/Dockerfile
FROM node:20-alpine AS builder

# BUILD-TIME: Variables deben estar aquí para ser embebidas
ARG NEXT_PUBLIC_API_URL=http://localhost:8001
ARG NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
ARG NODE_ENV=production

# Copiar ARG a ENV para que Next.js las vea durante el build
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_MAX_FILE_SIZE_MB=$NEXT_PUBLIC_MAX_FILE_SIZE_MB
ENV NODE_ENV=production

# Build (aquí se embeben las variables en el JS bundle)
RUN pnpm build
```

#### 2. docker-compose.yml (Build Args)

```yaml
# infra/docker-compose.yml
services:
  web:
    build:
      context: ..
      dockerfile: apps/web/Dockerfile
      target: dev
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://api:8001}
        NEXT_PUBLIC_MAX_FILE_SIZE_MB: ${NEXT_PUBLIC_MAX_FILE_SIZE_MB:-50}
```

#### 3. Script de Deploy (Build Args)

```bash
# scripts/deploy-with-tar.sh
docker build -f apps/web/Dockerfile \
    --build-arg NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8001}" \
    --build-arg NEXT_PUBLIC_MAX_FILE_SIZE_MB="${NEXT_PUBLIC_MAX_FILE_SIZE_MB:-50}" \
    -t infra-web:latest \
    --target runner .
```

#### 4. .env.prod (Source de Verdad)

```bash
# envs/.env.prod
NEXT_PUBLIC_API_URL=http://34.42.214.246:8001
NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
```

### Verificación

```bash
# En producción, después del deploy:
# Opción 1: Inspeccionar bundle JavaScript
curl https://tu-dominio.com/_next/static/chunks/pages/_app*.js | grep -o "MAX_FILE_SIZE_MB.*50"

# Opción 2: Desde DevTools del navegador
# Console → ejecutar:
console.log(process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB)
# Debe mostrar: 50
```

---

## 🌐 CORS y Proxy Reverso

### Escenario 1: Sin Nginx (Desarrollo)

```
Browser → http://localhost:3000 (Next.js)
       ↘ http://localhost:8001 (FastAPI)
```

**Problema:** Orígenes diferentes = CORS requerido

```bash
# .env.local (desarrollo)
NEXT_PUBLIC_API_URL=http://localhost:8001
CORS_ORIGINS=["http://localhost:3000"]
```

### Escenario 2: Con Nginx Proxy (Producción)

```
Browser → http://34.42.214.246 (Nginx)
             ├→ / → web:3000 (Next.js)
             └→ /api → api:8001 (FastAPI)
```

**Ventaja:** Un solo origen = CORS NO necesario

```bash
# .env.prod (producción con nginx)
NEXT_PUBLIC_API_URL=http://34.42.214.246/api  # ← Sin puerto, nginx hace proxy
CORS_ORIGINS=["http://34.42.214.246"]  # Solo el dominio público
```

`★ Insight ─────────────────────────────────────`
**Nginx elimina necesidad de CORS:**
- Navegador solo ve un origen: `http://34.42.214.246`
- Nginx internamente rutea `/api/*` → `api:8001`
- CORS solo aplica a requests cross-origin (diferentes dominios/puertos)
- Con proxy, todo viene del mismo origen desde perspectiva del navegador
`─────────────────────────────────────────────────`

### Configuración Nginx Recomendada

```nginx
# infra/nginx/nginx.conf
http {
    client_max_body_size 50M;  # Debe coincidir con backend

    upstream api {
        server copilotos-api:8001;
        keepalive 32;
    }

    upstream web {
        server copilotos-web:3000;
        keepalive 32;
    }

    server {
        listen 80;
        server_name 34.42.214.246;

        # API endpoints (sin trailing slash)
        location /api {
            limit_req zone=api burst=20 nodelay;

            # IMPORTANTE: Sin trailing / en proxy_pass
            # Preserva /api en el path enviado al backend
            proxy_pass http://api;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # Timeouts para uploads grandes
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
            proxy_connect_timeout 60s;
        }

        # Frontend
        location / {
            limit_req zone=web burst=50 nodelay;

            proxy_pass http://web;
            proxy_set_header Host $host;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
        }
    }
}
```

---

## ⚡ Optimización de Nginx

### 1. Rate Limiting

```nginx
# Protección contra DDoS/abuse
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=web:10m rate=30r/s;

location /api {
    limit_req zone=api burst=20 nodelay;
    # Permite ráfagas de 20 requests, luego limita a 10/s
}
```

### 2. Keepalive Connections

```nginx
upstream api {
    server copilotos-api:8001;
    keepalive 32;  # Mantiene 32 conexiones persistentes
}

# Beneficio: Reduce latencia de establecer nueva conexión TCP
# Reduce overhead de SSL handshakes (si usas HTTPS)
```

### 3. Caching de Estáticos

```nginx
location /_next/static/ {
    proxy_pass http://web;
    expires 1y;  # Cachea assets por 1 año
    add_header Cache-Control "public, immutable";
}

location ~* \.(jpg|jpeg|png|gif|ico|svg|woff|woff2)$ {
    proxy_pass http://web;
    expires 30d;
    add_header Cache-Control "public";
}
```

### 4. Compression

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1024;
gzip_comp_level 6;
gzip_types
    text/plain
    text/css
    text/javascript
    application/json
    application/javascript
    image/svg+xml;

# Beneficio: Reduce bandwidth 60-80% en JSON/JS/CSS
```

---

## ✅ Checklist de Deployment

### Pre-deployment

```bash
# 1. Validar configuración local
cd /home/jazielflo/Proyects/copilotos-bridge
grep -E "NEXT_PUBLIC_MAX_FILE_SIZE_MB|MAX_FILE_SIZE" envs/.env.prod

# 2. Verificar build args en scripts
grep -A 5 "build-arg" scripts/deploy-with-tar.sh
grep -A 5 "build-arg" scripts/push-to-registry.sh

# 3. Test de build local (opcional)
docker build -f apps/web/Dockerfile \
    --build-arg NEXT_PUBLIC_MAX_FILE_SIZE_MB=50 \
    -t test-web:latest \
    --target runner .

# 4. Validar imagen tiene variable embebida
docker run --rm test-web:latest env | grep NEXT_PUBLIC_MAX_FILE_SIZE_MB
# Debe mostrar: NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
```

### Deployment

```bash
# Opción 1: Tar deployment (no requiere registry)
make deploy-tar

# Opción 2: Registry deployment (más rápido)
make deploy-prod
```

### Post-deployment (En el servidor)

```bash
ssh jf@34.42.214.246

cd /home/jf/copilotos-bridge

# 1. Validar configuración
bash scripts/validate-env-server.sh

# 2. Verificar servicios corriendo
docker ps | grep copilotos

# 3. Verificar logs sin errores
docker logs copilotos-web-prod --tail 50 | grep -i error
docker logs copilotos-api-prod --tail 50 | grep -i error

# 4. Test funcional: Upload de archivo
curl -X POST http://34.42.214.246/api/documents/upload \
  -H "Authorization: Bearer $(cat /tmp/test-token.txt)" \
  -F "file=@tests/data/pdf/HPE.pdf"

# Debe retornar 200 OK con document_id
```

### Rollback (Si algo falla)

```bash
# En el servidor

# 1. Detener servicios
docker-compose -f infra/docker-compose.prod.yml down

# 2. Restaurar backup de .env
cp envs/.env.prod.backup-YYYYMMDD-HHMMSS envs/.env.prod

# 3. Cargar imagen anterior (si existe tag backup)
docker tag copilotos-web:backup copilotos-web:latest
docker tag copilotos-api:backup copilotos-api:latest

# 4. Reiniciar
docker-compose -f infra/docker-compose.prod.yml up -d

# 5. Verificar
docker ps
curl http://34.42.214.246/health
```

---

## 📊 Matriz de Variables de Entorno

| Variable | Local (.env.local) | Prod (.env.prod) | Dockerfile ARG | docker-compose | Descripción |
|----------|-------------------|------------------|----------------|----------------|-------------|
| `NEXT_PUBLIC_API_URL` | http://localhost:8001 | http://IP/api | ✅ Sí | ✅ Sí | URL del API (vista por navegador) |
| `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | 50 | 50 | ✅ Sí | ✅ Sí | Límite frontend (MB) |
| `MAX_FILE_SIZE` | 52428800 | 52428800 | ❌ No | ✅ Sí | Límite backend (bytes) |
| `JWT_SECRET_KEY` | dev-secret | crypto-random | ❌ No | ✅ Sí | Secret para JWT |
| `MONGODB_PASSWORD` | dev-pass | crypto-random | ❌ No | ✅ Sí | Password de MongoDB |
| `SAPTIVA_API_KEY` | va-ai-dev... | va-ai-prod... | ❌ No | ✅ Sí | API key de Saptiva |

---

## 🔗 Referencias

- **Auditoría completa:** [`ENV_SERVER_AUDIT_AND_FIX.md`](./ENV_SERVER_AUDIT_AND_FIX.md)
- **Scripts:**
  - [`scripts/validate-env-server.sh`](../../scripts/validate-env-server.sh)
  - [`scripts/fix-env-server.sh`](../../scripts/fix-env-server.sh)
- **Dockerfile Web:** [`apps/web/Dockerfile`](../../apps/web/Dockerfile)
- **Nginx Config:** [`infra/nginx/nginx.conf`](../../infra/nginx/nginx.conf)

---

**Última revisión:** 2025-10-21 | **Mantenedor:** JazzzFM
