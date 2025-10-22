# 📋 Pre-Migration Checklist: copilotos → octavios

**Target Date**: ___________________
**Executed By**: ___________________  
**Started At**: ___________________

---

## ✅ Phase 1: Local Preparation (COMPLETED ✓)

- [x] Migración local completada y testeada
- [x] Contenedores octavios-* funcionando localmente
- [x] Sistema de backups automáticos implementado
- [x] Scripts validados y documentados
- [x] Workflow de GitHub Actions actualizado
- [x] Tests de backups pasando (scripts/test-backup-system.sh)
- [x] Archivos `.env.example` actualizados
- [x] CLAUDE.md documentado
- [x] Auto-deploy deshabilitado (manual workflow_dispatch)
- [x] UI branding actualizado (CopilotOS → OctaviOS Chat)

**Commits**:
- 9ff759d (feat: add automatic data backups)
- 456a83f (fix(ci-cd): change deployment to manual-only trigger)
- 8c4031a (chore(web): update branding from CopilotOS to OctaviOS Chat)

**Branch**: develop

---

## ✅ Phase 2: Pre-Migration Verification (COMPLETED ✓)

### 2.1 Local Testing
```bash
# Verificar que local está funcionando
- [x] make dev → todos los contenedores healthy ✓
- [x] make test-all → tests passing (script faltante, tests individuales OK)
- [x] ./scripts/test-backup-system.sh → backups working (884K total)
```

### 2.2 Code Review
```bash
# Revisar cambios antes de push a main
- [x] git diff main develop | less
- [x] grep -r "copilotos" . --exclude-dir=node_modules --exclude-dir=.git
- [x] No quedan referencias críticas a "copilotos"
  ✓ package.json actualizado: octavios-bridge
  ✓ Makefile: referencias correctas (cleanup de contenedores viejos)
  ✓ Tests legacy pueden actualizarse post-migración
```

### 2.3 GitHub Actions Check
```bash
- [x] .github/workflows/ci-cd.yml actualizado a octavios_user (líneas 130, 169)
- [x] No hay secretos hardcodeados en workflows (solo test_password para CI)
- [x] Workflow triggers configurados correctamente (workflow_dispatch línea 8, 350)
```

**Commits**:
- 8d0acae (chore: update project name from copilotos-bridge to octavios-bridge)

---

## 🔄 Phase 3: Repository Sync (TODO)

### 3.1 Merge to Main
```bash
cd ~/Proyects/copilotos-bridge

# Revisar estado
- [ ] git status → working tree clean
- [ ] git log develop --oneline -5 → commits correctos

# Merge
- [ ] git checkout main
- [ ] git pull origin main → sync con remote
- [ ] git merge develop → merge local
- [ ] Resolver conflictos si hay
- [ ] git push origin main → subir cambios
```

### 3.2 Verify GitHub Actions
```bash
# Esperar a que GitHub Actions termine
- [ ] Ir a github.com/tu-repo/actions
- [ ] Verificar que workflow pasó (✓ green check)
- [ ] Confirmar que tests pasaron (backend, frontend, integration)
```

**⚠️ IMPORTANTE - Auto-Deploy Deshabilitado**:
- ✅ El job `deploy_tar` ahora requiere trigger MANUAL (`workflow_dispatch`)
- ✅ Push a main ejecutará SOLO tests, NO deployment
- ✅ Deployment se ejecutará manualmente después de backups verificados
- Commit: 456a83f (fix(ci-cd): change deployment to manual-only trigger)

---

## 🔒 Phase 4: Production Server Preparation (TODO)

### 4.1 Connect to Server
```bash
- [ ] ssh jf@copilot → connection successful
- [ ] whoami → confirmar usuario correcto
- [ ] pwd → /home/jf
```

### 4.2 Verify Current State
```bash
cd ~/copilotos-bridge

# Estado actual
- [ ] docker ps | grep copilotos-prod → 4 containers running
- [ ] docker ps --format "{{.Names}}: {{.Status}}" → all healthy
- [ ] curl http://localhost:8001/api/health → {"status":"ok"}
- [ ] curl -I http://localhost:3000 → HTTP 200
```

### 4.3 Check Disk Space
```bash
- [ ] df -h / → at least 10GB free
- [ ] df -h /home → at least 5GB free
- [ ] du -sh ~/copilotos-bridge → tamaño actual
- [ ] du -sh /var/lib/docker/volumes → tamaño volúmenes
```

### 4.4 Document Current Setup
```bash
# Guardar configuración actual
- [ ] docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" > /tmp/containers-before-migration.txt
- [ ] docker volume ls > /tmp/volumes-before-migration.txt
- [ ] docker images | grep copilotos > /tmp/images-before-migration.txt
- [ ] env | grep -E "MONGO|REDIS|COMPOSE" > /tmp/env-before-migration.txt (be careful with passwords!)
```

