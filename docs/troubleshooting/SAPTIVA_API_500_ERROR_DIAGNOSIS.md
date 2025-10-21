# Diagnóstico: Error 500 de API Saptiva - "No pude conectar con el servidor de chat"

**Fecha:** 2025-10-20
**Reportado por:** Usuario (prueba con HPE.pdf)
**Estado:** CONFIRMADO - La API de Saptiva está devolviendo errores 500

---

## 📋 Resumen Ejecutivo

El error "Lo siento, no pude conectar con el servidor de chat en este momento" que aparece al subir archivos PDF y hacer preguntas **NO está relacionado con el sistema de procesamiento de PDFs ni con el OCR**.

**Causa raíz:** La API de Saptiva (`https://api.saptiva.com/v1/chat/completions/`) está devolviendo errores HTTP 500 (Internal Server Error) para todas las peticiones de chat.

---

## 🔍 Análisis Detallado

### 1. Reproducción del Problema

**Escenario del usuario:**
1. Usuario sube archivo: `HPE Private Cloud AI - Small (1).pdf`
2. Usuario pregunta: "Que es esto?"
3. Sistema muestra error: "Lo siento, no pudo conectar con el servidor de chat en este momento. Intenta nuevamente en unos segundos."

### 2. Investigación Realizada

#### ✅ Componentes Verificados (Funcionando Correctamente)
- **Frontend (Next.js):** ✓ Funcionando
- **Backend (FastAPI):** ✓ Funcionando (healthy)
- **MongoDB:** ✓ Conectado y respondiendo
- **Redis:** ✓ Conectado y respondiendo
- **Procesamiento de archivos:** ✓ Sistema OCR funcional
- **Autenticación:** ✓ JWT tokens funcionando

#### ❌ Componente con Fallo Identificado
- **API de Saptiva:** ✗ Devolviendo 500 Internal Server Error

### 3. Evidencia de Logs

#### Logs del Backend (copilotos-api)
```json
{
  "error": "Server error '500 Internal Server Error' for url 'https://api.saptiva.com/v1/chat/completions/'",
  "attempt": 1,
  "event": "SAPTIVA request failed, retrying",
  "timestamp": "2025-10-21T04:12:06.569284Z"
}

{
  "error": "Server error '500 Internal Server Error' for url 'https://api.saptiva.com/v1/chat/completions/'",
  "attempt": 2,
  "wait_time": 2,
  "event": "SAPTIVA request failed, retrying",
  "timestamp": "2025-10-21T04:12:08.769284Z"
}

{
  "error": "Server error '500 Internal Server Error' for url 'https://api.saptiva.com/v1/chat/completions/'",
  "attempt": 3,
  "wait_time": 4,
  "event": "SAPTIVA request failed, retrying",
  "timestamp": "2025-10-21T04:12:10.989286Z"
}

{
  "error": "Server error '500 Internal Server Error' for url 'https://api.saptiva.com/v1/chat/completions/'",
  "endpoint": "/v1/chat/completions/",
  "event": "SAPTIVA request failed after all retries",
  "level": "error",
  "timestamp": "2025-10-21T04:12:15.207900Z"
}
```

**Patrón de reintentos:**
- Intento 1: Falla inmediato
- Intento 2: Espera 2s, falla
- Intento 3: Espera 4s, falla
- Total: 3 reintentos con backoff exponencial (configuración correcta según `apps/api/src/services/saptiva_client.py:64`)

#### Prueba Directa a la API de Saptiva
```bash
$ curl -X POST https://api.saptiva.com/v1/chat/completions/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SAPTIVA_API_KEY" \
  -d '{"model": "Saptiva Turbo", "messages": [{"role": "user", "content": "Hola"}]}'

# Respuesta:
Internal Server Error
# HTTP Status: 500
```

**Confirmación:** La API de Saptiva está devolviendo errores 500 incluso para peticiones simples sin archivos adjuntos.

---

## 🛠️ Configuración Verificada

