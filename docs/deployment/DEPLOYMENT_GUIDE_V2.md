# Guía de Deploy a Producción - V2 (Mejorada)

**Versión:** 2.0
**Fecha:** 2025-12-02
**Cambios:** Soluciona problemas de env vars, tablas faltantes, y dependencias

---

## 📋 Tabla de Contenidos

- [Cambios Principales](#cambios-principales)
- [Scripts Nuevos](#scripts-nuevos)
- [Deploy Completo (Primera Vez)](#deploy-completo-primera-vez)
- [Deploy Actualización (Deploy Incremental)](#deploy-actualización-deploy-incremental)
- [Inicializar/Poblar Bank Advisor](#inicializarpoblar-bank-advisor)
- [Troubleshooting](#troubleshooting)
- [Checklist de Pre-Deploy](#checklist-de-pre-deploy)

---

## 🔥 Cambios Principales

### Problemas Solucionados

1. **Variables de entorno no se cargan correctamente**
   - ❌ **Problema:** Docker Compose resuelve `${SECRET_KEY:-default}` desde el host, no del env_file
   - ✅ **Solución:** Script carga y exporta variables antes de `docker compose up`

2. **Tabla `etl_runs` faltante**
   - ❌ **Problema:** Bank Advisor health check falla porque `etl_runs` no existe
   - ✅ **Solución:** Script de deploy crea automáticamente la tabla

3. **Dependencias faltantes (polars)**
   - ❌ **Problema:** Polars en requirements.txt pero no se instala si se usa cache de Docker
   - ✅ **Solución:** Script de inicialización instala dependencias si faltan

4. **ETL manual y lento**
   - ❌ **Problema:** ETL debe ejecutarse manualmente y procesa 1.3M+ registros
   - ✅ **Solución:** Script dedicado con tracking y logging mejorado

5. **Verificación de datos incorrecta**
   - ❌ **Problema:** Script buscaba usuarios en PostgreSQL (están en MongoDB)
   - ✅ **Solución:** Script verifica PostgreSQL para Bank Advisor y MongoDB para usuarios

---

## 📦 Scripts Nuevos

### 1. `scripts/deploy-production-v2.sh`

**Deploy completo y seguro con mejoras:**

- Carga variables de entorno correctamente
- Detecta automáticamente `docker compose` vs `docker-compose`
- Crea tablas faltantes automáticamente
- Verifica datos en PostgreSQL Y MongoDB
- Mejor manejo de errores y logging

**Uso:**
```bash
cd /path/to/octavios-chat-bajaware_invex
chmod +x scripts/deploy-production-v2.sh
./scripts/deploy-production-v2.sh
```

### 2. `scripts/init-bankadvisor-db.sh`

**Inicialización completa de Bank Advisor:**

- Crea todas las tablas necesarias
- Verifica e instala dependencias faltantes
- Ejecuta ETL completo con tracking
- Verifica datos poblados correctamente

**Uso:**
```bash
# Después de que los servicios estén corriendo
chmod +x scripts/init-bankadvisor-db.sh
./scripts/init-bankadvisor-db.sh
```

---

## 🚀 Deploy Completo (Primera Vez)

### Paso 1: Preparación

```bash
# Conectar al servidor
ssh ${PROD_SERVER_USER}@${PROD_SERVER_IP}

# Ir al directorio del proyecto
cd /path/to/octavios-chat-bajaware_invex

# Verificar que estamos en main
git checkout main
git pull origin main
```

### Paso 2: Verificar Variables de Entorno

```bash
# Verificar que existen las variables críticas
grep -E '^SECRET_KEY=|^JWT_SECRET_KEY=' envs/.env

# Deben tener mínimo 32 caracteres cada una
```

### Paso 3: Ejecutar Deploy

```bash
# Hacer el script ejecutable
chmod +x scripts/deploy-production-v2.sh

# Ejecutar deploy
./scripts/deploy-production-v2.sh
```

**Salida esperada:**
```
🚀 Iniciando deploy seguro a producción (v2)...
🔍 Verificando pre-requisitos...
✅ Pre-checks completados
📋 Cargando variables de entorno...
✅ Variables de entorno cargadas
ℹ️  SECRET_KEY: lmHB00uG... (43 chars)
...
✅ DEPLOY COMPLETADO
```

### Paso 4: Inicializar Bank Advisor (Primera Vez)

```bash
# Hacer el script ejecutable
chmod +x scripts/init-bankadvisor-db.sh

# Ejecutar inicialización (tarda 5-10 minutos)
./scripts/init-bankadvisor-db.sh
```

**Salida esperada:**
```
╔════════════════════════════════════════════════════════════╗
║     Bank Advisor - Inicialización de Base de Datos         ║
╚════════════════════════════════════════════════════════════╝
...
✅ ETL completado exitosamente
✅ Total de registros: 7,119
✅ Total de bancos: 50
```

### Paso 5: Verificar

```bash
# Verificar todos los servicios
docker compose -f infra/docker-compose.yml ps

# Verificar health checks
curl http://localhost:8002/health
curl http://localhost:8000/health

# Verificar datos
docker compose -f infra/docker-compose.yml exec postgres psql -U octavios -d bankadvisor -c "SELECT COUNT(*) FROM monthly_kpis;"
```

---

## 🔄 Deploy Actualización (Deploy Incremental)

### Cuando NO hay cambios en Bank Advisor

```bash
# Conectar al servidor
ssh ${PROD_SERVER_USER}@${PROD_SERVER_IP}
cd /path/to/octavios-chat-bajaware_invex

# Pull cambios
git pull origin main

# Deploy rápido (solo backend/web)
export SECRET_KEY=$(grep '^SECRET_KEY=' envs/.env | cut -d '=' -f2)
export JWT_SECRET_KEY=$(grep '^JWT_SECRET_KEY=' envs/.env | cut -d '=' -f2)

docker compose -f infra/docker-compose.yml down
docker compose -f infra/docker-compose.yml build --no-cache backend web
docker compose -f infra/docker-compose.yml up -d
```

### Cuando SÍ hay cambios en Bank Advisor

```bash
# Usar el script completo
./scripts/deploy-production-v2.sh

# Si cambiaron los datos ETL, re-ejecutar:
./scripts/init-bankadvisor-db.sh
```

---

## 🗄️ Inicializar/Poblar Bank Advisor

### Cuándo ejecutar este script:

- Primera instalación
- Los datos de Bank Advisor están vacíos o incompletos
- Se agregaron nuevos archivos de datos
- Necesitas repoblar la base de datos

### Ejecución:

```bash
# Asegurarse de que los servicios estén corriendo
docker compose -f infra/docker-compose.yml up -d postgres bank-advisor

# Verificar que los archivos de datos existen
ls -la plugins/bank-advisor-private/data/raw/

# Ejecutar inicialización
./scripts/init-bankadvisor-db.sh
```

### Qué hace el script:

1. **Crea tablas:**
   - `monthly_kpis` (con todos los campos del ETL enhanced)
   - `etl_runs` (tracking de ejecuciones)
   - Índices para performance

2. **Instala dependencias:**
   - Verifica si polars está instalado
   - Si no, lo instala junto con openpyxl y pyarrow

3. **Ejecuta ETL:**
   - Procesa `CNBV_Cartera_Bancos_V2.xlsx`
   - Procesa `CorporateLoan_CNBVDB.csv` (1.3M+ registros)
   - Integra ICAP, TDA, Tasas Efectivas
   - Calcula tasas corporativas MN/ME

4. **Tracking:**
   - Registra inicio en `etl_runs`
   - Registra duración y registros procesados
   - Registra errores si falla

---

## 🔧 Troubleshooting

### Problema: Backend está "unhealthy"

**Síntoma:**
```
dependency failed to start: container octavios-chat-bajaware_invex-backend is unhealthy
```

**Causa:** `SECRET_KEY` demasiado corto o no cargado

**Solución:**
```bash
# Verificar longitud
grep '^SECRET_KEY=' envs/.env | cut -d '=' -f2 | wc -c
# Debe ser >= 33 (32 chars + newline)

# Cargar y reiniciar
export SECRET_KEY=$(grep '^SECRET_KEY=' envs/.env | cut -d '=' -f2)
export JWT_SECRET_KEY=$(grep '^JWT_SECRET_KEY=' envs/.env | cut -d '=' -f2)
docker compose -f infra/docker-compose.yml restart backend
```

---

### Problema: Bank Advisor health check falla

**Síntoma:**
```json
{"status":"unhealthy","error":"relation \"etl_runs\" does not exist"}
```

**Causa:** Tabla `etl_runs` no existe

**Solución:**
```bash
# Crear tabla manualmente
docker compose -f infra/docker-compose.yml exec postgres psql -U octavios -d bankadvisor <<EOF
CREATE TABLE IF NOT EXISTS etl_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_seconds FLOAT,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    rows_processed_base INTEGER,
    rows_processed_icap INTEGER,
    rows_processed_tda INTEGER,
    rows_processed_tasas INTEGER,
    etl_version VARCHAR(50),
    triggered_by VARCHAR(50) DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_etl_runs_started_at ON etl_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_etl_runs_status ON etl_runs(status);
EOF

# Reiniciar bank-advisor
docker compose -f infra/docker-compose.yml restart bank-advisor
```

---

### Problema: ETL falla con "No module named 'polars'"

**Síntoma:**
```
ModuleNotFoundError: No module named 'polars'
```

**Causa:** Build de Docker usó cache y no instaló polars

**Solución 1 (rápida):**
```bash
# Instalar en el contenedor corriendo
docker compose -f infra/docker-compose.yml exec bank-advisor pip install polars openpyxl pyarrow
```

**Solución 2 (permanente):**
```bash
# Rebuild sin cache
docker compose -f infra/docker-compose.yml build --no-cache bank-advisor
docker compose -f infra/docker-compose.yml up -d bank-advisor
```

---

### Problema: ETL muy lento

**Síntoma:** ETL tarda más de 30 minutos

**Causas posibles:**
1. Servidor con pocos recursos (CPU/RAM)
2. Archivo `CorporateLoan_CNBVDB.csv` corrupto o muy grande
3. PostgreSQL sin índices

**Solución:**
```bash
# Verificar tamaño del archivo
ls -lh plugins/bank-advisor-private/data/raw/CorporateLoan_CNBVDB.csv
# Debe ser ~228 MB

# Verificar recursos del servidor
docker stats

# Si necesario, aumentar recursos del contenedor en docker-compose.yml
```

---

### Problema: Datos no se preservaron después del deploy

**Síntoma:** Usuarios o datos desaparecieron

**Verificación:**
```bash
# Verificar volúmenes (deben existir)
docker volume ls | grep octavios

# Verificar MongoDB (usuarios)
docker compose -f infra/docker-compose.yml exec mongodb mongosh -u octavios_user -p secure_password_change_me --authenticationDatabase admin octavios --eval 'db.users.countDocuments()'

# Verificar PostgreSQL (Bank Advisor)
docker compose -f infra/docker-compose.yml exec postgres psql -U octavios -d bankadvisor -c 'SELECT COUNT(*) FROM monthly_kpis;'
```

**Si los volúmenes existen pero los datos no:**
- Puede ser que el servicio esté conectándose a una DB diferente
- Verificar variables de entorno en `envs/.env`

---

## ✅ Checklist de Pre-Deploy

Antes de hacer deploy a producción, verifica:

- [ ] Estoy en la rama correcta (`main` o la rama de deploy)
- [ ] He hecho pull de los últimos cambios
- [ ] Las variables `SECRET_KEY` y `JWT_SECRET_KEY` existen en `envs/.env`
- [ ] Ambas tienen mínimo 32 caracteres
- [ ] Los archivos de datos existen en `plugins/bank-advisor-private/data/raw/` (si es primera vez)
- [ ] Tengo backup reciente de la base de datos (opcional pero recomendado)
- [ ] Los usuarios están informados del downtime (si aplica)
- [ ] He probado el código en staging/local

---

## 📊 Comandos Útiles Post-Deploy

```bash
# Ver logs de todos los servicios
docker compose -f infra/docker-compose.yml logs -f

# Ver logs de un servicio específico
docker compose -f infra/docker-compose.yml logs -f bank-advisor

# Ver stats de recursos
docker stats

# Reiniciar un servicio
docker compose -f infra/docker-compose.yml restart [servicio]

# Verificar datos en Bank Advisor
docker compose -f infra/docker-compose.yml exec postgres psql -U octavios -d bankadvisor -c "
SELECT banco_norm, COUNT(*) as registros
FROM monthly_kpis
GROUP BY banco_norm
ORDER BY registros DESC
LIMIT 10;
"

# Verificar usuarios en MongoDB
docker compose -f infra/docker-compose.yml exec mongodb mongosh -u octavios_user -p secure_password_change_me --authenticationDatabase admin octavios --eval 'db.getCollectionNames().forEach(c => print(c, db[c].countDocuments()))'
```

---

## 📝 Notas Finales

### Diferencias con versión anterior

| Aspecto | V1 (Anterior) | V2 (Mejorada) |
|---------|---------------|---------------|
| Carga de env vars | ❌ No funciona | ✅ Funciona correctamente |
| Tabla etl_runs | ❌ Manual | ✅ Automático |
| Dependencias | ❌ Manual | ✅ Auto-instala si falta |
| ETL | ❌ Manual | ✅ Script dedicado |
| Verificación de datos | ❌ PostgreSQL solo | ✅ PostgreSQL + MongoDB |
| Docker Compose V1/V2 | ❌ Hardcoded | ✅ Auto-detecta |

### Recomendaciones

1. **Siempre usa `deploy-production-v2.sh`** para deploys completos
2. **Corre `init-bankadvisor-db.sh`** solo en primera instalación o cuando cambien datos
3. **Monitorea los logs** después del deploy por al menos 5 minutos
4. **Prueba el health check** de todos los servicios antes de dar por finalizado
5. **Documenta los cambios** de cada deploy en el commit message

---

**Última actualización:** 2025-12-02
**Contacto:** equipo-dev
**Versión de este documento:** 2.0
