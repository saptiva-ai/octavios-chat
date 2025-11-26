# COPILOTO_414 / AuditFile - Análisis de Arquitectura y Propuesta de Mejoras

**Fecha**: 2025-11-25
**Versión**: 1.0
**Estado**: Propuesta de Mejoras

---

## 📊 Resumen Ejecutivo

**COPILOTO_414** y **AuditFile** son el **mismo sistema** de auditoría de documentos PDF. Actualmente funciona correctamente pero tiene oportunidades de mejora en:

1. **Desacoplamiento como microservicio MCP**
2. **Sincronización de auditores** (MCP Tool vs ValidationCoordinator)
3. **Escalabilidad** (procesamiento asíncrono)
4. **Documentación** de arquitectura

---

## 🏗️ Arquitectura Actual

### Componentes Principales

```
┌────────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  1. Usuario sube PDF                                     │  │
│  │  2. Presiona "botón azul" o escribe comando              │  │
│  │  3. Recibe resultados en Open Canvas                     │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────┐
│                Backend (FastAPI)                               │
│                                                                │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  AuditCommandHandler                                  │    │
│  │  (apps/api/src/domain/audit_handler.py)              │    │
│  │                                                       │    │
│  │  - Detecta: "Auditar archivo: nombre.pdf"           │    │
│  │  - Encuentra documento en MongoDB                    │    │
│  │  - Descarga de MinIO                                 │    │
│  │  - Llama a ValidationCoordinator                     │    │
│  └───────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  MCP Tool: AuditFileTool                              │    │
│  │  (apps/api/src/mcp/tools/audit_file.py)              │    │
│  │                                                       │    │
│  │  ⚠️ PROBLEMA: Solo expone 4 auditores                │    │
│  │  - enable_disclaimer                                  │    │
│  │  - enable_format                                      │    │
│  │  - enable_logo                                        │    │
│  │  - enable_grammar                                     │    │
│  │                                                       │    │
│  │  ❌ Faltantes: typography, color_palette,            │    │
│  │                entity_consistency,                    │    │
│  │                semantic_consistency                   │    │
│  └───────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  ValidationCoordinator                                │    │
│  │  (apps/api/src/services/validation_coordinator.py)   │    │
│  │                                                       │    │
│  │  ✅ Implementa los 8 auditores completos:            │    │
│  │  1. Disclaimer       (compliance)                    │    │
│  │  2. Format           (números, formato)              │    │
│  │  3. Typography       (tipografías)                   │    │
│  │  4. Grammar          (ortografía)                    │    │
│  │  5. Logo             (detección logos)               │    │
│  │  6. Color Palette    (paleta de colores)             │    │
│  │  7. Entity Consistency (consistencia entidades)      │    │
│  │  8. Semantic Consistency (consistencia semántica)    │    │
│  └───────────────────────────────────────────────────────┘    │
│                          │                                     │
│                          ▼                                     │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  Auditores Individuales                               │    │
│  │  (apps/api/src/services/*_auditor.py)                │    │
│  │                                                       │    │
│  │  - compliance_auditor.py                             │    │
│  │  - format_auditor.py                                 │    │
│  │  - typography_auditor.py                             │    │
│  │  - grammar_auditor.py                                │    │
│  │  - logo_auditor.py                                   │    │
│  │  - color_palette_auditor.py                          │    │
│  │  - entity_consistency_auditor.py                     │    │
│  │  - semantic_consistency_auditor.py                   │    │
│  └───────────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────┐
│  ValidationReport (MongoDB)                                    │
│  Artifact/Canvas (Frontend visualization)                      │
└────────────────────────────────────────────────────────────────┘
```

---

## ⚠️ PROBLEMAS IDENTIFICADOS

### 1. Desincronización entre MCP Tool y ValidationCoordinator

**Problema**:
- `AuditFileTool` (MCP) solo expone **4 auditores**
- `ValidationCoordinator` implementa **8 auditores**

**Archivo afectado**: `apps/api/src/mcp/tools/audit_file.py`

**Código actual** (Líneas 31-34):
```python
class AuditInput(BaseModel):
    doc_id: str = Field(..., description="ID del documento a auditar")
    user_id: str = Field(..., description="ID del usuario propietario")
    policy_id: str = Field("auto", description="ID de la política")
    enable_disclaimer: bool = Field(True, description="Activar auditor de disclaimers")
    enable_format: bool = Field(True, description="Activar auditor de formato")
    enable_logo: bool = Field(True, description="Activar auditor de logos")
    enable_grammar: bool = Field(True, description="Activar auditor de gramática")
    # ❌ FALTANTES: typography, color_palette, entity_consistency, semantic_consistency
```