---

## 💾 Phase 5: Manual Pre-Migration Backup (CRITICAL)

### 5.1 Create Backup Directory
```bash
- [ ] BACKUP_DIR=~/backups/pre-migration-$(date +%Y%m%d-%H%M%S)
- [ ] mkdir -p $BACKUP_DIR
- [ ] echo $BACKUP_DIR → anotar ubicación
```

### 5.2 Backup MongoDB
```bash
cd ~/copilotos-bridge
- [ ] make backup-mongodb-prod
- [ ] ls -lh ~/backups/ | tail -5 → verify backup exists
- [ ] du -sh ~/backups/* | tail -1 → verify size > 0
```

### 5.3 Backup Docker Volumes
```bash
- [ ] make backup-volumes
- [ ] ls -lh ~/backups/ | tail -10 → verify both backups
```

### 5.4 Backup Environment Files
```bash
- [ ] cp envs/.env.prod $BACKUP_DIR/env.prod.backup
- [ ] cp envs/.env.prod.example $BACKUP_DIR/env.prod.example.backup (optional)
- [ ] ls -la $BACKUP_DIR → verify files copied
```

### 5.5 Verify Backups
```bash
- [ ] cat ~/backups/*/backup.log → check for errors
- [ ] du -sh $BACKUP_DIR → should be several MB
- [ ] tar -tzf $BACKUP_DIR/../*mongodb*.tar.gz | head → verify contents
```

**⚠️ CHECKPOINT**: Do NOT proceed until all backups are verified!

---

## 📥 Phase 6: Code Update on Server (TODO)

### 6.1 Git Pull
```bash
cd ~/copilotos-bridge

# Stash local changes if any
- [ ] git status → check for uncommitted changes
- [ ] git stash → if needed

# Pull from main
- [ ] git checkout main
- [ ] git pull origin main
- [ ] git log -1 --oneline → verify latest commit
- [ ] git log --oneline -5 → review recent commits
```

### 6.2 Verify Updated Files
```bash
- [ ] grep "octavios" infra/docker-compose.yml | head -3 → should show octavios
- [ ] grep "octavios" Makefile | head -2 → should show octavios
- [ ] grep "octavios" scripts/migrate-prod-to-octavios.sh | head -1 → file exists
```

### 6.3 Update Production .env
```bash
# CRITICAL: Update envs/.env.prod manually
- [ ] vim envs/.env.prod
- [ ] Change: COMPOSE_PROJECT_NAME=octavios
- [ ] Change: MONGODB_USER=octavios_prod_user (or octavios_user)
- [ ] Change: MONGODB_DATABASE=octavios
- [ ] Change: OTEL_SERVICE_NAME=octavios-bridge-prod
- [ ] Verify MONGODB_PASSWORD is set (don't change if working)
- [ ] Verify REDIS_PASSWORD is set (don't change if working)
- [ ] Save and exit
```

### 6.4 Verify .env.prod
```bash
- [ ] cat envs/.env.prod | grep COMPOSE_PROJECT_NAME → should be octavios
- [ ] cat envs/.env.prod | grep MONGODB_USER → should be octavios_*
- [ ] cat envs/.env.prod | grep MONGODB_DATABASE → should be octavios
- [ ] cat envs/.env.prod | grep OTEL_SERVICE_NAME → should be octavios-bridge-prod
```

---

## 🚀 Phase 7: Execute Migration (THE BIG MOMENT)

### 7.1 Final Verification Before Migration
```bash
# Triple-check everything
- [ ] Backups completed: ls -lh ~/backups/ | tail -10
- [ ] Code updated: git log -1 --format="%h %s"
- [ ] .env.prod updated: grep octavios envs/.env.prod | wc -l → should be > 0
- [ ] Disk space OK: df -h / → should have ≥10GB free
```

### 7.2 Run Migration Script
```bash
cd ~/copilotos-bridge

# Execute automated migration
- [ ] ./scripts/migrate-prod-to-octavios.sh

# During execution, script will:
  ✓ Verify prerequisites
  ✓ Verify backups exist
  ✓ Show current state
  ✓ Ask for confirmation (type "yes")
  ✓ Stop old containers (copilotos-prod-*)
  ✓ Verify volumes exist
  ✓ Start new containers (octavios-prod-*)
  ✓ Wait for health checks
  ✓ Test API and Web endpoints
  ✓ Show rollback instructions

# Expected duration: 3-5 minutes
# Expected downtime: 2-3 minutes
```

### 7.3 Monitor Migration Progress
```bash
# In another terminal (if possible):
- [ ] watch -n 2 'docker ps --format "{{.Names}}: {{.Status}}"'
```

