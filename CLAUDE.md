# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Saptiva OctaviOS Chat** - A production-ready conversational interface for SAPTIVA language models with integrated document review (RAG) capabilities and enterprise-grade security. The architecture combines a Next.js 14 frontend with a FastAPI backend, using MongoDB for persistence and Redis for caching.

## Essential Commands

### Development Setup
```bash
# First-time setup (interactive - recommended)
make setup          # Creates .env, installs deps, configures project

# Quick setup (non-interactive, uses defaults)
make setup-quick

# Start development environment
make dev            # Starts all services (Next.js, FastAPI, MongoDB, Redis)

# Create demo user for testing (demo/Demo1234)
make create-demo-user
```

### Testing
```bash
# Run all tests (API + web + shell scripts)
make test-all

# Run specific test suites
make test-api        # Only pytest tests (FastAPI)
make test-web        # Only frontend tests (pnpm test)
make test-e2e        # Playwright E2E tests (requires stack running)

# Run single test file
cd apps/api && pytest tests/e2e/test_chat_models.py -v

# Health check
make verify          # Health checks + demo login + API probe
```

### Common Issues

**Code changes not reflecting in containers?**
```bash
# API code changed but container shows old code
make rebuild-api      # Builds with --no-cache, recreates container

# Multiple files changed or env vars updated
make rebuild-all      # Rebuilds all containers without cache

# Why? Docker caches image layers. `docker restart` keeps old code.
# You need --no-cache build + down/up to reload changes.
```

**Environment variables not loading?**
```bash
# CRITICAL: docker compose restart does NOT reload .env
# WRONG:  docker compose restart api
# RIGHT:  make reload-env-service SERVICE=api
#         or make restart (does down + up)
```

**Permission errors with .next directory?**
```bash
./scripts/fix-docker-permissions.sh
make clean-next      # Removes .next directory + Docker volumes
```

### Database Operations
```bash
# Database access
make shell-db        # Opens mongosh in container

# Backup/restore
make backup-mongodb-prod      # Production backup with retention
make restore-mongodb-prod     # Restore from backup

# Debugging
make db-collections  # List all collections with document counts
make redis-stats     # Show Redis keys and memory usage
```

### Deployment
```bash
# Recommended: Automated tar deployment (no registry needed)
make deploy-tar      # Build + transfer + deploy (~8-12 min)

# Faster: Registry deployment
make deploy-prod     # Build + push + deploy via registry (~4-6 min)

# Fastest: Deploy existing images
make deploy-fast     # Reuse built images (~2-3 min)
```

### Resource Management
```bash
# Monitor Docker resource usage
make resources         # Shows disk usage, container stats, memory
make resources-monitor # Real-time monitoring (Ctrl+C to exit)

# Cleanup
make docker-cleanup              # Safe: removes old cache/images
make docker-cleanup-aggressive   # Deep: removes ALL unused resources
```

## Architecture Overview

### High-Level Design

**Monorepo Structure** - pnpm workspace with:
- `apps/web/` - Next.js 14 frontend (App Router, TypeScript, Tailwind CSS)
- `apps/api/` - FastAPI backend (Python 3.10+, async/await, Beanie ODM)
- `infra/` - Docker Compose orchestration

**Data Flow Pattern**:
1. User uploads PDF/image via frontend (`ChatComposer`)
2. Backend extracts text using **extraction abstraction layer** (pypdf → Saptiva SDK → Saptiva OCR)
3. Text cached in Redis (1-hour TTL), metadata in MongoDB
4. User sends chat message with file references
5. Backend injects document context into LLM prompt (RAG)
6. SAPTIVA API returns response based on document content
7. Frontend displays response with file indicator badge

### Backend Architecture (Design Patterns)

**Strategy Pattern** (`apps/api/src/domain/chat_strategy.py`):
- **StandardChatStrategy** - Simple SAPTIVA chat (no documents)
- **RAGChatStrategy** - Chat with document context injection
- **DeepResearchStrategy** - Future Aletheia integration (currently disabled)
- Factory selects strategy based on `document_ids` presence and feature flags

