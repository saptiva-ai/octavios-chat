# Guía de Deployment Rápido - 414.saptiva.com

## 🚀 Opciones de Deployment

### 1. Deployment Completo (Primera vez / Cambios mayores)

```bash
./scripts/deploy-cloudflare-414.sh
```

**Tiempo:** ~8-10 minutos
**Cuándo usar:** Primera vez, cambios en dependencies, cambios de infraestructura

**Proceso:**
1. Build de imágenes Docker (API + Web)
2. Export a tar.gz
3. Transfer a servidor
4. Load en servidor
5. Restart de todos los servicios

---

### 2. Modo Rápido (Cambios de código)

```bash
./scripts/deploy-cloudflare-414.sh --fast
```

**Tiempo:** ~3-4 minutos
**Cuándo usar:** Cambios en código backend/frontend, sin cambios en base de datos

**Ventajas:**
- ✅ MongoDB, Redis, MinIO permanecen corriendo
- ✅ Sin downtime de datos
- ✅ Solo recreate web/api/nginx

**Ejemplo:**
```bash
# Hiciste cambios en el frontend o API
vim apps/web/src/components/chat/ChatComposer.tsx
git add . && git commit -m "fix: improve chat UI"
./scripts/deploy-cloudflare-414.sh --fast
```

---

### 3. Solo Configuración (Cambios de config)

```bash
./scripts/deploy-cloudflare-414.sh --only-config
```

**Tiempo:** ~30 segundos
**Cuándo usar:** Cambios en nginx, variables de entorno, docker-compose

**Ventajas:**
- ⚡ Ultra rápido
- ✅ Sin rebuild de imágenes
- ✅ Sin restart de servicios

**Proceso:**
1. Transfer configs (nginx, .env, docker-compose)
2. Restart manual de servicios afectados

**Ejemplo:**
```bash
# Cambiaste CORS o timeouts
vim envs/.env.prod
./scripts/deploy-cloudflare-414.sh --only-config

# Restart solo el servicio afectado
ssh jf@34.172.67.93 "cd /home/jf/capital414-chat && \
  docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml restart api"
```

---

### 4. Sin Rebuild (Imágenes ya construidas)

```bash
./scripts/deploy-cloudflare-414.sh --skip-build
```

**Tiempo:** ~4-5 minutos
**Cuándo usar:** Testing, imágenes ya construidas localmente

**Ventajas:**
- ✅ Skip build step (usa imágenes existentes)
- ✅ Útil para testing rápido

---

## 📊 Comparativa de Tiempos

| Modo | Tiempo | Build | Transfer | Restart | Uso Principal |
|------|--------|-------|----------|---------|---------------|
| **Completo** | 8-10 min | ✅ | ✅ | Todo | Primera vez, dependencies |
| **Fast** | 3-4 min | ✅ | ✅ | web/api/nginx | Cambios de código |
| **Config Only** | 30 seg | ❌ | Config | Manual | Variables, nginx |
| **Skip Build** | 4-5 min | ❌ | ✅ | Todo | Testing |

---

## 🔄 Workflow Recomendado

### Desarrollo Normal (Cambios de código)

```bash
# 1. Local: hacer cambios
vim apps/web/src/components/chat/ChatComposer.tsx
vim apps/api/src/routers/chat.py

# 2. Commit
git add .
git commit -m "feat: add new chat feature"

# 3. Deploy en modo rápido
./scripts/deploy-cloudflare-414.sh --fast

# 4. Verificar
curl https://414.saptiva.com/api/health
```

**Tiempo total:** ~5 minutos (commit + deploy)

---

### Hotfix Urgente

```bash
# 1. Fix crítico
vim apps/api/src/routers/auth.py
git add . && git commit -m "fix: critical auth bug"

# 2. Deploy inmediato (fast mode)
./scripts/deploy-cloudflare-414.sh --fast

# 3. Monitor
ssh jf@34.172.67.93 "docker logs capital414-chat-api -f"
```

**Tiempo total:** ~3-4 minutos

---

### Cambio de Configuración

```bash
# 1. Editar config
vim envs/.env.prod
# Cambiar: CORS_ORIGINS, timeouts, feature flags

# 2. Deploy config
./scripts/deploy-cloudflare-414.sh --only-config

# 3. Restart servicio afectado
ssh jf@34.172.67.93 "cd /home/jf/capital414-chat && \
  docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml restart api"
```

**Tiempo total:** ~1 minuto

---

## 🛠️ Comandos Útiles Post-Deployment

### Verificar Status