**Impacto**:
- Usuario no puede controlar los 4 auditores adicionales vía MCP
- Documentación de la herramienta MCP está incompleta
- API externa no puede desactivar auditores específicos

---

### 2. Acoplamiento entre AuditCommandHandler y ValidationCoordinator

**Problema**:
- `AuditCommandHandler` tiene lógica mezclada (parsing, validación, orquestación)
- No hay separación clara de responsabilidades
- Difícil reutilizar la lógica fuera del contexto de chat

**Archivo afectado**: `apps/api/src/domain/audit_handler.py`

**Acoplamiento actual**:
```python
# Handler tiene TODAs estas responsabilidades:
- Parse del comando "Auditar archivo: X"
- Búsqueda de documento en MongoDB
- Validación de ownership
- Descarga de MinIO
- Llamada a ValidationCoordinator
- Generación de reporte PDF
- Formateo de respuesta de chat
- Creación de artifact
```

**Debería ser**:
```python
# Handler solo debería:
- Parse del comando
- Validación básica
- Delegación a MCP Tool (que hace el resto)
```

---

### 3. Procesamiento Síncrono (Bloqueante)

**Problema**:
- La auditoría bloquea la respuesta del chat
- Usuario no puede hacer otras cosas mientras espera
- PDFs grandes (>20 páginas) pueden timeout

**Archivo afectado**: `apps/api/src/services/validation_coordinator.py` (líneas 66-86)

**Comentario en el código**:
```python
"""
TODO [Octavius-2.0 / Phase 3]: Migrate to queue-based worker
Current implementation: Synchronous execution (blocks chat response)
Target implementation: Background job with progress updates

Migration plan:
1. Create AuditProducer (enqueue validation job)
2. Implement AuditWorker in workers/audit_worker.py (consumer)
3. Add job progress tracking for each auditor phase
4. Emit WebSocket/SSE events for real-time canvas updates
5. Update endpoint to return 202 Accepted + task_id immediately
6. Add streaming endpoint GET /api/audit/{task_id}/stream
"""
```

**Impacto**:
- Límite actual: ~30 segundos (timeout)
- No hay retry logic
- No hay progreso en tiempo real

---

### 4. Falta de Documentación Arquitectural

**Problema**:
- No hay documentación sobre cómo funcionan los 8 auditores
- No hay guía de cómo agregar nuevos auditores
- No hay diagrama de flujo completo

---

## ✅ PROPUESTAS DE MEJORA

### Mejora 1: Sincronizar AuditFileTool con los 8 Auditores

**Objetivo**: Exponer todos los auditores vía MCP Tool

**Cambios en** `apps/api/src/mcp/tools/audit_file.py`:

```python
class AuditInput(BaseModel):
    doc_id: str = Field(..., description="ID del documento a auditar")
    user_id: str = Field(..., description="ID del usuario propietario")
    policy_id: str = Field("auto", description="ID de la política")

    # 8 Auditores completos
    enable_disclaimer: bool = Field(True, description="Auditor de disclaimers")
    enable_format: bool = Field(True, description="Auditor de formato")
    enable_typography: bool = Field(True, description="Auditor de tipografías")
    enable_grammar: bool = Field(True, description="Auditor de ortografía")
    enable_logo: bool = Field(True, description="Auditor de logos")
    enable_color_palette: bool = Field(True, description="Auditor de paleta de colores")
    enable_entity_consistency: bool = Field(True, description="Auditor de consistencia de entidades")
    enable_semantic_consistency: bool = Field(True, description="Auditor de consistencia semántica")
```

**Actualizar input_schema del ToolSpec** (líneas 61-96):
```python
input_schema={
    "type": "object",
    "properties": {
        "doc_id": {...},
        "policy_id": {...},
        "enable_disclaimer": {"type": "boolean", "default": True, ...},
        "enable_format": {"type": "boolean", "default": True, ...},
        "enable_typography": {"type": "boolean", "default": True, ...},
        "enable_grammar": {"type": "boolean", "default": True, ...},
        "enable_logo": {"type": "boolean", "default": True, ...},
        "enable_color_palette": {"type": "boolean", "default": True, ...},
        "enable_entity_consistency": {"type": "boolean", "default": True, ...},
        "enable_semantic_consistency": {"type": "boolean", "default": True, ...},
    },
    "required": ["doc_id"],
}
```

**Actualizar llamada a validate_document** (líneas 236-247):
```python
report = await validate_document(
    document=doc,
    pdf_path=pdf_path,
    client_name=policy.client_name,
    enable_disclaimer=enable_disclaimer,
    enable_format=enable_format,
    enable_typography=input_data.enable_typography,  # NUEVO
    enable_grammar=enable_grammar,
    enable_logo=enable_logo,
    enable_color_palette=input_data.enable_color_palette,  # NUEVO
    enable_entity_consistency=input_data.enable_entity_consistency,  # NUEVO
    enable_semantic_consistency=input_data.enable_semantic_consistency,  # NUEVO
    policy_config=policy.to_compliance_config(),
    policy_id=policy.id,
    policy_name=policy.name,
)
```

