# Arquitectura OctaviOS Chat + MCP

## Panorama general

```mermaid
flowchart LR
    subgraph Frontend (Next.js App Router)
        Composer["Chat Composer\n(Zustand stores)"]
        FilesPanel["Files Panel\n(SSE events)"]
        SDK["@octavios/mcp-sdk"]
        Composer --> SDK
        FilesPanel --> Composer
    end

    subgraph Backend (FastAPI)
        APIRouters["Routers (/api/*)"]
        Middleware["Auth + Rate limit + Telemetry"]
        MCPLayer["/mcp routes\nToolRegistry + ToolSpecs"]
        Services["Domain services\n(chat, history, files, validation)"]
        Storage["MongoDB (Beanie)\nRedis cache\nMinIO\nPostgre (BI)"]
        LLM["Saptiva Client\nOCR/NLP jobs"]
    end

    Composer -->|REST /api| APIRouters
    FilesPanel -->|SSE /api/files/events| APIRouters
    SDK -->|/api/mcp| MCPLayer
    APIRouters --> Middleware --> Services --> Storage
    Services --> LLM
    MCPLayer --> Services
```

### Backend FastAPI

* **Routers** agrupados en `apps/api/src/routers`: `auth`, `chat`, `conversations`, `history`, `files`, `documents`, `deep_research`, `review`, `reports`, `intent`, `metrics`, `settings`, `features`, `stream`, etc.
* **Dominio / Servicios** (`apps/api/src/services`):
  * `chat_service.py`, `history_service.py`, `research_coordinator.py`, `deep_research_service.py`.
  * Auditores (format/logo/grammar/typography/compliance/entity_consistency/semantic_consistency).
  * Integraciones: `saptiva_client.py`, `ocr_service.py`, `minio_storage.py`, `policy_manager.py`, `report_generator.py`.
* **Infra**:
  * MongoDB (Beanie models en `apps/api/src/models`), Redis cache para rate-limit y caching de documentos, MinIO para PDFs, SSE vía `file_event_bus`.
  * Middleware: `TelemetryMiddleware`, `AuthMiddleware`, `RateLimitMiddleware`.
  * Telemetría Prometheus + OpenTelemetry centralizada en `core/telemetry.py`.

### Frontend Next.js

* Repo `apps/web` (App Router). Componentes principales en `src/app/chat/_components`.
* **State management**: múltiples stores con Zustand (`lib/stores/*`): `chat-store`, `files-store`, `audit-store`, `ui-store`, `research-store`, `history-store`, `settings-store`, `auth-store`. Persistencia selectiva con `zustand/middleware`.
* **Feature flags**: `lib/feature-flags`, `lib/features`, `settings-store` hacen fetch a `/api/feature-flags` y exponen toggles (`deep_research_enabled`, `files`, `auditInline`, etc.).
* **API client**: `lib/api-client.ts` y `lib/auth-client.ts` encapsulan llamadas REST y SSE; historial en `app/chat/_components/ChatView`.
* **Files & auditorías**: componentes en `components/files/*`, `components/validation/*`, SSE `EventSource` a `/api/files/events/{file_id}`.
* **Renderer**: chat composer habilita herramientas (`ToolsPanel`) y dispara `/api/chat/tools/audit-file`.

### Estratos de dominio & flows

| Capa | Detalle |
| --- | --- |
| **Auth / sesiones** | JWT + cookie httpOnly (`AuthMiddleware`). `/api/auth/*` usa `services/auth_service.py` (Motor + Redis tokens). |
| **Gestión de archivos** | `/api/files/upload` -> `file_ingest_service` → MinIO + OCR. SSE via `file_event_bus`. Documentos persistidos en Mongo `Document`. |
| **Chat & History** | `/api/chat` (Streaming), `/api/history/*`, `/api/conversations/*` orquestan `ChatService`, `HistoryService`, `ChatContext` (Builder/Strategy patterns). |
| **Auditor de archivos** | `execute_audit_file_tool` coordina validaciones (policy resolver, `validation_coordinator`, auditores). Crea `ValidationReport` + `ChatMessage`. |
| **Deep Research / BI** | `deep_research` router dispara `research_coordinator`, `reports` router expone PDFs, `viz_tool` (nuevo) apunta a SQL/BI. |
| **Observabilidad** | `core/telemetry` métricas: request count, durations, research histograms, tool counters (`increment_tool_invocation`). `/api/metrics` expone Prometheus. |

### Hot-spots

1. **Adjuntos**: `files.py` (upload + SSE) y `documents.py` (legacy) mueven PDFs a MinIO y cachean texto en Redis. Rate limiting y ownership checks críticas.
2. **LLM SAPTIVA**: `saptiva_client.py` gestiona retries, streaming SSE, feature toggles (mock fallback). `chat_service` y `deep_research_service` dependen directamente.
3. **OCR/NLP/SQL jobs**: `document_extraction`, `ocr_service`, `research_coordinator`, `viz_tool` (nuevo) pueden saturar CPU/IO; preferible offloading a colas en fases siguientes.
4. **Rendering/Streaming**: `stream.py`, `chat.py` (SSE + `EventSourceResponse`), `history_stream.py`.

