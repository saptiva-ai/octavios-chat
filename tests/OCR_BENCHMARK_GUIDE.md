# 📊 OCR Benchmark Guide

Guía completa para ejecutar y analizar benchmarks de estrategias de extracción de texto OCR.

## 🎯 Objetivo

Comparar el desempeño y confiabilidad de tres estrategias de OCR:

1. **Tesseract Local** - pypdf + pytesseract (local, gratis, básico)
2. **Saptiva OCR** - Actualmente en producción (API Saptiva, robusto, probado)
3. **DeepSeek OCR** - Propuesta nueva (vía HuggingFace/AlphaXiv, alta calidad)

## ⚙️ Configuración

### Variables de Entorno Requeridas

Añade a `envs/.env`:

```bash
# DeepSeek OCR (opcional - solo si quieres incluirlo en el benchmark)
HF_OCR_ENDPOINT=https://saptivaDev1-DeepSeek-OCR-Space.hf.space/ocr
HF_TOKEN=your_huggingface_token_here
```

**Nota**: Si no configuras DeepSeek, el benchmark solo comparará Tesseract vs Saptiva OCR.

## 🚀 Uso Rápido

### Opción 1: Comando Make (Recomendado)

```bash
# Desde la raíz del proyecto
make test-benchmark
```

Esto ejecuta el benchmark con configuración por defecto:
- **PDF**: Capital414_presentacion.pdf
- **Páginas**: Primeras 3 páginas
- **Output**: tests/reports/

### Opción 2: Comando Manual

```bash
# Dentro del contenedor API
docker exec octavios-api python -m tests.test_ocr_benchmark \
    --pdf /app/../../tests/data/capital414/Capital414_presentacion.pdf \
    --pages 3 \
    --output /app/../../tests/reports
```

### Opción 3: Comando Directo con Python

```bash
cd apps/api
python -m tests.test_ocr_benchmark \
    --pdf ../../tests/data/capital414/Capital414_presentacion.pdf \
    --pages 3 \
    --output ../../tests/reports \
    --deepseek-endpoint "$HF_OCR_ENDPOINT" \
    --deepseek-token "$HF_TOKEN"
```

## 📋 Opciones de Línea de Comandos

| Opción | Descripción | Default | Ejemplos |
|--------|-------------|---------|----------|
| `--pdf` | Path al PDF de prueba | (requerido) | `Capital414_presentacion.pdf` |
| `--pages` | Páginas a probar | `1,2,3` | `3`, `1,5,10`, `1-5` |
| `--output` | Directorio de reportes | `tests/reports` | `tests/benchmark_results` |
| `--deepseek-endpoint` | Endpoint de DeepSeek | (opcional) | `https://api.example.com/ocr` |
| `--deepseek-token` | Token de autenticación | (opcional) | `hf_xxxxx` |

### Ejemplos de Uso

```bash
# Probar solo primera página (rápido)
make test-benchmark PAGES=1

# Probar páginas específicas
python -m tests.test_ocr_benchmark --pdf test.pdf --pages 1,3,5

# Probar rango de páginas
python -m tests.test_ocr_benchmark --pdf test.pdf --pages 1-10

# Usar otro PDF
python -m tests.test_ocr_benchmark --pdf tests/data/capital414/Capital414_usoIA.pdf --pages 5
```

## 📊 Resultados Generados

El benchmark genera automáticamente 2 archivos en `tests/reports/`:

### 1. `ocr_benchmark.json` - Datos Estructurados

