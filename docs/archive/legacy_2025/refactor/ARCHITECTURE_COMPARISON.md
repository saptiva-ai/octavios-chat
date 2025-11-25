# Comparación de Arquitecturas: Antes vs. Después

**Documento**: Análisis arquitectural detallado
**Audiencia**: Tech leads, arquitectos, senior developers

---

## 🏗️ Arquitectura Actual (Post Capital 414 Fixes)

### Diagrama de Flujo

```
┌─────────────┐
│   Usuario   │
│ [adjunta    │
│  report.pdf]│
└──────┬──────┘
       │
       │ POST /api/chat
       │ { message: "Resume",
       │   file_ids: ["doc-123"] }
       ▼
┌──────────────────────────────────────────┐
│         API Gateway                       │
│  /api/chat/message (streaming_handler)   │
└──────┬───────────────────────────────────┘
       │
       │ 1. Validar auth
       │ 2. Cargar ChatSession
       │ 3. Procesar archivos (SÍNCRONO)
       ▼
┌──────────────────────────────────────────┐
│    DocumentService.get_text_from_cache   │
│                                           │
│    for file_id in file_ids:               │
│      ├─ cache_key = f"doc:{file_id}"     │
│      ├─ cached = redis.get(cache_key)    │
│      │                                    │
│      └─ if not cached:                   │
│           ├─ GET /storage/file           │
│           ├─ extract_text() ─────────┐   │
│           │   (pypdf → 15s)          │   │
│           │   (OCR → 30s)            │   │
│           │                          │   │
│           └─ redis.set(cache_key) ◄──┘   │
│                                           │
│    PROBLEMA: Bloquea request completo    │
└──────┬───────────────────────────────────┘
       │
       │ 4. Si extraction falla:
       │    → warning (no bloquea)
       │ 5. Continuar sin docs
       ▼
┌──────────────────────────────────────────┐
│      Prompt Construction                  │
│                                           │
│  system_prompt = registry.resolve(model) │
│  if doc_texts:                            │
│    system_prompt += doc_texts            │
│                                           │
│  messages = build_messages(...)          │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         Saptiva LLM                       │
│  (Streaming response)                     │
└──────┬───────────────────────────────────┘
       │
       │ SSE chunks
       ▼
┌──────────────────────────────────────────┐
│         Frontend                          │
│  - Recibe chunks                          │
│  - PROBLEMA: No sabe si PDF se procesó    │
│  - Si hubo error: silencio               │
└───────────────────────────────────────────┘
```

### Problemas Identificados

| # | Problema | Severidad | Impacto |
|---|----------|-----------|---------|
| 1 | Procesamiento síncrono de PDFs | 🔴 Alta | Request timeout (15-30s) |
| 2 | Re-procesamiento en cada turno | 🟡 Media | Desperdicio de recursos |
| 3 | Sin estado de documentos | 🟡 Media | Usuario no sabe qué pasó |
| 4 | Error handling reactivo | 🟢 Baja | Ya resuelto en Capital 414 fix |

---

## 🚀 Arquitectura Propuesta (Document-Centric)

### Diagrama de Flujo

