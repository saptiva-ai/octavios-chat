# PDF to Markdown Conversion Tool

Esta herramienta automatizada convierte archivos PDF a Markdown usando el mismo pipeline de extracción de texto que se utiliza en producción (pypdf + OCR selectivo).

## 📋 Objetivo

Facilitar la comparación de calidad de extracción entre el método local actual (pypdf + Tesseract/Saptiva/HuggingFace) y otros pipelines externos (DeepSeq, AlphaXiv, etc.).

## 🚀 Uso Rápido

### 1. Colocar PDFs a convertir

```bash
# Copiar PDFs a la carpeta de entrada
cp /ruta/a/tus/pdfs/*.pdf tests/inputs_pdfs/
```

### 2. Ejecutar conversión

```bash
# Desde la raíz del proyecto
make convert-markdown
```

### 3. Revisar resultados

```bash
# Ver archivos generados
ls tests/outputs_markdown/

# Ver reporte de comparación
cat tests/outputs_markdown/CONVERSION_REPORT.md
```

## 📂 Estructura de Directorios

```
tests/
├── inputs_pdfs/           # PDFs de entrada (colocar aquí tus archivos)
│   ├── report1.pdf
│   ├── report2.pdf
│   └── report3.pdf
├── outputs_markdown/      # Archivos Markdown generados
│   ├── report1.md
│   ├── report2.md
│   ├── report3.md
│   └── CONVERSION_REPORT.md  # Reporte consolidado con estadísticas
└── README.md             # Este archivo
```

## 🔧 Cómo Funciona

El proceso de conversión utiliza el mismo pipeline que se ejecuta en producción:

### Pipeline de Extracción (Producción)

1. **Extracción híbrida con pypdf:**
   - Se intenta extraer texto de cada página usando pypdf
   - Se cuenta el número de caracteres extraídos por página

2. **OCR selectivo para páginas con poco texto:**
   - Si una página tiene < 50 caracteres, se aplica OCR
   - Se usa PyMuPDF (fitz) para rasterizar la página a imagen
   - Se extrae texto usando el extractor configurado:
     - `EXTRACTOR_PROVIDER=third_party` → Tesseract (local)
     - `EXTRACTOR_PROVIDER=saptiva` → Saptiva Native Tools API
     - `EXTRACTOR_PROVIDER=huggingface` → DeepSeek OCR via HuggingFace

3. **Combinación de resultados:**
   - Se compara la calidad del texto de pypdf vs OCR
   - Se usa el texto de mejor calidad (mayor cantidad de caracteres)
   - Se preserva la estructura de páginas del documento original

### Variables de Configuración

```bash
# En envs/.env o envs/.env.local
EXTRACTOR_PROVIDER=third_party     # third_party | saptiva | huggingface
MIN_CHARS_THRESHOLD=50             # Umbral para activar OCR
OCR_RASTER_DPI=180                 # DPI para rasterización OCR
MAX_OCR_PAGES=30                   # Máximo de páginas para OCR
```

## 📊 Reporte de Comparación

El archivo `CONVERSION_REPORT.md` generado incluye:

### 1. Tabla de Resumen

| Archivo | Páginas | Total Caracteres | Tamaño MD (KB) | Promedio Chars/Página | Estado |
|---------|---------|------------------|----------------|-----------------------|--------|
| report1.pdf | 16 | 12,345 | 45.2 | 771 | ✅ success |

### 2. Detalles por Archivo

- **Estado:** Éxito o error
- **Páginas:** Número total de páginas procesadas
- **Caracteres:** Total de caracteres extraídos
- **Tamaño MD:** Tamaño del archivo Markdown generado
- **Ruta:** Ubicación del archivo Markdown

### 3. Notas Técnicas

- Método de extracción utilizado
- Configuración del sistema
- Umbrales y parámetros

## 📝 Formato del Markdown Generado

Cada PDF se convierte a un archivo Markdown con la siguiente estructura:

```markdown
# nombre_archivo.pdf

**Fecha de extracción:** 2025-11-04 15:30:00
**Total de páginas:** 16
**Método de extracción:** pypdf + OCR selectivo

---

## Página 1

*📊 Contiene tablas | 🖼️ Contiene imágenes*

[Texto extraído de la página 1...]

---

## Página 2

[Texto extraído de la página 2...]

---
```

