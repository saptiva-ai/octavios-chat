# CI/CD Optimization Summary

## 📊 Resultados Esperados

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| **Tiempo total CI/CD** | ~30 min | ~8-10 min | **67% más rápido** |
| **Docker build** | 10-12 min | 2-3 min | **75% más rápido** (cache) |
| **Backend tests** | 4-5 min | 1-2 min | **60% más rápido** (paralelo) |
| **Integration tests** | 3-4 min | 1-2 min | **50% más rápido** (paralelo) |
| **Frontend install** | 2-3 min | 30-60s | **75% más rápido** (fetch) |
| **Deployment** | 8-10 min | 3-5 min | **50% más rápido** (registry) |

---

## ✅ Optimizaciones Implementadas

### 1. **Concurrency Control** ✅
**Impacto**: Evita workflows duplicados consumiendo runners

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Beneficio**: Cancela automáticamente builds obsoletos cuando llega un nuevo push.

---

### 2. **paths-ignore** ✅
**Impacto**: Evita builds innecesarios en cambios de documentación

```yaml
on:
  push:
    paths-ignore:
      - 'docs/**'
      - '**.md'
      - 'LICENSE'
```

**Beneficio**: No ejecuta CI completo al actualizar solo docs → ahorra **30 min** por commit de docs.

---

### 3. **Docker Build Cache** ✅ **(MÁS IMPORTANTE)**
**Impacto**: Reutiliza layers entre builds → **10-12 min → 2-3 min**

**Nuevo job `build_images`**:
```yaml
build_images:
  runs-on: ubuntu-latest
  steps:
    - uses: docker/setup-buildx-action@v3
    - uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Build and push API
      uses: docker/build-push-action@v5
      with:
        context: ./apps/api
        push: true
        tags: ghcr.io/.../api:latest
        cache-from: type=registry,ref=ghcr.io/.../api:buildcache
        cache-to: type=registry,ref=ghcr.io/.../api:buildcache,mode=max
```

**Cómo funciona**:
- **Primera vez**: Build completo (10-12 min) + crea buildcache
- **Siguientes**: Reutiliza layers sin cambios (2-3 min)
- **Cache storage**: GHCR (gratis para repos públicos)

**IMPORTANTE**: El job `integration` ahora usa `--no-build` y pull de GHCR:
```yaml
integration:
  needs: [build_images]  # Espera a que las imágenes estén listas
  steps:
    - name: Pull pre-built images
      run: |
        docker pull ghcr.io/.../api:latest
        docker pull ghcr.io/.../web:latest

    - name: Start services (NO rebuild)
      run: docker compose up -d --no-build --wait
```

---

### 4. **Pytest Paralelo (pytest-xdist)** ✅
**Impacto**: Ejecuta tests en paralelo → **4-5 min → 1-2 min**

```yaml
- name: Install dependencies
  run: pip install pytest-xdist

- name: Run tests (parallelized)
  run: pytest -n auto  # -n auto usa todos los CPUs disponibles
```

**Backend tests**: `-n auto` (4 workers en GitHub runners)
**Integration tests**: `-n auto` consolidado en un solo comando

---

### 5. **pnpm Fetch Optimization** ✅
**Impacto**: Download paralelo + offline mode → **2-3 min → 30-60s**

```yaml
- name: Fetch dependencies
  run: pnpm fetch  # Descarga en paralelo

- name: Install (offline mode)
  run: pnpm install --frozen-lockfile --offline --prefer-offline
```

**Beneficio**: `pnpm fetch` descarga en paralelo, luego install usa cache local.

---

### 6. **Venv Cache** ✅
**Impacto**: Reutiliza venv entre jobs → ahorra **1-2 min** por job

```yaml
- name: Cache venv
  uses: actions/cache@v4
  with:
    path: apps/api/.venv
    key: venv-${{ runner.os }}-py3.11-${{ hashFiles('apps/api/requirements.txt') }}
```

**Beneficio**: Solo reinstala si `requirements.txt` cambia.

---

## 🔵🟢 Blue/Green Deployment

### **Arquitectura**

```
┌─────────────────────────────────────────┐
│  Shared Data Layer (Always Running)     │
│  ┌──────────┐        ┌──────────┐      │
│  │ MongoDB  │        │  Redis   │      │
│  │ (27017)  │        │  (6379)  │      │
│  └──────────┘        └──────────┘      │
│       ▲                    ▲            │
│       └────────┬───────────┘            │
│                │ copilotos-data-network │
└────────────────┼────────────────────────┘
                 │
      ┌──────────┴──────────┐
      │                     │
┌─────▼─────┐        ┌──────▼────┐
│   BLUE    │        │   GREEN   │
│  Stack    │        │  Stack    │
│ ┌───────┐ │        │ ┌───────┐ │
│ │  API  │ │        │ │  API  │ │
│ │  Web  │ │        │ │  Web  │ │
│ └───────┘ │        │ └───────┘ │
└─────┬─────┘        └──────┬────┘
      │  (idle)       (active)│
      └───────────┬───────────┘
                  │
            ┌─────▼─────┐
            │   Nginx   │ ← Switch entre colores
            └───────────┘
```

### **Componentes**

1. **`docker-compose.data.yml`**: Capa de datos compartida
   - MongoDB + Redis con volúmenes externos
   - Siempre activa, independiente del color

2. **`docker-compose.app.yml`**: Capa de aplicación
   - API + Web sin bases de datos
   - Se instancia como `-p copilotos-blue` o `-p copilotos-green`

