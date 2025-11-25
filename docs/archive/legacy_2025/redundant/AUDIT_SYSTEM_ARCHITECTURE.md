# 📐 Arquitectura del Sistema de Auditoría - COPILOTO_414

## 🎯 Descripción General

El sistema de auditoría COPILOTO_414 es un **framework extensible** para validar documentos PDF contra políticas de cumplimiento corporativo. Utiliza un **patrón de coordinador + auditores** donde múltiples validadores especializados se ejecutan en paralelo.

---

## 🏗️ Arquitectura de Alto Nivel

```
┌─────────────────────────────────────────────────────────────┐
│                   Chat Router (chat.py)                     │
│  - Detecta comando: "Auditar archivo: filename.pdf"        │
│  - Materializa PDF desde MinIO                              │
│  - Invoca ValidationCoordinator                             │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│         ValidationCoordinator (validation_coordinator.py)   │
│  1. Carga política (Policy Manager)                         │
│  2. Extrae fragmentos del PDF                               │
│  3. Ejecuta auditores en paralelo                           │
│  4. Agrega findings y genera reporte                        │
└───────────────────────┬─────────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┬─────────────┐
          │             │             │             │
          ▼             ▼             ▼             ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
    │Disclaimer│   │ Format  │   │ Grammar │   │  Logo   │
    │ Auditor │   │ Auditor │   │ Auditor │   │ Auditor │
    └─────────┘   └─────────┘   └─────────┘   └─────────┘
          │             │             │             │
          └─────────────┴─────────────┴─────────────┘
                        │
                        ▼
                  ┌───────────┐
                  │ Findings  │
                  │ + Summary │
                  └───────────┘
```

---

## 📂 Estructura de Archivos

### **Core Files (Coordinación)**

```
apps/api/src/services/
├── validation_coordinator.py    # Orquestador principal
├── policy_manager.py             # Auto-detección de políticas
└── minio_storage.py              # Almacenamiento de PDFs
```

### **Auditores (Validators)**

```
apps/api/src/services/
├── compliance_auditor.py         # ✅ Disclaimers legales
├── format_auditor.py             # ⚠️ Números, fuentes, colores
├── grammar_auditor.py            # ✏️ Ortografía y gramática
└── logo_auditor.py               # 🎨 Identidad visual
```

### **Configuración**

```
apps/api/src/config/
├── policies.yaml                 # Políticas de validación
└── compliance.yaml               # Templates de disclaimers
```

### **Schemas**

```
apps/api/src/schemas/
└── audit_message.py              # Finding, Location, Evidence, ValidationReportResponse
```

---

## 🔄 Flujo de Ejecución

### **1. Detección de Comando** (`chat.py:379-643`)

```python
if context.message.strip().startswith("Auditar archivo:"):
    filename = context.message.replace("Auditar archivo:", "").strip()

    # 1. Buscar documento en archivos adjuntos
    target_doc = find_document_by_filename(filename)

    # 2. Materializar PDF desde MinIO
    pdf_path = minio_storage.materialize_document(target_doc.minio_key)

    # 3. Resolver política (auto-detección o explícita)
    policy = await resolve_policy("auto", document=target_doc)

    # 4. Ejecutar validación
    report = await validate_document(
        document=target_doc,
        pdf_path=pdf_path,
        client_name=policy.client_name,
        enable_disclaimer=True,
        enable_format=True,
        enable_logo=True,
        policy_config=policy.to_compliance_config()
    )
```

### **2. Coordinación de Auditores** (`validation_coordinator.py:40-396`)