## Tabla de endpoints → servicios → efectos

(Prefijo `/api` omitido para brevedad. Side-effects resumidos; routers comparten auth JWT salvo health/metrics públicos.)

| Endpoint (método) | Handler | Servicios / Dependencias | Side-effects |
| --- | --- | --- | --- |
| `GET /models` | `routers.models.get_models` | `Settings` | Lee configuración para lista de modelos permitidos. |
| `POST /auth/register` | `auth.register` | `services.auth_service.register_user` | Inserta usuario en Mongo, genera tokens. |
| `POST /auth/login` | `auth.login` | `authenticate_user`, Redis tokens | Set-cookie sesión + emite JWT/refresh. |
| `POST /auth/refresh` | `auth.refresh` | `refresh_access_token` | Emite nuevo JWT, actualiza cookie. |
| `GET /auth/me` | `auth.me` | `get_user_profile` | Lectura Mongo. |
| `POST /auth/logout` | `auth.logout` | `logout_user` | Blacklist tokens en Redis. |
| `GET /health/*` | `health.router` | None | Respuestas estáticas (liveness/readiness). |
| `GET /metrics` | `metrics.get_prometheus_metrics` | `core.telemetry.get_metrics` | Serializa métricas Prometheus. |
| `POST /intent` | `intent.router` | `intent_service` | Llama a Saptiva para clasificación, escribe métricas. |
| `POST /files/upload` | `files.upload_files` | `file_ingest_service`, Redis rate-limit, MinIO | Guarda archivo, crea documento, dispara SSE. |
| `GET /files/events/{id}` | `files.file_events` | `file_event_bus`, Redis/Mongo | SSE streaming con progreso, heartbeats. |
| `POST /documents/upload(-legacy)` | `documents` | `file_ingest_service` | Legacy redirect / ingest directo. |
| `GET /documents` | `documents.list_documents` | `Document` model | Lista docs por usuario/ conversación. |
| `POST /chat` | `chat.chat` | `ChatService`, `ChatResponseBuilder`, `saptiva_client`, `HistoryService`, Redis cache | Inserta mensajes, invoca LLM, crea tasks. |
| `POST /chat/{chat_id}/escalate` | `chat.escalate` | `ChatService`, `HistoryService` | Marca sesión, dispara tasks. |
| `POST /chat/tools/audit-file` | `chat.invoke_audit_file_tool` | **Nuevo:** `backend.mcp.registry.invoke("audit_file")` (fallback a `execute_audit_file_tool`) | Ejecuta validaciones, genera `ValidationReport` + `ChatMessage`. |
| `GET /history/*` | `history` | `HistoryService`, `ChatMessageModel`, `Redis cache` | Listas, exportaciones, unificaciones (SSE). |
| `GET/POST /conversations*` | `conversations` | `ChatSessionModel`, `HistoryService` | CRUD de sesiones, normaliza `tools_enabled`. |
| `GET /chat/history/{chat_id}` | `chat.get_chat_history` | `HistoryService`, `ChatMessageModel` | Paginación, optionally include system messages. |
| `POST /deep-research`, `GET /deep-research/{task}` | `deep_research` | `deep_research_service`, `research_coordinator`, `TaskModel`, SSE | Lanza jobs, consulta progreso, cancelaciones. |
| `POST /review/start|validate` | `review` | `review_service`, `validation_coordinator` | Dispara pipelines de auditoría para attachments. |
| `GET /reports/*` | `reports` | `report_generator`, MinIO/Redis | Descargas y sharing tokens. |
| `GET /features/tools` | `features` | `services.tools.DEFAULT_AVAILABLE_TOOLS` | Devuelve toggles para UI. |
| `GET/POST/DELETE /settings/saptiva-key` | `settings_router` | `settings_service` | Guarda API key cifrada. |
| `GET /stream/*` | `stream` | `streaming_service`, `history_stream` | SSE para tasks LLM. |
| `POST /chat_new_endpoint/chat` | `chat_new_endpoint` | `ChatService` (experimental) | Falta wiring final (paralelo al endpoint principal). |

> Resto de rutas (e.g., `/reports/...`, `/history/.../research`, `/metrics/research/*`, etc.) mantienen el mismo patrón: router valida, delega en servicio especializado, luego persiste en Mongo / MinIO / Redis y publica SSE cuando aplica.

## Decisión de ubicación MCP

