# 🔒 Plan de Migración de Producción: copilotos → octavios

**Objetivo**: Renombrar todos los contenedores de "copilotos" a "octavios" en producción SIN pérdida de datos.

**Downtime estimado**: 2-3 minutos
**Complejidad**: Media
**Riesgo**: Bajo (con backups y rollback disponible)

---

## ⚠️ IMPORTANTE: Leer ANTES de Empezar

### Estrategia de Migración

Usaremos **recreación de contenedores con datos compartidos**:

- ✅ **Los volúmenes de datos NO se tocan** (MongoDB y Redis mantienen sus datos)
- ✅ **Contenedores antiguos se detienen pero NO se eliminan** (rollback rápido)
- ✅ **Nuevos contenedores usan los mismos volúmenes** (zero data loss)
- ✅ **Backups completos antes de cualquier cambio**

### Requisitos Previos

1. **Acceso SSH al servidor**: `ssh jf@copilot`
2. **Permisos Docker**: Usuario debe estar en grupo `docker`
3. **Espacio en disco**: Mínimo 5GB libres para backups
4. **Ventana de mantenimiento**: 10-15 minutos recomendados
5. **Código actualizado localmente**: Todos los cambios comiteados

---

## 📋 Checklist Pre-Migración

```bash
# En el servidor de producción
ssh jf@copilot

# ✓ Verificar espacio en disco
df -h
# Debe mostrar al menos 5GB disponibles en /

# ✓ Verificar contenedores corriendo
docker ps
# Debes ver: copilotos-prod-web, copilotos-prod-api, copilotos-prod-mongodb, copilotos-prod-redis

# ✓ Verificar volúmenes
docker volume ls | grep copilotos
# Debes ver volúmenes de mongodb y redis

# ✓ Verificar conectividad
curl http://localhost:8001/api/health
curl http://localhost:3000
# Ambos deben responder con status 200
```

---

## 🎯 Plan de Ejecución (8 Pasos)

### **Paso 1: Preparación Local** (5 minutos)

```bash
# En tu máquina local
cd ~/Proyects/copilotos-bridge

# 1.1 Verificar que todos los cambios están comiteados
git status
# Debe decir: "nothing to commit, working tree clean"

# 1.2 Commit y push si hay cambios pendientes
git add .
git commit -m "feat: migración de copilotos a octavios en producción"
git push origin develop

# 1.3 Verificar que archivos críticos tienen los cambios
grep "octavios" infra/docker-compose.yml | head -3
grep "octavios" Makefile | head -2
grep "octavios" envs/.env.production.example | head -3
```

**✓ CHECKPOINT**: Todos los archivos deben tener "octavios" en lugar de "copilotos".

---

### **Paso 2: Backup Completo en Producción** (10 minutos)

```bash
# En producción
ssh jf@copilot
cd ~/copilotos-bridge

# 2.1 Crear directorio de backups con fecha
mkdir -p ~/backups/migration-$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=~/backups/migration-$(date +%Y%m%d-%H%M%S)

# 2.2 Backup MongoDB (CRÍTICO)
echo "Haciendo backup de MongoDB..."
docker exec copilotos-prod-mongodb mongodump \
  --out=/data/backup-pre-rename-$(date +%Y%m%d-%H%M%S) \
  --authenticationDatabase=admin

# Verificar backup
docker exec copilotos-prod-mongodb ls -lh /data/ | grep backup

# 2.3 Backup Redis (CRÍTICO)
echo "Haciendo backup de Redis..."
docker exec copilotos-prod-redis redis-cli SAVE
docker cp copilotos-prod-redis:/data/dump.rdb $BACKUP_DIR/redis-dump.rdb

# 2.4 Backup volúmenes Docker (extra seguridad)
echo "Haciendo backup de volúmenes..."
docker run --rm \
  -v copilotos-bridge_mongodb_data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/mongodb-volume.tar.gz /data

docker run --rm \
  -v copilotos-bridge_redis_data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/redis-volume.tar.gz /data

# 2.5 Backup archivos subidos (si existen)
echo "Haciendo backup de archivos subidos..."
sudo tar -czf $BACKUP_DIR/uploaded-files.tar.gz \
  /tmp/copilotos_documents/ 2>/dev/null || echo "No hay archivos subidos"

# 2.6 Verificar backups
echo ""
echo "=== BACKUPS CREADOS ==="
ls -lh $BACKUP_DIR/
du -sh $BACKUP_DIR/
echo ""
```