```python
async def validate_document(
    document: Document,
    pdf_path: Path,
    client_name: str,
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
    policy_config: Optional[Dict[str, Any]] = None
) -> ValidationReportResponse:

    # 1. Cargar configuración de política
    config = policy_config or load_compliance_config()

    # 2. Extraer fragmentos del PDF
    fragments = extract_fragments_with_bbox(pdf_path)

    # 3. Ejecutar auditores en paralelo
    all_findings = []

    # Disclaimer Auditor
    if enable_disclaimer:
        findings, summary = await audit_disclaimers(fragments, client_name, config)
        all_findings.extend(findings)

    # Format Auditor
    if enable_format:
        findings, summary = await audit_format(fragments, pdf_path, config)
        all_findings.extend(findings)

    # Grammar Auditor
    if enable_grammar:
        findings, summary = await audit_grammar(document, config)
        all_findings.extend(findings)

    # Logo Auditor
    if enable_logo:
        findings, summary = await audit_logo(pdf_path, config)
        all_findings.extend(findings)

    # 4. Agregar findings y generar resumen
    return ValidationReportResponse(
        job_id=job_id,
        status="done",
        findings=all_findings,
        summary=aggregate_summary(all_findings),
        attachments={}
    )
```

---

## 🧩 Anatomía de un Auditor

Cada auditor sigue el mismo **patrón de interfaz**:

### **Firma de Función Estándar**

```python
async def audit_{nombre}(
    # Inputs específicos del auditor
    fragments: List[PageFragment],  # o document, pdf_path, etc.
    config: Dict[str, Any],         # Configuración de política
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Ejecuta validación específica.

    Args:
        fragments/pdf_path/document: Fuente de datos
        config: Configuración desde policies.yaml

    Returns:
        (findings, summary) tuple
        - findings: Lista de objetos Finding con violaciones
        - summary: Métricas agregadas (ej: coverage, counts, etc.)
    """
```

### **Estructura de un Finding**

```python
from ..schemas.audit_message import Finding, Location, Evidence, Severity

Finding(
    id="unique-finding-id",           # UUID o hash único
    category="format",                 # compliance | format | logo | linguistic
    rule="color_palette",              # Identificador de regla
    issue="Color no autorizado #FF5733 detectado",  # Descripción legible
    severity="medium",                 # low | medium | high | critical
    location=Location(
        page=5,                        # Número de página (1-indexed)
        bbox=[100, 200, 400, 250],    # Coordenadas opcionales
        fragment_id="frag-123",        # Referencia a fragmento
        text_snippet="Texto relevante" # Contexto opcional
    ),
    suggestion="Usar colores corporativos: #003366, #FFFFFF",
    evidence=[
        Evidence(
            kind="metric",             # text | image | metric | rule
            data={
                "found_color": "#FF5733",
                "allowed_palette": ["#003366", "#FFFFFF"]
            }
        )
    ]
)
```

---

## 🎨 Ejemplo 1: Agregar Auditor de Tipografía

### **Paso 1: Crear el Archivo del Auditor**

**Archivo**: `apps/api/src/services/typography_auditor.py`