**Builder Pattern** (`apps/api/src/domain/chat_response_builder.py`):
- Constructs consistent ChatResponse objects
- Handles sanitization, metadata, error formatting

**DTO Pattern** (`apps/api/src/domain/chat_context.py`):
- `ChatContext` - Type-safe request data container
- `ChatProcessingResult` - Standardized response structure
- Decouples router from service logic

**Service Layer**:
- `ChatService` - Orchestrates chat flow, persists messages
- `DocumentService` - RAG retrieval, ownership validation
- `HistoryService` - Unified timeline events (chat + research + file uploads)

**Key Implementation Detail**: Chat router (`apps/api/src/routers/chat.py`) merges request `file_ids` with session `attached_file_ids` for multi-turn conversations without re-uploading files.

### Document Extraction Abstraction

**Location**: `apps/api/src/services/document_extraction.py`

**Three-Tier Fallback Strategy**:
1. **pypdf** (local, free) - For searchable PDFs (80-90% of cases)
2. **Saptiva PDF SDK** (`obtener_texto_en_documento`) - For scanned PDFs
3. **Saptiva OCR** (Chat Completions API) - For images (PNG/JPG)

**Cache Strategy**: Extracted text cached in Redis with 1-hour TTL using key pattern `doc:text:{document_id}`. Always check cache before re-extracting.

**File Storage**: Temporary files stored in `/tmp/octavios_documents/` inside container. Cleanup handled by OS tmpfs.

### Frontend State Management

**Zustand Stores**:
- `filesStore` (`apps/web/src/lib/stores/files-store.ts`) - File attachments by conversation
- `chatStore` - Conversation state, message history
- Uses `sessionStorage` for persistence across refreshes

**File Upload Flow**:
1. `useFiles` hook (`apps/web/src/hooks/useFiles.ts`) validates type/size
2. `CompactChatComposer` renders drag-and-drop UI
3. `uploadDocument()` sends multipart to `/api/documents`
4. Backend returns `document_id`, frontend adds to `filesStore`
5. `FileAttachmentList` displays status badges (⏳ Processing → ✓ Ready)

### System Prompts Architecture

**Model-Specific Prompts** - Configured via YAML (`apps/api/prompts/registry.yaml`):
- Different instructions per model (Turbo: speed/brevity, Cortex: rigor, Ops: DevOps)
- Dynamic placeholders: `{CopilotOS}`, `{Saptiva}`, `{TOOLS}`
- Channel-based token limits: `chat` (1200), `report` (3500), `code` (2048)
- Feature flag: `ENABLE_MODEL_SYSTEM_PROMPT=true`

**Adding New Model**: Edit `registry.yaml` (no code changes needed), restart API.

## Critical Configuration

### Environment Variables

**Location**: `envs/.env` (dev), `envs/.env.prod` (production)

**SAPTIVA API Integration** (critical for avoiding 404s):
```bash
SAPTIVA_BASE_URL=https://api.saptiva.com  # Must match API docs exactly
SAPTIVA_API_KEY=va-ai-xxxxx...            # From Saptiva dashboard

# CRITICAL: Model names are case-sensitive
# CORRECT: "Saptiva Turbo", "Saptiva Cortex", "Saptiva OCR"
# WRONG:   "saptiva turbo", "SAPTIVA_TURBO"
```

**File Upload Limits**:
```bash
# Backend validation
MAX_FILE_SIZE_MB=50              # Server-side limit

# Frontend display
NEXT_PUBLIC_MAX_FILE_SIZE_MB=50  # Must match backend
```

**Feature Flags**:
```bash
# Files V1 - Document upload/RAG
NEXT_PUBLIC_FEATURE_ADD_FILES=true

# Deep Research - Aletheia integration (currently disabled)
DEEP_RESEARCH_KILL_SWITCH=true   # Global kill switch
DEEP_RESEARCH_ENABLED=false      # Only active if kill switch is false
```

### Docker Compose Profiles

**Development** (default):
```bash
make dev  # Runs: web, api, mongodb, redis
```

**Production**:
```bash
docker compose --profile production up -d  # Adds nginx
```

