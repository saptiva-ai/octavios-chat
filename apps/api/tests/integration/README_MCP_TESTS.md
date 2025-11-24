# MCP Integration Tests

Este directorio contiene tests de integración end-to-end para las herramientas MCP (Model Context Protocol) integradas en OctaviOS Chat.

## 📋 Descripción

Los tests de integración MCP verifican el comportamiento completo del sistema usando **conexiones reales** a:
- ✅ MongoDB (base de datos)
- ✅ Redis (caché)
- ✅ MinIO (almacenamiento de archivos)
- ✅ FastAPI (servidor HTTP)

A diferencia de los tests unitarios que usan mocks, estos tests validan el flujo completo desde la petición HTTP hasta la respuesta, incluyendo autenticación, autorización, y servicios reales.

## 🧪 Tests Incluidos

### `test_mcp_tools_integration.py`

**Cobertura total**: 17 tests organizados en 6 clases

#### 1. TestMCPToolsEndpoints (2 tests)
- ✅ Listar todas las herramientas MCP disponibles
- ✅ Rechazar peticiones sin autenticación

#### 2. TestDeepResearchToolIntegration (3 tests)
- ✅ Crear tarea de investigación vía endpoint MCP
- ✅ Validar parámetros (depth inválido)
- ✅ Rechazar peticiones sin autenticación

#### 3. TestDocumentExtractionToolIntegration (3 tests)
- ✅ Extraer texto de documento usando caché
- ✅ Verificar permisos de acceso entre usuarios
- ✅ Manejar documentos no encontrados

#### 4. TestAuditFileToolIntegration (1 test)
- ✅ Validar documento PDF con Document Audit

#### 5. TestExcelAnalyzerToolIntegration (2 tests)
- ✅ Analizar archivo Excel y retornar estadísticas
- ✅ Rechazar documentos con tipo incorrecto

#### 6. TestMCPToolErrorHandling (2 tests)
- ✅ Manejar herramientas no encontradas
- ✅ Validar campos requeridos faltantes

## 🚀 Ejecución de Tests

### Comandos Makefile (Recomendado)

```bash
# Ejecutar TODOS los tests MCP (unit + integration)
make test-mcp-all

# Ejecutar SOLO tests de integración MCP
make test-mcp-integration

# Ejecutar SOLO tests unitarios MCP (sin integration)
make test-mcp-unit

# Ejecutar tests MCP regulares (marker mcp)
make test-mcp

# Ejecutar con argumentos adicionales
make test-mcp-integration ARGS="-v -s"
make test-mcp-integration ARGS="--tb=short"
```

### Pytest Directo (Dentro del contenedor)

```bash
# Entrar al contenedor
docker compose exec api bash

# Ejecutar todos los tests de integración MCP
pytest tests/integration/test_mcp_tools_integration.py -v -m integration

# Ejecutar una clase específica
pytest tests/integration/test_mcp_tools_integration.py::TestDeepResearchToolIntegration -v

# Ejecutar un test específico
pytest tests/integration/test_mcp_tools_integration.py::TestMCPToolsEndpoints::test_mcp_tools_list_endpoint -v

# Ver output detallado
pytest tests/integration/test_mcp_tools_integration.py -v -s

# Stop on first failure
pytest tests/integration/test_mcp_tools_integration.py -v -x
```

## 🏗️ Arquitectura de Tests

### Fixtures Compartidas

Los tests utilizan fixtures definidas en `conftest.py`:

- **`client`**: AsyncClient HTTP autenticado
- **`clean_db`**: Limpia la base de datos antes/después de cada test
- **`initialize_db`**: Inicializa conexión a MongoDB
- **`test_user`**: Usuario de prueba con credenciales

### Fixtures MCP Específicas

Definidas en `test_mcp_tools_integration.py`:

- **`test_user_with_token`**: Usuario + token de acceso
- **`test_document_pdf`**: Documento PDF de prueba en base de datos
- **`test_document_excel`**: Documento Excel de prueba en base de datos

### Patrón de Test

```python
async def test_tool_invocation(self, client: AsyncClient, test_user_with_token):
    """Test pattern."""
    access_token, user_id = test_user_with_token

    # 1. Preparar payload
    payload = {
        "tool": "tool_name",
        "payload": {...},
        "context": {"user_id": user_id}
    }

    # 2. Hacer petición HTTP
    response = await client.post(
        "/api/mcp/tools/invoke",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"}
    )

    # 3. Verificar respuesta
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

## 🔧 Configuración

### Prerequisitos

1. **Docker Compose** debe estar corriendo:
   ```bash
   make dev
   ```

2. **Servicios necesarios**:
   - ✅ MongoDB (puerto 27018 → 27017)
   - ✅ Redis (puerto 6380 → 6379)
   - ✅ MinIO (puerto 9000)
   - ✅ API (puerto 8000)

### Variables de Entorno

Los tests usan las variables de `envs/.env` con overrides para testing:

```bash
# MongoDB test connection
MONGODB_URL=mongodb://user:pass@localhost:27018/octavios?authSource=admin

