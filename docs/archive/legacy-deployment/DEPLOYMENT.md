# 🚀 Secure Production Deployment Guide

> **⚡ TL;DR**: For fastest deployment, see [QUICK-DEPLOY.md](QUICK-DEPLOY.md) (3-5 minutes)

## 🔒 Security Notice
⚠️ **SECURITY UPDATE**: This system has been hardened with comprehensive secrets management. All hardcoded credentials have been **REMOVED** and replaced with secure configuration.

## 📋 Overview
This system operates in **production mode only** with mandatory security requirements:
- **Zero hardcoded credentials** ✅
- **Secure secrets management** ✅
- **Encrypted credential storage** ✅
- **Fail-fast security validation** ✅

## 🎯 Quick Deployment Options

| Command | Time | Best For |
|---------|------|----------|
| `make deploy-quick` | 3-5 min | Daily deployments (incremental build) |
| `make deploy-tar-fast` | 2-3 min | Redeploy existing images |
| `make deploy-tar` | 8-12 min | Major updates (clean build) |



## 🐳 Docker Registry Deployment (Recommended)

### Why Use Docker Registry?
- **Efficiency**: No need to build on production servers
- **Consistency**: Same images across all environments
- **Speed**: Pull images instead of building (~2-3 min vs ~10-15 min)
- **Rollback**: Easy version management with tags

### 🎯 Quick Start (Using Scripts)

We provide automated scripts for easy deployment:

```bash
# === LOCAL MACHINE ===
# Build and push to registry
./scripts/push-to-registry.sh

# === PRODUCTION SERVER ===
ssh your_user@34.42.214.246
cd /home/your_user/copilotos-bridge
./scripts/deploy-from-registry.sh
```

📚 **See [scripts/README-DEPLOY.md](../scripts/README-DEPLOY.md) for complete guide**

### Quick Deploy Commands

#### 1. Build and Push to Registry (Local Machine)
```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Build images locally
cd infra
docker compose -f docker-compose.yml build --no-cache

# Tag images for registry
docker tag copilotos-api:latest ghcr.io/jazielflo/copilotos-bridge/api:latest
docker tag copilotos-web:latest ghcr.io/jazielflo/copilotos-bridge/web:latest

# Optional: Tag with version/commit
export VERSION=$(git rev-parse --short HEAD)
docker tag copilotos-api:latest ghcr.io/jazielflo/copilotos-bridge/api:$VERSION
docker tag copilotos-web:latest ghcr.io/jazielflo/copilotos-bridge/web:$VERSION

# Push to registry
docker push ghcr.io/jazielflo/copilotos-bridge/api:latest
docker push ghcr.io/jazielflo/copilotos-bridge/web:latest
docker push ghcr.io/jazielflo/copilotos-bridge/api:$VERSION
docker push ghcr.io/jazielflo/copilotos-bridge/web:$VERSION
```

#### 2. Deploy on Production Server
```bash
# SSH to production
ssh your_user@34.42.214.246

# Navigate to project
cd /home/your_user/copilotos-bridge

# Pull latest code
git pull origin main

# Login to registry (if private)
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull latest images
docker pull ghcr.io/jazielflo/copilotos-bridge/api:latest
docker pull ghcr.io/jazielflo/copilotos-bridge/web:latest

# Tag locally (docker-compose expects copilotos-api/web names)
docker tag ghcr.io/jazielflo/copilotos-bridge/api:latest copilotos-api:latest
docker tag ghcr.io/jazielflo/copilotos-bridge/web:latest copilotos-web:latest

# Restart services
cd infra
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up -d

# Verify deployment
docker ps
curl -sS http://localhost:8001/api/health | jq '.'
```

### One-Liner Deploy Script
```bash
#!/bin/bash
# Quick production deploy from registry
set -e

echo "🚀 Deploying from Docker Registry..."

# Pull latest images
docker pull ghcr.io/your_user/copilotos-bridge/api:latest
docker pull ghcr.io/your_user/copilotos-bridge/web:latest

# Tag for local use
docker tag ghcr.io/your_user/copilotos-bridge/api:latest copilotos-api:latest
docker tag ghcr.io/your_user/copilotos-bridge/web:latest copilotos-web:latest

# Restart services
cd infra
docker compose down
docker compose up -d

# Health check
sleep 10
curl -sS http://localhost:8001/api/health || echo "⚠️  API not ready yet"

echo "✅ Deploy complete!"
```