```json
{
  "metadata": {
    "timestamp": "2025-01-03 16:30:45",
    "pdf_path": "tests/data/capital414/Capital414_presentacion.pdf",
    "pages_tested": [1, 2, 3]
  },
  "results": {
    "Tesseract Local": {
      "success": true,
      "pages": [...],
      "total_duration_ms": 5432.1,
      "total_chars": 3212,
      "total_words": 492
    },
    "Saptiva OCR": {
      "success": true,
      "pages": [...],
      "total_duration_ms": 12045.7,
      "total_chars": 20529,
      "total_words": 3201
    },
    "DeepSeek OCR": {
      "success": false,
      "pages": [...],
      "total_duration_ms": 145320.5,
      "total_chars": 72,
      "total_words": 12,
      "error": "Timeout on page 2"
    }
  },
  "comparison": {
    "text_similarities": {
      "Tesseract Local_vs_Saptiva OCR": 15.3,
      "Saptiva OCR_vs_DeepSeek OCR": 87.4
    },
    "best_speed": {
      "strategy": "Tesseract Local",
      "duration_ms": 5432.1
    },
    "best_extraction": {
      "strategy": "Saptiva OCR",
      "total_chars": 20529
    }
  }
}
```

### 2. `ocr_benchmark.md` - Reporte Visual

Ejemplo de reporte generado:

```markdown
# 📊 OCR Benchmark Report

**Generated**: 2025-01-03 16:30:45
**PDF**: Capital414_presentacion.pdf
**Pages Tested**: [1, 2, 3]

## Performance Summary

| Strategy | Success Rate | Avg Duration | Total Chars | Total Words | Status |
|----------|--------------|--------------|-------------|-------------|--------|
| Tesseract Local | 3/3 (100.0%) | 1810.7ms | 3,212 | 492 | ✅ Success |
| Saptiva OCR | 3/3 (100.0%) | 4015.2ms | 20,529 | 3,201 | ✅ Success |
| DeepSeek OCR | 1/3 (33.3%) | 48440.2ms | 72 | 12 | ❌ Failed (Timeout) |

## Text Similarity (Accuracy)

| Comparison | Similarity |
|------------|------------|
| Tesseract Local vs Saptiva OCR | 15.3% |
| Saptiva OCR vs DeepSeek OCR | 87.4% |

## 🏆 Best Performers

**Fastest**: Tesseract Local (5432ms total)
**Most Text Extracted**: Saptiva OCR (20,529 chars)

## 💡 Recommendation

✅ **MAINTAIN Saptiva OCR** - Balanced performance and reliability
```

## 📈 Métricas Evaluadas

### Por Estrategia

| Métrica | Descripción |
|---------|-------------|
| **Success Rate** | Porcentaje de páginas procesadas exitosamente |
| **Avg Duration** | Tiempo promedio por página (ms) |
| **Total Chars** | Caracteres totales extraídos |
| **Total Words** | Palabras totales extraídas |
| **Status** | Estado general (Success/Failed) |

### Comparación entre Estrategias

| Métrica | Descripción |
|---------|-------------|
| **Text Similarity** | Similitud textual usando difflib (0-100%) |
| **Best Speed** | Estrategia más rápida |
| **Best Extraction** | Estrategia que extrae más texto |

## 🔍 Interpretación de Resultados

### Criterios de Evaluación

1. **Confiabilidad** (más importante)
   - Success Rate > 95% ✅
   - Success Rate 80-95% ⚠️
   - Success Rate < 80% ❌

2. **Velocidad** (importante para UX)
   - < 5s por página: Excelente ⚡
   - 5-15s por página: Aceptable 👍
   - \> 15s por página: Lento 🐌

3. **Calidad de Extracción** (crítico para RAG)
   - Text Similarity > 85%: Alta precisión 🎯
   - Text Similarity 70-85%: Aceptable ⚠️
   - Text Similarity < 70%: Baja precisión ❌

4. **Completitud**
   - Total Chars diferencia < 10%: Equivalente ✅
   - Total Chars diferencia 10-30%: Revisar 🔍
   - Total Chars diferencia > 30%: Problema serio ❌

### Casos de Decisión

#### ✅ Caso 1: Estrategia Dominante
```
Estrategia A: 100% éxito, 4s/página, 20K chars
Estrategia B: 50% éxito, 8s/página, 10K chars
→ DECISION: Usar Estrategia A
```

#### ⚖️ Caso 2: Trade-off Velocidad vs Calidad
```
Estrategia A: 100% éxito, 2s/página, 15K chars
Estrategia B: 100% éxito, 10s/página, 20K chars (+33% texto)
→ DECISION: Evaluar requisitos
   - Si UX es prioridad → Estrategia A
   - Si precisión RAG es prioridad → Estrategia B
```