**Testing**:
```bash
docker compose --profile testing up --build  # Adds playwright
```

## Database Schema (MongoDB via Beanie ODM)

**Critical Collections**:

**`chat_sessions`** - Conversation containers
```python
{
  "_id": UUID,
  "title": str,
  "user_id": str,
  "attached_file_ids": List[str],  # Persistent file references
  "message_count": int,
  "created_at": datetime
}
```

**`chat_messages`** - Individual messages
```python
{
  "_id": UUID,
  "chat_id": UUID,
  "role": "user" | "assistant" | "system",
  "content": str,
  "status": "pending" | "completed" | "error",
  "created_at": datetime
}
```

**`documents`** - File metadata + extracted text
```python
{
  "_id": UUID,
  "user_id": str,
  "filename": str,
  "mime_type": str,
  "file_size": int,
  "status": "PENDING" | "READY" | "ERROR",
  "extraction_source": "pypdf" | "saptiva_sdk" | "saptiva_ocr",
  "storage_path": str,  # /tmp/octavios_documents/{id}.pdf
  "pages": [{"page_num": 1, "text_md": "..."}],
  "uploaded_at": datetime,
  "processed_at": datetime
}
```

**`history_events`** - Unified timeline (chat + research + file uploads)
```python
{
  "_id": UUID,
  "chat_id": UUID,
  "user_id": str,
  "event_type": "chat_message" | "file_upload" | "research_start" | "research_complete",
  "timestamp": datetime
}
```

### Redis Cache Patterns

**Document Text Cache**:
```
Key:    doc:text:{document_id}
Value:  Full extracted text (markdown format)
TTL:    3600 seconds (1 hour)
```

**Session Cache**:
```
Key:    session:{user_id}
Value:  JWT session metadata
TTL:    Based on JWT_ACCESS_TOKEN_EXPIRE_MINUTES
```

**Rate Limiting**:
```
Key:    rate_limit:{user_id}:{endpoint}
Value:  Request count
TTL:    60 seconds
```

## Code Conventions

### Python (FastAPI Backend)

**Type Hints** - Required everywhere (enforced by mypy strict mode):
```python
async def process_document(file_id: str, user_id: str) -> Dict[str, Any]:
    # mypy will error if return type doesn't match
```

**Logging** - Use structlog with structured context:
```python
logger.info(
    "document_processed",
    document_id=doc_id,
    user_id=user_id,
    extraction_source="pypdf",
    page_count=len(pages)
)
```

**Error Handling** - Always raise HTTPException with proper status codes:
```python
from fastapi import HTTPException, status

raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail=f"Document {doc_id} not found or access denied"
)
```

**Async/Await** - All database operations must be async:
```python
# CORRECT
document = await Document.get(doc_id)

# WRONG (will error)
document = Document.get(doc_id)
```

### TypeScript (Next.js Frontend)

**API Client** - Centralized in `apps/web/src/lib/api-client.ts`:
```typescript
// Always use the centralized client (includes auth headers)
import { apiClient } from '@/lib/api-client';

const response = await apiClient.sendChatMessage({
  message: "Hello",
  file_ids: ["doc123"]
});
```

**State Updates** - Use Zustand stores:
```typescript
// Get store instance
const { addFile, removeFile } = useFilesStore();

// Update state
addFile(conversationId, {
  id: "doc123",
  filename: "report.pdf",
  status: "ready"
});
```

**Feature Flags** - Check before rendering:
```typescript
import { featureFlags } from '@/lib/feature-flags';

{featureFlags.addFiles && (
  <FileUploadButton />
)}
```

## Testing Guidelines

### API Tests (pytest)

**Location**: `apps/api/tests/`

**Running Tests**:
```bash
# All API tests
make test-api

# Specific test file
cd apps/api && pytest tests/e2e/test_chat_models.py -v

# With coverage
cd apps/api && pytest --cov=src --cov-report=html
```

**Test Structure**:
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_document_upload(client: AsyncClient, auth_headers: dict):
    """Test document upload endpoint."""
    with open("test.pdf", "rb") as f:
        response = await client.post(
            "/api/documents",
            headers=auth_headers,
            files={"file": f}
        )

    assert response.status_code == 200
    assert "document_id" in response.json()