```python
"""
Typography Auditor for COPILOTO_414.

Validates typography best practices:
- Consistent heading hierarchy (H1, H2, H3)
- Proper line spacing and paragraph margins
- Font size consistency across similar elements
- Text alignment and justification
"""

from typing import List, Dict, Any, Tuple
from uuid import uuid4
import structlog

from ..models.document import PageFragment
from ..schemas.audit_message import Finding, Location, Evidence, Severity

logger = structlog.get_logger(__name__)


def analyze_heading_hierarchy(fragments: List[PageFragment]) -> List[Dict[str, Any]]:
    """
    Detect heading hierarchy violations.

    Returns:
        List of violations with page numbers and issues
    """
    violations = []
    heading_sizes = []

    for frag in fragments:
        # Detect headings (heuristic: larger font, bold, short text)
        if frag.font_size and frag.font_size > 14 and len(frag.text.strip()) < 100:
            heading_sizes.append({
                "page": frag.page,
                "size": frag.font_size,
                "text": frag.text.strip()[:50]
            })

    # Check for inconsistent heading sizes
    if len(heading_sizes) > 1:
        sizes_used = set(h["size"] for h in heading_sizes)
        if len(sizes_used) > 5:  # Too many heading sizes
            violations.append({
                "issue": f"Jerarquía de encabezados inconsistente: {len(sizes_used)} tamaños detectados",
                "page": heading_sizes[0]["page"],
                "suggestion": "Limitar a 3-4 niveles de encabezados (H1, H2, H3, H4)"
            })

    return violations


def validate_line_spacing(fragments: List[PageFragment], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Validate line spacing meets standards.

    Args:
        fragments: List of page fragments with bbox data
        config: Typography configuration (min/max line spacing)

    Returns:
        List of line spacing violations
    """
    violations = []
    min_line_spacing = config.get("min_line_spacing", 1.0)
    max_line_spacing = config.get("max_line_spacing", 2.0)

    # Group fragments by page
    pages = {}
    for frag in fragments:
        if frag.page not in pages:
            pages[frag.page] = []
        pages[frag.page].append(frag)

    # Analyze line spacing per page
    for page_num, page_frags in pages.items():
        # Sort by vertical position
        sorted_frags = sorted(page_frags, key=lambda f: f.bbox[1] if f.bbox else 0)

        for i in range(len(sorted_frags) - 1):
            current = sorted_frags[i]
            next_frag = sorted_frags[i + 1]

            if not current.bbox or not next_frag.bbox:
                continue

            # Calculate spacing (simplified)
            current_bottom = current.bbox[3]
            next_top = next_frag.bbox[1]
            spacing = next_top - current_bottom

            # Check if spacing is too tight or too loose
            if spacing < 0:  # Overlapping text
                violations.append({
                    "issue": "Texto superpuesto detectado",
                    "page": page_num,
                    "suggestion": "Ajustar espaciado entre líneas"
                })

    return violations


async def audit_typography(
    fragments: List[PageFragment],
    pdf_path: Any,  # Path, not used but kept for consistency
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit typography best practices.

    Args:
        fragments: Extracted page fragments with font metadata
        pdf_path: Path to PDF (not used, for interface consistency)
        config: Policy configuration (typography section)

    Returns:
        (findings, summary) tuple
    """
    findings: List[Finding] = []
    typography_config = config.get("typography", {})

    logger.info("Starting typography audit", fragments_count=len(fragments))

    # 1. Heading Hierarchy
    heading_violations = analyze_heading_hierarchy(fragments)
    for violation in heading_violations:
        findings.append(
            Finding(
                id=f"typo-heading-{uuid4().hex[:8]}",
                category="format",
                rule="heading_hierarchy",
                issue=violation["issue"],
                severity="low",
                location=Location(
                    page=violation["page"],
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None
                ),
                suggestion=violation["suggestion"],
                evidence=[
                    Evidence(kind="rule", data={"rule": "heading_hierarchy"})
                ]
            )
        )

    # 2. Line Spacing
    line_spacing_violations = validate_line_spacing(fragments, typography_config)
    for violation in line_spacing_violations:
        findings.append(
            Finding(
                id=f"typo-spacing-{uuid4().hex[:8]}",
                category="format",
                rule="line_spacing",
                issue=violation["issue"],
                severity="low",
                location=Location(
                    page=violation["page"],
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None
                ),
                suggestion=violation["suggestion"],
                evidence=[
                    Evidence(kind="rule", data={"rule": "line_spacing"})
                ]
            )
        )

    # Generate summary
    summary = {
        "total_violations": len(findings),
        "heading_issues": len(heading_violations),
        "spacing_issues": len(line_spacing_violations)
    }

    logger.info(
        "Typography audit completed",
        findings=len(findings),
        summary=summary
    )

    return findings, summary
```

### **Paso 2: Integrar en ValidationCoordinator**

**Archivo**: `apps/api/src/services/validation_coordinator.py`

