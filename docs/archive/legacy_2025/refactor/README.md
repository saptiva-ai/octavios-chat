# 📚 Documentación de Refactorización - Document-Centric Architecture

**Proyecto**: OctaviOS Chat v2.0
**Cliente**: 414 Capital
**Autor**: Claude Code + Equipo Backend
**Fecha**: 2025-11-18

---

## 🎯 Propósito

Esta carpeta contiene el **plan completo de refactorización arquitectural** para transformar el sistema de adjuntos de archivos de OctaviOS de un modelo "payload bruto por turno" a una **arquitectura document-centric** con estado persistente y procesamiento asíncrono.

---

## 📖 Índice de Documentos

### 1. [**EXECUTIVE_SUMMARY.md**](./EXECUTIVE_SUMMARY.md)
**Para quién**: C-level, Product Managers, 414 Capital stakeholders

**Contenido**:
- Resumen ejecutivo del problema y solución
- Comparación antes/después con diagramas de flujo
- ROI estimado ($18.5k inversión, recuperación en 2 meses)
- Roadmap de 2 semanas con hitos claros
- Riesgos y mitigación
- Métricas de éxito (KPIs técnicos y de negocio)
- Criterios de aprobación para producción

**Cuándo leer**: Antes de aprobar el proyecto

---

### 2. [**PHASE1_DOCUMENT_STATE.md**](./PHASE1_DOCUMENT_STATE.md)
**Para quién**: Backend developers, DB engineers

**Contenido** (Días 1-5):
- Diseño del modelo `DocumentState` con ciclo de vida (UPLOADING → PROCESSING → READY)
- Modificación de `ChatSession` model
- Script de migración de datos (`attached_file_ids` → `documents`)
- Tests unitarios y de integración
- Plan de rollback
- Validación en staging

**Archivos a crear**:
- `apps/api/src/models/document_state.py`
- `scripts/migrate_attached_files_to_documents.py`
- `tests/unit/models/test_document_state.py`

**Criterios de aceptación**: Migration exitosa, zero data loss, backward compatible

---

### 3. [**PHASE2_MCP_TOOLS.md**](./PHASE2_MCP_TOOLS.md)
**Para quién**: Backend developers, MCP specialists

**Contenido** (Días 6-8):
- Tool `IngestFilesTool`: Ingesta asíncrona de archivos
- Tool `GetRelevantSegmentsTool`: Recuperación de contexto para RAG
- Background worker `process_document_task`: Procesamiento async con Celery
- Segmentación de texto y caching
- Integration tests end-to-end

**Archivos a crear**:
- `apps/api/src/mcp/tools/ingest_files.py`
- `apps/api/src/mcp/tools/get_segments.py`
- `apps/api/src/services/document_tasks.py`
- `tests/integration/test_document_workflow.py`

**Criterios de aceptación**: Ingesta < 500ms, procesamiento < 30s, segmentos recuperables

---

### 4. [**PHASE3_ORCHESTRATOR.md**](./PHASE3_ORCHESTRATOR.md)
**Para quién**: Backend developers

**Contenido** (Días 9-10):
- Refactorización de `streaming_handler.py` para usar nuevos MCP tools
- Separación de flujo: ingesta async → retrieval → prompt → stream
- Manejo de errores resiliente (cada turno independiente)
- SSE events especificados (system, warning, info, document_ready)
- Tests de error recovery

**Archivos a modificar**:
- `apps/api/src/routers/chat/handlers/streaming_handler.py`
- `apps/api/src/domain/chat_context.py` (agregar `new_file_refs`)

**Criterios de aceptación**: Zero regressions, error handling resiliente, SSE events funcionando

---

### 5. [**PHASE4_FRONTEND_UX.md**](./PHASE4_FRONTEND_UX.md)
**Para quién**: Frontend developers, UX designers

**Contenido** (Día 11):
- Componente `DocumentChip` con estados visuales (uploading/processing/ready/failed)
- Store Zustand para `DocumentState`
- SSE event handler con updates de UI
- Componente `SystemMessage` para mensajes de sistema/warning/info
- Polling como fallback si SSE falla

**Archivos a crear**:
- `apps/web/src/types/document.ts`
- `apps/web/src/lib/stores/documentStore.ts`
- `apps/web/src/components/chat/DocumentChip.tsx`
- `apps/web/src/components/chat/SystemMessage.tsx`
- `apps/web/src/lib/chat/useSSEHandler.ts`

**Criterios de aceptación**: Estados visibles en tiempo real, no "colgados", UX clara

---

## 🗺️ Roadmap Visual