**Beneficios**:
- ✅ MCP Tool refleja capacidad real del sistema
- ✅ Usuario puede controlar todos los auditores
- ✅ API externa tiene control granular
- ✅ Documentación sincronizada con implementación

---

### Mejora 2: Desacoplar AuditCommandHandler → Delegar a MCP Tool

**Objetivo**: Reducir responsabilidades del handler, reutilizar lógica MCP

**Cambios en** `apps/api/src/domain/audit_handler.py`:

**Antes** (lógica duplicada):
```python
# Handler hace TODO esto:
target_doc = await self._find_target_document(...)
pdf_path = await self._get_pdf_path(target_doc)
validation_report = await self._execute_validation(...)
report_url = await self._generate_report_url(...)
artifact = await self._create_artifact(...)
```

**Después** (delegación a MCP):
```python
async def process(self, context: ChatContext, chat_service, **kwargs):
    # 1. Parse comando y extraer filename
    filename = context.message.replace(self.AUDIT_COMMAND_PREFIX, "").strip()

    # 2. Encontrar documento
    target_doc = await self._find_target_document(filename, context.document_ids)

    # 3. Delegar TODO a MCP Tool
    from ...mcp.tools.audit_file import AuditFileTool

    audit_tool = AuditFileTool()
    result = await audit_tool.execute(
        payload={
            "doc_id": str(target_doc.id),
            "user_id": context.user_id,
            "policy_id": "auto"  # o extraer de comando
        },
        context={
            "user_id": context.user_id,
            "session_id": context.session_id
        }
    )

    # 4. Formatear respuesta de chat
    response_text = self._format_audit_response(result)

    # 5. Crear artifact para Canvas
    artifact = await self._create_canvas_artifact(result)

    return ChatProcessingResult(
        response=response_text,
        artifacts=[artifact],
        ...
    )
```

**Beneficios**:
- ✅ Elimina duplicación de lógica
- ✅ Handler más simple (solo parsing + delegación)
- ✅ MCP Tool es la única fuente de verdad
- ✅ Más fácil de testear

---

### Mejora 3: Procesamiento Asíncrono con Background Jobs

**Objetivo**: No bloquear el chat, permitir auditorías largas

**Arquitectura propuesta**:

```
Usuario envía comando
       │
       ▼
AuditCommandHandler
       │
       ├─► Encola job en Redis/RabbitMQ
       │   (retorna 202 Accepted + task_id)
       │
       └─► Responde inmediatamente:
           "⏳ Auditoría iniciada. ID: abc-123
            Te notificaré cuando termine."

[En background]
       │
       ▼
AuditWorker (consumer)
       │
       ├─► 1. Descarga PDF
       ├─► 2. Ejecuta Auditor 1 → Emite progreso (12%)
       ├─► 3. Ejecuta Auditor 2 → Emite progreso (25%)
       ├─► ...
       └─► 8. Ejecuta Auditor 8 → Emite progreso (100%)

       │
       ▼
Guarda ValidationReport
       │
       ▼
Notifica al usuario (WebSocket/SSE)
       │
       ▼
Frontend actualiza Canvas en tiempo real
```

**Implementación sugerida**:

1. **Crear AuditProducer** (`apps/api/src/workers/audit_producer.py`):
```python
from redis import Redis
import json

async def enqueue_audit_job(
    doc_id: str,
    user_id: str,
    policy_id: str,
    enable_auditors: dict
) -> str:
    """Encola job de auditoría."""
    task_id = str(uuid4())

    job_data = {
        "task_id": task_id,
        "doc_id": doc_id,
        "user_id": user_id,
        "policy_id": policy_id,
        "enable_auditors": enable_auditors,
        "created_at": datetime.utcnow().isoformat()
    }

    redis = Redis(...)
    redis.lpush("audit_queue", json.dumps(job_data))

    return task_id
```

2. **Crear AuditWorker** (`apps/api/src/workers/audit_worker.py`):
```python
async def process_audit_job(job_data: dict):
    """Worker que procesa auditorías."""
    task_id = job_data["task_id"]

    # Emitir progreso
    await emit_progress(task_id, 0, "Descargando PDF...")

    # Ejecutar auditores uno por uno
    for i, auditor_name in enumerate(AUDITORS):
        progress = int((i / len(AUDITORS)) * 100)
        await emit_progress(task_id, progress, f"Ejecutando {auditor_name}...")

        # Ejecutar auditor
        findings = await execute_auditor(auditor_name, ...)

    # Finalizar
    await emit_progress(task_id, 100, "Completado")
    await notify_user(user_id, task_id, "Auditoría completada")
```