```
┌─────────────┐
│   Usuario   │
│ [adjunta    │
│  report.pdf]│
└──────┬──────┘
       │
       │ POST /api/chat
       │ { message: "Resume",
       │   file_ids: ["doc-123"] }
       ▼
┌──────────────────────────────────────────┐
│         API Gateway                       │
│  /api/chat/message (streaming_handler)   │
└──────┬───────────────────────────────────┘
       │
       │ 1. Validar auth
       │ 2. Cargar ChatSession
       │ 3. Detectar nuevos adjuntos
       ▼
┌──────────────────────────────────────────┐
│  ¿Hay nuevos file_ids?                   │
│                                           │
│  new_files = [f for f in file_ids        │
│               if f not in session.docs]  │
└──────┬────────────────┬──────────────────┘
       │ SÍ             │ NO
       ▼                │
┌──────────────────┐    │
│ IngestFilesTool  │    │
│                  │    │
│ 1. Crear         │    │
│    DocumentState │    │
│    (status=      │    │
│     UPLOADING)   │    │
│                  │    │
│ 2. Guardar en    │    │
│    session.docs  │    │
│                  │    │
│ 3. Dispatch      │    │
│    async worker  │    │
│    ┌──────────┐  │    │
│    │ Celery   │  │    │
│    │ Queue    │  │    │
│    └────┬─────┘  │    │
│         │        │    │
│ 4. Return        │    │
│    (< 500ms)     │    │
│    "Procesando"  │    │
└──────┬───────────┘    │
       │                │
       │ SSE event      │
       │ "system"       │
       ▼                │
   Frontend             │
   actualiza UI         │
   [🔄 Procesando...]   │
                        │
   ┌─────────────────┐  │
   │ Background      │  │
   │ Worker          │  │
   │                 │  │
   │ 1. GET storage  │  │
   │ 2. extract_text │  │
   │    (15-30s)     │  │
   │ 3. segment()    │  │
   │ 4. cache()      │  │
   │ 5. Update       │  │
   │    status=READY │  │
   │                 │  │
   │ 6. SSE event    │  │
   │    "doc_ready"  │  │
   └─────────────────┘  │
          │              │
          ▼              │
      Frontend           │
      [✅ Listo]         │
                         │
       ┌─────────────────┘
       │ (continúa mientras worker procesa)
       │
       ▼
┌──────────────────────────────────────────┐
│  GetRelevantSegmentsTool                  │
│                                           │
│  1. Filter session.docs where            │
│     status == READY                       │
│                                           │
│  2. Load segments from cache             │
│     segments = redis.get(f"seg:{doc}")   │
│                                           │
│  3. Score/rank by relevance              │
│     score = keyword_match(seg, question) │
│                                           │
│  4. Return top N segments                │
│     (< 200ms)                             │
└──────┬───────────────────────────────────┘
       │
       │ segments: [
       │   {doc: "report.pdf", page: 12, text: "..."},
       │   {doc: "guide.pdf", page: 3, text: "..."}
       │ ]
       ▼
┌──────────────────────────────────────────┐
│      Prompt Construction                  │
│                                           │
│  system_prompt = registry.resolve(model) │
│  if segments:                             │
│    context = format_segments(segments)   │
│    system_prompt += context              │
│                                           │
│  messages = build_messages(...)          │
└──────┬───────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│         Saptiva LLM                       │
│  (Streaming response)                     │
│                                           │
│  "Según el reporte (pág. 12): ..."       │
└──────┬───────────────────────────────────┘
       │
       │ SSE chunks
       ▼
┌──────────────────────────────────────────┐
│         Frontend                          │
│  - Recibe chunks                          │
│  - Ve estado de docs en tiempo real       │
│  - Mensajes de sistema claros             │
└───────────────────────────────────────────┘
```

---

## 📊 Comparación Detallada

### 1. Modelo de Datos

#### ANTES
```python
# ChatSession
class ChatSession(Document):
    attached_file_ids: List[str] = Field(default_factory=list)
    # Solo IDs, sin metadatos
```

**Problemas**:
- ❌ No sé si un doc está procesado o no
- ❌ No sé si falló el procesamiento
- ❌ No sé cuándo fue procesado
- ❌ No sé cuántos segmentos tiene

#### DESPUÉS
```python
# DocumentState
class DocumentState(BaseModel):
    doc_id: str
    name: str
    status: ProcessingStatus  # UPLOADING/PROCESSING/READY/FAILED
    segments_count: int
    indexed_at: datetime
    error: Optional[str]

# ChatSession
class ChatSession(Document):
    documents: List[DocumentState] = Field(default_factory=list)
    # attached_file_ids kept for backward compatibility
```

**Ventajas**:
- ✅ Estado explícito por documento
- ✅ Metadatos estructurados
- ✅ Auditable (indexed_at, error messages)
- ✅ Backward compatible (migration script)

---

### 2. Procesamiento de Archivos

#### ANTES
```python
# streaming_handler.py
async def _stream_chat_response(...):
    if context.document_ids:
        # SÍNCRONO - bloquea request
        doc_texts = await DocumentService.get_document_text_from_cache(
            document_ids=context.document_ids
        )
        # Si cache miss → extract_text() aquí mismo (15-30s)
```

**Problemas**:
- ❌ Bloquea el request de chat
- ❌ Usuario espera sin feedback
- ❌ Timeout si PDF es muy grande
- ❌ Re-procesa en cada turno si cache expira

