# Resource Lifecycle Management

## Overview

Sistema completo de gestión del ciclo de vida de recursos para prevenir desbordamiento de memoria y optimizar el uso de storage en el sistema RAG de Capital 414.

## Problemática

En sistemas RAG con múltiples usuarios y documentos, los recursos pueden crecer descontroladamente:

- **Redis**: Cache de chunks de texto puede consumir GB de RAM
- **Qdrant**: Vectores de embeddings ocupan espacio (384-dim × 4 bytes × N puntos)
- **MinIO**: Archivos originales (PDFs, imágenes) acumulan GB de storage
- **MongoDB**: Metadata de documentos crece linealmente

**Sin gestión de lifecycle:**
- ❌ Memory leaks en Redis (cache nunca expira)
- ❌ Qdrant crece indefinidamente (vectores de sesiones antiguas)
- ❌ MinIO almacena archivos que nunca se volverán a usar
- ❌ Duplicados innecesarios (mismo PDF subido múltiples veces)

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│         Resource Lifecycle Manager (Singleton)               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Deduplication│  │  Monitoring  │  │   Cleanup    │      │
│  │   (SHA256)   │  │  (Metrics)   │  │   (Queue)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
  ┌──────────┐      ┌──────────┐       ┌──────────┐
  │  Redis   │      │  Qdrant  │       │  MinIO   │
  │  Cache   │      │  Vectors │       │  Storage │
  └──────────┘      └──────────┘       └──────────┘
   TTL: 1h           TTL: 24h           TTL: 7d
```

## Componentes

### 1. Resource Lifecycle Manager

**Ubicación**: `apps/api/src/services/resource_lifecycle_manager.py`

**Responsabilidades:**
- ✅ Deduplicación de archivos (hash SHA256)
- ✅ Monitoreo de uso de recursos
- ✅ Limpieza automática de recursos obsoletos
- ✅ Cola de prioridad para cleanup tasks

**Estrategia de Deduplicación:**

```python
# Calcular hash SHA256 del archivo
file_hash = hashlib.sha256(file_content).hexdigest()

# Verificar si existe duplicado para el usuario
existing_doc = await Document.find_one({
    "metadata.file_hash": file_hash,
    "user_id": user_id
})

if existing_doc:
    # Reutilizar documento existente
    # Eliminar archivo recién subido de MinIO
    return existing_doc.id
```

**Beneficios:**
- 🚀 Ahorra storage (no almacena duplicados)
- 🚀 Ahorra procesamiento (no re-extrae texto)
- 🚀 Respuesta instantánea (documento ya procesado)

### 2. Resource Cleanup Worker

**Ubicación**: `apps/api/src/workers/resource_cleanup_worker.py`

**Background Tasks Concurrentes:**

| Task | Intervalo | Descripción |
|------|-----------|-------------|
| Redis Cleanup | 1 hora | Limpia keys sin TTL o expiradas |
| Qdrant Cleanup | 6 horas | Elimina vectores de sesiones antiguas (> 24h) |
| MinIO Cleanup | 24 horas | Elimina archivos no referenciados (> 7 días) |
| Resource Monitoring | 30 min | Monitorea uso y programa cleanup urgente |

**Arquitectura Asyncio:**

```python
class ResourceCleanupWorker:
    async def start(self):
        self.tasks = [
            asyncio.create_task(self._redis_cleanup_loop()),
            asyncio.create_task(self._qdrant_cleanup_loop()),
            asyncio.create_task(self._minio_cleanup_loop()),
            asyncio.create_task(self._monitoring_loop())
        ]

    async def stop(self):
        # Graceful shutdown
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
```

**Integración con FastAPI:**

```python
# apps/api/src/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_worker = get_cleanup_worker()
    await cleanup_worker.start()

    yield

    await cleanup_worker.stop()
