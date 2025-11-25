# Guía Anti-Alucinaciones - Mejoras Implementadas

## ✅ Cambios Implementados

### 1. Validación de Calidad de Texto (Más Estricta)
**Archivo:** `apps/api/src/services/document_extraction.py:29-76`

**Triple validación:**
- ✅ Mínimo 40% caracteres válidos (alfanuméricos + espacios)
- ✅ Mínimo 5 palabras reales (2+ letras consecutivas)
- ✅ Máximo 80% caracteres especiales

**Detecta y rechaza:**
- Metadata corrupto con < 5 palabras
- Texto con exceso de símbolos especiales
- Secuencias aleatorias de caracteres

### 2. Umbral de Longitud Aumentado
**Archivo:** `apps/api/src/services/document_extraction.py:133`

```python
MIN_CHARS_THRESHOLD = 150  # Antes: 50
```

**Razón:** PDFs escaneados con capas de texto de 50-100 chars de metadata corrupta engañaban al sistema.

### 3. System Prompts Reforzados
**Archivo:** `apps/api/prompts/registry.yaml`

**Cambios clave:**

#### A. Eliminado placeholder `[entidad]`
```diff
- "No tengo información específica sobre [entidad]..."
+ "No encuentro información sobre (tema concreto)..."
+ "NUNCA uses placeholders como '[entidad]'"
```

#### B. Instrucciones explícitas contra alucinaciones
```yaml
REGLA CRÍTICA: CERO ALUCINACIONES - LEE ESTO CUIDADOSAMENTE

* SOLO menciona información que esté EXPLÍCITAMENTE y LITERALMENTE
  presente en el contexto de documentos proporcionado

* NUNCA inventes secciones, datos, cifras, empresas, personas, URLs,
  fechas, procedimientos, arquitecturas, sistemas o CUALQUIER contenido
  que no aparezca TEXTUALMENTE en el contexto

* Si no ves algo con tus propios "ojos" en el contexto, NO lo menciones

* PROHIBIDO usar conocimiento general para "llenar vacíos" del documento
```

#### C. Manejo de documentos corruptos/ilegibles
```yaml
Si el contexto del documento está vacío, corrupto, o no contiene
texto legible:
→ "No puedo leer el contenido del documento. Parece estar dañado
   o ser una imagen sin texto. ¿Puedes compartir el documento en
   otro formato?"
```

#### D. Protocolo de verificación paso a paso
```yaml
1. ¿El contexto tiene texto legible?
   NO → "No puedo leer el documento"
   SÍ → Continuar

2. Citar textualmente entre comillas

3. Si no está en el contexto → NO mencionarlo

4. Prohibido "rellenar" con conocimiento general
```

### 4. Feedback de Baja Relevancia
**Archivo:** `apps/api/src/mcp/tools/get_segments.py:281-322`

```python
LOW_RELEVANCE_THRESHOLD = 0.1  # 10%

if max_score < 0.1:
    message = "⚠️ No encontré información muy relevante en los documentos.
               La búsqueda podría no ser precisa."
```

---

## 🚨 IMPORTANTE: Cómo Aplicar los Cambios

### Problema de Volumenes Docker
Los cambios en `prompts/registry.yaml` **NO se reflejan automáticamente** porque el directorio `prompts/` **NO** está montado como volumen en Docker.

### Solución: Copiar Manualmente
Después de editar `prompts/registry.yaml`, ejecutar:

```bash
# 1. Copiar el archivo actualizado al contenedor
docker cp apps/api/prompts/registry.yaml octavios-chat-client-project-api:/app/prompts/registry.yaml

# 2. Reiniciar la API
docker restart octavios-chat-client-project-api

# 3. Verificar que los cambios se aplicaron
docker exec octavios-chat-client-project-api cat /app/prompts/registry.yaml | grep "CERO ALUCINACIONES"
```

### Alternativa: Agregar Volumen (Permanente)
Editar `infra/docker-compose.yml`:

```yaml
services:
  api:
    volumes:
      - ../apps/api/prompts:/app/prompts  # Agregar esta línea
```

Luego:
```bash
docker compose -f infra/docker-compose.yml down
docker compose -f infra/docker-compose.yml up -d
```

---

## 🧪 Cómo Verificar que Funcionó

### 1. Verificar Prompts Cargados
```bash
python apps/api/tests/manual/diagnose_hallucination.py
```

**Debe mostrar:**
```
✅ Zero hallucinations rule
✅ No [entidad] placeholder
✅ Explicit content check
✅ Corrupted doc handling
```