```

**Fixtures** - Defined in `apps/api/tests/conftest.py`:
- `client` - Async HTTP client
- `auth_headers` - JWT authorization headers
- `test_user` - Demo user instance

### Frontend Tests (Jest + Testing Library)

**Location**: `apps/web/src/**/__tests__/`

**Running Tests**:
```bash
make test-web
# or
cd apps/web && pnpm test
```

### E2E Tests (Playwright)

**Location**: `tests/e2e/`

**Running E2E Tests**:
```bash
# Start stack first
make dev

# Run E2E tests
make test-e2e
```

## Troubleshooting Common Issues

### 1. SAPTIVA API Returns 404

**Symptoms**: Chat works but returns 404 even with valid API key.

**Root Cause**: SAPTIVA API is case-sensitive and requires exact endpoint format.

**Solution**:
```python
# CORRECT
url = "https://api.saptiva.com/v1/chat/completions/"  # Trailing slash required
model = "Saptiva Turbo"  # Capitalized

# WRONG
url = "https://api.saptiva.com/v1/chat/completions"  # Missing trailing slash
model = "saptiva-turbo"  # Wrong case
```

### 2. MongoDB/Redis Authentication Failures After Credential Rotation

**Symptoms**: API container shows `WRONGPASS` or `Authentication failed`.

**Root Cause**: `docker compose restart` does NOT reload environment variables.

**Solution**:
```bash
# WRONG
docker compose restart api

# RIGHT
docker compose down api && docker compose up -d api
# or
make reload-env-service SERVICE=api
```

**Prevention**: Always ensure `env_file` directive in docker-compose.yml:
```yaml
services:
  api:
    env_file:
      - ../envs/.env  # CRITICAL
```

### 3. Document Upload Succeeds But No Text Extracted

**Symptoms**: Document status is `READY` but chat doesn't include file content.

**Debugging Steps**:
```bash
# 1. Check Redis cache
make shell-redis
> KEYS doc:text:*
> GET doc:text:{document_id}

# 2. Check MongoDB document
make shell-db
> use octavios
> db.documents.find({_id: ObjectId("{document_id}")})

# 3. Check extraction logs
make logs-api | grep extraction_source
```

**Common Causes**:
- Empty PDF (no searchable text) - Falls back to Saptiva SDK
- Saptiva SDK 500 error - Check API quota/connectivity
- OCR model unavailable - Verify `Saptiva OCR` model exists

### 4. File Upload Fails with Size Limit Error

**Symptoms**: Frontend shows "File too large" or backend rejects upload.

**Solution**: Ensure consistent limits across stack:

**Frontend** (`apps/web/src/hooks/useFiles.ts`):
```typescript
const maxSizeBytes = parseInt(process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB || "50") * 1024 * 1024;
```

**Backend** (`apps/api/src/routers/documents.py`):
```python
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
```

**Nginx** (`infra/nginx/nginx.conf`):
```nginx
client_max_body_size 50M;
```

**Docker** (`apps/web/Dockerfile`):
```dockerfile
ARG NEXT_PUBLIC_MAX_FILE_SIZE_MB=50
```

## Deployment Notes

### Pre-Deployment Checklist

1. **Update credentials** in `envs/.env.prod`:
   ```bash
   SAPTIVA_API_KEY=va-ai-prod-xxxx
   MONGODB_PASSWORD=<strong-production-password>
   REDIS_PASSWORD=<strong-production-password>
   JWT_SECRET_KEY=<cryptographically-secure-key>
   ```

2. **Run validation**:
   ```bash
   ./scripts/validate-config.sh
   make test-all
   ```

3. **Backup production database** (if updating existing deployment):
   ```bash
   make backup-mongodb-prod
   ```

### Deployment Process (Recommended: Tar Method)

```bash
# 1. Build and deploy in one command
make deploy-tar

# Behind the scenes:
# - Builds production images with cache optimization
# - Saves to tar files
# - Transfers to production server
# - Loads images on server
# - Recreates containers with new images
# - Verifies health checks

