# Guía Práctica: Tools MCP de OctaviOS

Guía completa para usar las herramientas MCP (Model Context Protocol) en OctaviOS Chat, con énfasis en **adjuntar archivos** y **auditar archivos** (COPILOTO_414).

---

## 📋 Tools Disponibles

OctaviOS actualmente tiene **5 tools MCP** implementadas:

| # | Tool | Descripción | Versión |
|---|------|-------------|---------|
| 1 | `audit_file` | Validación COPILOTO_414 de compliance | 1.0.0 |
| 2 | `excel_analyzer` | Análisis de archivos Excel | 1.0.0 |
| 3 | `viz_tool` | Generación de gráficos (Plotly/ECharts) | 1.0.0 |
| 4 | `deep_research` | Investigación multi-paso con Aletheia | 1.0.0 |
| 5 | `extract_document_text` | Extracción de texto multi-tier | 1.0.0 |

---

## 🚀 Inicio Rápido

### 1. Iniciar el ambiente

```bash
# Iniciar servicios
make dev

# Verificar que todo está corriendo
docker compose ps
```

### 2. Crear usuario demo (opcional)

```bash
make create-demo-user
# Usuario: demo
# Password: Demo1234
```

### 3. Verificar MCP está activo

```bash
# Health check
curl http://localhost:8000/api/mcp/health

# Debería responder:
# {
#   "status": "ok",
#   "mcp_version": "1.0.0",
#   "tools_registered": 5,
#   "tools": [...]
# }
```

---

## 📁 Flujo: Adjuntar y Auditar Archivo

Este es el flujo completo para subir un PDF y auditarlo con COPILOTO_414.

### Paso 1: Autenticación

```bash
# Login para obtener token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "identifier": "demo",
    "password": "Demo1234"
  }'

# Respuesta:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIs...",
#   "token_type": "bearer",
#   "user": { ... }
# }

# Guardar token en variable
export TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

### Paso 2: Adjuntar Archivo (Upload)

```bash
# Subir un PDF
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/ruta/a/tu/documento.pdf" \
  -F "conversation_id=test-conversation-001"

# Respuesta exitosa:
# {
#   "files": [
#     {
#       "file_id": "674a5b8c9e7f12a3b4c5d6e7",
#       "filename": "documento.pdf",
#       "status": "processing",
#       "size_bytes": 245678,
#       "content_type": "application/pdf",
#       "sse_url": "/api/files/events/674a5b8c9e7f12a3b4c5d6e7",
#       "phase": "upload",
#       "timestamp": "2025-11-11T16:30:45.123Z"
#     }
#   ]
# }

# IMPORTANTE: Guardar el file_id
export FILE_ID="674a5b8c9e7f12a3b4c5d6e7"
```

#### Monitorear Progreso (SSE)

```bash
# Escuchar eventos de procesamiento en tiempo real
curl -N http://localhost:8000/api/files/events/$FILE_ID \
  -H "Authorization: Bearer $TOKEN"

# Eventos SSE:
# event: progress
# data: {"phase":"upload","progress":100,"message":"Upload complete"}
#
# event: progress
# data: {"phase":"extract","progress":50,"message":"Extracting text..."}
#
# event: complete
# data: {"phase":"ready","file_id":"674a5b8c9e7f12a3b4c5d6e7","status":"ready"}
```

### Paso 3: Listar Tools MCP Disponibles

```bash
# Ver todas las tools
curl http://localhost:8000/api/mcp/tools \
  -H "Authorization: Bearer $TOKEN"

# Respuesta:
# [
#   {
#     "name": "audit_file",
#     "version": "1.0.0",
#     "display_name": "Audit File",
#     "description": "Validate PDF documents against COPILOTO_414 compliance policies...",
#     "category": "general",
#     "requires_auth": true
#   },
#   ...
# ]
```

### Paso 4: Auditar Archivo (COPILOTO_414)

```bash
# Invocar tool de auditoría
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "audit_file",
    "payload": {
      "doc_id": "'"$FILE_ID"'",
      "policy_id": "auto",
      "enable_disclaimer": true,
      "enable_format": true,
      "enable_logo": true
    }
  }'