---

## ✅ Phase 8: Post-Migration Verification (TODO)

### 8.1 Container Status
```bash
- [ ] docker ps | grep octavios-prod → 4 containers running
- [ ] docker ps --format "{{.Names}}: {{.Status}}" | grep octavios → all healthy
- [ ] docker ps -a | grep copilotos-prod → old containers stopped (NOT removed)
```

### 8.2 Service Health Checks
```bash
- [ ] curl http://localhost:8001/api/health → {"status":"ok"}
- [ ] curl -I http://localhost:3000 → HTTP 200
- [ ] docker logs --tail 50 octavios-prod-api → no critical errors
- [ ] docker logs --tail 50 octavios-prod-web → no critical errors
```

### 8.3 Database Connectivity
```bash
- [ ] docker exec octavios-prod-mongodb mongosh --eval "db.adminCommand('ping')" → { ok: 1 }
- [ ] docker exec octavios-prod-redis redis-cli ping → PONG or auth required
```

### 8.4 Data Integrity
```bash
# Verify data is accessible
- [ ] docker exec octavios-prod-mongodb mongosh octavios --eval "db.users.countDocuments()" → should match pre-migration count
- [ ] docker exec octavios-prod-mongodb mongosh octavios --eval "db.chat_sessions.countDocuments()" → should match
- [ ] docker exec octavios-prod-mongodb mongosh octavios --eval "db.messages.countDocuments()" → should match
```

### 8.5 Functional Testing
```bash
# From your browser or curl:
- [ ] Login with existing user → success
- [ ] View existing conversations → visible
- [ ] Create new conversation → works
- [ ] Send message → response received
- [ ] Upload file (if enabled) → processed correctly
```

---

## 🎉 Phase 9: Post-Migration Cleanup (WAIT 24-48 HOURS)

### 9.1 Monitor for 24-48 Hours
```bash
# Before cleanup, ensure:
- [ ] No errors in logs for 24 hours
- [ ] Users can access without issues
- [ ] No performance degradation
- [ ] All features working correctly
```

### 9.2 Cleanup Old Containers (OPTIONAL)
```bash
# After 24-48 hours of stable operation:
- [ ] Confirm everything is working: curl http://localhost:8001/api/health
- [ ] Remove old containers:
      docker rm -f copilotos-prod-web copilotos-prod-api \
                   copilotos-prod-mongodb copilotos-prod-redis
- [ ] Verify only octavios containers remain: docker ps
```

### 9.3 Cleanup Old Images (OPTIONAL)
```bash
# After cleanup of containers:
- [ ] docker images | grep copilotos → list old images
- [ ] docker rmi copilotos-web:latest copilotos-api:latest (if safe)
- [ ] docker system prune -a --volumes → careful! (interactive)
```

---

## 🆘 Rollback Procedure (IF NEEDED)

If something goes wrong during or after migration:

### Immediate Rollback (Within 48 hours)
```bash
# 1. Stop new containers
cd ~/copilotos-bridge/infra
docker compose -f docker-compose.yml --env-file ../envs/.env.prod down

# 2. Restart old containers (they were NOT removed)
docker start copilotos-prod-mongodb
docker start copilotos-prod-redis
sleep 5
docker start copilotos-prod-api
docker start copilotos-prod-web

# 3. Verify
docker ps
curl http://localhost:8001/api/health

# 4. Investigate issue
docker logs copilotos-prod-api | tail -100
```

### Data Restore (If needed)
```bash
# Find backup location
cat /tmp/last_data_backup

# Restore MongoDB (if data corruption)
cd ~/copilotos-bridge
./scripts/restore-mongodb.sh --backup-dir <backup-path>
```

---

## 📞 Emergency Contacts

- **Server**: jf@copilot
- **Backup Location**: ~/backups/pre-migration-YYYYMMDD-HHMMSS/
- **Rollback Script**: scripts/migrate-prod-to-octavios.sh (has rollback instructions)

---

## ✅ Final Checklist Summary

- [x] Phase 1: Local preparation → DONE ✓
- [x] Phase 2: Pre-migration verification → DONE ✓
- [ ] Phase 3: Repository sync → TODO (READY)
- [ ] Phase 4: Server preparation → TODO
- [ ] Phase 5: Manual backups → TODO (CRITICAL)
- [ ] Phase 6: Code update → TODO
- [ ] Phase 7: Execute migration → TODO
- [ ] Phase 8: Post-migration verification → TODO
- [ ] Phase 9: Cleanup (after 24-48h) → TODO

---

**Migration Status**: ⏸️ READY TO START  
**Last Updated**: 2025-10-21  
**Version**: 1.0