# 2. Verify deployment
make ssh-prod
docker ps
curl http://localhost:8001/api/health
```

### Post-Deployment Verification

```bash
# Check all services are healthy
make status-prod

# Monitor logs for errors
make logs-prod

# Test API health
curl https://your-domain.com/api/health

# Test frontend
curl https://your-domain.com
```

## Observability

**Prometheus Metrics** - Exposed at `/api/metrics`:
- HTTP request rate, latency (P50, P95, P99), error rate
- Active connections, memory usage
- Cache hit/miss rates
- Document processing metrics (PDF ingestion, OCR latency)
- External API call latency (SAPTIVA, Aletheia)

**Structured Logging** - All services use structlog:
```python
logger.info(
    "event_name",
    user_id=user_id,
    document_id=doc_id,
    latency_ms=latency
)
```

**Optional Observability Stack** (`make obs-up`):
- Grafana (dashboards) - http://localhost:3001
- Prometheus (metrics) - http://localhost:9090
- Loki (log aggregation)
- Promtail (log shipping)
- cAdvisor (container metrics)

**Resource Overhead**: ~1.5 GB RAM, ~2 GB disk for 7 days retention.

## Security Considerations

**Authentication Flow**:
1. User registers/logs in via `/api/auth/login`
2. Backend returns JWT `access_token` (60 min) + `refresh_token` (7 days)
3. Frontend stores tokens in memory + localStorage
4. All API requests include `Authorization: Bearer {token}` header
5. Middleware validates JWT signature + expiration

**Rate Limiting** - Redis-based, configurable per endpoint:
```python
RATE_LIMIT_ENABLED=true
RATE_LIMIT_CALLS=100  # requests
RATE_LIMIT_PERIOD=60  # seconds
```

**File Upload Security**:
- Type validation: Only PDF, PNG, JPG allowed
- Size limit: 50 MB default (configurable)
- Ownership validation: Users can only access their own documents
- Temporary storage: Files stored in container tmpfs, cleaned by OS

**Secrets Management**:
- Never commit `.env` files (in `.gitignore`)
- Use `make generate-credentials` for secure random passwords
- Rotate credentials every 3 months: `make rotate-mongo-password`, `make rotate-redis-password`

## Important Files Reference

**Configuration**:
- `envs/.env.local.example` - Development environment template
- `envs/.env.prod.example` - Production environment template
- `apps/api/prompts/registry.yaml` - System prompts per model

**Key Services**:
- `apps/api/src/routers/chat.py` - Chat endpoint with file merging logic
- `apps/api/src/services/document_extraction.py` - Extraction abstraction layer
- `apps/api/src/domain/chat_strategy.py` - Strategy pattern implementation
- `apps/web/src/hooks/useFiles.ts` - File upload state management

**Database Models**:
- `apps/api/src/models/chat.py` - ChatSession, ChatMessage
- `apps/api/src/models/document.py` - Document, PageContent
- `apps/api/src/models/user.py` - User authentication

**Documentation**:
- `docs/operations/deployment.md` - Deployment runbook
- `docs/operations/resource-optimization.md` - Docker optimization guide
- `docs/testing/TESTS_E2E_GUIDE.md` - E2E testing guide
- `docs/api/REFACTOR_SUMMARY.md` - Design patterns documentation

## Common Pitfalls

1. **Don't manually edit MongoDB** - Always use Beanie ODM models to maintain validation and type safety.

2. **Don't bypass the extraction abstraction** - Always use `DocumentService.get_document_text_from_cache()` instead of direct Redis access.

3. **Don't forget to check feature flags** - Always wrap new features in environment variable checks (`NEXT_PUBLIC_FEATURE_*`).

4. **Don't use `docker compose restart` after env changes** - Use `make reload-env-service` or `make restart` (which does down/up).

5. **Don't delete volumes to fix auth errors** - Usually it's just credentials not synced. Use `make reload-env-service` first.

6. **Don't test in production first** - Always test credential rotation in dev: `make reset` (dev only), then `make rotate-*-password` in staging before prod.