# Respuesta exitosa:
# {
#   "success": true,
#   "tool": "audit_file",
#   "version": "1.0.0",
#   "result": {
#     "job_id": "audit_job_123abc",
#     "status": "done",
#     "findings": [
#       {
#         "type": "disclaimer",
#         "severity": "error",
#         "issue": "Disclaimer 'CONFIDENCIAL' not found",
#         "location": "page:1,footer",
#         "suggestion": "Add 'CONFIDENCIAL' disclaimer in footer"
#       },
#       {
#         "type": "format",
#         "severity": "warning",
#         "issue": "Font 'Arial' used instead of 'Helvetica'",
#         "location": "page:2",
#         "suggestion": "Use Helvetica font as per brand guidelines"
#       }
#     ],
#     "summary": {
#       "total_findings": 2,
#       "errors": 1,
#       "warnings": 1,
#       "info": 0,
#       "policy_id": "auto",
#       "policy_name": "Auto-detected Policy"
#     }
#   },
#   "error": null,
#   "duration_ms": 2345.67,
#   "invocation_id": "inv_abc123"
# }
```

---

## 🛠️ Ejemplos Detallados por Tool

### 1️⃣ audit_file - Validación COPILOTO_414

**Propósito**: Validar compliance de documentos PDF contra políticas corporativas.

**Parámetros**:

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `doc_id` | string | ✅ Sí | - | ID del documento a validar |
| `policy_id` | string | ❌ No | "auto" | Política: auto, 414-std, 414-strict, banamex, afore-xxi |
| `enable_disclaimer` | boolean | ❌ No | true | Activar auditor de disclaimers |
| `enable_format` | boolean | ❌ No | true | Activar auditor de formato |
| `enable_logo` | boolean | ❌ No | true | Activar auditor de logos |

**Ejemplo con política estricta**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "audit_file",
    "payload": {
      "doc_id": "'"$FILE_ID"'",
      "policy_id": "414-strict",
      "enable_disclaimer": true,
      "enable_format": true,
      "enable_logo": true
    }
  }'
```

**Ejemplo con solo disclaimer**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "audit_file",
    "payload": {
      "doc_id": "'"$FILE_ID"'",
      "policy_id": "auto",
      "enable_disclaimer": true,
      "enable_format": false,
      "enable_logo": false
    }
  }'
```

**Tipos de findings**:

| Tipo | Descripción |
|------|-------------|
| `disclaimer` | Validación de textos legales obligatorios |
| `format` | Validación de fuentes, colores, números |
| `logo` | Detección de presencia/posición de logos |
| `grammar` | Ortografía y gramática (LanguageTool) |

**Severidades**:

- `error` 🔴 - Viola política (debe corregirse)
- `warning` 🟡 - Recomendación (debería corregirse)
- `info` 🔵 - Informativo (opcional)

---

### 2️⃣ extract_document_text - Extracción de Texto

**Propósito**: Extraer texto de PDFs e imágenes con estrategia multi-tier.

**Parámetros**:

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `doc_id` | string | ✅ Sí | - | ID del documento |
| `method` | string | ❌ No | "auto" | auto, pypdf, saptiva_sdk, ocr |
| `include_metadata` | boolean | ❌ No | true | Incluir metadata del documento |

**Ejemplo básico**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "extract_document_text",
    "payload": {
      "doc_id": "'"$FILE_ID"'",
      "method": "auto"
    }
  }'

# Respuesta:
# {
#   "success": true,
#   "result": {
#     "doc_id": "674a5b8c9e7f12a3b4c5d6e7",
#     "text": "Contenido del documento extraído...",
#     "method_used": "pypdf",
#     "metadata": {
#       "filename": "documento.pdf",
#       "content_type": "application/pdf",
#       "char_count": 5432,
#       "word_count": 987,
#       "cached": false,
#       "extraction_duration_ms": 234.56
#     }
#   }
# }
```

**Forzar OCR para documentos escaneados**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "extract_document_text",
    "payload": {
      "doc_id": "'"$FILE_ID"'",
      "method": "ocr"
    }
  }'
```

---

### 3️⃣ excel_analyzer - Análisis de Excel

**Propósito**: Analizar archivos Excel y generar estadísticas.

**Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `doc_id` | string | ✅ Sí | ID del documento Excel |
| `sheet_name` | string | ❌ No | Nombre de la hoja (default: primera) |
| `operations` | array | ❌ No | ["stats", "aggregate", "validate", "preview"] |
| `aggregate_columns` | array | ❌ No | Columnas para agregar |

**Ejemplo con estadísticas**:

```bash
# Primero subir un archivo Excel
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/ruta/a/datos.xlsx"

# Analizar Excel
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "excel_analyzer",
    "payload": {
      "doc_id": "'"$EXCEL_FILE_ID"'",
      "operations": ["stats", "aggregate", "preview"],
      "aggregate_columns": ["revenue", "cost", "profit"]
    }
  }'

