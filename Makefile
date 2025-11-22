# ============================================================================ 
# OCTAVIOS CHAT - CONSOLIDATED MAKEFILE
# ============================================================================ 
# Simplified Makefile - Complex logic delegated to scripts
# Original: 2624 lines → Consolidated: ~150 lines (94% reduction)
# ============================================================================ 

.PHONY: help setup dev stop restart clean logs shell test deploy db health

# --- CONFIGURATION ---
ifneq (,$(wildcard envs/.env))
    include envs/.env
    export
endif

PROJECT_NAME := octavios-chat-capital414
COMPOSE := docker compose -p $(PROJECT_NAME) -f infra/docker-compose.yml

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
	@echo "  $(YELLOW)make dev$(NC)                - Start development environment (hot reload)"
	@echo "  $(YELLOW)make stop$(NC)               - Stop all services"
	@echo "  $(YELLOW)make restart [S=api]$(NC)    - Restart all services or specific one"
	@echo ""
	@echo "$(CYAN)🔧 Development:$(NC)"
	@echo "  $(YELLOW)make logs [S=api]$(NC)       - View logs (all or specific service)"
	@echo "  $(YELLOW)make shell S=api$(NC)        - Open shell in container (api, web, db)"
	@echo "  $(YELLOW)make health$(NC)             - Check all services health"
	@echo "  $(YELLOW)make reload-env S=api$(NC)   - Reload environment variables"
	@echo ""
	@echo "$(CYAN)🧪 Testing:$(NC)"
	@echo "  $(YELLOW)make test$(NC)               - Run all tests"
	@echo "  $(YELLOW)make test T=api$(NC)         - Run API tests"
	@echo "  $(YELLOW)make test T=web$(NC)         - Run Web tests"
	@echo "  $(YELLOW)make test T=mcp$(NC)         - Run MCP tests"
	@echo "  $(YELLOW)make test T=e2e$(NC)         - Run E2E tests"
	@echo "  $(YELLOW)make test-rag$(NC)           - Test RAG ingestion pipeline"
	@echo "  $(YELLOW)make test-semantic$(NC)      - Test semantic search with Qdrant"
	@echo "  $(YELLOW)make analyze-chunks$(NC)     - Analyze chunk optimization & recommendations"
	@echo "  $(YELLOW)make test-lifecycle$(NC)     - Test resource lifecycle management"
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

# ============================================================================ 
# LIFECYCLE
# ============================================================================ 

setup:
	@echo "$(YELLOW)🔧 Setting up project...$(NC)"
	@chmod +x scripts/*.sh
	@./scripts/interactive-env-setup.sh development
	@echo "$(GREEN)✅ Setup complete. Run 'make dev' to start.$(NC)"

dev:
	@echo "$(YELLOW)🟡 Starting development environment...$(NC)"
	@echo ""
	@$(COMPOSE) up -d
	@echo ""
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(GREEN)🟢  Services started $(NC)"
	@echo "$(GREEN)🟢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "  $(BLUE)🔵 Frontend:  $(YELLOW)http://localhost:3000$(NC)"
	@echo "  $(BLUE)🔵 API:       $(YELLOW)http://localhost:8001$(NC)"
	@echo "  $(BLUE)🔵 Docs:      $(YELLOW)http://localhost:8001/docs$(NC)"
	@echo ""
	@echo "$(YELLOW)🟡 Waiting for services to be healthy...$(NC)"
	@sleep 5
	@$(MAKE) --no-print-directory health

stop:
	@echo "$(YELLOW)🛑 Stopping services...$(NC)"
	@$(COMPOSE) down
	@echo "$(GREEN)✅ Services stopped$(NC)"

restart:
ifdef S
	@echo "$(YELLOW)♻️  Restarting service: $(S)...$(NC)"
	@$(COMPOSE) restart $(S)
else
	@echo "$(YELLOW)♻️  Restarting all services...$(NC)"
	@$(COMPOSE) restart
endif
	@echo "$(GREEN)✅ Restart complete$(NC)"

# ============================================================================ 
# DEVELOPMENT TOOLS
# ============================================================================ 

logs:
ifdef S
	@$(COMPOSE) logs -f --tail=100 $(S)
else
	@$(COMPOSE) logs -f --tail=100
endif

shell:
ifndef S
	@echo "$(RED)❌ Error: Specify service with S=<service>$(NC)"
	@echo "Example: make shell S=api"
	@echo "Available: api, web, db, redis, minio"
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
	@printf "  $(YELLOW)🟡 API Health:         $(NC)"
	@if curl -sf http://localhost:8001/api/health > /dev/null 2>&1; then \
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
	@if $(COMPOSE) exec -T mongodb mongosh --eval \"db.adminCommand('ping')\" > /dev/null 2>&1; then \
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
# TESTING
# ============================================================================ 

test:
	@chmod +x scripts/test-runner.sh
ifdef T
	@./scripts/test-runner.sh $(T) $(ARGS)
else
	@./scripts/test-runner.sh all
endif

test-rag:
	@echo "$(YELLOW)🧪 Testing RAG ingestion pipeline...$(NC)"
	@chmod +x scripts/test-rag-wrapper.sh
	@./scripts/test-rag-wrapper.sh

test-semantic:
	@echo "$(YELLOW)🧠 Testing semantic search with Qdrant...$(NC)"
	@chmod +x scripts/test-rag-wrapper.sh
	@PYTHONPATH=. scripts/test-rag-wrapper.sh python scripts/test-semantic-search.py

analyze-chunks:
	@echo "$(YELLOW)📊 Analyzing chunk optimization...$(NC)"
	@chmod +x scripts/test-rag-wrapper.sh
	@PYTHONPATH=. scripts/test-rag-wrapper.sh python scripts/analyze-chunk-optimization.py

test-lifecycle:
	@echo "$(YELLOW)♻️  Testing resource lifecycle management...$(NC)"
	@chmod +x scripts/test-rag-wrapper.sh
	@PYTHONPATH=. scripts/test-rag-wrapper.sh python scripts/test-resource-lifecycle.py

test-local:
	@echo "$(YELLOW)🧪 Running tests locally with .venv...$(NC)"
	@if [ ! -d "apps/api/.venv" ]; then \
		echo "$(RED)❌ .venv not found in apps/api. Run 'make setup' or create it manually.$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)📥 Loading environment from envs/.env.local (if exists)...$(NC)"
ifdef FILE
	@eval $$(./scripts/env-manager.sh load local) && \
	cd apps/api && .venv/bin/python -m pytest $(FILE) $(ARGS)
else
	@eval $$(./scripts/env-manager.sh load local) && \
	cd apps/api && .venv/bin/python -m pytest tests/ $(ARGS)
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
	@$(COMPOSE) exec -T \
		-e MONGODB_URI="$(MONGODB_URL)" \
		-e MONGODB_DB_NAME="$(MONGODB_DATABASE)" \
		api python scripts/create_demo_user.py

verify:
	@$(MAKE) health
