# Plan de Migración MCP

## Objetivo
Agregar una capa MCP reusable sin romper clientes actuales del “auditor de archivos”, habilitar nuevas tools (Excel, BI) y dejar camino hacia un microservicio dedicado si el load lo requiere.

## Línea de tiempo y fases

### Fase 0 – Pre-flight
1. **Inventario**: mapear routers, servicios, sesiones y feature flags (documentado en `ARCHITECTURE.md`).
2. **Compatibilidad**: identificar endpoints críticos a mantener (`/api/chat/tools/audit-file`, `/api/files/upload`, `/api/feature-flags`).
3. **Observabilidad base**: validar `/api/metrics` y logging structlog para poder comparar antes/después.

### Fase 1 – MCP in-process (implementado)
1. **Añadir `backend/mcp`** con `protocol`, `registry`, `routes`, `tools/*`.
2. **Montar rutas**: `create_mcp_router` dentro del mismo FastAPI (`/api/mcp/tools`, `/api/mcp/invoke`), exigir JWT y request tracing.
3. **Registrar tools mínimas**: `audit_file` (wrap servicio actual), `excel_analyzer`, `viz_tool`.
4. **Compatibilidad**: actualizar `/api/chat/tools/audit-file` para invocar MCP internamente (fallback al servicio viejo si no hay registry).
5. **SDK TS**: publicar `packages/sdk` con `MCPClient`, `listTools`, `invokeTool`, `filterToolsByFlags`.
6. **Shadow traffic**: activar flag en FE para listar tools vía `/api/mcp/tools` sin ejecutar (comprobar latencia < 50ms).
7. **Validación**: unit tests de registry + smoke manual con `curl /api/mcp/invoke`.

### Fase 2 – Herramientas pesadas → jobs/colas
1. **Excel Analyzer**: cuando se conecte a archivos grandes (S3/MinIO) o Postgres, mover la ejecución pesada a una cola (Celery/RQ) y hacer que MCP sólo orqueste (`status=queued`).
2. **Viz Tool**: ejecutar queries BI en workers aislados (limitar CPU/IO), cachear resultados en Redis/Postgres y devolver share tokens a UI.
3. **Auditorías OCR/ETL**: si `execute_audit_file_tool` supera SLA, envolver en job y usar statuses en tool output.
4. **Rate limiting/quotas**: añadir contadores por tool (Redis) y exponer métricas en Prometheus (latencia p95, error rate).
5. **Contratos compartidos**: generar OpenAPI / SDK TS automáticamente en CI para evitar drift.

### Fase 3 – Microservicio MCP (opcional)
1. **Extraer contenedor**: empaquetar `backend/mcp` en imagen ligera (FastAPI o serverless) reusando `ToolRegistry`.
2. **Contrato externo**: conservar `/mcp/*` HTTP/WS. FastAPI principal hablaría vía HTTP (o message bus) con autenticación mTLS/JWT inter-service.
3. **Escalado independiente**: autoscaling por tool (GPU para OCR, CPU para BI). Añadir circuit breakers en backend principal.
4. **Observabilidad cross-service**: propagar `traceparent` y `request_id`, unificar métricas en Prometheus/Grafana.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
| --- | --- |
| Límite de payload/timeout rompe clientes | Validar `payload_size_kb` y exponer `limits` en `/api/mcp/tools`; SDK aplica chunking y warnings en UI. |
| Auditor legacy produce esquema distinto | `AuditFileTool` mantiene output original y endpoint resume `ChatMessage` igual que antes. |
| Falta de dependencias (Mongo, Redis, MinIO) en ambientes locales | Documentar variables obligatorias y proveer mocks en tests (ver `tests/unit/test_mcp_registry.py`). |
| Latencia adicional en `/api/chat/tools/audit-file` | Registro in-process (<1ms); monitorear `copilotos_tool_invocations_total` + latencia en Prometheus. |
| Nuevas tools acceden a data sensible | `ToolInvokeContext.user_id` y feature flags + roles en SDK, `SECURITY_OBS_CHECKLIST.md` detalla scopes. |

## Rollback
1. Mantener `execute_audit_file_tool` importable directamente; si MCP falla, se puede desregistrar `AuditFileTool` y el endpoint legacy usará fallback automáticamente.
2. Para tools nuevas (`excel_analyzer`, `viz_tool`), feature flags permiten ocultarlas sin redeploy (FE y BE chequean flag).
3. Revertir rutas `/api/mcp/*` removiendo `app.include_router` sin impactar otras partes.

## Toggles / flags
* `featureFlags.tools.audit_file`, `excel_analyzer`, `viz_tool`: control FE.
* (Opcional) Flag server-side para activar shadow invocations (`MCP_SHADOW=true` → ejecutar tool y descartar respuesta).
* Rate limit por tool (Redis key `tool:{name}:user:{id}`) configurable via settings.

## Métricas de aceptación
| Métrica | Objetivo |
| --- | --- |
| **Compatibilidad** | `/api/chat/tools/audit-file` responde `ChatMessage` idéntico, sin cambios en UI actual. |
| **GET /api/mcp/tools** | Lista ≥3 tools con `limits` y `capabilities`. Latencia < 50ms P95. |
| **POST /api/mcp/invoke** | Ruta general enruta a cada tool; errores entregan `ToolError` estructurado. |
| **Tipado** | Pydantic payloads (BE) + tipos TS (SDK). |
| **Observabilidad** | `copilotos_tool_invocations_total{tool}` incrementa; logs incluyen `request_id`. |
| **CI** | Pytest unitario `tests/unit/test_mcp_registry.py` + lint/build de SDK; generación de OpenAPI/SDK documentada para next iteration. |