```
Semana 1
├── Día 1-2: DocumentState model + tests
├── Día 3-4: Migration script
├── Día 5: Validación staging (Fase 1 ✅)
│
Semana 2
├── Día 6: IngestFilesTool
├── Día 7: GetRelevantSegmentsTool + worker
├── Día 8: Integration tests (Fase 2 ✅)
├── Día 9: Orquestador refactor
├── Día 10: Error recovery tests (Fase 3 ✅)
└── Día 11: Frontend UI (Fase 4 ✅)

Semana 3
└── Deploy a producción + monitoreo
```

---

## 🎯 Problema vs. Solución (TL;DR)

### ❌ Problema Actual

```
Usuario: [adjunta report.pdf] "Resume esto"
Backend: (procesa síncrono 15s) → timeout → error silencioso
Usuario: 😕 "¿Por qué no responde?"
```

### ✅ Solución Propuesta

```
Usuario: [adjunta report.pdf]
Backend: "📄 Recibí report.pdf. Procesando..." (inmediato)
Worker: (procesa async en background)
Backend: (SSE) "✅ report.pdf listo"
Usuario: "Resume esto"
Backend: (usa segmentos cacheados) "Según el reporte pág. 12..."
```

---

## 📊 Métricas Clave

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| Tiempo de respuesta (con PDFs) | 15-30s | < 1s | **95%** ⬇️ |
| Tasa de errores silenciosos | 15% | 0% | **100%** ⬇️ |
| NPS (414 Capital) | 6/10 | 9/10 | **+50%** ⬆️ |
| Tickets de soporte | 20/mes | < 5/mes | **75%** ⬇️ |

---

## 🚀 Cómo Usar Esta Documentación

### Para Product Managers / Stakeholders
1. Leer `EXECUTIVE_SUMMARY.md` primero
2. Revisar ROI y riesgos
3. Aprobar presupuesto y timeline

### Para Arquitectos / Tech Leads
1. Leer `EXECUTIVE_SUMMARY.md` para contexto
2. Revisar las 4 fases en orden
3. Validar diseño técnico
4. Asignar recursos

### Para Developers (Backend)
1. Empezar con `PHASE1_DOCUMENT_STATE.md`
2. Implementar en orden: Fase 1 → 2 → 3
3. Ejecutar tests después de cada fase
4. Revisar criterios de aceptación

### Para Developers (Frontend)
1. Esperar a que Fase 3 esté completa
2. Implementar `PHASE4_FRONTEND_UX.md`
3. Integrar con SSE events del backend

---

## 🔗 Referencias Adicionales

### Documentación del Proyecto
- [CLAUDE.md](../../CLAUDE.md) - Arquitectura actual del sistema
- [Capital 414 Success Report](../CAPITAL414_SUCCESS_REPORT.md) - Fixes tácticos ya implementados
- [README.md](../../README.md) - Documentación general del proyecto

### Contexto de 414 Capital
- Los fixes tácticos ya resuelven los síntomas (errores silenciosos, identidad Qwen)
- Esta refactorización resuelve los **problemas arquitecturales raíz**
- Cliente aprobó POC basado en fixes tácticos
- Refactorización = siguiente sprint después de validación

---

## ⚠️ Avisos Importantes

### 🔴 CRÍTICO
- **NO ejecutar migration script en producción sin backup completo**
- **NO saltarse Fase 1** - es la fundación de todo
- **NO desplegar sin validación de 414 Capital en staging**

### 🟡 IMPORTANTE
- Workers async requieren Celery/Redis configurados
- Frontend depende de SSE events - validar compatibilidad de browsers
- Migration puede tomar 5-10 minutos en DBs grandes

### 🟢 RECOMENDACIONES
- Ejecutar migration en horario de bajo tráfico (madrugada)
- Tener DBA disponible durante migration
- Monitorear métricas durante primeras 24h post-deploy

---

## 📞 Contacto

**Preguntas técnicas**: backend@saptiva.com
**Preguntas de negocio**: product@saptiva.com
**Urgencias 414 Capital**: 414capital@client.com

---

## 📝 Changelog

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | 2025-11-18 | Plan inicial de refactorización |
| 1.1 | TBD | Ajustes post-review de arquitectura |
| 2.0 | TBD | Actualización post-implementación |

---

## ✅ Estado del Proyecto

- [x] Capital 414 fixes tácticos implementados (v1.0)
- [x] Plan de refactorización documentado (este directorio)
- [ ] Fase 1: Document State (pendiente)
- [ ] Fase 2: MCP Tools (pendiente)
- [ ] Fase 3: Orchestrator (pendiente)
- [ ] Fase 4: Frontend UX (pendiente)
- [ ] Deploy a producción (pendiente)

**Última actualización**: 2025-11-18
**Próxima revisión**: Después de aprobación de stakeholders