**✓ CHECKPOINT**: Verificar que todos los backups existen y tienen tamaño > 0.

```bash
# Debe mostrar archivos como:
# mongodb-volume.tar.gz    (varios MB)
# redis-volume.tar.gz      (varios KB/MB)
# redis-dump.rdb           (varios KB/MB)
```

---

### **Paso 3: Actualizar Código en Servidor** (2 minutos)

```bash
# En producción
cd ~/copilotos-bridge

# 3.1 Stash cambios locales si los hay
git stash

# 3.2 Pull cambios con nuevos nombres
git pull origin develop

# 3.3 Verificar que se actualizó correctamente
grep "octavios" infra/docker-compose.yml | head -3
# Debe mostrar líneas con "octavios"

grep "octavios" Makefile | head -2
# Debe mostrar DEFAULT_COMPOSE_PROJECT_NAME := octavios

# 3.4 Actualizar archivo .env.prod manualmente
vim envs/.env.prod
# Cambiar:
#   MONGODB_USER=copilotos_user → MONGODB_USER=octavios_user
#   MONGODB_DATABASE=copilotos → MONGODB_DATABASE=octavios
#   OTEL_SERVICE_NAME=copilotos-bridge-prod → OTEL_SERVICE_NAME=octavios-bridge-prod
```

**✓ CHECKPOINT**: Archivos actualizados y .env.prod configurado con nuevos nombres.

---

### **Paso 4: Ejecutar Script de Migración** (3 minutos)

```bash
# En producción
cd ~/copilotos-bridge

# 4.1 Revisar el script (opcional)
cat scripts/migrate-prod-to-octavios.sh | less

# 4.2 Ejecutar migración automática
./scripts/migrate-prod-to-octavios.sh
```

**El script hará**:
1. ✓ Verificar prerrequisitos y backups
2. ✓ Mostrar estado actual
3. ✓ Solicitar confirmación (escribir "yes")
4. ✓ Detener contenedores antiguos
5. ✓ Verificar volúmenes intactos
6. ✓ Crear contenedores nuevos
7. ✓ Verificar health checks
8. ✓ Probar acceso a API y Web

**⏱️ Durante la ejecución**: La aplicación estará inaccesible por 2-3 minutos.

---

### **Paso 5: Verificación Post-Migración** (5 minutos)

```bash
# En producción

# 5.1 Ver contenedores nuevos corriendo
docker ps
# Debes ver: octavios-prod-web, octavios-prod-api, octavios-prod-mongodb, octavios-prod-redis

# 5.2 Ver contenedores antiguos detenidos
docker ps -a | grep copilotos-prod
# Debes ver contenedores con status "Exited"

# 5.3 Verificar health de servicios
docker ps --format "table {{.Names}}\t{{.Status}}"
# Todos deben mostrar "(healthy)"

# 5.4 Probar API
curl http://localhost:8001/api/health
# Debe responder: {"status":"ok",...}

# 5.5 Probar Web
curl -I http://localhost:3000
# Debe responder: HTTP/1.1 200 OK

# 5.6 Verificar logs de API
docker logs --tail 50 octavios-prod-api
# No debe haber errores críticos

# 5.7 Verificar logs de Web
docker logs --tail 50 octavios-prod-web
# No debe haber errores críticos

# 5.8 Verificar datos de MongoDB
docker exec octavios-prod-mongodb mongosh \
  --eval "db.adminCommand('ping')"
# Debe responder: { ok: 1 }

# 5.9 Probar login en la aplicación
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"demo","password":"Demo1234"}'
# Debe devolver un token de acceso
```

**✓ CHECKPOINT**: Todos los servicios healthy, API y Web responden, datos accesibles.

---

### **Paso 6: Pruebas de Usuario** (10 minutos)

```bash
# Acceder desde navegador
http://YOUR_SERVER_IP:3000
```

**Probar funcionalidad**:
- ✓ Login con usuario existente
- ✓ Ver conversaciones anteriores (datos preservados)
- ✓ Crear nueva conversación
- ✓ Enviar mensaje al chat
- ✓ Subir archivo (si feature está habilitada)
- ✓ Ver historial de investigaciones

**✓ CHECKPOINT**: Aplicación funciona completamente, datos intactos.

---

### **Paso 7: Actualizar Nginx (si aplica)** (2 minutos)

Si usas Nginx como reverse proxy:

