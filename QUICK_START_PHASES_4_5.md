# 🚀 Quick Start: Phases 4 & 5 on Production Server

This guide provides **copy-paste commands** for executing Phases 4 and 5 on the production server.

**Prerequisites**:
- ✅ Phase 1 & 2 completed locally
- ✅ Phase 3 completed (merge to main)
- ✅ SSH access to production server

---

## 📍 Phase 4: Production Server Preparation

**Goal**: Verify current state of production server before migration.

### Quick Commands

```bash
# 1. Connect to production server
ssh jf@copilot

# 2. Navigate to project directory
cd ~/copilotos-bridge

# 3. Pull latest code (includes new scripts)
git fetch origin
git checkout main
git pull origin main

# 4. Run automated verification
./scripts/phase4-server-verification.sh
```

### What the script does:
- ✅ Verifies server context (user, hostname, directory)
- ✅ Checks running containers (copilotos-prod-*)
- ✅ Tests API and Web endpoints
- ✅ Analyzes disk space (needs >=10GB free)
- ✅ Documents current configuration
- ✅ Saves report to `/tmp/pre-migration-verification-YYYYMMDD-HHMMSS/`

### Expected Output:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Phase 4: Production Server Verification
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▸ 4.1 Server Context Verification
  User:     jf
  Hostname: copilot
  Directory: /home/jf/copilotos-bridge

▸ 4.2 Current Container State
  Copilotos containers running: 4
  ✓ Found 4 copilotos-prod containers

  Container health check:
    ✓ copilotos-prod-web: Up 2 days (healthy)
    ✓ copilotos-prod-api: Up 2 days (healthy)
    ✓ copilotos-prod-mongodb: Up 2 days (healthy)
    ✓ copilotos-prod-redis: Up 2 days (healthy)

  API Health Check:
    ✓ API responding: healthy

  Web Frontend Check:
    ✓ Web responding: HTTP 200

▸ 4.3 Disk Space Analysis
  / (root):     15G available (45% used)
  /home:        8.5G available (38% used)
  Project dir:  2.3G (~/copilotos-bridge)
  Docker vols:  5.1G (/var/lib/docker/volumes)
  ✓ Sufficient disk space available

▸ 4.4 Documenting Current Configuration
  Saving Docker volumes list...
    Found 4 copilotos volumes
  Saving Docker images list...
    Found 2 copilotos images
  Checking environment configuration...
    ✓ .env.prod exists
  Checking git repository status...
    Branch: main
    Commit: e2095f4 - fix(deps): update urllib3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Verification Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Review the Report:
```bash
# View the verification summary
VERIFICATION_DIR=$(ls -dt /tmp/pre-migration-verification-* | head -1)
cat $VERIFICATION_DIR/SUMMARY.txt

# List all generated files
ls -lh $VERIFICATION_DIR/
```

### Manual Verification (Optional):
If you prefer to run commands manually:

```bash
# Check containers
docker ps | grep copilotos-prod

# Check API health
curl http://localhost:8001/api/health

# Check disk space
df -h /
du -sh ~/copilotos-bridge
```

---

## 💾 Phase 5: Manual Pre-Migration Backup (CRITICAL)

**Goal**: Create comprehensive backups before migration.

⚠️ **CRITICAL**: This is your safety net. Do not skip!

### Quick Commands

```bash
# Still on production server (ssh jf@copilot)
cd ~/copilotos-bridge

# Run automated backup
./scripts/phase5-manual-backup.sh
```

### What the script does:
- ✅ Creates backup directory: `~/backups/pre-migration-YYYYMMDD-HHMMSS/`
- ✅ Backs up MongoDB database (mongodump with BSON)
- ✅ Backs up Docker volumes (MongoDB + Redis data)
- ✅ Backs up environment files (.env.prod)
- ✅ Documents container configuration
- ✅ Verifies backup integrity (minimum size checks)
- ✅ Saves backup location to `/tmp/last_data_backup`

### Expected Output:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Phase 5: Manual Pre-Migration Backup (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  CRITICAL: This backup is your safety net!
   Do not proceed without verified backups.

Backup destination: /home/jf/backups/pre-migration-20251021-230000

▸ 5.1 Creating Backup Directory
  ✓ Created: /home/jf/backups/pre-migration-20251021-230000

▸ 5.2 Backing Up MongoDB Database
  Using backup-mongodb.sh...
  ✓ MongoDB backup verified: 45M

