# Análisis de Bug: Historial de Chat No se Muestra Correctamente

**Fecha**: 2025-11-12
**Severidad**: P0 (Crítico - funcionalidad core rota)
**Estado**: Identificado, pendiente de fix

---

## Síntoma Reportado

El historial de chats no se guarda correctamente o no se muestra al usuario. Los mensajes desaparecen o solo se ven algunos.

---

## Análisis Técnico

### Arquitectura de Historial

El sistema tiene **DOS sistemas paralelos** para almacenar mensajes:

1. **Colección directa `chat_messages`** (MongoDB)
   - Modelo: `ChatMessageModel` (`src/models/chat.py`)
   - Almacena todos los mensajes directamente

2. **Colección unificada `history_events`** (MongoDB)
   - Modelo: `HistoryEvent` (`src/models/history.py`)
   - Timeline unificado de chat + research + otros eventos
   - Requiere registro explícito via `HistoryService.record_chat_message()`

### El Bug: Inconsistencia en el Registro

#### Guardado de Mensajes del Usuario ✅

**Archivo**: `src/services/chat_service.py:360-407`

```python
async def add_user_message(...):
    # 1. Guardar en chat_messages (MongoDB)
    await user_message.insert()  # ✅ Línea 362

    # 2. Registrar en history_events (HistoryService)
    await HistoryService.record_chat_message(  # ✅ Línea 383
        chat_id=chat_session.id,
        user_id=chat_session.user_id,
        message=user_message
    )
```

✅ **Funciona correctamente**: El mensaje del usuario se guarda en AMBOS lugares.

---

#### Guardado de Mensajes del Asistente ❌

**Archivo**: `src/services/chat_service.py:430-457`

```python
async def add_assistant_message(...):
    # 1. Guardar en chat_messages (MongoDB)
    ai_message = await chat_session.add_message(...)  # ✅ Línea 441

    # 2. Registrar en history_events (HistoryService)
    # ❌ FALTA: NO se llama a HistoryService.record_chat_message()

    # Solo se invalida cache
    await cache.invalidate_chat_history(chat_session.id)

    return ai_message
```

❌ **BUG**: El mensaje del asistente **solo** se guarda en `chat_messages`, **NO** se registra en `history_events`.

---

### Lectura de Mensajes: Dos Endpoints

#### Endpoint 1: `/api/history/{chat_id}` (Directo)

**Archivo**: `src/routers/history.py:62-103`

```python
@router.get("/history/{chat_id}", response_model=ChatHistoryResponse)
async def get_chat_detailed_history(...):
    # Lee DIRECTAMENTE de chat_messages
    result = await HistoryService.get_chat_messages(
        chat_id=chat_id,
        limit=limit,
        offset=offset
    )
```

**Fuente de datos**: Colección `chat_messages` directa

**Estado**: ✅ **Funciona** - Lee todos los mensajes (usuario + asistente) porque están en `chat_messages`

---

#### Endpoint 2: `/api/history/{chat_id}/unified` (Timeline)

**Archivo**: `src/routers/history.py:176-297`

```python
@router.get("/history/{chat_id}/unified")
async def get_unified_chat_history(...):
    # Lee de history_events (timeline unificado)
    timeline_data = await HistoryService.get_chat_timeline(
        chat_id=chat_id,
        event_types=[HistoryEventType.CHAT_MESSAGE, ...]
    )
```

**Fuente de datos**: Colección `history_events` (timeline unificado)

**Estado**: ❌ **ROTO** - Solo muestra mensajes del usuario, falta los del asistente

---

## Impacto del Bug

### Escenario A: Frontend usa `/api/history/{chat_id}` (Directo)

✅ **Funciona**: Se ven todos los mensajes (usuario + asistente)

**Problema potencial**:
- No muestra eventos de research integrados
- No aprovecha el timeline unificado

---

### Escenario B: Frontend usa `/api/history/{chat_id}/unified` (Timeline)

❌ **ROTO**: Solo se ven mensajes del usuario

**Conversación típica**:
```
Usuario: Hola, ¿cómo estás?          ✅ Visible
Asistente: ¡Bien! ¿En qué puedo...   ❌ No aparece
Usuario: Cuéntame sobre Python        ✅ Visible
Asistente: Python es un lenguaje...   ❌ No aparece
```

**Experiencia del usuario**:
- Parece que el bot no responde
- Solo ve sus propios mensajes
- Confusión total

---

## Root Cause

**Inconsistencia en la implementación**:

1. Se implementó `HistoryService` para timeline unificado
2. Se actualizó `add_user_message` para registrar en ambos sistemas
3. ❌ **Se olvidó actualizar** `add_assistant_message` para hacer lo mismo
4. Resultado: Solo la mitad de los mensajes están en el timeline

---

## Solución Propuesta

### Fix Inmediato (P0)

**Archivo**: `src/services/chat_service.py:430-457`

Agregar registro en `HistoryService` después de guardar el mensaje:

```python
async def add_assistant_message(
    self,
    chat_session: ChatSessionModel,
    content: str,
    model: str,
    task_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    tokens: Optional[Dict] = None,
    latency_ms: Optional[int] = None
) -> ChatMessageModel:
    """Add assistant message to session and record in history."""

    # 1. Guardar mensaje en chat_messages
    ai_message = await chat_session.add_message(
        role=MessageRole.ASSISTANT,
        content=content,
        model=model,
        task_id=task_id,
        metadata=metadata or {},
        tokens=tokens,
        latency_ms=latency_ms
    )

    # 2. ✅ AGREGAR: Registrar en history_events (igual que user_message)
    try:
        from ..services.history_service import HistoryService
        await HistoryService.record_chat_message(
            chat_id=chat_session.id,
            user_id=chat_session.user_id,
            message=ai_message
        )
        logger.debug(
            "Recorded assistant message in history",
            message_id=ai_message.id,
            chat_id=chat_session.id
        )
    except Exception as hist_err:
        # No fallar si history falla
        logger.error(
            "Failed to record assistant message in history",
            error=str(hist_err),
            message_id=ai_message.id,
            chat_id=chat_session.id,
            exc_info=True
        )

    # 3. Invalidar cache
    cache = await get_redis_cache()
    await cache.invalidate_chat_history(chat_session.id)
    if task_id:
        await cache.invalidate_research_tasks(chat_session.id)

    return ai_message
```

---

### Tests de Regresión

Crear test que verifique ambos mensajes se registran:

```python
@pytest.mark.asyncio
async def test_chat_history_shows_both_user_and_assistant_messages():
    """
    Test: Historial debe mostrar AMBOS mensajes (usuario + asistente)

    Este test reproduce el bug reportado.
    """
    # Arrange
    chat_session = await create_test_chat_session()
    chat_service = ChatService()

    # Act: Simular conversación
    user_msg = await chat_service.add_user_message(
        chat_session=chat_session,
        content="Hola, ¿cómo estás?",
        file_ids=[],
        files=[],
        metadata={}
    )

    assistant_msg = await chat_service.add_assistant_message(
        chat_session=chat_session,
        content="¡Bien! ¿En qué puedo ayudarte?",
        model="saptiva-turbo",
        tokens={"total": 20},
        latency_ms=500
    )

    # Assert: Verificar timeline unificado
    timeline = await HistoryService.get_chat_timeline(
        chat_id=chat_session.id,
        limit=10,
        offset=0,
        event_types=[HistoryEventType.CHAT_MESSAGE]
    )

    events = timeline["events"]

    # Debe haber 2 eventos
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"

    # Verificar mensaje del usuario
    user_event = next(e for e in events if e["chat_data"]["role"] == "user")
    assert user_event["chat_data"]["content"] == "Hola, ¿cómo estás?"

    # Verificar mensaje del asistente (ESTO FALLA actualmente)
    assistant_event = next(e for e in events if e["chat_data"]["role"] == "assistant")
    assert assistant_event["chat_data"]["content"] == "¡Bien! ¿En qué puedo ayudarte?"

    # Verificar orden cronológico
    assert events[0]["timestamp"] < events[1]["timestamp"]
```

---

### Refactorización Futura (P2)

**Extraer lógica común** para evitar duplicación:

```python
async def _save_message_to_history(
    self,
    chat_session: ChatSessionModel,
    message: ChatMessageModel
) -> None:
    """Helper: Save message to unified history (DRY)"""
    try:
        await HistoryService.record_chat_message(
            chat_id=chat_session.id,
            user_id=chat_session.user_id,
            message=message
        )
        logger.debug(
            "Recorded message in history",
            message_id=message.id,
            role=message.role.value
        )
    except Exception as e:
        logger.error(
            "Failed to record message in history",
            error=str(e),
            message_id=message.id,
            exc_info=True
        )

# Usar en ambos métodos
async def add_user_message(...):
    user_message = ...
    await user_message.insert()
    await self._save_message_to_history(chat_session, user_message)  # DRY

async def add_assistant_message(...):
    ai_message = ...
    await self._save_message_to_history(chat_session, ai_message)  # DRY
```

---

## Prioridad de Fix

**P0 - Crítico**:
- Funcionalidad core rota
- Afecta experiencia de usuario directamente
- Solución simple (agregar 15 líneas de código)

**Tiempo estimado**: 30 minutos (fix + test)

---

## Checklist de Implementación

- [ ] Aplicar fix en `chat_service.py:add_assistant_message`
- [ ] Crear test de regresión `test_chat_history_both_messages`
- [ ] Ejecutar tests existentes (no romper nada)
- [ ] Verificar en DB que se crean `HistoryEvent` para ambos roles
- [ ] Probar endpoint `/api/history/{chat_id}/unified` manualmente
- [ ] Verificar cache invalidation funciona correctamente
- [ ] Documentar en CHANGELOG.md
- [ ] Deploy con smoke test

---

## Referencias

- **Bug report**: Usuario reporta "historial no se guarda correctamente"
- **Archivos afectados**:
  - `src/services/chat_service.py` (fix principal)
  - `src/services/history_service.py` (ya funciona, no tocar)
  - `src/routers/history.py` (endpoints funcionan, no tocar)
- **Tests relacionados**:
  - `tests/unit/test_history_service.py`
  - `tests/integration/test_chat_history_pagination_integration.py`