```

### 3. Resource Monitoring API

**Ubicación**: `apps/api/src/routers/resources.py`

**Endpoints:**

#### GET /api/resources/metrics

Obtiene métricas en tiempo real de todos los recursos.

**Response:**
```json
{
  "redis": {
    "total_items": 1250,
    "size_mb": 45.3,
    "usage_percentage": 17.7,
    "cleanup_priority": "LOW",
    "oldest_age_hours": 0.5
  },
  "qdrant": {
    "total_items": 33,
    "size_mb": 0.5,
    "usage_percentage": 0.03,
    "cleanup_priority": "LOW",
    "oldest_age_hours": 24.0
  },
  "minio": {
    "total_items": 12,
    "size_mb": 48.5,
    "usage_percentage": 0.09,
    "cleanup_priority": "LOW",
    "oldest_age_hours": 168.0
  },
  "mongodb": {
    "total_items": 12,
    "size_mb": 0.06,
    "usage_percentage": 0.12,
    "cleanup_priority": "LOW",
    "oldest_age_hours": 0
  }
}
```

#### POST /api/resources/cleanup

Trigger manual de limpieza.

**Request:**
```json
{
  "resource_type": "redis_cache"  // opcional: null = todos
}
```

**Response:**
```json
{
  "success": true,
  "deleted_counts": {
    "redis": 45,
    "qdrant": 0,
    "minio": 0
  },
  "message": "Cleanup completed. Total items deleted: 45"
}
```

#### GET /api/resources/queue

Estado de la cola de limpieza.

**Response:**
```json
{
  "queue_size": 2,
  "tasks": [
    {
      "priority": "HIGH",
      "resource_type": "qdrant_vectors",
      "target_id": "all",
      "created_at": "2025-01-20T15:30:00Z",
      "reason": "High resource usage: 78.5%"
    }
  ]
}
```

## Configuración

### Variables de Entorno

Todas las configuraciones en `envs/.env`:

```bash
# ========================================
# RESOURCE LIFECYCLE MANAGEMENT
# ========================================

# TTLs (Time To Live)
REDIS_CACHE_TTL_HOURS=1              # Cache de chunks
RAG_SESSION_TTL_HOURS=24             # Vectores en Qdrant
FILES_TTL_DAYS=7                     # Archivos en MinIO

# Intervalos de limpieza (segundos)
REDIS_CLEANUP_INTERVAL_SECONDS=3600       # 1 hora
QDRANT_CLEANUP_INTERVAL_SECONDS=21600     # 6 horas
MINIO_CLEANUP_INTERVAL_SECONDS=86400      # 24 horas
RESOURCE_MONITORING_INTERVAL_SECONDS=1800 # 30 min

# Umbrales de uso (0.0 a 1.0)
CLEANUP_THRESHOLD_CRITICAL=0.9       # 90% - cleanup urgente
CLEANUP_THRESHOLD_HIGH=0.75          # 75% - alta prioridad
CLEANUP_THRESHOLD_MEDIUM=0.5         # 50% - prioridad media

# Límites de recursos (soft limits)
MAX_REDIS_MEMORY_MB=256              # 256 MB
MAX_QDRANT_POINTS=100000             # 100k vectores
MAX_MINIO_STORAGE_GB=50              # 50 GB
```

### Políticas de Retención Recomendadas

#### Por Tipo de Aplicación

**Aplicación de Alta Rotación (Capital 414):**
```bash
REDIS_CACHE_TTL_HOURS=1              # Cache corto
RAG_SESSION_TTL_HOURS=24             # Sesiones de un día
FILES_TTL_DAYS=7                     # Archivos de una semana
```

**Aplicación de Largo Plazo (Archivo Histórico):**
```bash
REDIS_CACHE_TTL_HOURS=24             # Cache largo
RAG_SESSION_TTL_HOURS=168            # Sesiones de una semana
FILES_TTL_DAYS=365                   # Archivos de un año
```

**Desarrollo/Testing:**
```bash
REDIS_CACHE_TTL_HOURS=0.5            # 30 minutos
RAG_SESSION_TTL_HOURS=2              # 2 horas
FILES_TTL_DAYS=1                     # 1 día
```

## Flujo de Limpieza

### 1. Limpieza Automática (Background)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Monitoring Loop (cada 30 min)                        │
│    - Obtiene métricas de todos los recursos             │
│    - Calcula usage_percentage                           │
│    - Asigna cleanup_priority (LOW/MEDIUM/HIGH/CRITICAL) │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Scheduler (si priority >= HIGH)                      │
│    - Agrega CleanupTask a cola de prioridad             │
│    - Ordena por priority (menor = más urgente)          │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Process Queue (cada 30 min)                          │
│    - Procesa hasta 5 tareas de la cola                  │
│    - Ejecuta cleanup_expired_resources()                │
│    - Logs de items eliminados                           │
└─────────────────────────────────────────────────────────┘
```

