# Plan de Refactorización: Document-Centric Architecture

**Cliente**: 414 Capital
**Proyecto**: OctaviOS Chat
**Versión**: 2.0 (Post Capital 414 fixes)
**Fecha**: 2025-11-18

---

## 🎯 Resumen Ejecutivo

### Problema Actual

El sistema de adjuntos de archivos tiene **3 problemas arquitecturales críticos**:

1. **Adjuntos = "payload bruto"**: Cada turno intenta procesar PDFs sincrónicamente → silencios/colgados
2. **Sin sesión de documentos**: No hay memoria persistente de "qué docs tiene esta conversación"
3. **UI de caja negra**: Usuario no sabe si docs están procesando, listos o fallaron

**Impacto en 414 Capital**:
- ❌ Experiencia frustrante ("se cuelga al subir PDFs")
- ❌ Pérdida de confianza (comportamiento impredecible)
- ❌ Imposible diagnosticar problemas ("no sé qué pasó")

### Solución Propuesta

**Arquitectura Document-Centric** con 4 fases de refactorización:

| Fase | Objetivo | Duración | Impacto |
|------|----------|----------|---------|
| 1 | Estado estructurado de docs | 5 días | Alto (fundación) |
| 2 | MCP tools separados | 3 días | Alto (UX crítico) |
| 3 | Orquestador resiliente | 2 días | Medio |
| 4 | Frontend UI con estados | 1 día | Alto (percepción) |

**Total**: 2 semanas (10 días laborables)

---

## 📊 Comparación: Antes vs. Después

### Flujo Actual (Post Capital 414 fixes)

```
Usuario: [adjunta report.pdf] "Resume el reporte"
  ↓
API: GET /storage/report.pdf → extract_text() → (espera 15s)
  ↓ (si falla OCR)
API: ⚠️ Warning en logs, continúa sin doc
  ↓
LLM: Responde sin contexto
  ↓
Usuario: 😕 "¿Por qué no usó el PDF?"
```

**Problemas**:
- ✅ Ya NO se cuelga (Capital 414 fix)
- ❌ Procesamiento síncrono (bloquea request)
- ❌ Usuario no sabe qué pasó con el PDF
- ❌ Próximo turno: vuelve a intentar procesar el mismo PDF

### Flujo Propuesto (Document-Centric)

```
Usuario: [adjunta report.pdf] "Resume el reporte"
  ↓
API: IngestFilesTool → "📄 Recibí report.pdf (32 págs). Procesando..."
      (respuesta inmediata < 500ms)
  ↓ (async worker)
Worker: extract_text() → segment() → cache() → status=READY
  ↓ (SSE event)
Frontend: Chip actualizado "✅ Listo"
  ↓
Usuario: "Resume el reporte" (siguiente turno)
  ↓
API: GetRelevantSegmentsTool → encuentra segmentos
  ↓
LLM: "Según el reporte (pág. 12): ..."
```

**Ventajas**:
- ✅ Respuesta inmediata (no bloquea)
- ✅ Usuario ve progreso en tiempo real
- ✅ Docs se procesan una sola vez
- ✅ Próximos turnos: reutilizan segmentos cacheados

---

## 🏗️ Arquitectura Detallada

### Componentes Nuevos

#### 1. **DocumentState Model** (Backend)

```python
class DocumentState(BaseModel):
    doc_id: str
    name: str
    status: ProcessingStatus  # UPLOADING → PROCESSING → READY
    segments_count: int
    indexed_at: datetime
```

**Reemplaza**: `ChatSession.attached_file_ids: List[str]`
**Por**: `ChatSession.documents: List[DocumentState]`

#### 2. **MCP Tools** (Backend)

```python
# Tool 1: Ingesta asíncrona
IngestFilesTool(conversation_id, file_refs)
  → Crea DocumentState
  → Dispara worker async
  → Retorna "Procesando..." (inmediato)

# Tool 2: Recuperación de contexto
GetRelevantSegmentsTool(conversation_id, question)
  → Filtra docs con status=READY
  → Busca segmentos relevantes
  → Retorna snippets estructurados
```

#### 3. **Orquestador** (Backend)

```python
# streaming_handler.py (refactorizado)

STEP 1: ¿Nuevos adjuntos? → IngestFilesTool
STEP 2: Recuperar segmentos → GetRelevantSegmentsTool
STEP 3: Construir prompt → system + context + segments
STEP 4: Stream LLM → respuesta
STEP 5: Manejo de errores → warning/info events (no bloquea)
```