### Rollback to Previous Version
```bash
# List available versions
docker images ghcr.io/your_user/copilotos-bridge/api

# Pull specific version
export VERSION=abc1234
docker pull ghcr.io/your_user/copilotos-bridge/api:$VERSION
docker pull ghcr.io/your_user/copilotos-bridge/web:$VERSION

# Tag and deploy
docker tag ghcr.io/your_user/copilotos-bridge/api:$VERSION copilotos-api:latest
docker tag ghcr.io/your_user/copilotos-bridge/web:$VERSION copilotos-web:latest

cd infra && docker compose down && docker compose up -d
```

### Alternative: tar File Transfer (No Registry Access)
```bash
# === LOCAL MACHINE ===
# Build images
cd infra && docker compose -f docker-compose.yml build --no-cache

# Export to tar
docker save copilotos-api:latest -o copilotos-api.tar
docker save copilotos-web:latest -o copilotos-web.tar

# Transfer to server
scp copilotos-api.tar jf@34.42.214.246:/home/your_user/copilotos-bridge/
scp copilotos-web.tar jf@34.42.214.246:/home/your_user/copilotos-bridge/

# === PRODUCTION SERVER ===
ssh your_user@34.42.214.246
cd /home/your_user/copilotos-bridge

# Import images
docker load -i copilotos-api.tar
docker load -i copilotos-web.tar

# Restart services
cd infra && docker compose down && docker compose up -d

# Cleanup
rm -f copilotos-api.tar copilotos-web.tar
```

## 🔑 SAPTIVA API Key Configuration

### 🔐 Secure Configuration Methods

**⚠️ SECURITY WARNING: Never use hardcoded credentials!**

#### Method 1: Docker Secrets (Production Recommended)
```bash
# 1. Generate secure secrets
python3 scripts/generate-secrets.py

# 2. Setup Docker secrets
./scripts/setup-docker-secrets.sh

# 3. Deploy securely
docker stack deploy -c docker-compose.secure.yml copilotos
```

#### Method 2: Environment Variables (Development Only)
```bash
# Generate secure values first!
export SAPTIVA_API_KEY=your-saptiva-api-key-here
export MONGODB_PASSWORD=$(openssl rand -base64 32)
export JWT_SECRET_KEY=$(openssl rand -hex 32)
export SECRET_KEY=$(openssl rand -hex 32)
```

### Security Priority Order
1. **Docker Secrets** (/run/secrets/) - HIGHEST SECURITY
2. **Environment Variables** - MEDIUM SECURITY
3. **Secure Files** (/etc/copilotos/secrets/) - HIGH SECURITY
4. **Admin UI** - For API key management only

## ⚙️ Deployment Steps

### 1. Environment Variables
Ensure `SAPTIVA_API_KEY` is set in your deployment environment:
```bash
# For Docker
export SAPTIVA_API_KEY=your-key
docker-compose up

# For Kubernetes
kubectl create secret generic saptiva-secret \
  --from-literal=SAPTIVA_API_KEY=your-key

# For other platforms
# Add SAPTIVA_API_KEY to your environment variables
```

### 2. Verify Configuration
After deployment, check the API key status:
```bash
# Health check
curl http://your-domain/api/health

# Key status (requires authentication)
curl -H "Authorization: Bearer YOUR_JWT" \
     http://your-domain/api/settings/saptiva-key
```

Expected response:
```json
{
  "configured": true,
  "mode": "live",
  "source": "environment" | "database",
  "hint": "••••hc_A",
  "status_message": "API key configured"
}
```

## 🔄 Automatic Loading
- API key is loaded automatically on startup
- Database configuration overrides environment variables
- System validates connectivity with SAPTIVA servers
- No manual intervention required after deployment