### Variables de Entorno (Correctas)
```bash
SAPTIVA_BASE_URL=https://api.saptiva.com
SAPTIVA_API_KEY=va-ai-Jm4BHuDYPiNAlv7OoBuO8G58S23sSgIAmbZ6nqUKFOqSY8vmB2Liba-ZRzcgjJLpqOFmza8bK9vvUT39EhaKjeGZHFJE8EVQtKABOG1hc_A
SAPTIVA_MAX_RETRIES=3
SAPTIVA_TIMEOUT=30
MAX_FILE_SIZE=52428800 (50MB)
```

### Configuración del Cliente Saptiva (Correcta)
**Archivo:** `apps/api/src/services/saptiva_client.py`
- ✓ Retry logic: 3 intentos con exponential backoff
- ✓ Timeout: 30s total, 120s read (para streaming)
- ✓ HTTP/2 habilitado
- ✓ Follow redirects habilitado
- ✓ Conexiones keep-alive configuradas

---

## 💡 Causa Raíz

**Problema:** La infraestructura de la API de Saptiva está devolviendo errores 500, lo que indica un problema del lado del servidor de Saptiva (no del código del cliente).

**Razones posibles:**
1. **Sobrecarga del servidor:** El backend de Saptiva podría estar experimentando alta carga
2. **Mantenimiento:** Podría estar en proceso de mantenimiento no anunciado
3. **Error de despliegue:** Podría haber un bug en la última versión desplegada
4. **Problema de infraestructura:** Podría haber un problema con la base de datos, caché o servicios internos de Saptiva

**Por qué el mensaje es genérico:**
El frontend en `apps/web/src/app/chat/_components/ChatView.tsx:648` captura cualquier error en el bloque `catch` y muestra un mensaje genérico:
```typescript
} catch (error) {
  logError("Failed to send chat message", error);
  return {
    id: placeholderId,
    role: "assistant",
    content: "Lo siento, no pude conectar con el servidor de chat en este momento. Intenta nuevamente en unos segundos.",
    timestamp: new Date().toISOString(),
    status: "error" as const,
    isStreaming: false,
  };
}
```

---

## ✅ Soluciones y Recomendaciones

### Soluciones Inmediatas (Para el Usuario)

#### 1. **Esperar y Reintentar** (Recomendado)
- **Acción:** Esperar 5-10 minutos y volver a intentar
- **Razón:** Los errores 500 suelen ser temporales
- **Cómo:** Simplemente recargar la página y enviar el mensaje nuevamente

#### 2. **Verificar Estado de Saptiva**
- **Contactar a soporte:** Reportar el problema a soporte@saptiva.com
- **Incluir:** Timestamp del error (2025-10-21 04:12 UTC), API key (primeros 10 caracteres)

#### 3. **Monitoreo**
```bash
# Verificar si la API de Saptiva vuelve a estar disponible
make test-saptiva-api

# O manualmente:
curl -X POST https://api.saptiva.com/v1/chat/completions/ \
  -H "Authorization: Bearer $SAPTIVA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"Saptiva Turbo","messages":[{"role":"user","content":"test"}]}'
```

### Mejoras a Largo Plazo (Para el Equipo de Desarrollo)

#### 1. **Mejorar Mensajes de Error en el Frontend**
**Archivo:** `apps/web/src/app/chat/_components/ChatView.tsx:642-653`

**Problema actual:** El mensaje es demasiado genérico
**Propuesta:** Diferenciar entre tipos de errores

```typescript
} catch (error: any) {
  logError("Failed to send chat message", error);

  // Extraer información del error para mensaje más específico
  let errorMessage = "Lo siento, no pude conectar con el servidor de chat en este momento.";

  if (error?.response?.status === 500) {
    errorMessage = "El servicio de chat está experimentando problemas temporales. Por favor intenta en unos minutos.";
  } else if (error?.response?.status === 503) {
    errorMessage = "El servicio de chat está en mantenimiento. Por favor intenta más tarde.";
  } else if (error?.code === 'ECONNREFUSED' || error?.code === 'ETIMEDOUT') {
    errorMessage = "No se pudo conectar con el servidor. Verifica tu conexión a internet.";
  }

  return {
    id: placeholderId,
    role: "assistant",
    content: errorMessage,
    timestamp: new Date().toISOString(),
    status: "error" as const,
    isStreaming: false,
    metadata: {
      error_type: error?.response?.status || error?.code || 'unknown',
      retryable: true
    }
  };
}
```