#### 🔍 Caso 3: Baja Similitud Textual
```
Estrategia A: 100% éxito, texto legible
Estrategia B: 100% éxito, texto corrupto (15% similitud)
→ DECISION: Investigar causa de corrupción
   - Verificar manualmente archivos de texto
   - Puede ser problema de encoding, orientación, etc.
```

## 🛠️ Troubleshooting

### Error: "Missing dependencies: pytesseract"

```bash
# Instalar Tesseract en el contenedor
docker exec octavios-api apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-spa
```

### Error: "DeepSeek OCR: 401 Unauthorized"

```bash
# Verificar token en .env
grep HF_TOKEN envs/.env

# Si está mal, actualizar y recargar
echo "HF_TOKEN=your_huggingface_token_here" >> envs/.env
make reload-env-service SERVICE=api
```

### Error: "PDF not found"

```bash
# Verificar path del PDF
ls -la tests/data/capital414/*.pdf

# Usar path absoluto si es necesario
python -m tests.test_ocr_benchmark --pdf /full/path/to/file.pdf
```

### Benchmark Muy Lento

```bash
# Probar solo 1-2 páginas primero
make test-benchmark PAGES=2

# Deshabilitar DeepSeek si tiene timeouts
# (remover HF_OCR_ENDPOINT y HF_TOKEN de .env temporalmente)
```

## 📝 Casos de Uso Reales

### 1. Validación de Nueva Estrategia

```bash
# Escenario: Evaluar si DeepSeek mejora sobre Saptiva OCR
make test-benchmark

# Análisis:
# - Comparar Success Rate (debe ser >= Saptiva)
# - Comparar Text Similarity (debe ser > 85%)
# - Verificar velocidad aceptable (< 10s/página)
# - Revisar manualmente archivos .txt generados
```

### 2. Regresión de Calidad

```bash
# Escenario: Verificar que cambios no degradaron OCR
make test-benchmark

# Guardar baseline:
cp tests/reports/ocr_benchmark.json tests/reports/baseline_2025-01-03.json

# Después de cambios, comparar:
diff tests/reports/baseline_2025-01-03.json tests/reports/ocr_benchmark.json
```

### 3. Optimización de Costos

```bash
# Escenario: Decidir si vale la pena API externa vs local
make test-benchmark

# Análisis:
# - Calcular costo por página (API externa)
# - Comparar con costo de infraestructura local
# - Factor de calidad: ¿justifica el costo?
```

## 🔄 Integración con CI/CD

### GitHub Actions

```yaml
name: OCR Benchmark

on:
  schedule:
    - cron: '0 0 * * 0'  # Semanal
  workflow_dispatch:     # Manual

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run OCR Benchmark
        run: make test-benchmark
      - name: Upload Reports
        uses: actions/upload-artifact@v3
        with:
          name: ocr-benchmark-reports
          path: tests/reports/
```

## 📚 Recursos Adicionales

- **Documentación Principal**: `CLAUDE.md` - Sección "Document Extraction Abstraction"
- **Implementación**: `apps/api/src/services/document_extraction.py`
- **Tests Existentes**: `apps/api/tests/unit/test_extractors.py`
- **Comparación Simple**: `tests/ocr_compare_simple.py` (versión standalone)

## 🤝 Contribuir

Para añadir nuevas estrategias al benchmark:

1. Crear clase que herede de `OCRStrategy`
2. Implementar método `extract_pages()`
3. Añadir instancia en `OCRBenchmark.run()`
4. Actualizar esta documentación

Ejemplo:

```python
class MyCustomOCRStrategy(OCRStrategy):
    def __init__(self):
        super().__init__("My Custom OCR")

    async def extract_pages(self, pdf_path: Path, page_numbers: List[int]) -> Dict[str, Any]:
        # Tu implementación aquí
        pass
```

---

**Última actualización**: 2025-01-03
**Versión**: 1.0.0
**Mantenedor**: Equipo Saptiva