▸ 5.3 Backing Up Docker Volumes
  Using backup-docker-volumes.sh...
  ✓ Docker volumes backed up

▸ 5.4 Backing Up Environment Configuration
  ✓ .env.prod backed up
  ✓ .env.prod.example backed up

▸ 5.5 Documenting Container Configuration
  ✓ Container list saved
  ✓ docker-compose.yml backed up
  ✓ Volume list saved

▸ 5.6 Verifying Backup Integrity
  ✓ Backup size verified: 46M

  Backup contents:
    copilotos_20251021_230000.gz (45M)
    copilotos_mongodb_data_20251021_230001.tar.gz (856K)
    copilotos_redis_data_20251021_230001.tar.gz (12K)
    env.prod.backup (2.1K)
    containers-snapshot.txt (1.2K)
    docker-compose.yml.backup (3.4K)
    volumes-snapshot.txt (543)
    backup.log (1.8K)

  ✓ Backup location saved to /tmp/last_data_backup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Pre-Migration Backup Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Backup Summary:
  Location: /home/jf/backups/pre-migration-20251021-230000
  Size: 46M
  Status: ✅ VERIFIED

What was backed up:
  ✓ MongoDB database (mongodump)
  ✓ Docker volumes (MongoDB + Redis data)
  ✓ Environment files (.env.prod)
  ✓ Container configuration

Emergency Restore:
  If migration fails, restore with:
    cd ~/copilotos-bridge
    ./scripts/restore-mongodb.sh --backup-dir /home/jf/backups/pre-migration-20251021-230000

⚠️  CHECKPOINT: Backup Complete!
   You may now proceed to Phase 6: Code Update
```

### Verify the Backup:
```bash
# Check backup location
cat /tmp/last_data_backup

# Review backup contents
BACKUP_DIR=$(cat /tmp/last_data_backup)
ls -lh $BACKUP_DIR/
du -sh $BACKUP_DIR/

# Read backup log
cat $BACKUP_DIR/backup.log
```

### Manual Backup Verification:
```bash
# Verify MongoDB backup exists and has reasonable size
ls -lh ~/backups/pre-migration-*/copilotos_*.gz

# Verify size is > 1MB (should be 10MB+ for production)
du -h ~/backups/pre-migration-*/copilotos_*.gz
```

---

## ✅ Completion Checklist

After running both scripts, verify:

**Phase 4**:
- [ ] All 4 containers running and healthy
- [ ] API responding on localhost:8001
- [ ] Web responding on localhost:3000
- [ ] At least 10GB free disk space on `/`
- [ ] Verification report saved

**Phase 5**:
- [ ] Backup directory created (check `/tmp/last_data_backup`)
- [ ] MongoDB backup > 1MB (should be much larger for production)
- [ ] Docker volumes backed up
- [ ] Environment files backed up
- [ ] Backup integrity verified (script passed all checks)

---

## 🆘 Troubleshooting

### Script Not Found
```bash
# Make sure you're on the latest main branch
cd ~/copilotos-bridge
git pull origin main

# Make scripts executable
chmod +x scripts/phase4-server-verification.sh
chmod +x scripts/phase5-manual-backup.sh
```

### Phase 4: No Containers Found
```bash
# Check if containers are running with different names
docker ps

# Check if containers are stopped
docker ps -a | grep copilotos
```

### Phase 5: Backup Too Small
```bash
# Check MongoDB container is running
docker ps | grep mongodb

# Check MongoDB has data
docker exec copilotos-prod-mongodb mongosh copilotos --eval "db.stats()"

# Run backup with debug output
./scripts/phase5-manual-backup.sh 2>&1 | tee backup-debug.log
```

### Permission Denied
```bash
# Ensure scripts are executable
chmod +x scripts/phase*.sh

# Check you're the correct user
whoami  # Should be: jf
```

---

## 🚀 Next Steps

After completing Phases 4 & 5:

1. **Review PRE_MIGRATION_CHECKLIST.md** - Mark phases as complete
2. **Proceed to Phase 6**: Code Update on Server
3. **Then Phase 7**: Execute Migration (run `scripts/migrate-prod-to-octavios.sh`)

---

## 📞 Emergency Contacts

If something goes wrong:
- **Backup Location**: `cat /tmp/last_data_backup`
- **Restore Command**: `./scripts/restore-mongodb.sh --backup-dir <backup-path>`
- **Rollback**: Keep old containers stopped (don't remove!) for 48 hours

---

**Last Updated**: 2025-10-21
**For**: copilotos → octavios migration