```python
# Agregar import al inicio
from ..services.typography_auditor import audit_typography

async def validate_document(
    document: Document,
    pdf_path: Path,
    client_name: Optional[str] = None,
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
    enable_typography: bool = True,  # ← NUEVO
    policy_config: Optional[Dict[str, Any]] = None,
) -> ValidationReportResponse:

    # ... código existente ...

    # ---- Typography Auditor (NUEVO) ----
    if enable_typography:
        try:
            logger.info("Running typography auditor", job_id=job_id)
            typography_start = time.time()

            typography_findings, typography_summary = await audit_typography(
                fragments=fragments,
                pdf_path=pdf_path,
                config=config,
            )

            typography_duration = time.time() - typography_start

            all_findings.extend(typography_findings)
            summary["auditors_run"].append("typography")
            summary["typography"] = typography_summary
            summary["typography_duration_ms"] = int(typography_duration * 1000)

            logger.info(
                "Typography auditor completed",
                job_id=job_id,
                findings=len(typography_findings),
                duration_ms=int(typography_duration * 1000)
            )

        except Exception as exc:
            logger.error(
                "Typography auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True
            )
            summary["typography_error"] = str(exc)
```

### **Paso 3: Configurar en policies.yaml**

**Archivo**: `apps/api/src/config/policies.yaml`

```yaml
policies:
  - id: "414-std"
    name: "414 Capital Standard"
    # ... configuración existente ...

    # NUEVA SECCIÓN: Typography
    typography:
      enabled: true
      min_line_spacing: 1.0      # Mínimo espaciado entre líneas
      max_line_spacing: 2.0      # Máximo espaciado entre líneas
      max_heading_levels: 4      # Máximo niveles de encabezados
      severity: "low"            # Severidad por defecto
```

### **Paso 4: Habilitar en Chat Router**

**Archivo**: `apps/api/src/routers/chat.py`

```python
# Línea ~523 (en la llamada a validate_document)
report = await validate_document(
    document=target_doc,
    pdf_path=pdf_path,
    client_name=policy.client_name,
    enable_disclaimer=True,
    enable_format=True,
    enable_logo=True,
    enable_typography=True,  # ← NUEVO
    policy_config=policy.to_compliance_config(),
    policy_id=policy.id,
    policy_name=policy.name
)
```

---

## 🎨 Ejemplo 2: Agregar Auditor de Paleta de Colores (Avanzado)

Este auditor valida que TODOS los colores del documento estén dentro de la paleta corporativa.

### **Crear el Archivo**

**Archivo**: `apps/api/src/services/color_palette_auditor.py`