### 2. Limpieza Manual (via API)

```bash
# Ver métricas actuales
curl http://localhost:8001/api/resources/metrics \
  -H "Authorization: Bearer $TOKEN"

# Trigger cleanup de Redis
curl -X POST http://localhost:8001/api/resources/cleanup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_type": "redis_cache"}'

# Ver cola de cleanup
curl http://localhost:8001/api/resources/queue \
  -H "Authorization: Bearer $TOKEN"
```

## Deduplicación de Archivos

### Flujo de Upload con Deduplicación

```
User uploads file
      ↓
Compute SHA256 hash
      ↓
Check database for duplicate (user_id + file_hash)
      ↓
  ┌───┴───┐
  │       │
FOUND    NOT FOUND
  │       │
  │       ├── Upload to MinIO
  │       ├── Store hash in metadata
  │       ├── Process (extract + chunk + embed)
  │       └── Return new document ID
  │
  ├── Delete newly uploaded file from MinIO
  ├── Return existing document ID
  └── Log: "Duplicate file detected"
```

### Beneficios Cuantificados

**Ejemplo: 100 usuarios, cada uno sube el mismo PDF 10 veces**

Sin deduplicación:
- 📁 Storage: 1000 archivos × 2 MB = 2 GB
- ⚙️ Procesamiento: 1000 × 5 segundos = 83 minutos
- 💾 Qdrant: 1000 × 11 chunks × 1.5 KB = 16.5 MB

Con deduplicación:
- 📁 Storage: 100 archivos × 2 MB = 200 MB ✅ **90% ahorro**
- ⚙️ Procesamiento: 100 × 5 segundos = 8.3 minutos ✅ **90% ahorro**
- 💾 Qdrant: 100 × 11 chunks × 1.5 KB = 1.65 MB ✅ **90% ahorro**

## Monitoreo y Alertas

### Métricas Clave

**1. Usage Percentage**
- **Qué mide**: % de uso respecto al límite configurado
- **Umbral crítico**: > 90%
- **Acción**: Cleanup urgente automático

**2. Cleanup Priority**
- **LOW**: < 50% uso (sin acción)
- **MEDIUM**: 50-75% uso (monitoreo)
- **HIGH**: 75-90% uso (cleanup programado)
- **CRITICAL**: > 90% uso (cleanup inmediato)

**3. Oldest Item Age**
- **Qué mide**: Edad del recurso más antiguo (horas)
- **Umbral**: > 2× TTL configurado
- **Acción**: Indica que cleanup no está funcionando

### Logs Estructurados

```json
{
  "event": "Resource monitoring completed",
  "metrics": {
    "redis": {"usage_percentage": 0.177, "priority": "LOW"},
    "qdrant": {"usage_percentage": 0.0003, "priority": "LOW"},
    "minio": {"usage_percentage": 0.009, "priority": "LOW"}
  },
  "timestamp": "2025-01-20T15:30:00Z"
}
```

```json
{
  "event": "Cleanup task processed",
  "resource_type": "qdrant_vectors",
  "priority": "HIGH",
  "deleted_count": 150,
  "reason": "High resource usage: 78.5%",
  "timestamp": "2025-01-20T15:35:00Z"
}
```

## Troubleshooting

### Problema: Uso de memoria creciendo constantemente

**Diagnóstico:**
```bash
# Ver métricas
curl http://localhost:8001/api/resources/metrics -H "Authorization: Bearer $TOKEN" | jq .

# Verificar si cleanup worker está corriendo
docker logs octavios-chat-client-project-api | grep "ResourceCleanupWorker"
```

**Soluciones:**
1. **Worker no está iniciado**: Verificar `lifespan()` en `main.py`
2. **Intervalos muy largos**: Reducir `*_CLEANUP_INTERVAL_SECONDS`
3. **TTL muy largos**: Reducir `*_TTL_HOURS` / `*_TTL_DAYS`
4. **Límites muy altos**: Reducir `MAX_*` variables