### 2. Probar con PDF Problemático

**Pasos:**
1. **Re-subir** el PDF (fuerza re-procesamiento con nuevas validaciones)
2. **Revisar logs** de la API:
   ```bash
   docker logs octavios-chat-client-project-api --tail 100 | grep -E "OCR|quality|insufficient"
   ```
3. **Hacer pregunta** "¿Qué es esto?"
4. **Validar respuesta:**
   - ✅ Si PDF legible → Debe citar textualmente
   - ✅ Si corrupto → "No puedo leer el documento"
   - ❌ Si inventa contenido → TODAVÍA HAY PROBLEMA

### 3. Inspeccionar Texto Extraído
```bash
python apps/api/tests/manual/inspect_pdf_extraction.py /ruta/al/archivo.pdf
```

**Debe mostrar:**
- Cantidad de caracteres extraídos
- Ratio de calidad (debe ser > 40%)
- Cantidad de palabras reales (debe ser > 5)
- Preview del texto

---

## 📊 Resumen de Protecciones

| Capa | Protección | Archivo |
|------|-----------|---------|
| **Extracción** | Umbral 150 chars | `document_extraction.py:133` |
| **Validación** | 3 checks de calidad | `document_extraction.py:29-76` |
| **OCR Fallback** | Auto-activación si calidad < 40% | `document_extraction.py:191-194` |
| **System Prompt** | Instrucciones anti-alucinación | `prompts/registry.yaml:122-148` |
| **RAG Search** | Advertencia de baja relevancia | `get_segments.py:283-303` |

---

## ❓ Si Sigue Alucinando

### Diagnóstico Paso a Paso

1. **Verificar prompts cargados:**
   ```bash
   python tests/manual/diagnose_hallucination.py
   ```
   Si falla algún check → Copiar registry.yaml y reiniciar

2. **Verificar texto extraído:**
   ```bash
   python tests/manual/inspect_pdf_extraction.py /tmp/archivo.pdf
   ```
   Si chars == 0 → PDF es imagen pura, necesita OCR

3. **Verificar logs de procesamiento:**
   ```bash
   docker logs octavios-chat-client-project-api --tail 200 | grep -A 5 "hybrid PDF extraction"
   ```
   Debe mostrar:
   - `"min_chars_threshold": 150`
   - `"Applying OCR to page with insufficient/poor text"`
   - Razón específica: "poor quality (X% valid chars)" o "insufficient text"

4. **Verificar contexto RAG:**
   ```bash
   docker logs octavios-chat-client-project-api --tail 200 | grep "Added document context"
   ```
   Debe mostrar:
   - `"context_length": > 0`
   - `"has_pdfs": true`

### Posibles Problemas

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Sigue usando `[entidad]` | Prompts no cargados | Copiar registry.yaml + restart |
| Inventa todo | Texto extraído = 0 chars | Re-subir PDF, verificar OCR |
| Inventa parcialmente | Texto corrupto pasó validación | Subir umbral quality_ratio a 0.5 |
| No activa OCR | PDF tiene > 150 chars corruptos | Bajar threshold a 100 o mejorar validación |

---

## 🔧 Ajustes Finos (Si es Necesario)

### Hacer Validación MÁS Estricta
**Archivo:** `document_extraction.py:29-76`

```python
# Opción 1: Exigir más palabras
if len(words) < 10:  # Antes: 5
    return False

# Opción 2: Exigir mejor ratio de calidad
if quality_ratio < 0.5:  # Antes: 0.4
    return False

# Opción 3: Exigir menos caracteres especiales
if special_ratio > 0.6:  # Antes: 0.8
    return False
```

### Bajar Umbral de Longitud (Si OCR No se Activa)
**Archivo:** `document_extraction.py:133`

```python
MIN_CHARS_THRESHOLD = 100  # Antes: 150
```

---

## 📝 Notas Importantes

1. **Siempre re-subir PDFs** después de cambios en validación para forzar re-procesamiento
2. **Verificar logs** antes de concluir que algo no funciona
3. **Usar scripts de diagnóstico** para identificar problemas específicos
4. **Copiar prompts al contenedor** después de cada edición de `registry.yaml`

---

## ✅ Lista de Verificación Post-Cambios

- [ ] Prompts copiados al contenedor
- [ ] API reiniciada
- [ ] Diagnóstico muestra ✅ en todos los checks
- [ ] PDF re-subido (no usar uno viejo en cache)
- [ ] Logs muestran nueva validación activándose
- [ ] Respuesta del LLM no inventa contenido
- [ ] No usa placeholder `[entidad]`