# Respuesta:
# {
#   "success": true,
#   "result": {
#     "stats": {
#       "row_count": 150,
#       "column_count": 5,
#       "columns": [
#         {"name": "revenue", "dtype": "float64", "non_null_count": 150, "null_count": 0}
#       ]
#     },
#     "aggregates": {
#       "revenue": {"sum": 150000.0, "mean": 1000.0, "median": 950.0, "std": 234.5}
#     },
#     "preview": [
#       {"month": "Jan", "revenue": 10000, "cost": 5000, "profit": 5000},
#       ...
#     ]
#   }
# }
```

---

### 4️⃣ deep_research - Investigación Aletheia

**Propósito**: Investigación multi-paso con síntesis.

**Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `query` | string | ✅ Sí | Pregunta de investigación |
| `depth` | string | ❌ No | shallow, medium, deep |
| `focus_areas` | array | ❌ No | Áreas de enfoque |
| `max_iterations` | integer | ❌ No | Máximo de iteraciones (1-10) |

**Ejemplo**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "deep_research",
    "payload": {
      "query": "¿Cuáles son las tendencias en IA para 2025?",
      "depth": "medium",
      "focus_areas": ["LLMs", "computer vision", "robotics"]
    }
  }'

# Respuesta:
# {
#   "success": true,
#   "result": {
#     "task_id": "research_task_abc123",
#     "status": "pending",
#     "query": "¿Cuáles son las tendencias en IA para 2025?",
#     "metadata": {
#       "max_iterations": 3,
#       "depth": "medium"
#     }
#   }
# }
```

---

### 5️⃣ viz_tool - Visualización de Datos

**Propósito**: Generar especificaciones de gráficos interactivos.

**Parámetros**:

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `chart_type` | string | ✅ Sí | bar, line, pie, scatter, heatmap |
| `data_source` | object | ✅ Sí | Fuente de datos |
| `x_column` | string | ❌ No | Columna eje X |
| `y_column` | string | ❌ No | Columna eje Y |
| `title` | string | ❌ No | Título del gráfico |

**Ejemplo con datos inline**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "viz_tool",
    "payload": {
      "chart_type": "bar",
      "data_source": {
        "type": "inline",
        "data": [
          {"month": "Jan", "revenue": 10000},
          {"month": "Feb", "revenue": 15000},
          {"month": "Mar", "revenue": 12000}
        ]
      },
      "x_column": "month",
      "y_column": "revenue",
      "title": "Monthly Revenue"
    }
  }'
```

**Ejemplo con datos de Excel**:

```bash
curl -X POST http://localhost:8000/api/mcp/tools/invoke \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "viz_tool",
    "payload": {
      "chart_type": "line",
      "data_source": {
        "type": "excel",
        "doc_id": "'"$EXCEL_FILE_ID"'",
        "sheet_name": "Sales"
      },
      "x_column": "date",
      "y_column": "revenue",
      "title": "Sales Trend"
    }
  }'
```

---

## 🧪 Testing con Postman

### Colección de Requests

Crea una colección en Postman con estas requests:

**1. Login**
```
POST http://localhost:8000/api/auth/login
Body (JSON):
{
  "identifier": "demo",
  "password": "Demo1234"
}

# Guardar access_token en variable de entorno: {{token}}
```

**2. Upload File**
```
POST http://localhost:8000/api/files/upload
Headers:
  Authorization: Bearer {{token}}
Body (form-data):
  files: [seleccionar archivo]
  conversation_id: test-conv-001

# Guardar file_id en variable: {{file_id}}
```

**3. Audit File**
```
POST http://localhost:8000/api/mcp/tools/invoke
Headers:
  Authorization: Bearer {{token}}
  Content-Type: application/json
Body (JSON):
{
  "tool": "audit_file",
  "payload": {
    "doc_id": "{{file_id}}",
    "policy_id": "auto"
  }
}
```

---

## 🐛 Troubleshooting

### Error: "Document not found"

**Causa**: El documento no existe o no se ha terminado de procesar.

**Solución**:
```bash
# Verificar que el archivo se subió correctamente
curl http://localhost:8000/api/files/events/$FILE_ID \
  -H "Authorization: Bearer $TOKEN"

# Esperar a que el status sea "ready"
```

### Error: "Tool not found"

**Causa**: La tool MCP no está registrada.

**Solución**:
```bash
# Verificar tools disponibles
curl http://localhost:8000/api/mcp/tools \
  -H "Authorization: Bearer $TOKEN"

# Reiniciar servicio API
docker compose restart api
```

### Error: "Permission denied"

**Causa**: Intentando acceder a documento de otro usuario.

**Solución**:
```bash
# Asegurarse de usar el mismo usuario que subió el archivo
# Verificar que el token sea válido
```

---

## 📚 Referencias

- [MCP Architecture](./MCP_ARCHITECTURE.md) - Arquitectura completa de MCP
- [Integration Tests](../apps/api/tests/integration/README_MCP_TESTS.md) - Tests de integración
- [Performance Tests](../apps/api/tests/performance/README_PERFORMANCE.md) - Tests de performance
- [CLAUDE.md](../CLAUDE.md) - Contexto del proyecto
- [FastMCP Documentation](https://github.com/jlowin/fastmcp) - SDK oficial

---

## 🎯 Próximos Pasos

1. **Frontend UI**: Interfaz gráfica para invocar tools
2. **Webhooks**: Notificaciones cuando auditoría completa
3. **Batch Processing**: Auditar múltiples archivos en paralelo
4. **Custom Policies**: Editor visual de políticas COPILOTO_414
5. **Reportes PDF**: Generación automática de reportes de auditoría
