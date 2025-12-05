# Deploy Scripts - Guía Completa

Scripts de deployment para Octavios - Soporta deployments granulares y completos.

## 📋 Tabla de Contenidos

- [Scripts Disponibles](#scripts-disponibles)
- [Setup Inicial](#-setup-inicial)
- [Deployment Granular (NUEVO)](#-deployment-granular-nuevo)
- [Deployment Completo (Legacy)](#-deployment-completo-legacy)
- [Workflow Recomendado](#-workflow-recomendado)
- [Variables de Entorno](#-variables-de-entorno)
- [Troubleshooting](#-troubleshooting)

## 🛠️ Scripts Disponibles

### Deployment Granular (v2.0)

#### **`deploy-service.sh`** - ⭐ Deploy selectivo de servicios
Despliega servicios específicos a producción (backend, web, file-manager, bank-advisor).

```bash
./scripts/deploy/deploy-service.sh "backend" 0.2.2          # Solo backend
./scripts/deploy/deploy-service.sh "backend web" 0.2.2      # Backend + web
./scripts/deploy/deploy-service.sh "all" 0.2.2              # Todos los servicios
```

#### **`detect-changes.sh`** - Detecta servicios modificados
Compara cambios en git para identificar qué servicios necesitan deploy.

```bash
./scripts/deploy/detect-changes.sh              # vs HEAD~1
./scripts/deploy/detect-changes.sh v0.2.1       # vs tag específico
```

#### **`tag-push-service.sh`** - Tag y push selectivo
Etiqueta y sube servicios específicos a Docker Hub.

```bash
./scripts/deploy/tag-push-service.sh "backend" 0.2.2        # Solo backend
./scripts/deploy/tag-push-service.sh "all" 0.2.2            # Todos
```

#### **`load-env.sh`** - Carga variables de entorno
Helper para cargar variables de deployment.

```bash
source scripts/deploy/load-env.sh prod          # Cargar .env.prod
source scripts/deploy/load-env.sh dev           # Cargar .env
```

### Deployment Completo (Legacy)

#### **`deploy-to-production.sh`** - Deploy completo
Despliega todos los servicios a producción.

```bash
./scripts/deploy/deploy-to-production.sh 0.2.2
```

#### **`tag-dockerhub.sh`** - Tag de todas las imágenes

```bash
./scripts/deploy/tag-dockerhub.sh 0.2.2
```

#### **`push-dockerhub.sh`** - Push de todas las imágenes

```bash
./scripts/deploy/push-dockerhub.sh
```

## 🚀 Setup Inicial

### 1. Configurar Variables de Entorno

Asegúrate de que `envs/.env.prod` tiene:

```bash
DEPLOY_SERVER=user@your-server-ip
DEPLOY_PROJECT_DIR=/home/user/project-dir
PROD_DOMAIN=your-domain.com
```

### 2. Verificar Acceso SSH

```bash
ssh $DEPLOY_SERVER "echo 'SSH OK'"
```

### 3. Cargar Variables

```bash
source scripts/deploy/load-env.sh prod
```

## 🎯 Deployment Granular (NUEVO)

### Ventajas
- ✅ Deploy solo lo que cambió
- ✅ Menor riesgo (servicios independientes)
- ✅ Más rápido (menos imágenes)
- ✅ Zero-downtime por servicio

### Workflow Completo

```bash
# 1. Detectar cambios
CHANGED=$(./scripts/deploy/detect-changes.sh | tail -1)
echo "Servicios modificados: $CHANGED"

# 2. Build solo lo modificado
make prod.build SVC="$CHANGED"

# 3. Tag y push
./scripts/deploy/tag-push-service.sh "$CHANGED" 0.2.2

# 4. Deploy
source scripts/deploy/load-env.sh prod
./scripts/deploy/deploy-service.sh "$CHANGED" 0.2.2
```

### Ejemplos de Uso

#### Deploy Backend (Bug Fix)

```bash
# Build
make prod.build SVC=backend

# Tag y push
./scripts/deploy/tag-push-service.sh "backend" 0.2.3

# Deploy
source scripts/deploy/load-env.sh prod
./scripts/deploy/deploy-service.sh "backend" 0.2.3
```

#### Deploy Frontend + Backend

```bash
# Build ambos
make prod.build SVC="backend web"

# Tag y push ambos
./scripts/deploy/tag-push-service.sh "backend web" 0.2.3

# Deploy
source scripts/deploy/load-env.sh prod
./scripts/deploy/deploy-service.sh "backend web" 0.2.3
```

#### Deploy con Detección Automática

```bash
CHANGED=$(./scripts/deploy/detect-changes.sh v0.2.2 | tail -1)

if [ ! -z "$CHANGED" ]; then
  make prod.build SVC="$CHANGED"
  ./scripts/deploy/tag-push-service.sh "$CHANGED" 0.2.3
  source scripts/deploy/load-env.sh prod
  ./scripts/deploy/deploy-service.sh "$CHANGED" 0.2.3
else
  echo "No changes detected"
fi
```

## 📦 Deployment Completo (Legacy)

### Workflow Tradicional

```bash
# LOCAL: Build y Push
make prod.build
./scripts/deploy/tag-dockerhub.sh 0.2.2
./scripts/deploy/push-dockerhub.sh

# SERVIDOR: Deploy
./scripts/deploy/deploy-to-production.sh 0.2.2
```

### Con Makefile

```bash
# Build todos los servicios
make prod.build

# O con servicios específicos
make prod.build SVC="backend web"

# O solo lo que cambió
make prod.build CHANGED=1

# O pull desde registry
make prod.build REGISTRY=1
```

## 💡 Workflow Recomendado

### Para Bug Fixes (1 servicio)
```bash
# ✅ Usa deployment granular
source scripts/deploy/load-env.sh prod
make prod.build SVC=backend
./scripts/deploy/tag-push-service.sh "backend" 0.2.3
./scripts/deploy/deploy-service.sh "backend" 0.2.3
```

### Para Features (2-3 servicios)
```bash
# ✅ Usa deployment granular
source scripts/deploy/load-env.sh prod
make prod.build SVC="backend web"
./scripts/deploy/tag-push-service.sh "backend web" 0.2.3
./scripts/deploy/deploy-service.sh "backend web" 0.2.3
```

### Para Releases Mayores
```bash
# ✅ Usa deployment completo
./scripts/deploy/tag-dockerhub.sh 0.3.0
./scripts/deploy/push-dockerhub.sh
./scripts/deploy/deploy-to-production.sh 0.3.0
```

## 📊 Variables de Entorno

| Variable | Ejemplo | Descripción |
|----------|---------|-------------|
| `DEPLOY_SERVER` | user@server-ip | Servidor de producción (SSH) |
| `DEPLOY_PROJECT_DIR` | /home/user/project | Directorio del proyecto |
| `PROD_DOMAIN` | example.com | Dominio de producción |
| `BACKUP_DB` | false (default) | Backup antes de deploy granular |

## 🐛 Troubleshooting

### Error: "DEPLOY_SERVER environment variable is required"

```bash
source scripts/deploy/load-env.sh prod
```

### Error: "No such image"

```bash
# Opción 1: Build
make prod.build SVC=backend

# Opción 2: Pull desde Docker Hub
docker pull jazielflores1998/octavios-invex-backend:0.2.2
```

### Error: "Failed to pull images"

```bash
# Verificar que existe en Docker Hub
curl -s "https://hub.docker.com/v2/repositories/jazielflores1998/octavios-invex-backend/tags" | grep "0.2.2"

# Si no existe, hacer push
./scripts/deploy/tag-push-service.sh "backend" 0.2.2
```

### Error: "Service unhealthy"

```bash
# Ver logs
ssh $DEPLOY_SERVER "cd $DEPLOY_PROJECT_DIR && docker compose logs backend"

# Rollback
source scripts/deploy/load-env.sh prod
./scripts/deploy/deploy-service.sh "backend" 0.2.1
```

### Error: "No space left on device"

```bash
# Limpiar imágenes antiguas
ssh $DEPLOY_SERVER "docker system prune -a --filter 'until=72h' -f"
```

## 📈 Monitoreo Post-Deploy

### Health Checks

```bash
# Backend
curl -s https://back-invex.saptiva.com/api/health | jq

# Frontend
curl -s -o /dev/null -w "%{http_code}" https://invex.saptiva.com
```

### Ver Logs

```bash
# Backend
ssh $DEPLOY_SERVER "cd $DEPLOY_PROJECT_DIR && docker compose logs -f backend"

# Todos
ssh $DEPLOY_SERVER "cd $DEPLOY_PROJECT_DIR && docker compose logs -f"
```

### Verificar Versiones Desplegadas

```bash
ssh $DEPLOY_SERVER "cd $DEPLOY_PROJECT_DIR && grep 'image:' infra/docker-compose.registry.yml"
```

## 🔐 Seguridad

### Variables Sensibles

**NUNCA** hardcodear en scripts:
- ❌ Passwords
- ❌ API keys
- ❌ JWT secrets

Usar `envs/.env.prod` (en `.gitignore`).

### SSH

- Usa SSH keys
- Limita IPs autorizadas
- Considera bastion host

## 📚 Referencias

- [Environment Variables](../../envs/.env.prod.example)
- [Makefile Targets](../../Makefile)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Docker Hub Registry](https://hub.docker.com/u/jazielflores1998)

---

**Última actualización:** 2025-12-04  
**Versión del sistema:** 2.0 (granular deployment)  
**Servicios disponibles:** backend, web, file-manager, bank-advisor