#### 4. **Frontend UI** (React/Next.js)

```tsx
// Document chips con estados
<DocumentChip status="processing">
  🔄 report.pdf (32 págs) - Procesando...
</DocumentChip>

<DocumentChip status="ready">
  ✅ guide.pdf (10 págs) - Listo
</DocumentChip>

<DocumentChip status="failed">
  ❌ corrupted.pdf - Error
</DocumentChip>

// System messages en chat
<SystemMessage type="info">
  ℹ️ Tengo 2 documentos en procesamiento.
  Responderé sin ellos por ahora.
</SystemMessage>
```

---

## 📅 Roadmap de Implementación

### **Fase 1: Estado de Documentos** (Días 1-5)

**Owner**: Backend team
**Reviewer**: Arquitectura + 414 Capital

| Día | Tarea | Entregable |
|-----|-------|------------|
| 1-2 | Crear `DocumentState` model + tests | `apps/api/src/models/document_state.py` |
| 2-3 | Actualizar `ChatSession` model | `ChatSession.documents: List[DocumentState]` |
| 3-4 | Migration script | `scripts/migrate_attached_files_to_documents.py` |
| 5 | Validación en staging | Zero data loss, backward compatible |

**Criterios de aceptación**:
- [ ] Migration script ejecutado en staging
- [ ] `documents` field funcional
- [ ] Tests unitarios >= 95% coverage
- [ ] Zero data loss verificado

---

### **Fase 2: MCP Tools** (Días 6-8)

**Owner**: Backend team + MCP specialist
**Dependencies**: Fase 1 completada

| Día | Tarea | Entregable |
|-----|-------|------------|
| 6 | Tool `ingest_files` + tests | `apps/api/src/mcp/tools/ingest_files.py` |
| 7 | Tool `get_relevant_segments` + worker | `apps/api/src/services/document_tasks.py` |
| 8 | Integration tests | `tests/integration/test_document_workflow.py` |

**Criterios de aceptación**:
- [ ] `IngestFilesTool` retorna < 500ms
- [ ] Worker procesa PDFs correctamente
- [ ] `GetRelevantSegmentsTool` recupera segmentos
- [ ] Integration tests pasan

---

### **Fase 3: Orquestador** (Días 9-10)

**Owner**: Backend team
**Dependencies**: Fase 2 completada

| Día | Tarea | Entregable |
|-----|-------|------------|
| 9 | Refactorizar `streaming_handler.py` | Uso de nuevos tools |
| 10 | Error recovery tests | `tests/integration/test_error_recovery.py` |

**Criterios de aceptación**:
- [ ] Orquestador usa MCP tools
- [ ] Error handling resiliente
- [ ] SSE events documentados
- [ ] Zero regressions en chat

---

### **Fase 4: Frontend UI** (Día 11)

**Owner**: Frontend team
**Dependencies**: Fase 3 completada

| Tarea | Entregable |
|-------|------------|
| Mañana: Document chips + SSE handler | `components/chat/DocumentChip.tsx` |
| Tarde: System messages + polling | `components/chat/SystemMessage.tsx` |

**Criterios de aceptación**:
- [ ] Chips muestran estados correctos
- [ ] SSE events actualizan UI
- [ ] System/warning/info messages visibles
- [ ] No "colgados" (siempre feedback)

---

## 💰 ROI Estimado

### Costos

| Recurso | Tiempo | Costo Estimado |
|---------|--------|----------------|
| Backend dev (senior) | 10 días | $15,000 USD |
| Frontend dev | 1 día | $1,200 USD |
| QA testing | 2 días | $1,500 USD |
| DevOps (migration support) | 1 día | $800 USD |
| **TOTAL** | **14 días** | **$18,500 USD** |

### Beneficios

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| Tiempo de respuesta (con PDFs) | 15-30s | < 1s | **95% más rápido** |
| Tasa de errores silenciosos | 15% | 0% | **100% reducción** |
| Satisfacción usuario (NPS) | 6/10 | 9/10 | **+50%** |
| Tickets de soporte (PDFs) | ~20/mes | < 5/mes | **-75%** |

**ROI**: Recuperación en **2 meses** (reducción de churn + menos soporte)

---