## ❌ Breaking Changes
- **Removed**: All mock/demo response functionality
- **Removed**: Fallback responses when API fails
- **Changed**: System fails fast if API key is missing
- **Changed**: All responses now come directly from SAPTIVA

## 🛡️ Security Notes
- API keys are encrypted when stored in database
- Environment variables should use secure secret management
- Key hints are shown as `••••last4` for privacy
- Keys are never logged in plaintext

## ⚠️ Common Deployment Pitfalls

### 0. TypeScript Build Errors (CRITICAL - NEW)

**Problem**: Code with TypeScript errors can pass to `main` branch and cause production build failures. Development builds may work locally but production builds with strict type checking fail.

**Real Example** (2025-10-16):
```typescript
// ChatView.tsx - Sending metadata that doesn't match ChatRequest type
const response = await apiClient.sendChatMessage({
  message: msg,
  metadata: userMessageMetadata,  // ❌ Type mismatch!
});

// userMessageMetadata was:
{
  file_ids: fileIds,        // ❌ NOT in ChatRequest.metadata type
  files: [{
    bytes: 123,             // ❌ Should be "size"
    mimetype: "text/pdf",   // ❌ Should be "mime_type"
    pages: 5                // ❌ NOT in ChatRequest.metadata type
  }]
}

// ChatRequest expects:
metadata?: {
  files?: Array<{
    file_id: string;
    filename: string;
    size: number;         // ✅ NOT "bytes"
    mime_type: string;    // ✅ NOT "mimetype"
  }>;
};
```

**Impact**:
- ❌ Production build fails: `tsc` compilation errors
- ❌ 18 minutes of build time wasted
- ❌ Deployment blocked completely
- ⚠️ Dev mode works locally (hot-reload skips type checking)

**Root Causes**:
1. Code committed without running production build locally
2. No pre-commit hooks to validate TypeScript
3. Type definitions updated but usages not refactored
4. Dev environment doesn't enforce strict type checking

**Prevention Checklist**:

```bash
# ✅ MANDATORY: Always run production build BEFORE committing to main
cd apps/web
pnpm build

# If this fails, DO NOT commit! Fix type errors first.
```

**Pre-Commit Hook** (Recommended):
Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
echo "🔍 Running TypeScript build check..."
cd apps/web
pnpm build

if [ $? -ne 0 ]; then
  echo "❌ TypeScript build failed! Fix errors before committing."
  exit 1
fi

echo "✅ TypeScript build passed"
```

```bash
# Make it executable
chmod +x .git/hooks/pre-commit
```

**Type Validation Strategy**:

1. **When modifying shared types** (interfaces, schemas):
   ```bash
   # Find all usages before changing
   grep -r "ChatRequest" apps/web/src --include="*.ts" --include="*.tsx"
   grep -r "metadata" apps/web/src --include="*.ts" --include="*.tsx"
   ```

2. **After type changes**:
   ```bash
   # Full rebuild to catch type errors
   cd apps/web
   rm -rf .next
   pnpm build
   ```

3. **Verify build artifacts**:
   ```bash
   # Check that build output includes all expected files
   ls -lh apps/web/.next/static/chunks/
   ```

**Quick Fix for Production**:
If you're blocked in production with type errors:

```bash
# Option A: Fix types to match interface
# Edit the file and align property names

# Option B: Use type assertion (NOT recommended, but unblocks)
metadata: userMessageMetadata as any,  // ⚠️ Bypasses type checking

# Option C: Rollback to last working version
docker images | grep backup-  # Find backup tag
docker tag copilotos-web:backup-20251016-012345 copilotos-web:latest
docker compose up -d web
```

**Detection in CI/CD**:
```yaml
# .github/workflows/validate-types.yml
name: TypeScript Validation
on: [push, pull_request]
jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: pnpm/action-setup@v2
      - name: Install dependencies
        run: cd apps/web && pnpm install
      - name: TypeScript Build
        run: cd apps/web && pnpm build
