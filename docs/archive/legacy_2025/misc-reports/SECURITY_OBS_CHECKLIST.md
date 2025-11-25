# Seguridad & Observabilidad – Checklist MCP/Chat

## Autenticación y autorización
- [x] **JWT obligatorio** en `/api/mcp/*` (usa `get_current_user`).
- [x] Middleware `AuthMiddleware` valida tokens y adjunta `request.state.user_id`.
- [ ] Definir **scopes/roles por tool**: SDK expone `filterToolsByFlags()` + `ToolGate` para filtrar por rol (`admin`, `analyst`, etc.). Backend puede extender `ToolInvokeContext.metadata` con roles para enforcement server-side.

## Acceso por herramienta
- [x] `ToolSpec.limits` (timeout/payload/attachment) anunciado en discovery.
- [x] `ToolRegistry.resolve` aplica payload-size guard y `413` si excede.
- [ ] Configurar `Redis` counters por `user_id + tool` para rate limiting.
- [ ] Añadir `allowed_roles` en `ToolSpec` cuando existan políticas formales.

## Manejo de datos sensibles / PII
- [x] `ToolInvokeContext.request_id/user_id/session_id` permite rastrear uso.
- [x] Auditorías reutilizan `text_sanitizer` y `validation_coordinator` (findings ya anonimizan posiciones).
- [ ] Para Excel/BI, sanitizar columnas marcadas como PII antes de regresar previews (`excel_analyzer` future hook).
- [ ] Revisar logs para evitar contenido de documentos (usar resumen, no payload completo).

## Límite de archivos / payload
- [x] `files.upload` rate limit (Redis sliding window 5/min).
- [x] MCP `payload_size_kb` chequea y bloquea > `ToolLimits.max_payload_kb`.
- [ ] Documentar tamaño máximo de attachments en FE (selector + dropzone).

## Telemetría y trazabilidad
- [x] `request_id`: generado por middleware y propagado a MCP + logs.
- [x] Métrica `copilotos_tool_invocations_total{tool}` incrementada en `create_app`.
- [x] `/api/metrics` incluye collectors (requests, research, cache, doc ingest).
- [ ] Añadir histogramas específicos por tool (`tool_latency_seconds`) y traces OTEL (`ToolInvokeContext` ya tiene `trace_id`).

## Logging estructurado
- [x] Todos los nuevos módulos usan shim `backend/mcp/_logging.get_logger()` → structlog/logging.
- [ ] Configurar scrubbing (regex para JWT, emails) en `core/logging` si aún no existe.
- [ ] Alinear formato JSON con SIEM (campo `tool`, `user_id`, `latency_ms`, `ok/error`).

## Secrets / credenciales
- [x] API key de SAPTIVA gestionada en `/api/settings/saptiva-key`.
- [ ] Si MCP accede a Postgres/BI, usar vault/per-file envs separados y no compartir con FastAPI base.

## Pruebas y CI
- [x] Unit tests para registry/router (`tests/unit/test_mcp_registry.py`) – aseguran discovery e invoke.
- [ ] Contract tests HTTP -> MCP (usar HTTPX client + fixtures).
- [ ] E2E Playwright: flujo chat → tool → render (pendiente).
- [ ] CI: compilar SDK (`pnpm --filter @octavios/mcp-sdk build`) y publicar tipado.

## Operaciones
- [x] `app.state.mcp_registry` permite habilitar/deshabilitar tools sin reiniciar (llamando `register`/`unregister` al boot).
- [ ] Añadir `/mcp/tools/:name` admin endpoints para toggles runtime (future).
- [x] Rollback sencillo: remover tool del registry y endpoint legacy sigue funcionando.