## ⚠️ Riesgos y Mitigación

### Riesgo 1: Migración de datos falla

**Probabilidad**: Media
**Impacto**: Alto (pérdida de datos)

**Mitigación**:
- ✅ Dry-run obligatorio antes de ejecutar
- ✅ Backup de `chat_sessions` collection
- ✅ Rollback plan (mantener `attached_file_ids`)
- ✅ Validación automática post-migración

### Riesgo 2: Workers async saturan recursos

**Probabilidad**: Media
**Impacto**: Medio (degradación performance)

**Mitigación**:
- ✅ Rate limiting en worker queue
- ✅ Timeout en procesamiento (max 60s)
- ✅ Monitoreo de CPU/memoria
- ✅ Auto-scaling de workers

### Riesgo 3: Frontend no recibe SSE events

**Probabilidad**: Baja
**Impacto**: Bajo (polling como fallback)

**Mitigación**:
- ✅ Polling cada 3s como fallback
- ✅ Retry logic en SSE connection
- ✅ Logs detallados de eventos
- ✅ Alertas si SSE falla > 5min

---

## 📈 Métricas de Éxito

### KPIs Técnicos

| Métrica | Target | Medición |
|---------|--------|----------|
| Tiempo de ingesta | < 500ms | Prometheus timer |
| Tiempo de procesamiento | < 30s | Worker logs |
| Tasa de éxito de migration | >= 99% | Migration script output |
| Coverage de tests | >= 90% | pytest --cov |

### KPIs de Negocio

| Métrica | Baseline | Target (1 mes) |
|---------|----------|----------------|
| Tickets "PDF no funciona" | 20/mes | < 5/mes |
| NPS (414 Capital) | 6/10 | 9/10 |
| Tiempo promedio de respuesta | 15s | < 2s |
| Tasa de retry (usuarios) | 30% | < 10% |

---

## ✅ Criterios de Aprobación

Para aprobar despliegue a producción:

### Checklist Técnico

- [ ] Todas las fases completadas (1-4)
- [ ] Tests pasan >= 90%
- [ ] Migration ejecutada en staging sin errores
- [ ] Performance benchmarks cumplidos
- [ ] Zero regressions en funcionalidad existente
- [ ] Documentación actualizada

### Checklist de Negocio

- [ ] Validación con 414 Capital en staging
- [ ] Feedback positivo de stakeholders
- [ ] Plan de rollback documentado
- [ ] Runbook de operaciones actualizado
- [ ] Monitoreo configurado (Prometheus/Grafana)

---

## 🔗 Referencias

### Documentos Técnicos

- [Fase 1: Document State](./PHASE1_DOCUMENT_STATE.md)
- [Fase 2: MCP Tools](./PHASE2_MCP_TOOLS.md)
- [Fase 3: Orchestrator](./PHASE3_ORCHESTRATOR.md)
- [Fase 4: Frontend UX](./PHASE4_FRONTEND_UX.md)

### Contexto del Proyecto

- [Capital 414 Success Report](../CAPITAL414_SUCCESS_REPORT.md) - Fixes tácticos implementados
- [CLAUDE.md](../../CLAUDE.md) - Arquitectura actual del sistema

---

## 📞 Contactos

| Rol | Responsable | Email |
|-----|-------------|-------|
| Tech Lead | [TBD] | tech-lead@saptiva.com |
| Backend Dev | [TBD] | backend@saptiva.com |
| Frontend Dev | [TBD] | frontend@saptiva.com |
| 414 Capital Contact | [TBD] | 414capital@client.com |
| DevOps | [TBD] | devops@saptiva.com |

---

## 🚀 Próximos Pasos

1. **Esta semana**:
   - [ ] Presentar plan a 414 Capital
   - [ ] Aprobar presupuesto ($18.5k)
   - [ ] Asignar recursos (backend + frontend devs)

2. **Semana 1**:
   - [ ] Iniciar Fase 1 (Document State)
   - [ ] Daily standups para tracking

3. **Semana 2**:
   - [ ] Completar Fases 2-4
   - [ ] Deploy a staging
   - [ ] Validación con 414 Capital

4. **Semana 3**:
   - [ ] Deploy a producción
   - [ ] Monitoreo intensivo
   - [ ] Retrospectiva

---

**Aprobado por**: _________________
**Fecha**: _________________
**Firma**: _________________