#### 2. **Agregar Retry Automático en el Frontend**
Cuando la API de Saptiva falla, el frontend podría reintentar automáticamente después de un delay.

```typescript
// Implementar en useOptimizedChat.ts
const sendWithRetry = async (message: string, maxRetries = 2) => {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await sendMessage(message);
    } catch (error) {
      if (attempt < maxRetries && error?.response?.status >= 500) {
        await new Promise(resolve => setTimeout(resolve, 2000 * (attempt + 1)));
        continue;
      }
      throw error;
    }
  }
};
```

#### 3. **Agregar Dashboard de Salud de Saptiva**
Crear un endpoint `/api/saptiva/health` que verifique el estado de la API de Saptiva:

```python
# apps/api/src/routers/health.py
@router.get("/saptiva/health")
async def check_saptiva_health():
    """Check if Saptiva API is responding"""
    try:
        client = get_saptiva_client()
        response = await client.chat_completion(
            model="Saptiva Turbo",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5
        )
        return {"status": "healthy", "latency_ms": response.get("latency")}
    except HTTPStatusError as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "status_code": e.response.status_code
        }
```

#### 4. **Agregar Alertas de Prometheus**
Crear alertas para cuando la tasa de errores 500 de Saptiva supere un umbral:

```yaml
# Prometheus alert rule
- alert: SaptivaAPIHighErrorRate
  expr: rate(http_requests_total{endpoint="/v1/chat/completions/", status="500"}[5m]) > 0.1
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Saptiva API tiene alta tasa de errores 500"
    description: "La API de Saptiva ha devuelto > 10% errores 500 en los últimos 5 minutos"
```

---

## 📊 Timeline del Incidente

| Timestamp (UTC) | Evento |
|-----------------|--------|
| 2025-10-21 04:11:53 | Usuario hace login (exitoso) |
| 2025-10-21 04:12:06 | Primer intento de chat → Saptiva 500 |
| 2025-10-21 04:12:08 | Segundo intento (retry) → Saptiva 500 |
| 2025-10-21 04:12:10 | Tercer intento (retry) → Saptiva 500 |
| 2025-10-21 04:12:15 | Backend devuelve error al frontend |
| 2025-10-21 04:12:15 | Usuario ve mensaje de error genérico |

**Duración total:** ~9 segundos (incluye 3 reintentos con backoff exponencial)

---

## 🔗 Referencias

### Archivos Relacionados
- **Frontend error handler:** `apps/web/src/app/chat/_components/ChatView.tsx:642-653`
- **Backend Saptiva client:** `apps/api/src/services/saptiva_client.py`
- **Backend chat router:** `apps/api/src/routers/chat.py:184-468`
- **Último commit revisado:** `b4bb465` (fix: use environment variable for max file size)
- **README:** Ver sección "Production Troubleshooting"

### Documentación Relevante
- **PDF OCR Architecture:** `docs/ocr/PDF_OCR_FALLBACK_ARCHITECTURE.md`
- **Saptiva Integration:** `docs/saptiva/SAPTIVA_SESSION_SUMMARY.md`
- **Error Handling:** README.md línea 658-813

---

## ✨ Conclusión

**El problema NO está en el código del proyecto ni en el sistema de procesamiento de PDFs.** El error es causado por un problema temporal en la infraestructura de la API de Saptiva.

**Acción recomendada para el usuario:**
1. Esperar 10-15 minutos
2. Reintentar la misma operación
3. Si persiste, contactar a soporte de Saptiva

**Acción recomendada para el equipo de desarrollo:**
1. Implementar mejoras en mensajes de error (ver sección "Mejoras a Largo Plazo")
2. Agregar monitoreo proactivo del estado de Saptiva
3. Considerar implementar un sistema de circuit breaker para APIs externas

---

**Última actualización:** 2025-10-21 04:15 UTC
**Investigado por:** Claude Code