```bash
# Status completo
ssh jf@34.172.67.93 "cd /home/jf/capital414-chat && \
  docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml ps"

# Health check
curl https://414.saptiva.com/api/health
```

### Ver Logs

```bash
# API logs
ssh jf@34.172.67.93 "docker logs capital414-chat-api -f --tail 50"

# Web logs
ssh jf@34.172.67.93 "docker logs capital414-chat-web -f --tail 50"

# Nginx logs
ssh jf@34.172.67.93 "docker logs capital414-chat-nginx -f --tail 50"
```

### Restart Individual

```bash
# Solo API
ssh jf@34.172.67.93 "cd /home/jf/capital414-chat && \
  docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml restart api"

# Solo Web
ssh jf@34.172.67.93 "cd /home/jf/capital414-chat && \
  docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml restart web"
```

---

## ⚠️ Notas Importantes

### Variables de Entorno en Next.js

**IMPORTANTE:** Las variables `NEXT_PUBLIC_*` se compilan en build time:

```bash
# Si cambias estas variables, necesitas rebuild
NEXT_PUBLIC_API_URL=https://414.saptiva.com/api
NEXT_PUBLIC_APP_NAME="Saptiva Copilot OS - Capital 414"
NEXT_PUBLIC_FEATURE_ADD_FILES=true
NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
```

**No funciona:**
```bash
vim envs/.env.prod  # Cambiar NEXT_PUBLIC_API_URL
docker compose restart web  # ❌ Cambio NO se refleja
```

**Funciona:**
```bash
vim envs/.env.prod  # Cambiar NEXT_PUBLIC_API_URL
./scripts/deploy-cloudflare-414.sh --fast  # ✅ Rebuild + deploy
```

### Caché del Navegador

Después de deployment, algunos usuarios pueden ver versión antigua:

**Solución para usuarios:**
- `Ctrl + Shift + R` (Windows/Linux)
- `Cmd + Shift + R` (Mac)
- Modo incógnito

**Prevención (futuro):**
- Agregar cache busting en `/api/version` endpoint
- Frontend check version on mount

---

## 📈 Métricas de Deployment

**Último deployment (2025-11-04):**
- Healthchecks: ✅ Todos healthy
- API Response Time: ~1.07ms (database latency)
- Build Time (local): ~4min
- Transfer Time: ~2min
- Deploy Time: ~2min
- **Total:** ~8min

**Con modo --fast:**
- Build Time: ~4min
- Transfer Time: ~2min
- Deploy Time: ~30seg (solo web/api)
- **Total:** ~3-4min

---

## 🎯 Checklist de Deployment

- [ ] Código testeado localmente
- [ ] Tests passing: `make test-all`
- [ ] Commit con mensaje descriptivo
- [ ] Variables de entorno actualizadas en `envs/.env.prod`
- [ ] Elegir modo de deployment apropiado
- [ ] Ejecutar script de deployment
- [ ] Verificar health checks: `curl https://414.saptiva.com/api/health`
- [ ] Verificar sitio en navegador
- [ ] Monitorear logs por 5min para detectar errores

---

## 🆘 Troubleshooting

### Problema: Healthchecks unhealthy

```bash
# Ver detalles del healthcheck
ssh jf@34.172.67.93 "docker inspect capital414-chat-web --format '{{json .State.Health}}' | python3 -m json.tool"

# Test manual
ssh jf@34.172.67.93 "docker exec capital414-chat-web wget --no-verbose --tries=1 --spider http://127.0.0.1:3000"
```

### Problema: CORS errors

```bash
# Verificar CORS config
ssh jf@34.172.67.93 "docker exec capital414-chat-api env | grep CORS"

# Test CORS preflight
curl -X OPTIONS https://414.saptiva.com/api/auth/register \
  -H "Origin: https://414.saptiva.com" \
  -H "Access-Control-Request-Method: POST" \
  -v
```

### Problema: Web muestra versión antigua

```bash
# Verificar variables compiladas
ssh jf@34.172.67.93 "docker exec capital414-chat-web env | grep NEXT_PUBLIC"

# Verificar imagen
ssh jf@34.172.67.93 "docker image inspect octavios-web:latest --format '{{.Created}}'"

# Si es antigua, rebuild
./scripts/deploy-cloudflare-414.sh --fast
```

---

## 📚 Referencias

- **Deployment principal:** `scripts/deploy-cloudflare-414.sh`
- **Docker Compose:** `infra/docker-compose.cloudflare.yml`
- **Nginx config:** `infra/nginx/nginx.414.cloudflare.conf`
- **Variables prod:** `envs/.env.prod`
- **Makefile:** `Makefile` (comandos de desarrollo)
