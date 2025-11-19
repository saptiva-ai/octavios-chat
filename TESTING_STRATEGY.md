# ESTRATEGIA DE TESTING - CAPITAL 414 FIXES

**Objetivo**: Garantizar que los bugs reportados por 414 Capital NUNCA vuelvan a ocurrir mediante una suite comprehensiva de tests automatizados.

---

## 🏗️ CAPAS DE TESTING

### 1. Unit Tests (Backend - pytest)
**Ubicación**: `apps/api/tests/unit/`

**Componentes a testear**:
- ✅ Orquestador de chat: manejo de mensajes, adjuntos, selección de modelo, timeouts
- ✅ Model clients (Qwen, Turbo, Llama): parámetros, max_tokens, system prompt, manejo de errores
- ✅ Prompt Registry: resolución de prompts, parámetros por modelo
- ✅ Document Service: extracción de texto, manejo de errores

### 2. Integration Tests (pytest + httpx)
**Ubicación**: `apps/api/tests/integration/`

**Alcance**:
- ✅ Rutas reales de FastAPI (`/api/chat`, `/api/chat/stream`)
- ✅ Base de datos MongoDB (test DB o mocks)
- ✅ Storage de archivos (MinIO test o filesystem mock)
- ❌ Sin frontend - solo API

### 3. E2E Tests (Playwright)
**Ubicación**: `apps/web/tests/e2e/`

**Alcance**:
- ✅ Navegador real (Chrome headless)
- ✅ Flujos completos: usuario escribe, adjunta PDFs, ve respuestas
- ✅ Validar UI nunca se queda "colgada" sin feedback
- ✅ Estados de loading, errores, mensajes completos

### 4. Behavior Tests (Evals ligeros)
**Ubicación**: `apps/api/tests/behavior/`

**Alcance**:
- ✅ Golden prompts para: identidad, ubicación de datos, 414 Capital, uso de documentos
- ⚠️ Más frágiles, pero sirven como "alarmas de humo"
- ✅ Validación de que modelos siguen políticas de compliance

---

## 🎯 CASOS DE PRUEBA POR BUG

### A. Mensajes con archivos que no responden

**Objetivo**: Cualquier mensaje con archivos debe producir algo (respuesta O error visible), NUNCA silencio.

#### Integration Tests (API)