## 🎯 Casos de Uso

### Comparar con Pipeline Externo

```bash
# 1. Convertir con método local
make convert-markdown

# 2. Convertir con pipeline externo (DeepSeq, etc.)
# [usar tu script externo aquí]

# 3. Comparar resultados manualmente
diff tests/outputs_markdown/report1.md external_outputs/report1.md
```

### Evaluar Calidad de Extracción

```bash
# 1. Procesar varios PDFs de prueba
cp tests/data/capital414/*.pdf tests/inputs_pdfs/
make convert-markdown

# 2. Revisar CONVERSION_REPORT.md
cat tests/outputs_markdown/CONVERSION_REPORT.md

# 3. Identificar PDFs con baja calidad
# (pocos caracteres, muchos errores, etc.)
```

### Benchmark de Extractores

```bash
# 1. Convertir con Tesseract
export EXTRACTOR_PROVIDER=third_party
make convert-markdown
mv tests/outputs_markdown tests/outputs_tesseract

# 2. Convertir con Saptiva
export EXTRACTOR_PROVIDER=saptiva
mkdir tests/outputs_markdown
make convert-markdown
mv tests/outputs_markdown tests/outputs_saptiva

# 3. Convertir con HuggingFace
export EXTRACTOR_PROVIDER=huggingface
mkdir tests/outputs_markdown
make convert-markdown
mv tests/outputs_markdown tests/outputs_huggingface

# 4. Comparar reportes
diff tests/outputs_tesseract/CONVERSION_REPORT.md \
     tests/outputs_saptiva/CONVERSION_REPORT.md
```

## 🐛 Troubleshooting

### Error: "No PDF files found"

```bash
# Verificar que los PDFs estén en la carpeta correcta
ls -la tests/inputs_pdfs/

# Crear carpeta si no existe
mkdir -p tests/inputs_pdfs
```

### Error: "Virtual environment not found"

```bash
# Instalar dependencias del proyecto
make venv-install

# Verificar que .venv existe
ls -la .venv/
```

### Error: "Module not found" al ejecutar

```bash
# Verificar que las dependencias de API estén instaladas
cd apps/api
source ../../.venv/bin/activate
pip install -r requirements.txt
```

### PDFs procesados pero con poco texto

Esto puede indicar que:
- El PDF es escaneado y necesita OCR (el script lo detecta automáticamente)
- La calidad del escaneo es muy baja
- El PDF contiene principalmente imágenes sin texto

**Solución:**
- Aumentar el DPI de rasterización: `export OCR_RASTER_DPI=300`
- Usar un extractor diferente: `export EXTRACTOR_PROVIDER=huggingface`
- Revisar el archivo original para confirmar que contiene texto

## 📚 Referencias

- **Código fuente:** `apps/api/tools/pdf_to_markdown.py`
- **Extracción de documentos:** `apps/api/src/services/document_extraction.py`
- **Extractores:** `apps/api/src/services/extractors/`
- **CLAUDE.md:** Documentación completa del proyecto

## 💡 Notas Importantes

1. **Uso de .venv:** El script siempre usa el entorno virtual del proyecto para garantizar consistencia con producción.

2. **No modifica archivos originales:** Los PDFs en `inputs_pdfs/` nunca se modifican, solo se leen.

3. **Idempotencia:** Ejecutar `make convert-markdown` múltiples veces sobrescribe los archivos de salida con los mismos resultados.

4. **Límites:** Por defecto, solo se procesan hasta 30 páginas con OCR por documento. Ajusta `MAX_OCR_PAGES` si necesitas más.

5. **Performance:** La conversión puede tardar varios segundos por página si se activa OCR, especialmente con extractores externos (Saptiva, HuggingFace).

## 🤝 Contribuciones

Para reportar problemas o sugerir mejoras:

1. Crear un issue en el repositorio
2. Incluir archivos de ejemplo si es posible
3. Especificar la configuración utilizada (`EXTRACTOR_PROVIDER`, etc.)

---

**Generado por:** Copilot OS Development Tools
**Última actualización:** 2025-11-04