#### DESPUÉS
```python
# streaming_handler.py
async def _stream_chat_response(...):
    # PASO 1: Ingestar nuevos archivos (async)
    if context.new_file_refs:
        result = await IngestFilesTool().execute(...)
        yield {"event": "system", "data": result["message"]}
        # NO bloquea - worker procesa en background

    # PASO 2: Recuperar segmentos de docs listos
    retrieval = await GetRelevantSegmentsTool().execute(...)
    # Solo docs con status=READY (< 200ms)
```

**Ventajas**:
- ✅ Respuesta inmediata (< 500ms)
- ✅ Procesamiento en background
- ✅ Usuario ve progreso en tiempo real
- ✅ Segmentos persistentes (no re-procesa)

---

### 3. Manejo de Errores

#### ANTES
```python
try:
    doc_texts = await get_document_text_from_cache(...)
except Exception as e:
    # Log warning pero continúa
    logger.warning("Failed to load docs", error=str(e))
    doc_texts = None
```

**Problemas**:
- ⚠️ Usuario no sabe que falló
- ⚠️ Próximo turno: reintenta (loop infinito)
- ⚠️ No hay forma de diagnosticar

#### DESPUÉS
```python
try:
    result = await IngestFilesTool().execute(...)
except Exception as e:
    # Emite evento SSE de warning
    yield {
        "event": "warning",
        "data": {
            "message": f"⚠️ No pude procesar {filename}: {error}"
        }
    }
    # Marca DocumentState como FAILED
    doc_state.mark_failed(str(e))
```

**Ventajas**:
- ✅ Usuario ve mensaje claro
- ✅ Estado persiste (no reintenta infinito)
- ✅ Diagnóstico en DB (doc.error field)
- ✅ Conversación continúa sin bloquearse

---

### 4. Experiencia de Usuario

#### ANTES

**Timeline del usuario**:
```
00:00 - Usuario: [adjunta report.pdf] "Resume esto"
00:01 - UI: (spinner genérico, sin info)
00:16 - Backend: (extrayendo texto con pypdf)
00:30 - Backend: (timeout o éxito)
00:31 - UI: Respuesta aparece O error genérico
```

**Problemas**:
- ❌ 30 segundos sin feedback
- ❌ No sabe si PDF se está procesando
- ❌ Si falla: mensaje críptico o silencio

#### DESPUÉS

**Timeline del usuario**:
```
00:00 - Usuario: [adjunta report.pdf] "Resume esto"
00:00.5 - UI: "📄 Recibí report.pdf (32 págs). Procesando..."
        - Chip: [🔄 report.pdf - Procesando]
00:01 - UI: (continúa mostrando respuesta basada en docs ya listos)
...
00:15 - Worker: (completó extracción)
00:15.5 - UI: Chip actualizado: [✅ report.pdf - Listo]
        - Notificación: "report.pdf está listo"
```

**Ventajas**:
- ✅ Feedback inmediato
- ✅ Estado visible en tiempo real
- ✅ Conversación NO bloqueada
- ✅ Puede usar doc en siguiente mensaje

---

## 🔧 Cambios Técnicos por Capa

### Base de Datos (MongoDB)

#### ANTES
```javascript
// chat_sessions collection
{
  "_id": "chat-123",
  "attached_file_ids": ["doc-abc", "doc-def"],  // Solo IDs
  "user_id": "user-456",
  "created_at": ISODate("...")
}
```

#### DESPUÉS
```javascript
// chat_sessions collection
{
  "_id": "chat-123",
  "documents": [
    {
      "doc_id": "doc-abc",
      "name": "report.pdf",
      "status": "ready",
      "segments_count": 15,
      "indexed_at": ISODate("2025-11-18T12:00:00Z"),
      "pages": 32
    },
    {
      "doc_id": "doc-def",
      "name": "guide.pdf",
      "status": "processing",
      "segments_count": 0,
      "pages": 10
    }
  ],
  "attached_file_ids": ["doc-abc", "doc-def"],  // Kept for compatibility
  "user_id": "user-456",
  "created_at": ISODate("...")
}
```

**Migration**: Script `migrate_attached_files_to_documents.py`

---

### Backend (FastAPI)

#### Nuevos Componentes

1. **MCP Tools**:
   - `IngestFilesTool` (async ingestion)
   - `GetRelevantSegmentsTool` (RAG retrieval)

