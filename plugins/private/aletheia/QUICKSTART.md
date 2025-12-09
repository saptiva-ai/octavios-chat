# 🚀 Quickstart - Aletheia Web Search API

## Inicio Rápido (5 minutos)

### 1. Configurar Variables de Entorno

```bash
# Navegar a la carpeta del proyecto
cd /home/jazielflo/Proyects/alethia_deepresearch

# Las claves ya están en infra/docker/.env.alethia
# Si necesitas cambiarlas, edita ese archivo
```

### 2. Levantar el API (Opción Local)

```bash
# Activar entorno virtual (si existe, sino crear con: python3 -m venv .venv)
source .venv/bin/activate

# Instalar dependencias (si no están instaladas)
pip install -r requirements.txt

# Exportar variables necesarias
export WEB_SEARCH_ENABLED=true
export SAPTIVA_API_KEY=va-ai-Jm4BHuDYPiNAlv7OoBuO8G58S23sSgIAmbZ6nqUKFOqSY8vmB2Liba-ZRzcgjJLpqOFmza8bK9vvUT39EhaKjeGZHFJE8EVQtKABOG1hc_A
export TAVILY_API_KEY=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
export SAPTIVA_MODEL_WRITER="Saptiva Cortex"
export PYTHONPATH=/home/jazielflo/Proyects/alethia_deepresearch

# Ejecutar API
uvicorn apps.api.main:app --host 0.0.0.0 --port 7070
```

### 3. Verificar que Funciona

```bash
# En otra terminal:
curl http://localhost:7070/health | jq
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "version": "v1alpha1",
  "uptime_seconds": 10.5,
  "environment": "production",
  "services": {
    "saptiva": true,
    "tavily": true,
    "web_search": true,
    "vector_store": false,
    "telemetry": false
  }
}
```

### 4. Hacer una Búsqueda Web

```bash
curl -X POST http://localhost:7070/web-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "¿Cuáles son los principales bancos digitales en México en 2024?",
    "max_uses": 5,
    "locale": "es"
  }' | jq
```

**Respuesta esperada:**
```json
{
  "answer": "Respuesta sintetizada con citaciones [1], [2]...",
  "confidence": 0.85,
  "sources": [
    {
      "url": "https://example.com/...",
      "title": "Título de la fuente",
      "snippet": "Extracto del contenido...",
      "first_seen_at": "2025-10-03T...",
      "source_type": "WEB"
    }
  ],
  "diagnostics": {
    "fetches": 5,
    "elapsed_ms": 2500
  }
}
```

---

## 📊 Endpoints Disponibles

### 1. Health Check
```bash
GET http://localhost:7070/health
```

### 2. Web Search
```bash
POST http://localhost:7070/web-search
Content-Type: application/json

{
  "query": "tu pregunta",
  "max_uses": 6,
  "locale": "es"
}
```

### 3. Research (básico)
```bash
POST http://localhost:7070/research
Content-Type: application/json

{
  "query": "análisis de mercado fintech"
}
```

### 4. Deep Research
```bash
POST http://localhost:7070/deep-research
Content-Type: application/json

{
  "query": "análisis estratégico",
  "max_iterations": 3,
  "min_completion_score": 0.75
}
```

---

## 🐳 Opción Docker (Recomendado para Producción)

```bash
# Levantar con docker-compose
docker-compose -f infra/docker/docker-compose.alethia.yml --env-file infra/docker/.env.alethia up -d

# Ver logs
docker logs -f alethia-api

# Detener
docker-compose -f infra/docker/docker-compose.alethia.yml down
```

---

## 🔧 Troubleshooting

### Error: "Web search is not enabled"
```bash
# Asegúrate de exportar:
export WEB_SEARCH_ENABLED=true
```

### Error: "Tavily API key not configured"
```bash
# Asegúrate de exportar:
export TAVILY_API_KEY=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
```

### Error: Puerto 7070 en uso
```bash
# Verificar qué usa el puerto
lsof -i :7070

# O usa otro puerto
uvicorn apps.api.main:app --host 0.0.0.0 --port 8080
```

---

## 📖 Documentación Completa

- **OpenAPI Spec**: `/openapi.yaml`
- **Implementación Detallada**: `/IMPLEMENTATION.md`
- **README Principal**: `/README.md`
- **SDK TypeScript**: `/sdk/typescript/README.md`

---

## 🎯 Próximos Pasos

1. **Integrar con copilot-ui**: El API está escuchando en `http://localhost:7070`
2. **Personalizar**: Ajustar parámetros en `.env.alethia` según necesidades
3. **Escalar**: Usar Docker Compose para producción
4. **Monitorear**: Activar telemetría con `ENABLE_TELEMETRY=true`

---

## 💡 Ejemplos de Uso

### Búsqueda Simple
```bash
curl -X POST http://localhost:7070/web-search \
  -H "Content-Type: application/json" \
  -d '{"query":"neobancos méxico","max_uses":5}'
```

### Búsqueda con Filtro de Dominios
```bash
curl -X POST http://localhost:7070/web-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "regulación fintech",
    "allowed_domains": ["gob.mx", "forbes.com.mx"],
    "max_uses": 8
  }'
```

### Usando el SDK TypeScript
```typescript
import { createAletheiaClient } from '@aletheia/client';

const client = createAletheiaClient({
  baseUrl: 'http://localhost:7070'
});

const result = await client.webSearch({
  query: 'bancos digitales México',
  max_uses: 6
});

console.log(result.answer);
```

¡Listo para usar! 🚀