```

**Related Files to Check**:
- `apps/web/src/lib/api-client.ts` - Type definitions
- `apps/web/src/app/chat/_components/ChatView.tsx` - Usage
- `apps/web/tsconfig.json` - TypeScript configuration
- `apps/web/next.config.js` - Build configuration

### 0.1. Missing Files in Git Repository (CRITICAL - NEW)

**Problem**: Files exist locally but were never pushed to remote repository. Production deployments fail with "Module not found" errors.

**Real Example** (2025-10-16):
```bash
# Error during build
Module not found: Can't resolve '../lib/stores/files-store'

# Investigation
git ls-tree origin/main apps/web/src/lib/stores/
# ❌ files-store.ts NOT in remote repository

ls apps/web/src/lib/stores/files-store.ts
# ✅ EXISTS locally
```

**Impact**:
- ❌ Production build fails: Missing module dependency
- ⚠️ Works locally because file exists in working directory
- 🔄 Requires manual file copy as workaround

**Root Causes**:
1. File was created but never added to git
2. File in `.gitignore` (check patterns)
3. `git add` skipped by mistake
4. Commit made from subdirectory without full `git add`

**Prevention Checklist**:

```bash
# ✅ MANDATORY: Before deploying, verify all files are in remote
git status  # Check for untracked files

# Verify new files are in remote
git ls-tree origin/main apps/web/src/lib/stores/

# Check for missing dependencies
git diff --name-only origin/main HEAD

# Search for uncommitted TypeScript/JavaScript files
git ls-files --others --exclude-standard | grep -E '\.(ts|tsx|js|jsx)$'
```

**Detection Strategy**:

1. **After creating new files**:
   ```bash
   # Immediately add to git
   git add apps/web/src/lib/stores/files-store.ts
   git commit -m "feat: add files store for persistence"
   git push origin main

   # Verify it's in remote
   git ls-tree origin/main apps/web/src/lib/stores/ | grep files-store
   ```

2. **Before production deployment**:
   ```bash
   # Compare local and remote file lists
   diff <(git ls-files | sort) <(git ls-tree -r origin/main --name-only | sort)
   ```

3. **In deployment script**:
   ```bash
   #!/bin/bash
   # Check for critical imports that might be missing
   MISSING_FILES=$(git diff --name-only origin/main HEAD | grep -E '\.(ts|tsx)$')
   if [ -n "$MISSING_FILES" ]; then
     echo "⚠️  Warning: New TypeScript files not in remote:"
     echo "$MISSING_FILES"
     read -p "Continue deployment? (y/N) " -n 1 -r
     echo
     if [[ ! $REPLY =~ ^[Yy]$ ]]; then
       exit 1
     fi
   fi
   ```

**Quick Fix for Production**:
If blocked in production with missing files:

```bash
# Option A: Emergency file copy (TEMPORARY)
scp local/path/to/file.ts user@prod:/path/to/project/
# Then rebuild image

# Option B: Commit and push properly (RECOMMENDED)
git add apps/web/src/lib/stores/files-store.ts
git commit -m "fix: add missing files-store.ts to repository"
git push origin main
# Then deploy normally

# Option C: Rollback
docker tag copilotos-web:backup-YYYYMMDD-HHMMSS copilotos-web:latest
docker compose up -d web
```

**`.gitignore` Audit**:
```bash
# Check if your pattern is too broad
cat .gitignore | grep -E 'stores|lib'

# Common culprits:
# *.ts         # ❌ TOO BROAD - ignores ALL TypeScript
# /lib         # ❌ TOO BROAD - ignores library code
# *-store.ts   # ❌ Might ignore state management files

# Better patterns:
# *.test.ts    # ✅ Only test files
# /lib/cache   # ✅ Specific cache directory
```

### 0.2. SECRET_KEY Validation Failures (MEDIUM - NEW)

**Problem**: New code enforces stricter secret validation. Production secrets that worked before now fail validation.

**Real Example** (2025-10-16):
```python
# New validation in code
SecretValidationError: Secret 'SECRET_KEY' too short (minimum 32 characters)

# Production had:
SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w  # 45 chars

