# ============================================================================ 
# OCTAVIOS CHAT - CONSOLIDATED MAKEFILE
# ============================================================================ 
# Simplified Makefile - Complex logic delegated to scripts
# Original: 2624 lines → Consolidated: ~150 lines (94% reduction)
# ============================================================================ 

.PHONY: help setup dev dev-rebuild dev-no-build dev-reset stop stop-all restart restart-dev clean logs logs-follow shell test deploy db health install install-web env-check env-info env-strict status ps preflight-prod wait-healthy prod

# --- CONFIGURATION ---
ENV ?=
ENV_CANDIDATE := $(if $(ENV),envs/.env.$(ENV),envs/.env)
ENV_FILE := $(if $(wildcard $(ENV_CANDIDATE)),$(ENV_CANDIDATE),envs/.env)

ifneq (,$(wildcard $(ENV_FILE)))
    include $(ENV_FILE)
    export
endif

PROJECT_NAME := octavios-chat-bajaware_invex
COMPOSE_BASE_FILE := infra/docker-compose.yml
COMPOSE_DEV_FILE := infra/docker-compose.dev.yml
COMPOSE_PROD_FILE := infra/docker-compose.production.yml
COMPOSE_REGISTRY_FILE := infra/docker-compose.registry.yml

# Compose builders (REGISTRY=1 adds registry override for prod targets)
define compose_cmd
docker compose -f $(COMPOSE_BASE_FILE) $(if $(1),-f $(1),)
endef

define compose_prod_cmd
docker compose --env-file $(ENV_FILE) -f $(COMPOSE_BASE_FILE) -f $(COMPOSE_PROD_FILE) $(if $(REGISTRY),-f $(COMPOSE_REGISTRY_FILE),)
endef

COMPOSE := $(call compose_cmd,)
COMPOSE_DEV := $(call compose_cmd,$(COMPOSE_DEV_FILE))
COMPOSE_PROD := $(call compose_prod_cmd)
HEALTH_TIMEOUT ?= 120
HEALTH_INTERVAL ?= 5

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
	@echo "  $(YELLOW)Flags: ENV=prod|demo$(NC)    - Select env file (envs/.env.<ENV>); default envs/.env"
	@echo "  $(YELLOW)       REGISTRY=1$(NC)       - Use Docker Hub images for prod targets (registry override)"
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
	@echo "$(CYAN)🏦 Bank Advisor Data:$(NC)"
	@echo "  $(YELLOW)make init-bank-advisor$(NC)  - Initialize Bank Advisor (migrations + ETL)"
	@echo "  $(YELLOW)make init-bank-advisor-migrations$(NC) - Run migrations only"
	@echo "  $(YELLOW)make init-bank-advisor-etl$(NC) - Run ETL only"
	@echo ""
	@echo "$(CYAN)🚀 Deployment:$(NC)"
	@echo "  $(YELLOW)make deploy ENV=demo$(NC)    - Deploy to demo (modes: fast, safe, tar)"
	@echo "  $(YELLOW)make deploy ENV=prod$(NC)    - Deploy to production"
	@echo "  $(YELLOW)make prod$(NC)               - Preflight + build/pull + up + wait-healthy + status"
	@echo "  $(YELLOW)REGISTRY=1 make prod-up$(NC) - Use registry images (infra/docker-compose.registry.yml) instead of local build"
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

# Rebuild individual services
rebuild-web:
	@echo "$(YELLOW)🔨 Rebuilding web service...$(NC)"
	@$(COMPOSE_DEV) up -d --build --no-deps web
	@echo "$(GREEN)✅ Web service rebuilt$(NC)"

rebuild-backend:
	@echo "$(YELLOW)🔨 Rebuilding backend service...$(NC)"
	@$(COMPOSE_DEV) up -d --build --no-deps backend
	@echo "$(GREEN)✅ Backend service rebuilt$(NC)"

rebuild-bank-advisor:
	@echo "$(YELLOW)🔨 Rebuilding bank-advisor service...$(NC)"
	@$(COMPOSE_DEV) up -d --build --no-deps bank-advisor
	@echo "$(GREEN)✅ Bank-advisor service rebuilt$(NC)"

rebuild-file-manager:
	@echo "$(YELLOW)🔨 Rebuilding file-manager service...$(NC)"
	@$(COMPOSE_DEV) up -d --build --no-deps file-manager
	@echo "$(GREEN)✅ File-manager service rebuilt$(NC)"

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