```python
"""
Color Palette Auditor for COPILOTO_414.

Validates strict color palette compliance:
- All colors must match corporate palette (with tolerance)
- Detects unauthorized brand colors
- Flags images with off-brand colors
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
from uuid import uuid4
import structlog

from ..schemas.audit_message import Finding, Location, Evidence

logger = structlog.get_logger(__name__)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def color_distance(color1: str, color2: str) -> float:
    """
    Calculate Euclidean distance between two hex colors.

    Returns:
        Distance (0.0 = identical, 441.67 = maximum difference)
    """
    rgb1 = hex_to_rgb(color1)
    rgb2 = hex_to_rgb(color2)

    return sum((a - b) ** 2 for a, b in zip(rgb1, rgb2)) ** 0.5


def is_color_in_palette(
    color: str,
    palette: List[str],
    tolerance: float = 10.0
) -> Tuple[bool, str]:
    """
    Check if color is within tolerance of palette.

    Args:
        color: Hex color to check
        palette: List of allowed hex colors
        tolerance: Maximum Euclidean distance (0-441.67)

    Returns:
        (is_valid, closest_match_color)
    """
    min_distance = float('inf')
    closest_color = palette[0] if palette else color

    for palette_color in palette:
        distance = color_distance(color, palette_color)
        if distance < min_distance:
            min_distance = distance
            closest_color = palette_color

    is_valid = min_distance <= tolerance
    return is_valid, closest_color


def extract_all_colors_from_pdf(pdf_path: Path) -> Set[str]:
    """
    Extract ALL unique colors from PDF (text + images).

    Uses PyMuPDF to analyze every element.
    """
    try:
        import fitz  # PyMuPDF

        colors_used = set()

        with fitz.open(str(pdf_path)) as doc:
            for page_num, page in enumerate(doc, 1):
                # Extract text colors
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") != 0:  # text block
                        continue

                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            color = span.get("color", 0)
                            if color:
                                hex_color = f"#{color:06X}"
                                colors_used.add(hex_color)

                # Extract drawing/shape colors
                for drawing in page.get_drawings():
                    # Fill colors
                    if drawing.get("fill"):
                        fill_color = drawing["fill"]
                        if isinstance(fill_color, tuple) and len(fill_color) == 3:
                            r, g, b = [int(c * 255) for c in fill_color]
                            hex_color = f"#{r:02X}{g:02X}{b:02X}"
                            colors_used.add(hex_color)

                    # Stroke colors
                    if drawing.get("color"):
                        stroke_color = drawing["color"]
                        if isinstance(stroke_color, tuple) and len(stroke_color) == 3:
                            r, g, b = [int(c * 255) for c in stroke_color]
                            hex_color = f"#{r:02X}{g:02X}{b:02X}"
                            colors_used.add(hex_color)

        logger.info(
            "Extracted colors from PDF",
            pdf_path=str(pdf_path),
            unique_colors=len(colors_used)
        )

        return colors_used

    except Exception as exc:
        logger.error("Color extraction failed", error=str(exc), exc_info=True)
        return set()


async def audit_color_palette(
    pdf_path: Path,
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit strict color palette compliance.

    Args:
        pdf_path: Path to PDF file
        config: Policy configuration (color_palette section)

    Returns:
        (findings, summary) tuple
    """
    findings: List[Finding] = []
    color_config = config.get("color_palette", {})

    # Configuration
    palette = color_config.get("allowed_colors", ["#003366", "#FFFFFF", "#000000"])
    tolerance = color_config.get("tolerance", 10.0)  # Euclidean distance
    severity = color_config.get("severity", "medium")

    logger.info(
        "Starting color palette audit",
        palette=palette,
        tolerance=tolerance
    )

    # Extract all colors from PDF
    colors_used = extract_all_colors_from_pdf(pdf_path)

    # Validate each color
    unauthorized_colors = []
    for color in colors_used:
        is_valid, closest_match = is_color_in_palette(color, palette, tolerance)

        if not is_valid:
            unauthorized_colors.append({
                "color": color,
                "closest_match": closest_match,
                "distance": color_distance(color, closest_match)
            })

    # Create findings
    for violation in unauthorized_colors:
        findings.append(
            Finding(
                id=f"color-palette-{uuid4().hex[:8]}",
                category="format",
                rule="color_palette_compliance",
                issue=f"Color no autorizado {violation['color']} detectado",
                severity=severity,
                location=Location(
                    page=1,  # Colors apply to entire document
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None
                ),
                suggestion=f"Usar color corporativo más cercano: {violation['closest_match']}",
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "unauthorized_color": violation["color"],
                            "suggested_replacement": violation["closest_match"],
                            "distance": round(violation["distance"], 2),
                            "allowed_palette": palette
                        }
                    )
                ]
            )
        )

    # Generate summary
    summary = {
        "total_colors_detected": len(colors_used),
        "unauthorized_colors": len(unauthorized_colors),
        "compliance_rate": 1.0 - (len(unauthorized_colors) / max(len(colors_used), 1)),
        "palette_used": palette,
        "unauthorized_colors_list": [v["color"] for v in unauthorized_colors[:10]]  # Top 10
    }

    logger.info(
        "Color palette audit completed",
        findings=len(findings),
        compliance_rate=f"{summary['compliance_rate']:.1%}"
    )

    return findings, summary
```

### **Integración Completa**

1. **Import en `validation_coordinator.py`**:
```python
from ..services.color_palette_auditor import audit_color_palette
```

2. **Agregar parámetro**:
```python
async def validate_document(
    # ...
    enable_color_palette: bool = True,
    # ...
)
```