3. **Endpoint de progreso** (`apps/api/src/routers/audit.py`):
```python
@router.get("/audit/{task_id}/progress")
async def get_audit_progress(task_id: str):
    """Retorna progreso de auditoría."""
    progress = await redis.get(f"audit:progress:{task_id}")
    return {
        "task_id": task_id,
        "progress": int(progress),
        "status": "in_progress" | "completed" | "failed"
    }
```

**Beneficios**:
- ✅ No bloquea el chat
- ✅ Soporta PDFs grandes (sin timeout)
- ✅ Progreso en tiempo real
- ✅ Retry logic en caso de falla
- ✅ Escalabilidad horizontal (múltiples workers)

---

### Mejora 4: Documentación Completa

**Objetivo**: Documentar arquitectura, auditores y flujos

**Crear documentos**:

1. **`docs/COPILOTO_414_USER_GUIDE.md`**
   - Cómo usar el sistema
   - Interpretar resultados
   - Configurar políticas

2. **`docs/COPILOTO_414_DEVELOPER_GUIDE.md`**
   - Cómo funciona cada auditor
   - Cómo agregar nuevos auditores
   - Testing y debugging

3. **`docs/COPILOTO_414_API_REFERENCE.md`**
   - Endpoints disponibles
   - MCP Tool specification
   - Ejemplos de uso

4. **Diagramas de flujo** (Mermaid)
   - Flujo completo de auditoría
   - Arquitectura de componentes
   - Integración con Canvas

---

## 📋 PLAN DE IMPLEMENTACIÓN

### Fase 1: Quick Wins (1-2 días)

**Prioridad: ALTA**

- [ ] **Mejora 1**: Sincronizar AuditFileTool con 8 auditores
  - Actualizar `AuditInput` con 4 campos nuevos
  - Actualizar `input_schema` del ToolSpec
  - Actualizar llamada a `validate_document`
  - Testing manual

- [ ] **Mejora 4 (parcial)**: Crear documentación básica
  - README de COPILOTO_414
  - Diagrama de arquitectura actual

**Estimación**: 1-2 días
**Impacto**: Alto (sincroniza sistema)
**Riesgo**: Bajo (cambios simples)

---

### Fase 2: Desacoplamiento (3-5 días)

**Prioridad: MEDIA**

- [ ] **Mejora 2**: Refactorizar AuditCommandHandler
  - Extraer lógica a métodos reutilizables
  - Delegar a MCP Tool en lugar de llamar directo a ValidationCoordinator
  - Tests unitarios

- [ ] **Mejora 4 (completa)**: Documentación avanzada
  - Developer Guide
  - API Reference
  - Diagramas de flujo

**Estimación**: 3-5 días
**Impacto**: Medio (mejora mantenibilidad)
**Riesgo**: Bajo (no rompe funcionalidad)

---

### Fase 3: Procesamiento Asíncrono (1-2 semanas)

**Prioridad: BAJA (futuro)**

- [ ] **Mejora 3**: Implementar background jobs
  - Setup de Redis/RabbitMQ
  - Implementar AuditProducer
  - Implementar AuditWorker
  - WebSocket/SSE para progreso
  - Endpoints de /progress y /cancel
  - Tests de integración

**Estimación**: 1-2 semanas
**Impacto**: Alto (mejora UX para PDFs grandes)
**Riesgo**: Medio (cambio arquitectural significativo)

**Nota**: Esta mejora está documentada en el código como TODO para Octavius-2.0 Phase 3

---

## 🎯 Recomendación Inmediata

**Empezar con Fase 1** (Quick Wins):

1. Actualizar `AuditFileTool` para exponer los 8 auditores (1 día)
2. Crear documentación básica (1 día)
3. Testear en staging
4. Desplegar a producción

**Beneficio inmediato**:
- Sistema completamente sincronizado
- Documentación clara para Capital414
- Base para futuras mejoras

**¿Procedo con la Fase 1?**

---

## 📎 Archivos a Modificar (Fase 1)

### Archivo 1: `apps/api/src/mcp/tools/audit_file.py`

**Líneas a cambiar**: 27-35, 61-96, 159-163, 236-247

### Archivo 2: Crear `docs/COPILOTO_414_README.md`

**Nuevo archivo** con documentación de arquitectura

### Archivo 3: Crear `docs/COPILOTO_414_ARCHITECTURE_DIAGRAM.md`

**Nuevo archivo** con diagrama Mermaid

---

**Última actualización**: 2025-11-25
**Autor**: Claude Code
**Revisión**: Pendiente