```bash
# En producción
sudo vim /etc/nginx/sites-available/copilotos

# Cambiar referencias de puertos si es necesario
# (los puertos NO cambiaron, sólo nombres de containers)

# No es necesario cambiar nada si usas localhost:3000 y localhost:8001
# Los puertos siguen siendo los mismos

# Recargar nginx por si acaso
sudo nginx -t
sudo systemctl reload nginx
```

---

### **Paso 8: Limpieza (Después de 24-48h)** (2 minutos)

**IMPORTANTE**: Espera 24-48 horas antes de este paso para confirmar que todo funciona.

```bash
# En producción

# 8.1 Verificar que todo sigue funcionando bien
docker ps
curl http://localhost:8001/api/health

# 8.2 Eliminar contenedores antiguos
docker rm -f copilotos-prod-web \
             copilotos-prod-api \
             copilotos-prod-mongodb \
             copilotos-prod-redis

# 8.3 Verificar que sólo quedan los nuevos
docker ps
# Sólo debe mostrar octavios-prod-*

# 8.4 (Opcional) Limpiar volúmenes huérfanos
docker volume prune
# CUIDADO: Esto elimina volúmenes no usados
```

---

## 🔄 Plan de Rollback (Si algo falla)

Si la migración falla o hay problemas, ejecuta:

```bash
# ROLLBACK RÁPIDO

# 1. Detener contenedores nuevos
cd ~/copilotos-bridge/infra
docker compose -f docker-compose.yml --env-file ../envs/.env.prod down

# 2. Reiniciar contenedores antiguos
docker start copilotos-prod-mongodb
docker start copilotos-prod-redis
sleep 5
docker start copilotos-prod-api
docker start copilotos-prod-web

# 3. Verificar
docker ps
curl http://localhost:8001/api/health

# 4. Investigar problema
docker logs copilotos-prod-api
docker logs copilotos-prod-web
```

**Ventana de rollback**: Los contenedores antiguos se conservan por 48 horas.

---

## 📊 Checklist de Verificación Final

Después de la migración, verifica:

- [ ] Todos los contenedores octavios-prod-* están corriendo
- [ ] Health checks pasan (docker ps muestra "healthy")
- [ ] API responde en http://localhost:8001/api/health
- [ ] Web responde en http://localhost:3000
- [ ] Usuario puede hacer login
- [ ] Conversaciones anteriores están visibles
- [ ] Se pueden crear nuevas conversaciones
- [ ] No hay errores en logs (docker logs octavios-prod-api)
- [ ] MongoDB tiene datos (docker exec octavios-prod-mongodb mongosh)
- [ ] Redis está operacional (docker exec octavios-prod-redis redis-cli ping)

---

## 🆘 Solución de Problemas

### Problema: Contenedores no inician

```bash
# Ver logs
docker logs octavios-prod-api
docker logs octavios-prod-mongodb

# Verificar puertos libres
sudo netstat -tulpn | grep -E "3000|8001|27017|6379"

# Verificar volúmenes
docker volume ls
docker volume inspect copilotos-bridge_mongodb_data
```

### Problema: Base de datos vacía

```bash
# Verificar que el volumen se montó correctamente
docker inspect octavios-prod-mongodb | grep -A 10 "Mounts"

# Restaurar desde backup si es necesario
docker exec octavios-prod-mongodb mongorestore \
  /data/backup-pre-rename-YYYYMMDD-HHMMSS
```

### Problema: Health checks fallan

```bash
# Esperar más tiempo (hasta 2 minutos)
watch -n 5 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Si persiste, revisar logs
docker logs --tail 100 octavios-prod-api
```

---

## 📞 Contacto y Soporte

Si encuentras problemas:

1. Revisa los logs detalladamente
2. Consulta la sección de troubleshooting
3. Si es crítico, ejecuta el rollback inmediatamente
4. Documenta el error para debugging posterior

---

## ✅ Resumen Ejecutivo

**Antes de empezar**:
- Backups completos ✓
- Código actualizado ✓
- Ventana de mantenimiento ✓

**Durante migración** (3 min):
- Detener contenedores antiguos
- Iniciar contenedores nuevos
- Verificar health checks

**Después**:
- Pruebas funcionales completas
- Monitoreo por 48 horas
- Limpieza de contenedores antiguos

**Rollback disponible**: Sí, en cualquier momento antes de eliminar contenedores antiguos.

---

**Fecha de creación**: 2025-10-21
**Autor**: Claude (Anthropic)
**Versión**: 1.0