3. **Ejecutar auditor**:
```python
if enable_color_palette:
    try:
        color_findings, color_summary = await audit_color_palette(
            pdf_path=pdf_path,
            config=config
        )
        all_findings.extend(color_findings)
        summary["color_palette"] = color_summary
    except Exception as exc:
        logger.error("Color palette audit failed", error=str(exc))
```

4. **Configuración en `policies.yaml`**:
```yaml
color_palette:
  enabled: true
  allowed_colors:
    - "#003366"  # Azul corporativo
    - "#FFFFFF"  # Blanco
    - "#000000"  # Negro
    - "#F0F0F0"  # Gris claro
  tolerance: 15.0  # Distancia Euclidiana máxima
  severity: "high"
```

---

## ✅ Checklist para Agregar un Nuevo Auditor

- [ ] **1. Crear archivo** en `apps/api/src/services/{nombre}_auditor.py`
- [ ] **2. Definir función principal** `async def audit_{nombre}(...) -> Tuple[List[Finding], Dict[str, Any]]`
- [ ] **3. Importar esquemas**: `Finding`, `Location`, `Evidence`, `Severity`
- [ ] **4. Implementar lógica de validación** específica
- [ ] **5. Generar findings** con estructura completa
- [ ] **6. Retornar summary** con métricas agregadas
- [ ] **7. Agregar import** en `validation_coordinator.py`
- [ ] **8. Agregar parámetro** `enable_{nombre}` en `validate_document()`
- [ ] **9. Ejecutar auditor** dentro del try-except block
- [ ] **10. Configurar en** `policies.yaml` (sección nueva)
- [ ] **11. Habilitar en** `chat.py` (enable_{nombre}=True)
- [ ] **12. Actualizar resumen** en `summary_formatter.py` (opcional)
- [ ] **13. Documentar en** `CLAUDE.md` (sección Audit System)
- [ ] **14. Escribir tests** en `apps/api/tests/unit/test_{nombre}_auditor.py`

---

## 🎓 Mejores Prácticas

### **Diseño de Auditores**

1. **Separación de Responsabilidades**: Un auditor = una preocupación específica
2. **Idempotencia**: Ejecutar el mismo auditor múltiples veces → mismo resultado
3. **Performance**: Optimizar para PDFs grandes (>50 páginas)
4. **Logging Estructurado**: Usar `structlog` con contexto rico
5. **Manejo de Errores**: Siempre usar try-except, nunca hacer crash del coordinador

### **Severidades**

```python
# Guía de severidad
"critical": Violación que impide distribución externa (disclaimer faltante)
"high":     Violación que afecta profesionalismo (logo incorrecto)
"medium":   Violación de estilo (fuente no autorizada)
"low":      Sugerencia de mejora (espaciado inconsistente)
```

### **Categorías**

```python
"compliance":  Cumplimiento legal/regulatorio
"format":      Formato, estilo, diseño
"linguistic":  Gramática, ortografía, idioma
"logo":        Identidad visual corporativa
```

---

## 🚀 Próximos Auditores Sugeridos

1. **Accessibility Auditor**: Contraste de colores, texto alternativo en imágenes
2. **Image Quality Auditor**: Resolución mínima, compresión excesiva
3. **Metadata Auditor**: Propiedades del PDF (autor, título, fecha)
4. **Table Consistency Auditor**: Estilos de tablas, alineación
5. **Footer/Header Auditor**: Numeración de páginas, encabezados consistentes

---

## 📚 Referencias

- **Finding Schema**: `apps/api/src/schemas/audit_message.py:40-57`
- **Coordinator**: `apps/api/src/services/validation_coordinator.py:40-396`
- **Format Auditor (ejemplo completo)**: `apps/api/src/services/format_auditor.py`
- **Policy Manager**: `apps/api/src/services/policy_manager.py`

---

**Última actualización**: 2025-10-30
**Versión**: 2.0
**Autor**: Sistema de Auditoría COPILOTO_414
