# ============================================================================ 
# OCTAVIOS CHAT - CONSOLIDATED MAKEFILE
# ============================================================================ 
# Simplified Makefile - Complex logic delegated to scripts
# Original: 2624 lines → Consolidated: ~150 lines (94% reduction)
# ============================================================================ 

.PHONY: help setup dev dev-rebuild dev-no-build dev-reset stop stop-all restart restart-dev clean logs logs-follow shell test deploy db health install install-web env-check env-info env-strict status ps

# --- CONFIGURATION ---
ifneq (,$(wildcard envs/.env))
    include envs/.env
    export
endif

PROJECT_NAME := octavios-chat-bajaware_invex
COMPOSE := docker compose -f infra/docker-compose.yml
COMPOSE_DEV := docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml

# Colors
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
RED    := \033[0;31m
CYAN   := \033[0;36m
NC     := \033[0m

.DEFAULT_GOAL := help

# ============================================================================ 
# HELP & DOCUMENTATION
# ============================================================================ 

help:
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE) $(PROJECT_NAME) - Command Center $(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "$(CYAN)🚀 Lifecycle:$(NC)"
	@echo "  $(YELLOW)make setup$(NC)              - Initial project setup (interactive)"
	@echo "  $(YELLOW)make env-check$(NC)          - Validate environment variables"
	@echo "  $(YELLOW)make dev$(NC)                - Start development environment (uses existing images)"
	@echo "  $(YELLOW)make dev-rebuild$(NC)        - Rebuild & start dev environment with hot reload"
	@echo "  $(YELLOW)make dev-no-build$(NC)       - Start dev environment without any build"
	@echo "  $(YELLOW)make dev-reset$(NC)          - Complete reset: stop, remove, rebuild everything"
	@echo "  $(YELLOW)make stop$(NC)               - Stop all services (preserves containers)"
	@echo "  $(YELLOW)make stop-all$(NC)           - Stop and remove all containers"
	@echo "  $(YELLOW)make restart [S=backend]$(NC) - Restart all services or specific one"
	@echo "  $(YELLOW)make restart-dev$(NC)        - Quick restart of dev services (backend, web, bank-advisor)"
	@echo "  $(YELLOW)make status$(NC) / $(YELLOW)make ps$(NC)   - Show status of all containers"
	@echo ""
	@echo "$(CYAN)🔧 Development:$(NC)"
	@echo "  $(YELLOW)make logs [S=backend]$(NC)   - View last 100 logs (all or specific service)"
	@echo "  $(YELLOW)make logs-follow [S=backend]$(NC) - Follow logs in real-time"
	@echo "  $(YELLOW)make shell S=backend$(NC)    - Open shell in container (backend, web, db)"
	@echo "  $(YELLOW)make health$(NC)             - Check all services health status"
	@echo "  $(YELLOW)make reload-env S=backend$(NC) - Reload environment variables for service"
	@echo ""
	@echo "$(CYAN)🧪 Testing:$(NC)"
	@echo "  $(YELLOW)make test$(NC)               - Run all tests"
	@echo "  $(YELLOW)make test T=api$(NC)         - Run API tests"
	@echo "  $(YELLOW)make test T=web$(NC)         - Run Web tests"
	@echo "  $(YELLOW)make test T=mcp$(NC)         - Run MCP tests"
	@echo "  $(YELLOW)make test T=e2e$(NC)         - Run E2E tests"
	@echo "  $(YELLOW)make test-local [FILE=...]$(NC) - Run API tests locally with .venv"
	@echo ""
	@echo "$(CYAN)💾 Database:$(NC)"
	@echo "  $(YELLOW)make db CMD=backup$(NC)      - Backup MongoDB"
	@echo "  $(YELLOW)make db CMD=restore$(NC)     - Restore MongoDB from backup"
	@echo "  $(YELLOW)make db CMD=stats$(NC)       - Show database statistics"
	@echo "  $(YELLOW)make db CMD=shell$(NC)       - Open MongoDB shell"
	@echo ""
	@echo "$(CYAN)🚀 Deployment:$(NC)"
	@echo "  $(YELLOW)make deploy ENV=demo$(NC)    - Deploy to demo (modes: fast, safe, tar)"
	@echo "  $(YELLOW)make deploy ENV=prod$(NC)    - Deploy to production"
	@echo ""
	@echo "$(CYAN)🧹 Cleanup:$(NC)"
	@echo "  $(YELLOW)make clean$(NC)              - Remove containers and cache"
	@echo "  $(YELLOW)make clean-deep$(NC)         - Remove containers, volumes, and data"
	@echo ""
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "$(CYAN)📋 Critical Environment Variables:$(NC)"
	@echo "  $(YELLOW)SAPTIVA_API_KEY$(NC)         - SAPTIVA LLM API key (required)"
	@echo "  $(YELLOW)JWT_SECRET_KEY$(NC)          - JWT signing key (32+ chars, required)"
	@echo "  $(YELLOW)MONGODB_URL$(NC)             - MongoDB connection string (required)"
	@echo "  $(YELLOW)REDIS_URL$(NC)               - Redis connection string (required)"
	@echo "  $(YELLOW)MINIO_ENDPOINT$(NC)          - MinIO S3 endpoint (required)"
	@echo ""
	@echo "  Run $(YELLOW)make env-check$(NC) for full validation or $(YELLOW)make env-info$(NC) for details"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"

# ============================================================================ 
# LIFECYCLE
# ============================================================================ 

setup:
	@echo "$(YELLOW)🔧 Setting up project...$(NC)"
	@chmod +x scripts/*.sh
	@./scripts/interactive-env-setup.sh development
	@echo "$(GREEN)✅ Setup complete. Run 'make dev' to start.$(NC)"

env-check:
	@echo "$(YELLOW)🔍 Validating environment variables...$(NC)"
	@chmod +x scripts/env-checker.sh
	@./scripts/env-checker.sh warn

env-info:
	@echo "$(YELLOW)📋 Environment variables information...$(NC)"
	@chmod +x scripts/env-checker.sh
	@./scripts/env-checker.sh info

env-strict:
	@echo "$(YELLOW)🔒 Strict environment validation...$(NC)"
	@chmod +x scripts/env-checker.sh
	@./scripts/env-checker.sh strict

dev:
	@echo "$(YELLOW)🟡 Starting development environment (using existing images)...$(NC)"
	@echo ""
	@$(MAKE) --no-print-directory env-check || { echo "$(RED)❌ Environment validation failed. Run 'make setup' to fix.$(NC)"; exit 1; }
	@echo ""
	@$(COMPOSE_DEV) up -d
	@echo ""
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(GREEN)🟢  Development Environment Started (Hot Reload Enabled) $(NC)"
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "  $(BLUE)🔵 Frontend:     $(YELLOW)http://localhost:3000$(NC)  (Next.js dev server)"
	@echo "  $(BLUE)🔵 Backend:      $(YELLOW)http://localhost:8000$(NC)  (Uvicorn --reload)"
	@echo "  $(BLUE)🔵 File Manager: $(YELLOW)http://localhost:8001$(NC)  (Uvicorn --reload)"
	@echo "  $(BLUE)🔵 Bank Advisor: $(YELLOW)http://localhost:8002$(NC)  (Uvicorn --reload)"
	@echo "  $(BLUE)🔵 Docs:         $(YELLOW)http://localhost:8000/docs$(NC)"
	@echo ""
	@echo "$(YELLOW)💡 Hot reload is active - code changes will auto-reload$(NC)"
	@echo "$(YELLOW)🟡 Waiting for services to be healthy...$(NC)"
	@sleep 5
	@$(MAKE) --no-print-directory health

dev-rebuild:
	@echo "$(YELLOW)🔨 Rebuilding development environment with hot reload...$(NC)"
	@echo ""
	@$(MAKE) --no-print-directory env-check || { echo "$(RED)❌ Environment validation failed. Run 'make setup' to fix.$(NC)"; exit 1; }
	@echo ""
	@echo "$(YELLOW)🛑 Stopping existing containers...$(NC)"
	@$(COMPOSE_DEV) down
	@echo ""
	@echo "$(YELLOW)🔨 Building containers for development (backend, web, bank-advisor)...$(NC)"
	@$(COMPOSE_DEV) up -d --build backend web bank-advisor
	@echo ""
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(GREEN)🟢  Development Environment Rebuilt (Hot Reload Enabled) $(NC)"
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "  $(BLUE)🔵 Frontend:     $(YELLOW)http://localhost:3000$(NC)  (Next.js dev server)"
	@echo "  $(BLUE)🔵 Backend:      $(YELLOW)http://localhost:8000$(NC)  (Uvicorn --reload)"
	@echo "  $(BLUE)🔵 File Manager: $(YELLOW)http://localhost:8001$(NC)  (Uvicorn --reload)"
	@echo "  $(BLUE)🔵 Bank Advisor: $(YELLOW)http://localhost:8002$(NC)  (Uvicorn --reload)"
	@echo "  $(BLUE)🔵 Docs:         $(YELLOW)http://localhost:8000/docs$(NC)"
	@echo ""
	@echo "$(YELLOW)💡 Hot reload is active - code changes will auto-reload$(NC)"
	@echo "$(YELLOW)🟡 Waiting for services to be healthy...$(NC)"
	@sleep 5
	@$(MAKE) --no-print-directory health

dev-no-build:
	@echo "$(YELLOW)🟡 Starting development environment (no build)...$(NC)"
	@$(COMPOSE_DEV) up -d --no-build
	@echo "$(GREEN)✅ Services started (no build performed)$(NC)"

dev-reset:
	@echo "$(RED)⚠️  WARNING: This will stop, remove, and rebuild all containers!$(NC)"
	@echo "$(YELLOW)Press Ctrl+C within 5 seconds to cancel...$(NC)"
	@sleep 5
	@echo ""
	@echo "$(YELLOW)🛑 Stopping all containers...$(NC)"
	@$(COMPOSE_DEV) down --remove-orphans
	@echo ""
	@echo "$(YELLOW)🔨 Rebuilding from scratch...$(NC)"
	@$(COMPOSE_DEV) build --no-cache backend web bank-advisor
	@echo ""
	@echo "$(YELLOW)🚀 Starting fresh environment...$(NC)"
	@$(COMPOSE_DEV) up -d
	@echo ""
	@echo "$(GREEN)✅ Complete reset done! All services rebuilt and started.$(NC)"
	@$(MAKE) --no-print-directory status

stop:
	@echo "$(YELLOW)🛑 Stopping services...$(NC)"
	@$(COMPOSE) down
	@echo "$(GREEN)✅ Services stopped (containers preserved)$(NC)"

stop-all:
	@echo "$(YELLOW)🛑 Stopping and removing all containers...$(NC)"
	@$(COMPOSE_DEV) down --remove-orphans
	@echo "$(GREEN)✅ All containers stopped and removed$(NC)"

restart:
ifdef S
	@echo "$(YELLOW)♻️  Restarting service: $(S)...$(NC)"
	@$(COMPOSE) restart $(S)
	@echo "$(GREEN)✅ Service $(S) restarted$(NC)"
else
	@echo "$(YELLOW)♻️  Restarting all services...$(NC)"
	@$(COMPOSE) restart
	@echo "$(GREEN)✅ All services restarted$(NC)"
endif

restart-dev:
	@echo "$(YELLOW)♻️  Quick restart of dev services (backend, web, bank-advisor)...$(NC)"
	@$(COMPOSE_DEV) restart backend web bank-advisor
	@echo "$(GREEN)✅ Dev services restarted$(NC)"
	@echo "$(YELLOW)💡 Hot reload is active on all services$(NC)"

# ============================================================================ 
# DEVELOPMENT TOOLS
# ============================================================================ 

logs:
ifdef S
	@$(COMPOSE) logs --tail=100 $(S)
else
	@$(COMPOSE) logs --tail=100
endif

logs-follow:
ifdef S
	@echo "$(YELLOW)📜 Following logs for $(S)... (Ctrl+C to stop)$(NC)"
	@$(COMPOSE) logs -f --tail=100 $(S)
else
	@echo "$(YELLOW)📜 Following logs for all services... (Ctrl+C to stop)$(NC)"
	@$(COMPOSE) logs -f --tail=100
endif

status:
	@echo "$(BLUE)🔵━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)🔵 Container Status $(NC)"
	@echo "$(BLUE)🔵━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@docker ps --filter "name=$(PROJECT_NAME)" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || echo "$(RED)No containers found$(NC)"
	@echo ""

ps: status

shell:
ifndef S
	@echo "$(RED)❌ Error: Specify service with S=<service>$(NC)"
	@echo "Example: make shell S=api"
	@echo "Available: backend, web, db, redis, minio"
	@exit 1
endif
	@if [ "$(S)" = "db" ]; then \
		$(COMPOSE) exec mongodb bash; \
	else \
		$(COMPOSE) exec $(S) bash; \
	fi

health:
	@echo "$(BLUE)🔵━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)🔵 Health Check $(NC)"
	@echo "$(BLUE)🔵━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@printf "  $(YELLOW)🟡 Backend Health:     $(NC)"
	@if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then \
		echo "$(GREEN)🟢 Healthy$(NC)"; \
	else \
		echo "$(RED)🔴 Unhealthy$(NC)"; \
	fi
	@printf "  $(YELLOW)🟡 File Manager:       $(NC)"
	@if curl -sf http://localhost:8001/health > /dev/null 2>&1; then \
		echo "$(GREEN)🟢 Healthy$(NC)"; \
	else \
		echo "$(RED)🔴 Unhealthy$(NC)"; \
	fi
	@printf "  $(YELLOW)🟡 Frontend:           $(NC)"
	@if curl -sf http://localhost:3000 > /dev/null 2>&1; then \
		echo "$(GREEN)🟢 Healthy$(NC)"; \
	else \
		echo "$(RED)🔴 Unhealthy$(NC)"; \
	fi
	@printf "  $(YELLOW)🟡 MongoDB:            $(NC)"
	@if $(COMPOSE) exec -T mongodb mongosh --eval 'db.adminCommand("ping")' > /dev/null 2>&1; then \
		echo "$(GREEN)🟢 Connected$(NC)"; \
	else \
		echo "$(RED)🔴 Disconnected$(NC)"; \
	fi
	@printf "  $(YELLOW)🟡 Redis:              $(NC)"
	@if $(COMPOSE) exec -T redis redis-cli ping > /dev/null 2>&1; then \
		echo "$(GREEN)🟢 Connected$(NC)"; \
	else \
		echo "$(RED)🔴 Disconnected$(NC)"; \
	fi
	@echo ""

reload-env:
ifndef S
	@echo "$(RED)❌ Error: Specify service with S=<service>$(NC)"
	@exit 1
endif
	@echo "$(YELLOW)♻️  Reloading environment for $(S)...$(NC)"
	@$(COMPOSE) stop $(S)
	@$(COMPOSE) rm -f $(S)
	@$(COMPOSE) up -d $(S)
	@echo "$(GREEN)✅ Environment reloaded$(NC)"

# ============================================================================
# PACKAGE MANAGEMENT
# ============================================================================

install-web:
	@echo "$(YELLOW)📦 Installing web dependencies in container...$(NC)"
	@$(COMPOSE) exec -T web sh -c "cd /app && pnpm install"
	@echo "$(GREEN)✅ Web dependencies installed$(NC)"

install: install-web
	@echo "$(GREEN)✅ All dependencies installed$(NC)"

# ============================================================================
# TESTING
# ============================================================================ 

test:
	@chmod +x scripts/test-runner.sh
ifdef T
	@./scripts/test-runner.sh $(T) $(ARGS)
else
	@./scripts/test-runner.sh all
endif



test-local:
	@echo "$(YELLOW)🧪 Running tests locally with .venv...$(NC)"
	@if [ ! -d "apps/backend/.venv" ]; then \
		echo "$(RED)❌ .venv not found in apps/backend. Run 'make setup' or create it manually.$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)📥 Loading environment from envs/.env.local (if exists)...$(NC)"
ifdef FILE
	@eval $$(./scripts/env-manager.sh load local) && \
	cd apps/backend && .venv/bin/python -m pytest $(FILE) $(ARGS)
else
	@eval $$(./scripts/env-manager.sh load local) && \
	cd apps/backend && .venv/bin/python -m pytest tests/ $(ARGS)
endif

# ============================================================================ 
# DATABASE MANAGEMENT
# ============================================================================ 

db:
ifndef CMD
	@echo "$(RED)❌ Error: Specify command with CMD=<command>$(NC)"
	@echo "Available: backup, restore, stats, shell"
	@exit 1
endif
	@chmod +x scripts/db-manager.sh
	@./scripts/db-manager.sh $(CMD) $(PROJECT_NAME)

# ============================================================================ 
# DEPLOYMENT
# ============================================================================ 

deploy:
ifndef ENV
	@echo "$(RED)❌ Error: Specify environment with ENV=<env>$(NC)"
	@echo "Available: demo, prod"
	@exit 1
endif
	@chmod +x scripts/deploy-manager.sh
	@./scripts/deploy-manager.sh $(ENV) $(MODE)

# ============================================================================ 
# CLEANUP
# ============================================================================ 

clean:
	@echo "$(YELLOW)🧹 Cleaning containers and cache...$(NC)"
	@$(COMPOSE) down --remove-orphans
	@rm -rf apps/web/.next
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

clean-deep:
	@echo "$(RED)⚠️  WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? Type 'DELETE' to continue: " confirm; \
	if [ "$$confirm" = "DELETE" ]; then \
		$(COMPOSE) down -v --remove-orphans; \
		rm -rf apps/web/.next; \
		echo "$(GREEN)✅ Deep cleanup complete$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

# ============================================================================ 
# LEGACY ALIASES (for backward compatibility)
# ============================================================================ 

logs-api:
	@$(MAKE) logs S=api

logs-web:
	@$(MAKE) logs S=web

shell-api:
	@$(MAKE) shell S=api

shell-web:
	@$(MAKE) shell S=web

shell-db:
	@$(MAKE) shell S=db

test-api:
	@$(MAKE) test T=api

test-web:
	@$(MAKE) test T=web

test-mcp:
	@$(MAKE) test T=mcp

test-all:
	@$(MAKE) test

deploy-demo:
	@$(MAKE) deploy ENV=demo MODE=safe

deploy-demo-fast:
	@$(MAKE) deploy ENV=demo MODE=fast

deploy-prod:
	@$(MAKE) deploy ENV=prod MODE=safe

db-backup:
	@$(MAKE) db CMD=backup

db-restore:
	@$(MAKE) db CMD=restore

create-demo-user:
	@echo "📝 Creating demo user..."
	@$(COMPOSE) exec -T backend sh -c 'MONGODB_URI="$$MONGODB_URL" MONGODB_DB_NAME="$$MONGODB_DATABASE" python scripts/create_demo_user.py'

verify:
	@$(MAKE) health