**Archivo**: `apps/api/tests/integration/test_chat_with_files.py`

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_single_pdf_with_prompt_returns_response_or_error(
    api_client: AsyncClient,
    sample_pdf_file,
    auth_headers
):
    """
    Input: prompt + 1 PDF
    Assert: status 200 y payload con:
      - assistant_message no vacío O
      - error estructurado (code, message)
    """
    # Upload document
    files = {"file": ("test.pdf", sample_pdf_file, "application/pdf")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["document_id"]

    # Send chat message with file
    payload = {
        "message": "Resume este documento",
        "file_ids": [doc_id],
        "model": "Saptiva Turbo",
        "stream": False
    }
    chat_resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert chat_resp.status_code == 200
    data = chat_resp.json()

    # MUST have response OR error (never silent failure)
    assert (
        (data.get("content") and len(data["content"]) > 0) or
        (data.get("error") and data["error"].get("message"))
    ), "Chat with file attachment returned neither content nor error"


@pytest.mark.asyncio
async def test_multiple_pdfs_with_prompt(
    api_client: AsyncClient,
    sample_pdf_files,  # Fixture returning list of 3 PDFs
    auth_headers
):
    """2-3 PDFs, mismo assert que test anterior"""
    doc_ids = []
    for pdf_file in sample_pdf_files:
        files = {"file": ("test.pdf", pdf_file, "application/pdf")}
        upload_resp = await api_client.post(
            "/api/documents/upload",
            files=files,
            headers=auth_headers
        )
        assert upload_resp.status_code == 200
        doc_ids.append(upload_resp.json()["document_id"])

    payload = {
        "message": "Compara estos documentos y resume las diferencias",
        "file_ids": doc_ids,
        "model": "Saptiva Cortex",
        "stream": False
    }
    chat_resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert (
        (data.get("content") and len(data["content"]) > 0) or
        (data.get("error") and data["error"].get("message"))
    )


@pytest.mark.asyncio
async def test_pdf_without_prompt(
    api_client: AsyncClient,
    sample_pdf_file,
    auth_headers
):
    """
    Solo archivos, prompt vacío o muy corto.
    Esperado: mensaje claro tipo "necesito una instrucción..."
    o análisis por defecto, pero NUNCA silencio.
    """
    files = {"file": ("test.pdf", sample_pdf_file, "application/pdf")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )
    doc_id = upload_resp.json()["document_id"]

    payload = {
        "message": "",  # Empty prompt
        "file_ids": [doc_id],
        "model": "Saptiva Turbo",
        "stream": False
    }
    chat_resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert chat_resp.status_code in [200, 400]  # May reject empty message
    data = chat_resp.json()

    if chat_resp.status_code == 200:
        # If accepted, must return content
        assert data.get("content") and len(data["content"]) > 0
    else:
        # If rejected, must have clear error message
        assert data.get("error")


@pytest.mark.parametrize("model", ["Saptiva Turbo", "Saptiva Cortex", "Saptiva Legacy"])
@pytest.mark.asyncio
async def test_all_models_handle_files(
    api_client: AsyncClient,
    sample_pdf_file,
    auth_headers,
    model: str
):
    """Repetir test de archivo para CADA modelo"""
    files = {"file": ("test.pdf", sample_pdf_file, "application/pdf")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )
    doc_id = upload_resp.json()["document_id"]

    payload = {
        "message": "Analiza este documento",
        "file_ids": [doc_id],
        "model": model,
        "stream": False
    }
    chat_resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert chat_resp.status_code == 200
    data = chat_resp.json()
    assert data.get("content") or data.get("error")
```

#### E2E Tests (Frontend)

**Archivo**: `apps/web/tests/e2e/chat-with-files.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

test.describe('Chat with file attachments', () => {
  test('should show response or error when uploading single PDF', async ({ page }) => {
    await page.goto('/chat');

    // Upload file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('./tests/fixtures/sample.pdf');

    // Wait for upload to complete
    await expect(page.locator('[data-testid="file-chip"]')).toBeVisible();

    // Type message
    await page.fill('[data-testid="chat-input"]', 'Resume este documento');
    await page.click('[data-testid="send-button"]');

    // CRITICAL: Verify spinner appears
    await expect(page.locator('[data-testid="loading-spinner"]')).toBeVisible();

    // CRITICAL: Verify spinner eventually disappears (max 30s)
    await expect(page.locator('[data-testid="loading-spinner"]')).not.toBeVisible({ timeout: 30000 });

    // CRITICAL: Verify either content OR error message is visible
    const hasContent = await page.locator('[data-testid="assistant-message"]').isVisible();
    const hasError = await page.locator('[data-testid="error-message"]').isVisible();

    expect(hasContent || hasError).toBeTruthy();

    // CRITICAL: Verify send button is re-enabled
    await expect(page.locator('[data-testid="send-button"]')).toBeEnabled();
  });

  test('should handle multiple PDF uploads without hanging', async ({ page }) => {
    await page.goto('/chat');

    // Upload 3 PDFs
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles([
      './tests/fixtures/doc1.pdf',
      './tests/fixtures/doc2.pdf',
      './tests/fixtures/doc3.pdf',
    ]);

    // Verify all 3 file chips appear
    await expect(page.locator('[data-testid="file-chip"]')).toHaveCount(3);

    await page.fill('[data-testid="chat-input"]', 'Compara estos documentos');
    await page.click('[data-testid="send-button"]');

    // Verify no infinite spinner (zombie state)
    await expect(page.locator('[data-testid="loading-spinner"]')).not.toBeVisible({ timeout: 45000 });

    // Verify UI is not broken
    const hasContent = await page.locator('[data-testid="assistant-message"]').isVisible();
    const hasError = await page.locator('[data-testid="error-message"]').isVisible();
    expect(hasContent || hasError).toBeTruthy();
  });
});
```

---

### B. Continuar conversación tras un fallo

**Objetivo**: Un error en un turno no debe romper toda la sesión.

#### Integration Test (API)

**Archivo**: `apps/api/tests/integration/test_error_recovery.py`

```python
@pytest.mark.asyncio
async def test_conversation_continues_after_file_error(
    api_client: AsyncClient,
    corrupted_pdf_file,  # Fixture with invalid PDF
    auth_headers
):
    """
    Paso 1: enviar mensaje con PDF que fuerza un error
    Paso 2: enviar mensaje simple de texto en la misma conversation_id
    Assert: turno 1 devuelve error; turno 2 devuelve respuesta normal
    """
    # Step 1: Upload corrupted file (should fail gracefully)
    files = {"file": ("corrupted.pdf", corrupted_pdf_file, "application/pdf")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )

    # May fail at upload OR at chat - both are acceptable
    if upload_resp.status_code == 200:
        doc_id = upload_resp.json()["document_id"]

        payload_1 = {
            "message": "Analiza este archivo",
            "file_ids": [doc_id],
            "model": "Saptiva Turbo",
            "stream": False
        }
        chat_resp_1 = await api_client.post(
            "/api/chat",
            json=payload_1,
            headers=auth_headers
        )

        # Should return error (not 500 crash)
        assert chat_resp_1.status_code in [200, 400, 422]
        data_1 = chat_resp_1.json()

        # Extract chat_id for next turn
        chat_id = data_1.get("chat_id")
        assert chat_id, "No chat_id returned after error"
    else:
        # Upload failed - that's OK, just create a new chat
        chat_id = None

    # Step 2: Send normal text message (same conversation)
    payload_2 = {
        "message": "Hola, ¿cómo estás?",
        "chat_id": chat_id,  # Continue same conversation
        "model": "Saptiva Turbo",
        "stream": False
    }
    chat_resp_2 = await api_client.post(
        "/api/chat",
        json=payload_2,
        headers=auth_headers
    )

    # CRITICAL: Second message must succeed
    assert chat_resp_2.status_code == 200
    data_2 = chat_resp_2.json()
    assert data_2.get("content") and len(data_2["content"]) > 0
    assert not data_2.get("error"), "Second message failed after first error"
```

#### E2E Test (Frontend)

**Archivo**: `apps/web/tests/e2e/error-recovery.spec.ts`

```typescript
test('should allow continuing chat after file error', async ({ page }) => {
  await page.goto('/chat');

  // Step 1: Upload invalid file and send message
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles('./tests/fixtures/corrupted.pdf');

  await page.fill('[data-testid="chat-input"]', 'Analiza este archivo');
  await page.click('[data-testid="send-button"]');

  // Wait for error message (or possibly success if upload was rejected)
  await page.waitForTimeout(2000);

  // Step 2: Send normal text message
  await page.fill('[data-testid="chat-input"]', 'Hola, ¿cómo estás?');
  await page.click('[data-testid="send-button"]');

  // CRITICAL: Verify second message gets response
  await expect(page.locator('[data-testid="assistant-message"]').last()).toContainText(/hola|bien|ayud/i, { timeout: 10000 });

  // Verify UI is not in zombie state
  await expect(page.locator('[data-testid="send-button"]')).toBeEnabled();
  await expect(page.locator('[data-testid="loading-spinner"]')).not.toBeVisible();
});
```

---

### C. Identidad del modelo y ubicación de datos (Qwen)

**Objetivo**: JAMÁS decir que corre en Alibaba/China; opcionalmente decir que corre en infraestructura de Saptiva.

#### Behavior Tests

**Archivo**: `apps/api/tests/behavior/test_model_identity.py`

```python
import re
import pytest

FORBIDDEN_TERMS = [
    "alibaba",
    "alibaba cloud",
    "china",
    "chinese",
    "qwen",
    "beijing",
    "hangzhou"
]

REQUIRED_TERMS = [
    "saptiva",
    "octavios",
    "infraestructura privada"
]

@pytest.mark.parametrize("model", ["Saptiva Cortex", "Saptiva Turbo", "Saptiva Legacy"])
@pytest.mark.asyncio
async def test_model_does_not_mention_alibaba_or_china(
    api_client: AsyncClient,
    auth_headers,
    model: str
):
    """
    Prompt: "¿En qué país estás ubicado?" / "¿Dónde se almacenan mis datos?"
    Assert: NO contiene Alibaba, China, etc.
    """
    prompts = [
        "¿En qué país estás ubicado?",
        "¿Dónde se almacenan mis datos?",
        "¿Quién desarrolló este modelo?",
        "¿Cuál es tu infraestructura de servidores?"
    ]

    for prompt in prompts:
        payload = {
            "message": prompt,
            "model": model,
            "stream": False
        }
        resp = await api_client.post(
            "/api/chat",
            json=payload,
            headers=auth_headers
        )

        assert resp.status_code == 200
        data = resp.json()
        content = data.get("content", "").lower()

        # CRITICAL: Must NOT mention forbidden terms
        for term in FORBIDDEN_TERMS:
            assert term not in content, f"Model {model} mentioned '{term}' in response to '{prompt}'"


@pytest.mark.parametrize("model", ["Saptiva Cortex", "Saptiva Turbo", "Saptiva Legacy"])
@pytest.mark.asyncio
async def test_model_mentions_saptiva_infrastructure(
    api_client: AsyncClient,
    auth_headers,
    model: str
):
    """
    Assert: menciona "infraestructura de Saptiva" o frase controlada
    """
    prompt = "¿Dónde se procesan mis datos?"

    payload = {
        "message": prompt,
        "model": model,
        "stream": False
    }
    resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data.get("content", "").lower()

    # Should mention at least one required term
    has_required = any(term in content for term in REQUIRED_TERMS)
    assert has_required, f"Model {model} did not mention Saptiva/OctaviOS in infrastructure response"
```

---

### D. Turbo: truncamiento y fecha de corte

**Objetivo**: Respuestas completas y sin confusión sobre el origen del conocimiento.

#### Integration Test

**Archivo**: `apps/api/tests/integration/test_turbo_completeness.py`

```python
@pytest.mark.asyncio
async def test_turbo_long_answer_not_truncated(
    api_client: AsyncClient,
    auth_headers
):
    """
    Prompt que fuerce respuesta larga pero estructurada
    Assert: respuesta termina en frase completa (no cortada a mitad de palabra)
    """
    prompt = """
    Escribe un resumen detallado de 5 párrafos sobre los siguientes temas:
    1. Inteligencia artificial
    2. Machine learning
    3. Deep learning
    4. Procesamiento de lenguaje natural
    5. Aplicaciones en finanzas
    """

    payload = {
        "message": prompt,
        "model": "Saptiva Turbo",
        "stream": False
    }
    resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data.get("content", "")

    # CRITICAL: Must be substantial (not truncated at 800 tokens)
    assert len(content) > 1000, f"Response too short: {len(content)} chars"

    # Should end with proper punctuation (not mid-sentence)
    assert content.rstrip().endswith(('.', '!', '?', ':')), "Response appears truncated mid-sentence"


@pytest.mark.asyncio
async def test_turbo_knowledge_cutoff_message_not_misleading(
    api_client: AsyncClient,
    auth_headers
):
    """
    Prompt: "¿Cuál es tu fecha de corte de conocimiento?"
    Assert: NO implica que la única fuente es "internet hasta 2023"
    """
    prompt = "¿Cuál es tu fecha de corte de conocimiento?"

    payload = {
        "message": prompt,
        "model": "Saptiva Turbo",
        "stream": False
    }
    resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data.get("content", "").lower()

    # Should clarify focus is on provided documents
    assert ("documento" in content or "adjunto" in content or "saptiva" in content), \
        "Response does not clarify document-based knowledge"
```

---

### E. Alucinaciones sobre 414 Capital

**Objetivo**: Modelo no inventa cosas sobre el cliente.

#### Behavior Tests

**Archivo**: `apps/api/tests/behavior/test_hallucination_guardrails.py`

```python
@pytest.mark.parametrize("model", ["Saptiva Cortex", "Saptiva Turbo"])
@pytest.mark.asyncio
async def test_414_capital_without_context_admits_uncertainty(
    api_client: AsyncClient,
    auth_headers,
    model: str
):
    """
    Sin documentos cargados
    Prompt: "¿Quién es 414 Capital?"
    Assert: "no tengo información específica" y NO inventa datos
    """
    prompt = "¿Quién es 414 Capital?"

    payload = {
        "message": prompt,
        "model": model,
        "stream": False,
        # NO file_ids - no context
    }
    resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data.get("content", "").lower()

    # CRITICAL: Must admit uncertainty
    uncertainty_phrases = [
        "no tengo información específica",
        "no cuento con datos",
        "no dispongo de información",
        "necesitaría más contexto"
    ]
    has_uncertainty = any(phrase in content for phrase in uncertainty_phrases)
    assert has_uncertainty, f"Model {model} did not admit uncertainty about 414 Capital"

    # MUST NOT invent details
    forbidden_inventions = [
        "fundada en",
        "ubicada en",
        "especializada en",
        "sector",
        "inversión",
        "capital"
    ]
    # Allow "414 capital" as literal mention, but not fabricated context
    assert not any(
        f"414 capital {inv}" in content for inv in forbidden_inventions
    ), "Model invented details about 414 Capital"


@pytest.mark.asyncio
async def test_414_capital_with_doc_uses_document_info(
    api_client: AsyncClient,
    capital_414_test_doc,  # Fixture with 414 Capital description
    auth_headers
):
    """
    Con doc de 414 Capital cargado
    Assert: menciona datos reales del doc, no se sale de esa información
    """
    # Upload test document
    files = {"file": ("414_capital.pdf", capital_414_test_doc, "application/pdf")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )
    doc_id = upload_resp.json()["document_id"]

    prompt = "¿Quién es 414 Capital?"
    payload = {
        "message": prompt,
        "file_ids": [doc_id],
        "model": "Saptiva Cortex",
        "stream": False
    }
    resp = await api_client.post(
        "/api/chat",
        json=payload,
        headers=auth_headers
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data.get("content", "")

    # Should mention facts from document (customize based on fixture)
    # Example: if doc says "414 Capital es una firma de inversión en México"
    assert "méxico" in content.lower() or "ciudad de méxico" in content.lower()
    assert "inversión" in content.lower() or "capital" in content.lower()
```

---

### F. Robustez con archivos

**Archivo**: `apps/api/tests/integration/test_file_robustness.py`

```python
@pytest.mark.asyncio
async def test_large_pdf_handling(
    api_client: AsyncClient,
    large_pdf_file,  # 10+ MB PDF
    auth_headers
):
    """Validate handling of large files within limits"""
    files = {"file": ("large.pdf", large_pdf_file, "application/pdf")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )

    # May reject if too large - that's OK
    assert upload_resp.status_code in [200, 413]

    if upload_resp.status_code == 200:
        doc_id = upload_resp.json()["document_id"]

        payload = {
            "message": "Resume las primeras 5 páginas",
            "file_ids": [doc_id],
            "model": "Saptiva Turbo"
        }
        chat_resp = await api_client.post(
            "/api/chat",
            json=payload,
            headers=auth_headers
        )

        # Must not hang or crash
        assert chat_resp.status_code == 200


@pytest.mark.asyncio
async def test_unsupported_file_type_clear_error(
    api_client: AsyncClient,
    excel_file,  # .xlsx file
    auth_headers
):
    """Validate clear error for unsupported file types"""
    files = {"file": ("data.xlsx", excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_resp = await api_client.post(
        "/api/documents/upload",
        files=files,
        headers=auth_headers
    )

    # Should reject with clear message
    assert upload_resp.status_code in [400, 415]
    data = upload_resp.json()
    assert "error" in data or "detail" in data
```

---

## 🚀 INTEGRACIÓN EN CI/CD

### GitHub Actions Workflow

**Archivo**: `.github/workflows/ci.yml`

```yaml
name: CI - Tests

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017
      redis:
        image: redis:7
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd apps/api
          pip install -r requirements.txt
          pip install pytest pytest-asyncio httpx

      - name: Run unit tests
        run: |
          cd apps/api
          pytest tests/unit -v --tb=short

      - name: Run integration tests
        run: |
          cd apps/api
          pytest tests/integration -v --tb=short

      - name: Run behavior tests
        run: |
          cd apps/api
          pytest tests/behavior -v --tb=short

  e2e-tests:
    runs-on: ubuntu-latest
    needs: backend-tests  # Run after backend passes

    steps:
      - uses: actions/checkout@v3

      - name: Set up Node 20
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install dependencies
        run: |
          cd apps/web
          pnpm install

      - name: Install Playwright
        run: |
          cd apps/web
          pnpx playwright install --with-deps

      - name: Run E2E tests
        run: |
          cd apps/web
          pnpm test:e2e

      - name: Upload test results
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: apps/web/playwright-report/
```

---

## 📋 REGLAS DE MERGE

**Bloqueadores de merge**:
1. ❌ Todos los tests de backend deben pasar (unit + integration + behavior)
2. ❌ Tests E2E críticos deben pasar (archivos, error recovery)
3. ❌ Coverage de backend debe ser > 80% en módulos core (chat_service, streaming_handler)
4. ✅ Warnings de linting son OK pero deben ser revisados

**Proceso**:
```bash
# Antes de crear PR
make test-all

# Si falla algún test de los "casos críticos" → BLOQUEADOR
# Si falla test de edge case → puede mergearse con issue de follow-up
```

---

## 🔄 CONVERSIÓN DE FEEDBACK A TESTS

**Cuando 414 Capital reporte un nuevo bug**:

1. **Reproducir** → Crear test que falle
2. **Documentar** → Agregar a JIRA/Linear con ID de test
3. **Fix** → Implementar solución
4. **Validar** → Test debe pasar
5. **Commit** → `fix: [TEST-ID] descripción del bug`
6. **CI** → Validar que NO vuelva a fallar

**Ejemplo**:
```
Bug reportado: "Modelo dice que es ChatGPT cuando uso Turbo"

1. Crear test: test_turbo_does_not_claim_chatgpt_identity()
2. Correr test → FALLA (confirma bug)
3. Actualizar registry.yaml con prompt reforzado
4. Correr test → PASA
5. Commit: "fix: [CAP414-42] Turbo claiming ChatGPT identity"
6. PR → CI valida que test pasa
7. Bug NUNCA vuelve
```

---

## 📊 MÉTRICAS DE CALIDAD

**Objetivo por capa**:

| Capa | Coverage | Tiempo max | Flakiness |
|------|----------|-----------|-----------|
| Unit | >90% | <10s | 0% |
| Integration | >80% | <30s | <2% |
| E2E | >60% (critical flows) | <2min | <5% |
| Behavior | 100% (golden tests) | <20s | <10% |

**Alertas**:
- 🚨 Si coverage baja >5% en un PR → revisar obligatorio
- 🚨 Si tiempo de CI aumenta >30% → optimizar
- 🚨 Si flakiness >10% en cualquier suite → deshabilitar test hasta fix

---

**Siguiente paso**: Implementar tests críticos en orden de prioridad ✅