| Criterio | **Opción A: In-process (FastAPI)** | **Opción B: Microservicio aparte** |
| --- | --- | --- |
| Complejidad inicial | ✅ Reusa app actual, comparte settings, sin despliegue adicional. | ❌ Requiere nuevo repo/imagen, contratos HTTP/WS, auth entre servicios. |
| Latencia | ✅ Llamada en memoria → ≈0.3ms overhead; comparte pool de conexiones DB/Redis. | ❌ Hop adicional (HTTP) + serialización; doble auth. |
| Despliegue / Ops | ✅ Misma imagen Docker, sin networking extra. | ❌ Necesita discovery, healthchecks, scaling separado. |
| Escala futura | Moderada: se puede shardear proceso FastAPI completo. | Alta: escalar workers específicos, aislar recursos pesados. |
| Blast radius | Medio: bug en tool puede impactar API si no se sandboxea. | Bajo: falla de tool no afecta chat if circuit-breaker. |
| Integración legacy | ✅ Endpoint `/api/chat/tools/audit-file` reusa MCP registry sin romper clientes. | ❌ Requiere cambios en chat para llamar nuevo servicio. |

**Decisión:** Fase 1 adopta **Opción A** (implementada). Permite compartir dependencias (Mongo, Redis, MinIO) y mantener compatibilidad. El diseño de `backend/mcp` mantiene contratos HTTP (`/api/mcp/*`) idénticos a los que usaría un microservicio, facilitando la **Fase 3** (extraer a contenedor) si la carga de herramientas pesadas (OCR/BI) lo amerita.

## Diseño MCP (implementado)

* **Protocolos (`backend/mcp/protocol.py`)**: `ToolSpec`, `ToolInvokeRequest`, `ToolInvokeResponse`, `ToolLimits`, `ToolInvokeContext`, `ToolError`. Todos Pydantic para fácil serialización.
* **ToolRegistry**: almacena tools por nombre/versión, valida payloads, maneja timeouts (`ToolExecutionError`), expone `list_tools` y `invoke`.
* **Rutas**: `create_mcp_router` monta `GET /api/mcp/tools` y `POST /api/mcp/invoke`, aplica auth (`get_current_user`), verifica tamaño payload, crea `ToolInvokeContext` (request_id, user_id, session_id, trace_id) y permite hook observabilidad (`increment_tool_invocation`).
* **Tools incluidos**:
  * `AuditFileTool`: adapta `execute_audit_file_tool` (validaciones + reporte). Conserva comportamiento legacy.
  * `ExcelAnalyzerTool`: valida payload y genera agregados inline (sum/avg/min/max/count) con `sample_rows`; sin data -> marca job `queued`.
  * `VizTool`: recibe query/config, genera spec Plotly/ECharts inline con dataset o agenda ejecución (status `queued`) para fuentes SQL/BI.
* **Observabilidad**: cada invocación se loguea (`request_id`, `tool`, `latency_ms`) y dispara `increment_tool_invocation`. Limita payload (KB) y expone `limits` por tool para el FE.
* **Legacy bridging**: `/api/chat/tools/audit-file` ahora invoca `app.state.mcp_registry` (fallback al servicio actual si no existe) → misma respuesta `ChatMessage`.

## Frontend SDK & activación gradual

* Nueva librería `packages/sdk`:
  * `MCPClient` (fetch + token injector).
  * `listTools()` y `invokeTool<TIn, TOut>()`.
  * `filterToolsByFlags()` permite cruzar feature flags (`/api/feature-flags`) + roles para exponer herramientas en UI.
  * `types.ts` contiene definiciones compartidas con backend (ToolSpec, ToolInvokeResponse, ToolError, ToolLimits).
* Integración propuesta:
  * `apps/web` puede importar `@octavios/mcp-sdk` en `lib/api-client` o directamente en `ToolsPanel`.
  * Feature flags existentes (Zustand `settings-store`) determinan si se muestra `audit_file`, `excel_analyzer`, `viz_tool`.
  * Result panes reutilizan patrones existentes: markdown (audit), tablas (excel), JSON spec (viz) con componentes `ValidationFindings`, `ReportPreview`.

## Observabilidad, seguridad y límites (resumen)

* `request_id` por contexto (middleware + MCP).
* Logging estructurado (structlog shim) + métricas en `/api/metrics`, contadores `copilotos_tool_invocations_total`.
* Límites: payload KB, attachments MB, timeouts por tool. `files.upload` rate-limited (Redis), MCP aplica `413` si se supera.
* Auth: JWT + scopes por tool (hook listo en MCP: `ToolInvokeContext.user_id`, gates en SDK). Documentado en `SECURITY_OBS_CHECKLIST.md`.
* PII scrubbing: validación en auditores + sanitizer `text_sanitizer.py`.

## Próximos pasos

1. Conectar FE (`ToolsPanel`) al nuevo SDK (`packages/sdk`).
2. Añadir colas/background workers para `excel_analyzer` y `viz_tool` cuando requieran acceso a Postgres/BI.
3. Completar pruebas E2E (`playwright`) cubriendo flujo chat → MCP → tool → UI.
4. Instrumentar tracing OpenTelemetry spans por tool (aprovechar `ToolInvokeContext`).
