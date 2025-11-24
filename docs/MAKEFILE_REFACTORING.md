# Makefile Refactoring - Documentation

**Date**: 2025-11-19
**Reduction**: 2624 lines → 290 lines (89% reduction)

---

## 📋 Overview

The Makefile has been dramatically simplified by delegating complex logic to specialized Bash scripts. This follows DevOps best practices:

- **Makefile**: Clean "table of contents" interface (290 lines)
- **Scripts**: Complex implementation logic (modular, testable)

---

## 🎯 Architecture

```
Makefile (Interface Layer)
    ├── scripts/deploy-manager.sh    - Deployment logic
    ├── scripts/test-runner.sh        - Testing orchestration
    └── scripts/db-manager.sh         - Database operations
```

### Benefits

1. **Maintainability**: Change deployment server? Edit one script, not 50 Makefile lines
2. **Testability**: Scripts can be tested independently
3. **Reusability**: Scripts can be called from CI/CD or manually
4. **Clarity**: Makefile shows WHAT, scripts show HOW

---

## 📖 Command Reference

### Lifecycle

```bash
make setup              # Interactive environment setup
make dev                # Start development (hot reload)
make stop               # Stop all services
make restart            # Restart all services
make restart S=api      # Restart specific service
```

### Development

```bash
make logs               # View all logs
make logs S=api         # View API logs
make shell S=api        # Open bash in API container
make shell S=db         # Open bash in MongoDB container
make health             # Check all services health
make reload-env S=api   # Reload environment variables
```

### Testing

```bash
make test               # Run all tests
make test T=api         # Run API tests only
make test T=web         # Run Web tests only
make test T=mcp         # Run MCP tests only
make test T=e2e         # Run E2E tests
```

### Database

```bash
make db CMD=backup      # Backup MongoDB
make db CMD=restore     # Restore MongoDB
make db CMD=stats       # Show database statistics
make db CMD=shell       # Open MongoDB shell
```

### Deployment

```bash
make deploy ENV=demo            # Deploy to demo (safe mode)
make deploy ENV=demo MODE=fast  # Deploy to demo (skip build)
make deploy ENV=prod MODE=safe  # Deploy to production (with backups)
```

### Cleanup

```bash
make clean              # Remove containers and cache
make clean-deep         # Remove containers, volumes, and data (DANGEROUS)
```

---

## 🔧 Script Details

### 1. deploy-manager.sh

Handles all deployment logic for different environments.

**Usage**:
```bash
./scripts/deploy-manager.sh <ENV> <MODE>
```

**Environments**:
- `demo`: Demo server (server.example.com)
- `prod`: Production server (from .env.prod)

**Modes**:
- `safe`: With backups (recommended)
- `fast`: Skip build, use existing images
- `tar`: Standard tarball deployment

**Example**:
```bash
make deploy ENV=demo MODE=fast
# Internally calls: ./scripts/deploy-manager.sh demo fast
```

---

### 2. test-runner.sh

Consolidates all testing logic.

**Usage**:
```bash
./scripts/test-runner.sh <TARGET> [ARGS]
```

**Targets**:
- `api`: FastAPI tests (pytest)
- `web`: Next.js tests (Jest)
- `mcp`: MCP unit tests
- `mcp-integration`: MCP integration tests
- `mcp-all`: All MCP tests
- `e2e`: Playwright E2E tests
- `shell`: Shell script tests
- `all`: Full test suite

**Example**:
```bash
make test T=mcp -v
# Internally calls: ./scripts/test-runner.sh mcp -v
```

---

### 3. db-manager.sh

Database operations consolidated.

**Usage**:
```bash
./scripts/db-manager.sh <CMD> [PROJECT_NAME]
```

**Commands**:
- `backup`: Create MongoDB backup (gzipped archive)
- `restore`: Restore from backup (interactive)
- `stats`: Show database statistics
- `shell`: Open MongoDB shell
- `rotate`: Rotate MongoDB credentials

**Example**:
```bash
make db CMD=backup
# Internally calls: ./scripts/db-manager.sh backup octavios-chat-capital414
```

**Backup Location**: `backups/mongodb/mongodb-YYYYMMDD-HHMMSS.archive`

---

## 🔄 Migration Guide

### Old Command → New Command

| Old | New | Notes |
|-----|-----|-------|
| `make logs-api` | `make logs S=api` | Unified interface |
| `make shell-api` | `make shell S=api` | Unified interface |
| `make test-mcp` | `make test T=mcp` | Unified interface |
| `make deploy-demo-fast` | `make deploy ENV=demo MODE=fast` | More explicit |
| `make db-backup` | `make db CMD=backup` | Unified interface |

**Backward Compatibility**: Old commands still work via aliases at the end of the Makefile.

---

## 📊 Before/After Comparison

### Before (2624 lines)

```makefile
# Hundreds of deployment targets
deploy-demo:
	@echo "Deploying to demo..."
	@ssh jf@server.example.com "cd /home/jf/capital414-chat && ..."
	# ... 50 more lines

deploy-demo-fast:
	@echo "Fast deploying to demo..."
	# ... another 50 lines

deploy-prod:
	# ... 100 more lines
```

### After (290 lines)

```makefile
deploy:
	@chmod +x scripts/deploy-manager.sh
	@./scripts/deploy-manager.sh $(ENV) $(MODE)
```

**Benefits**:
- ✅ 1 deploy target instead of 10+
- ✅ Server IPs in script, not Makefile
- ✅ Easy to add new environments
- ✅ Testable deployment logic

---

## 🛠️ Adding New Features

### Adding a New Environment

Edit `scripts/deploy-manager.sh`:

```bash
case "$ENV" in
  "demo")
    SERVER_HOST="jf@server.example.com"
    DEPLOY_PATH="/home/jf/capital414-chat"
    ;;
  "staging")  # NEW
    SERVER_HOST="user@staging.server.com"
    DEPLOY_PATH="/opt/app"
    ;;
  # ...
esac
```

Usage: `make deploy ENV=staging`

### Adding a New Test Target

Edit `scripts/test-runner.sh`:

```bash
case "$TARGET" in
  # ... existing targets
  "security")  # NEW
    echo "Running security tests..."
    $COMPOSE exec -T api pytest tests/security/ -v
    ;;
esac
```

Usage: `make test T=security`

---

## 🔍 Troubleshooting

### "Command not found" error

Scripts need execute permissions:
```bash
chmod +x scripts/*.sh
```

Or run:
```bash
make setup
```

### Deployment failing

Check script syntax:
```bash
bash -n scripts/deploy-manager.sh
```

### Tests not running

Verify containers are running:
```bash
make health
```

---

## 📝 Best Practices

1. **Keep Makefile Simple**: Add complexity to scripts, not Makefile
2. **Use Descriptive Variables**: `ENV=demo` not `D=demo`
3. **Document Scripts**: Add headers explaining usage
4. **Test Scripts**: Scripts should be testable independently
5. **Version Control**: Commit scripts with Makefile changes

---

## 🎓 Learning Resources

- **Make Documentation**: https://www.gnu.org/software/make/manual/
- **Bash Best Practices**: https://google.github.io/styleguide/shellguide.html
- **DevOps Patterns**: https://www.oreilly.com/library/view/devops-with-kubernetes/

---

## 📞 Support

For issues or questions:
1. Check `make help`
2. Review script source code
3. Check backup Makefile: `Makefile.backup-*`

**Rollback if needed**:
```bash
cp Makefile.backup-YYYYMMDD-HHMMSS Makefile
```