# Redis test connection
REDIS_URL=redis://:password@localhost:6380
```

## 📊 Cobertura de Tests

### Tools Cubiertas

| Tool | Unit Tests | Integration Tests | Total |
|------|-----------|-------------------|-------|
| `deep_research` | ✅ 15 | ✅ 3 | 18 |
| `extract_document_text` | ✅ 18 | ✅ 3 | 21 |
| `audit_file` | ✅ Existing | ✅ 1 | - |
| `excel_analyzer` | ✅ Existing | ✅ 2 | - |
| `viz_tool` | ✅ Existing | ❌ TODO | - |

### Endpoints HTTP Cubiertos

- ✅ `GET /api/mcp/tools` - Listar herramientas
- ✅ `POST /api/mcp/tools/invoke` - Invocar herramienta
- ✅ Autenticación JWT
- ✅ Manejo de errores
- ✅ Validación de permisos

## 🐛 Troubleshooting

### Error: "Connection refused"

**Problema**: No puede conectar a MongoDB/Redis

**Solución**:
```bash
# Verificar que Docker Compose está corriendo
docker compose ps

# Iniciar servicios si están parados
make dev

# Verificar logs
docker compose logs mongodb redis
```

### Error: "Tool not found"

**Problema**: La herramienta MCP no está registrada

**Solución**:
```bash
# Verificar registro de tools en server.py
# Verificar que FastMCP server está inicializado en main.py
# Reiniciar contenedor API
docker compose restart api
```

### Error: "Document not found"

**Problema**: El documento de prueba no se creó correctamente

**Solución**:
```bash
# Verificar que las fixtures crean documentos
# Verificar conexión a MongoDB
# Limpiar base de datos de test
make clean-db
```

### Tests muy lentos

**Problema**: Tests de integración tardan mucho

**Solución**:
```bash
# Ejecutar solo tests específicos
make test-mcp-integration ARGS="-k test_name"

# Usar pytest-xdist para paralelización (cuidado con fixtures async)
pytest tests/integration/test_mcp_tools_integration.py -v -n auto

# Ejecutar solo tests unitarios (más rápidos)
make test-mcp-unit
```

## 📝 Agregar Nuevos Tests

### 1. Crear nueva clase de test

```python
@pytest.mark.integration
@pytest.mark.asyncio
class TestNewToolIntegration:
    """Integration tests for new_tool."""

    async def test_new_tool_basic(self, client, test_user_with_token):
        """Test basic functionality."""
        access_token, user_id = test_user_with_token

        payload = {
            "tool": "new_tool",
            "payload": {"param": "value"}
        }

        response = await client.post(
            "/api/mcp/tools/invoke",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
```

### 2. Agregar fixtures específicas si es necesario

```python
@pytest.fixture
async def test_specific_data(test_user_with_token):
    """Create specific test data."""
    access_token, user_id = test_user_with_token

    # Create test data in database
    # ...

    return data_id, access_token, user_id
```

### 3. Ejecutar y verificar

```bash
# Ejecutar nuevo test
make test-mcp-integration ARGS="-k test_new_tool_basic -v"

# Verificar cobertura
pytest tests/integration/test_mcp_tools_integration.py --cov=src/mcp --cov-report=html
```

## 🎯 Best Practices

1. **Usar markers**: Siempre marcar tests de integración con `@pytest.mark.integration`
2. **Cleanup**: Las fixtures deben limpiar datos creados (usar `yield` + cleanup)
3. **Isolation**: Cada test debe ser independiente (no compartir estado)
4. **Real services**: No usar mocks en tests de integración (usar servicios reales)
5. **Fast fixtures**: Reutilizar fixtures cuando sea posible para speed
6. **Descriptive names**: Nombres de tests deben describir qué validan
7. **Assertions**: Múltiples assertions para verificar respuesta completa

## 📚 Referencias

- [MCP Architecture](../../../../docs/MCP_ARCHITECTURE.md) - Arquitectura general de MCP
- [MCP Testing Guide](../../../../docs/MCP_TESTING_GUIDE.md) - Guía de testing
- [CLAUDE.md](../../../../CLAUDE.md) - Contexto del proyecto
- [Pytest Async](https://pytest-asyncio.readthedocs.io/) - pytest-asyncio docs
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/) - FastAPI testing guide