# Bank Advisor Data Initialization
init-bank-advisor:
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)🏦 Initializing Bank Advisor Data$(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@chmod +x scripts/init_bank_advisor_data.sh
	@./scripts/init_bank_advisor_data.sh

init-bank-advisor-migrations:
	@chmod +x scripts/init_bank_advisor_data.sh
	@./scripts/init_bank_advisor_data.sh --migrations-only

init-bank-advisor-etl:
	@chmod +x scripts/init_bank_advisor_data.sh
	@./scripts/init_bank_advisor_data.sh --etl-only

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

# Production deployment helpers
preflight-prod:
	@echo "$(YELLOW)🔍 Preflight checks for production (ENV_FILE=$(ENV_FILE))...$(NC)"
	@test -f "$(ENV_FILE)" || { echo "$(RED)❌ Env file $(ENV_FILE) not found$(NC)"; exit 1; }
	@sk=$$(grep '^SECRET_KEY=' $(ENV_FILE) | cut -d= -f2-); \
	  if [ -z "$$sk" ] || [ $${#sk} -lt 32 ]; then \
	    echo "$(RED)❌ SECRET_KEY missing or too short in $(ENV_FILE)$(NC)"; exit 1; \
	  fi
	@jk=$$(grep '^JWT_SECRET_KEY=' $(ENV_FILE) | cut -d= -f2-); \
	  if [ -z "$$jk" ] || [ $${#jk} -lt 32 ]; then \
	    echo "$(RED)❌ JWT_SECRET_KEY missing or too short in $(ENV_FILE)$(NC)"; exit 1; \
	  fi
	@docker compose version >/dev/null 2>&1 || { echo "$(RED)❌ docker compose not available$(NC)"; exit 1; }
	@docker ps >/dev/null 2>&1 || { echo "$(RED)❌ Docker daemon not running$(NC)"; exit 1; }
	@echo "$(GREEN)✅ Preflight passed$(NC)"

wait-healthy:
	@echo "$(YELLOW)⏱ Waiting up to $(HEALTH_TIMEOUT)s for core services...$(NC)"
	@end_time=$$((SECONDS+$(HEALTH_TIMEOUT))); \
	while [ $$SECONDS -lt $$end_time ]; do \
	  ok=1; \
	  curl -sf http://localhost:8000/api/health >/dev/null 2>&1 || ok=0; \
	  curl -sf http://localhost:8001/health >/dev/null 2>&1 || ok=0; \
	  curl -sf http://localhost:8002/health >/dev/null 2>&1 || ok=0; \
	  curl -sf http://localhost:3000 >/dev/null 2>&1 || ok=0; \
	  if [ $$ok -eq 1 ]; then \
	    echo "$(GREEN)✅ All core services responded healthy$(NC)"; exit 0; \
	  fi; \
	  sleep $(HEALTH_INTERVAL); \
	done; \
	echo "$(RED)❌ Services not healthy after $(HEALTH_TIMEOUT)s$(NC)"; exit 1

prod-prepare:
	@echo "$(YELLOW)🔧 Preparing for production deployment...$(NC)"
	@echo "$(YELLOW)  ↳ Cleaning local .env files that may interfere...$(NC)"
	@rm -f apps/backend/.env apps/web/.env plugins/public/bank-advisor/.env plugins/public/file-manager/.env
	@echo "$(YELLOW)  ↳ Copying production environment...$(NC)"
	@test -f "$(ENV_FILE)" || { echo "$(RED)❌ Env file $(ENV_FILE) not found$(NC)"; exit 1; }
	@cp "$(ENV_FILE)" envs/.env
	@echo "$(GREEN)✅ Production environment prepared from $(ENV_FILE)$(NC)"

prod-build:
	@echo "$(YELLOW)🔨 Building production images...$(NC)"
ifdef REGISTRY
	@echo "$(YELLOW)ℹ️  REGISTRY=1 detected: pulling pre-built images instead of building$(NC)"
	@$(COMPOSE_PROD) pull backend web bank-advisor file-manager
	@echo "$(GREEN)✅ Registry images pulled$(NC)"
else
	@$(COMPOSE_PROD) build --no-cache backend web bank-advisor file-manager
	@echo "$(GREEN)✅ Production images built$(NC)"
endif

prod-up:
	@echo "$(YELLOW)🚀 Starting production containers...$(NC)"
	@$(COMPOSE_PROD) up -d
	@echo "$(GREEN)✅ Production containers started$(NC)"
	@echo "$(YELLOW)🟡 Waiting for services to be healthy...$(NC)"
	@sleep 10
	@$(COMPOSE_PROD) ps

prod-restart:
ifdef S
	@echo "$(YELLOW)♻️  Restarting production service: $(S)...$(NC)"
	@$(COMPOSE_PROD) restart $(S)
	@echo "$(GREEN)✅ Service $(S) restarted$(NC)"
else
	@echo "$(YELLOW)♻️  Restarting all production services...$(NC)"
	@$(COMPOSE_PROD) restart
	@echo "$(GREEN)✅ All services restarted$(NC)"
endif

prod-logs:
ifdef S
	@$(COMPOSE_PROD) logs --tail=100 $(S)
else
	@$(COMPOSE_PROD) logs --tail=100
endif

prod-status:
	@echo "$(BLUE)🔵━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)🔵 Production Container Status $(NC)"
	@echo "$(BLUE)🔵━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@$(COMPOSE_PROD) ps
	@echo ""

prod: preflight-prod prod-build prod-up wait-healthy prod-status

prod-deploy: prod-prepare prod-build prod-up
	@echo ""
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(GREEN)🟢  Production Deployment Complete $(NC)"
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "  $(BLUE)🔵 Frontend:     $(YELLOW)https://invex.saptiva.com$(NC)"
	@echo "  $(BLUE)🔵 Backend API:  $(YELLOW)https://back-invex.saptiva.com$(NC)"
	@echo "  $(BLUE)🔵 Health Check: $(YELLOW)https://back-invex.saptiva.com/api/health$(NC)"
	@echo ""
	@$(MAKE) prod-status

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