3. **`blue-green-switch.sh`**: Script de switching
   - Detecta color activo/idle
   - Verifica health checks
   - Actualiza nginx upstream
   - Rollback automático en fallo

---

## 📝 Guía de Uso

### **Primera vez: Inicializar Blue/Green**

```bash
# En el servidor de producción
cd /opt/copilotos-bridge

# 1. Crear volúmenes y levantar datos
./scripts/init-blue-green.sh

# 2. Deploy primer stack (blue)
docker compose -p copilotos-blue -f infra/docker-compose.app.yml up -d

# 3. Verificar health
./scripts/blue-green-switch.sh --status

# 4. Activar blue (primera vez)
./scripts/blue-green-switch.sh blue
```

---

### **Deployment Normal (con Blue/Green)**

```bash
# 1. Detectar color idle
IDLE_COLOR=$(./scripts/blue-green-switch.sh --status | grep "Idle" | awk '{print $3}')

# 2. Pull nuevas imágenes
docker pull ghcr.io/jazielflo/copilotos-bridge/api:latest
docker pull ghcr.io/jazielflo/copilotos-bridge/web:latest

# 3. Levantar stack idle con nuevas imágenes
docker compose -p copilotos-$IDLE_COLOR -f infra/docker-compose.app.yml up -d

# 4. Esperar health checks
sleep 30

# 5. Switch automático (con rollback si falla)
./scripts/blue-green-switch.sh auto

# ✅ Zero downtime - El color anterior queda idle para rollback rápido
```

---

### **Rollback Instantáneo**

```bash
# Si detectas problemas después del deploy:
./scripts/blue-green-switch.sh blue  # Vuelve al color anterior

# Rollback automático en <10 segundos
```

---

## 🚀 Deployment via CI/CD (GitHub Actions)

El workflow ahora:

1. **Build + Cache** (2-3 min)
   - Builds con cache reutilizable
   - Push a GHCR con tags versionados

2. **Tests Paralelos** (2-3 min)
   - Backend + Integration en paralelo
   - Usa imágenes preconstruidas

3. **Deploy Registry** (3-5 min)
   - Server pull de GHCR
   - Blue/Green switch automático
   - Rollback en fallo

**Total**: ~8-10 min (vs 30 min anterior)

---

## 🐛 Troubleshooting

### **GHCR Deny (Authentication Failure)**

**Síntoma**: `Error: denied: permission_denied`

**Causas posibles**:
1. Token sin scopes `write:packages` + `read:packages`
2. SSO no habilitado para el token (si la org lo requiere)
3. Visibility del package en "Private" en vez de "Public"

**Solución**:
```bash
# 1. Verificar token manualmente en el server
echo "$REGISTRY_TOKEN" | docker login ghcr.io -u "$REGISTRY_USER" --password-stdin

# 2. Si falla, ir a GitHub → Settings → Personal Access Tokens → Regenerar con scopes correctos

# 3. Habilitar SSO (si aplica)
# GitHub → Settings → Tokens → Configure SSO → Enable para la organización
```

---

### **Build Cache Miss**

**Síntoma**: Build sigue tardando 10+ min a pesar del cache

**Causa**: Cache invalidado por cambios en Dockerfile o base image

**Verificar**:
```bash
# Check si el buildcache tag existe en GHCR
docker manifest inspect ghcr.io/jazielflo/copilotos-bridge/api:buildcache

# Si no existe, primera build lo creará
```

---

### **Blue/Green Switch Failure**

**Síntoma**: `Cannot switch: green stack is not healthy`

**Debug**:
```bash
# 1. Ver logs del stack idle
docker compose -p copilotos-green -f infra/docker-compose.app.yml logs

# 2. Check health manualmente
docker inspect copilotos-green-api-1 | grep -A10 Health

# 3. Verificar conectividad a datos
docker exec copilotos-green-api-1 curl -f http://copilotos-data-mongodb:27017
```

---

## 📊 Monitoring Deployment Speed

```bash
# Ver historial de workflows
make ci-list

# Tiempo promedio de deploy
gh run list --workflow="CI + CD" --limit 10 --json conclusion,displayTitle,createdAt,updatedAt | \
  jq '.[] | select(.conclusion=="success") | {title: .displayTitle, duration: ((.updatedAt | fromdateiso8601) - (.createdAt | fromdateiso8601))}'
```

---

## 🎯 Next Steps

### **Opcional: Más Optimizaciones**

1. **Self-hosted Runners** → elimina queue time (~1-2 min)
2. **Docker Layer Cache en S3** → alternativa a GHCR (más rápido)
3. **Test Splitting** → dividir tests en múltiples jobs paralelos
4. **Tailscale VPN** → deploy directo sin SSH tunneling

### **Recomendaciones**

- **Monitorear cache hit rate** en GHCR (debería ser >80%)
- **Revisar `make ci-logs`** después de cada deploy
- **Ejecutar `make deploy-registry --dry-run`** antes de merge a main

---

## 📚 Referencias

- **GitHub Actions Cache**: https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows
- **Docker Build Cache**: https://docs.docker.com/build/cache/backends/
- **Blue/Green Deployment**: https://martinfowler.com/bliki/BlueGreenDeployment.html
- **pytest-xdist**: https://pytest-xdist.readthedocs.io/

---

**Autor**: Claude Code Assistant
**Fecha**: 2025-10-20
**Versión**: 1.0