# Validation expects:
# - Minimum 32 characters
# - Proper entropy (random generation)
```

**Impact**:
- ❌ API container fails to start
- ❌ Crash loop with validation error
- ⚠️ Even valid-looking keys can fail if format is wrong

**Root Causes**:
1. Validation requirements tightened in new code
2. Production secrets generated with old method
3. No validation when secrets were originally created
4. Missing `.env.example` with requirements documentation

**Prevention Strategy**:

1. **Document Secret Requirements** in `.env.example`:
   ```bash
   # .env.example
   # SECRET_KEY: Used for session encryption (REQUIRED)
   # - MUST be at least 32 characters
   # - Generate with: openssl rand -hex 32
   SECRET_KEY=__REPLACE_WITH_64_CHARS__

   # JWT_SECRET_KEY: Used for JWT token signing (REQUIRED)
   # - MUST be at least 32 characters
   # - Generate with: openssl rand -hex 32
   JWT_SECRET_KEY=__REPLACE_WITH_64_CHARS__
   ```

2. **Validate Before Deployment**:
   ```bash
   # scripts/validate-secrets.sh
   #!/bin/bash
   source envs/.env

   if [ ${#SECRET_KEY} -lt 32 ]; then
     echo "❌ SECRET_KEY too short: ${#SECRET_KEY} chars (minimum 32)"
     exit 1
   fi

   if [ ${#JWT_SECRET_KEY} -lt 32 ]; then
     echo "❌ JWT_SECRET_KEY too short: ${#JWT_SECRET_KEY} chars (minimum 32)"
     exit 1
   fi

   echo "✅ Secrets validation passed"
   ```

3. **Generate Proper Secrets**:
   ```bash
   # ✅ CORRECT: Use cryptographically secure random
   openssl rand -hex 32  # Generates 64 hex characters

   # ❌ WRONG: Predictable or short
   echo "mypassword123"
   date | md5sum
   ```

4. **Update Production Secrets Safely**:
   ```bash
   # 1. Generate new secrets
   NEW_SECRET=$(openssl rand -hex 32)
   NEW_JWT=$(openssl rand -hex 32)

   # 2. Update .env file
   sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${NEW_SECRET}/" envs/.env
   sed -i "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=${NEW_JWT}/" envs/.env

   # 3. Restart services
   docker compose down
   docker compose --env-file envs/.env up -d

   # 4. Test immediately
   curl -f http://localhost:8001/api/health || echo "❌ API failed to start"
   ```

**Quick Fix for Production**:
```bash
# If API is crash-looping due to SECRET_KEY validation:

# 1. Check current length
echo -n "$SECRET_KEY" | wc -c

# 2. Generate compliant key
openssl rand -hex 32 > /tmp/new_secret_key.txt

# 3. Update and restart
export SECRET_KEY=$(cat /tmp/new_secret_key.txt)
docker compose restart api

# 4. Persist to .env file
echo "SECRET_KEY=$(cat /tmp/new_secret_key.txt)" >> envs/.env
```

**Detection in Logs**:
```bash
# Look for validation errors
docker logs infra-api 2>&1 | grep -i "secret\|validation"

# Example error patterns:
# - "SecretValidationError"
# - "too short"
# - "minimum 32 characters"
# - "invalid format"
```

### 1. MongoDB Authentication Failures

**Problem**: Silent authentication failures that cause API to crash loop with generic "Authentication failed" errors.

**Root Cause**: Password mismatch between:
- MongoDB initialization (`MONGO_INITDB_ROOT_PASSWORD` in docker-compose)
- API connection string (`MONGODB_PASSWORD` environment variable)

**Prevention**:
```bash
# ✅ ALWAYS ensure infra/.env is the single source of truth
# Verify passwords match before deployment:
cd infra
docker compose config | grep -E "(MONGODB_PASSWORD|MONGO_INITDB)"

# If passwords differ, fix infra/.env and recreate volumes:
docker compose down -v
docker compose up -d
```

**Detection**: The API now includes improved error logging (v1.2.1+) that shows:
- Username being used
- Host and database
- AuthSource configuration
- Specific troubleshooting hints
- Password mismatch detection

**Example error log** (improved in v1.2.1+):
```json
{
  "event": "❌ MongoDB Connection Failed - AUTHENTICATION ERROR",
  "error_type": "OperationFailure",
  "error_code": 18,
  "connection_details": {
    "username": "copilotos_user",
    "host": "mongodb:27017",
    "database": "copilotos",
    "auth_source": "admin"
  },
  "troubleshooting_hints": [
    "Check that MONGODB_PASSWORD in infra/.env matches docker-compose initialization",
    "Verify MongoDB container initialized with same password",
    "If password changed, recreate volumes: docker compose down -v"
  ]
}
```

### 2. Docker Image Verification

**Problem**: Deployed images don't contain latest code changes.

**Root Cause**: Using cached images or forgetting to rebuild after code changes.

**Prevention**:
```bash
# ✅ ALWAYS verify image contents before deployment
docker run --rm copilotos-api:latest cat /app/src/models/chat.py | head -20
docker run --rm copilotos-web:latest cat /app/apps/web/src/components/chat/ModelSelector.tsx | grep -A 5 "currentModel"

# If outdated, rebuild without cache:
cd infra
docker compose build --no-cache api web
```

### 3. Environment Variable Synchronization

**Problem**: Different password values in multiple files cause confusion.

**Solution**: Use `infra/.env` as single source of truth:

```bash
# ✅ Correct structure:
# infra/.env (source of truth)
MONGODB_PASSWORD=SecureMongoProd2024!Change
REDIS_PASSWORD=SecureRedisProd2024!Change

# docker-compose.yml references it:
environment:
  MONGO_INITDB_ROOT_PASSWORD: ${MONGODB_PASSWORD:-secure_password_change_me}

# API uses same password via connection string:
MONGODB_URL: mongodb://${MONGODB_USER}:${MONGODB_PASSWORD}@mongodb:27017/${MONGODB_DATABASE}?authSource=admin
```

### 4. Volume Persistence Issues

**Problem**: Database retains old initialization with different password.

**Solution**: Always recreate volumes when changing passwords:
```bash
# ❌ WRONG: Restart without recreating volumes
docker compose restart

# ✅ CORRECT: Recreate volumes to apply new password
docker compose down -v
docker compose up -d
```

⚠️ **WARNING**: `-v` flag deletes all data. Only use in development or after backup.

## 🧪 Pre-Deployment Checklist

Before deploying to production, **ALWAYS** complete ALL these checks:

### 1. TypeScript Build Validation (CRITICAL - NEW)
```bash
# ✅ MANDATORY: This catches 90% of production issues
cd apps/web
pnpm build

# If this fails, DO NOT deploy! Fix errors first.
# Common failures:
# - Type mismatches in API calls
# - Missing properties in interfaces
# - Import errors for missing files
```

### 2. Git Repository Integrity (CRITICAL - NEW)
```bash
# Check for untracked files
git status

# Verify all new TypeScript/JavaScript files are committed
git ls-files --others --exclude-standard | grep -E '\.(ts|tsx|js|jsx)$'

# Compare local vs remote
git diff --name-only origin/main HEAD

# Verify critical files exist in remote
git ls-tree origin/main apps/web/src/lib/stores/ | grep files-store
```

### 3. Secret Validation (HIGH PRIORITY - NEW)
```bash
# Source environment variables
source envs/.env

# Validate SECRET_KEY length
if [ ${#SECRET_KEY} -lt 32 ]; then
  echo "❌ SECRET_KEY too short: ${#SECRET_KEY} chars (need 32+)"
  exit 1
fi

# Validate JWT_SECRET_KEY length
if [ ${#JWT_SECRET_KEY} -lt 32 ]; then
  echo "❌ JWT_SECRET_KEY too short: ${#JWT_SECRET_KEY} chars (need 32+)"
  exit 1
fi

echo "✅ Secrets validation passed"
```

### 4. Environment Variables
```bash
# Verify all required variables are set
docker compose config | grep -E "(MONGODB|REDIS|SAPTIVA|SECRET)"

# Check for missing or placeholder values
grep -E "__REPLACE__|CHANGE_ME|TODO" envs/.env
```

### 5. Image Verification
```bash
# Build images locally first
cd infra
docker compose build --no-cache web

# Verify image contents
docker run --rm copilotos-web:latest cat /app/apps/web/package.json | grep version

# Check that new files are in the image
docker run --rm copilotos-web:latest ls -la /app/apps/web/src/lib/stores/
```

### 6. Local Testing
```bash
# Test full stack locally BEFORE deploying
cd infra
docker compose up -d
sleep 10

# Health check
curl -sS http://localhost:8001/api/health | jq '.'

# Test web frontend
curl -I http://localhost:3000

# Manual testing: Open http://localhost:3000
# - Test login
# - Send a chat message
# - Test file upload ('+' button should be visible)
# - Verify responses are not errors
```

### 7. Password Synchronization
```bash
# Verify password consistency
grep MONGODB_PASSWORD infra/.env
grep MONGO_INITDB_ROOT_PASSWORD infra/docker-compose.yml
# These should reference the same value
```

### 8. Database Backup (CRITICAL)
```bash
# ALWAYS create backup before deployment
ssh user@prod-server "
  cd /home/user/copilotos-bridge
  BACKUP_DIR=~/backups/docker-volumes
  mkdir -p \$BACKUP_DIR
  docker run --rm \
    -v copilotos-prod_mongodb_data:/data \
    -v \$BACKUP_DIR:/backup \
    alpine tar czf /backup/mongodb_pre_deploy_\$(date +%Y%m%d_%H%M%S).tar.gz -C /data .
  echo '✅ Backup created'
"

# Verify backup integrity
ssh user@prod-server "
  cd ~/backups/docker-volumes
  LATEST_BACKUP=\$(ls -t mongodb_pre_deploy_*.tar.gz | head -1)
  tar tzf \$LATEST_BACKUP | grep _mdb_catalog.wt || echo '❌ Invalid backup'
"
```

### 9. Database Migration
```bash
# Run any pending migrations
make db-migrate
```

### 10. Deployment Dry-Run (Recommended)
```bash
# Test deployment process on staging first
# Or at minimum, verify images can be built
cd infra
docker compose -f docker-compose.yml build --no-cache 2>&1 | tee build.log

# Check for errors in build log
grep -i "error\|failed" build.log && echo "❌ Build has errors" || echo "✅ Build clean"
```

### ✅ Final Checklist Summary

Print and check each item before deploying:

- [ ] `pnpm build` completed without errors
- [ ] No untracked TypeScript/JavaScript files (`git status`)
- [ ] All new files committed and pushed to `origin/main`
- [ ] SECRET_KEY ≥ 32 characters
- [ ] JWT_SECRET_KEY ≥ 32 characters
- [ ] Environment variables set correctly
- [ ] Docker images built locally without errors
- [ ] Local testing passed (API health check, web frontend)
- [ ] MongoDB backup created and verified
- [ ] Password synchronization verified
- [ ] Database migrations run (if any)

**If ANY check fails, DO NOT deploy to production!**

## 🚨 Troubleshooting

### No API Key Error
```
Error: SAPTIVA API key is required but not configured
```
**Solution**: Set SAPTIVA_API_KEY environment variable or configure via admin UI

### API Connection Failed
```
Error: Error calling SAPTIVA API
```
**Solution**: Check network connectivity and API key validity

### Service Status Check
```bash
# Check service logs
docker logs infra-api

# Verify environment
docker exec infra-api env | grep SAPTIVA
```

## ✅ Validation Checklist

Before deployment:
- [ ] SAPTIVA_API_KEY is set in environment
- [ ] API key is valid and active
- [ ] Network access to api.saptiva.com is available
- [ ] Health endpoint returns 200
- [ ] Chat functionality produces real responses (not demo text)
- [ ] No "demo mode" indicators in UI
- [ ] Error handling works correctly without fallbacks

## 📞 Support
If you encounter issues:
1. Check environment variable configuration
2. Verify API key validity with SAPTIVA support
3. Review application logs for specific error messages
4. Test API connectivity manually with curl

---
Generated: $(date)
System: Production Ready ✅