2. **Background Workers**:
   - `process_document_task` (Celery task)

3. **Modificaciones**:
   - `streaming_handler.py` (usa nuevos tools)
   - `chat_context.py` (campo `new_file_refs`)

---

### Frontend (Next.js/React)

#### Nuevos Componentes

1. **UI Components**:
   - `DocumentChip` (estados visuales)
   - `SystemMessage` (mensajes de sistema/warning)

2. **State Management**:
   - `documentStore` (Zustand store)
   - `useSSEHandler` (procesa eventos)
   - `useDocumentStatusPolling` (fallback)

3. **Types**:
   - `DocumentState` interface
   - `ChatSSEEvent` union type

---

## 📈 Métricas de Performance

### Latencias Esperadas

| Operación | Antes | Después | Mejora |
|-----------|-------|---------|--------|
| Ingesta (respuesta inicial) | 15-30s | < 500ms | **98%** ⬇️ |
| Retrieval de segmentos | N/A | < 200ms | Nueva feature |
| Chat con docs ya listos | 15-30s | < 2s | **93%** ⬇️ |
| Procesamiento background | N/A | 15-30s | Sin bloqueo |

### Recursos

| Recurso | Antes | Después | Cambio |
|---------|-------|---------|--------|
| API request threads | Bloqueado | Liberado | ✅ Más throughput |
| Redis cache hits | 40% | 90% | ✅ Menos S3 reads |
| Worker pool | N/A | 4-8 workers | Nueva infra |
| MongoDB writes | 1x/msg | 2x/msg | +1 write (doc status) |

---

## 🎯 Decisiones de Diseño

### ¿Por qué Celery y no processing inline?

**Opción 1: Processing inline (actual)**
```python
# Bloquea request
text = extract_text(file_path)  # 15-30s
```
❌ Usuario espera
❌ Timeout risk
❌ No escalable

**Opción 2: Threading**
```python
# No bloquea, pero...
thread = Thread(target=extract_text, args=(file_path,))
thread.start()
```
⚠️ Pierde estado si servidor reinicia
⚠️ No distribuido (solo 1 servidor)

**Opción 3: Celery (elegida)**
```python
# Dispatch a queue
process_document_task.delay(doc_id)
```
✅ No bloquea
✅ Persistente (Redis queue)
✅ Distribuido (N workers)
✅ Retry logic built-in

---

### ¿Por qué segmentos en cache y no vector DB?

**Fase 2 (actual plan)**: Keyword-based retrieval con Redis cache
**Fase 3 (futuro)**: Vector embeddings con Pinecone/Weaviate

**Razón**: Simplicidad y ROI

| Feature | Keyword | Embeddings |
|---------|---------|------------|
| Precisión | 70% | 95% |
| Latencia | < 50ms | < 200ms |
| Costo infra | $0 (Redis existe) | +$500/mes |
| Tiempo implementación | 3 días | 2 semanas |

**Decisión**: Empezar con keyword, migrar a embeddings en Q1 2025 si ROI justifica.

---

## ✅ Criterios de Éxito Técnicos

### Fase 1 (Document State)
- [ ] Migration ejecutada sin data loss
- [ ] `documents` field funcional en 100% de sessions
- [ ] Tests >= 95% coverage

### Fase 2 (MCP Tools)
- [ ] `IngestFilesTool` responde < 500ms
- [ ] Workers procesan PDFs correctamente
- [ ] `GetRelevantSegmentsTool` recupera segmentos < 200ms

### Fase 3 (Orchestrator)
- [ ] Zero regressions en chat existente
- [ ] Error recovery funciona (tests pasan)
- [ ] SSE events emitidos correctamente

### Fase 4 (Frontend)
- [ ] Estados de docs visibles en tiempo real
- [ ] System messages mostrados en chat
- [ ] Polling funciona como fallback

---

## 🔗 Referencias

- [Fase 1 Detalle](./PHASE1_DOCUMENT_STATE.md)
- [Fase 2 Detalle](./PHASE2_MCP_TOOLS.md)
- [Fase 3 Detalle](./PHASE3_ORCHESTRATOR.md)
- [Fase 4 Detalle](./PHASE4_FRONTEND_UX.md)
- [Executive Summary](./EXECUTIVE_SUMMARY.md)

---

**Última actualización**: 2025-11-18
**Versión**: 1.0