### Problema: Archivos duplicados no se detectan

**Diagnóstico:**
```bash
# Verificar que hash se está almacenando
db.documents.find({}, {"metadata.file_hash": 1, "filename": 1})
```

**Soluciones:**
1. **Hash no se almacena**: Verificar integración en `file_ingest.py`
2. **Scope incorrecto**: Deduplicación es por usuario (user_id + hash)
3. **Hash diferente**: Archivos con metadata diferente generan hash diferente

### Problema: Cleanup muy agresivo (elimina archivos activos)

**Diagnóstico:**
```bash
# Ver sesiones activas
db.chat_sessions.find({"updated_at": {$gte: new Date(Date.now() - 24*60*60*1000)}})
```

**Soluciones:**
1. **TTL muy corto**: Aumentar `FILES_TTL_DAYS`
2. **No verifica sesiones activas**: Revisar `_cleanup_minio_files()`
3. **Timestamp incorrecto**: Verificar `updated_at` en sesiones

## Best Practices

### 1. Configuración por Entorno

**Development:**
```bash
# Limpieza agresiva para testing
REDIS_CACHE_TTL_HOURS=0.5
RAG_SESSION_TTL_HOURS=2
FILES_TTL_DAYS=1
REDIS_CLEANUP_INTERVAL_SECONDS=1800  # 30 min
```

**Production:**
```bash
# Balance entre disponibilidad y eficiencia
REDIS_CACHE_TTL_HOURS=1
RAG_SESSION_TTL_HOURS=24
FILES_TTL_DAYS=7
REDIS_CLEANUP_INTERVAL_SECONDS=3600  # 1 hora
```

### 2. Monitoreo Proactivo

```bash
# Cron job para alertas (cada 5 minutos)
*/5 * * * * curl -s http://localhost:8001/api/resources/metrics | \
  jq -r '.[] | select(.usage_percentage > 80) | "ALERT: \(.resource_type) at \(.usage_percentage)%"'
```

### 3. Cleanup Manual Periódico

```bash
# Script semanal de mantenimiento
#!/bin/bash
curl -X POST http://localhost:8001/api/resources/cleanup \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"resource_type": null}'  # Limpia todo
```

### 4. Backup Antes de Cleanup

```bash
# Backup MongoDB antes de cleanup masivo
docker exec octavios-chat-client-project-mongodb mongodump --out /backup/$(date +%Y%m%d)

# Ejecutar cleanup
curl -X POST http://localhost:8001/api/resources/cleanup ...
```

## Arquitectura de Cola de Prioridad

### Estructura de CleanupTask

```python
@dataclass
class CleanupTask:
    priority: CleanupPriority    # 1=CRITICAL, 4=LOW
    resource_type: ResourceType  # redis/qdrant/minio
    target_id: str               # ID específico o "all"
    created_at: datetime
    reason: str                  # "High resource usage: 85%"
```

### Algoritmo de Scheduling

```python
# 1. Monitoreo detecta uso alto
if usage_percentage >= 0.75:
    priority = CleanupPriority.HIGH

    # 2. Agrega a cola
    await manager.schedule_cleanup_task(
        resource_type=ResourceType.QDRANT_VECTORS,
        target_id="all",
        priority=priority,
        reason=f"High resource usage: {usage_percentage:.1%}"
    )

# 3. Cola se ordena automáticamente por priority
cleanup_queue.sort(key=lambda t: t.priority.value)

# 4. Procesa tareas de mayor prioridad primero
while cleanup_queue and processed < max_tasks:
    task = cleanup_queue.pop(0)  # FIFO dentro de misma prioridad
    await cleanup_expired_resources(task.resource_type)
```

## Referencias

- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [Asyncio Task Management](https://docs.python.org/3/library/asyncio-task.html)
- [Redis Memory Optimization](https://redis.io/docs/management/optimization/memory-optimization/)
- [Qdrant Collection Management](https://qdrant.tech/documentation/concepts/collections/)

## Changelog

- **v1.0** (2025-01-20): Implementación inicial
  - Deduplicación basada en SHA256
  - Background worker con 4 tasks concurrentes
  - API de monitoreo y cleanup manual
  - Políticas de retención configurables
