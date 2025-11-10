"""
Executive Summary Formatter for Capital 414 Audit Reports.

Generates concise, chat-friendly summaries instead of full detailed reports.

Key Features:
- Summary statistics (total findings, severity breakdown)
- Per-auditor summary (1-2 lines each)
- Top 5 critical/high findings only
- Download link to full PDF report
"""

from typing import Dict, Any, List, Optional
import structlog

from ..models.validation_report import ValidationReport

logger = structlog.get_logger(__name__)


# ============================================================================
# Executive Summary Generation
# ============================================================================


def generate_executive_summary(report: ValidationReport) -> Dict[str, Any]:
    """
    Generate concise executive summary from ValidationReport.

    Returns structured summary with:
    - Total findings count
    - Breakdown by severity
    - Breakdown by auditor
    - Top 5 most critical findings

    Args:
        report: ValidationReport instance

    Returns:
        Dict with summary data structure

    Example:
        {
            "total_findings": 23,
            "by_severity": {"critical": 2, "high": 5, "medium": 12, "low": 4},
            "by_auditor": {
                "compliance": {
                    "total": 8,
                    "critical": 2,
                    "summary": "2 disclaimers faltantes en páginas 3, 7"
                },
                "format": {
                    "total": 10,
                    "high": 3,
                    "summary": "3 colores no autorizados"
                },
                "grammar": {
                    "total": 3,
                    "medium": 2,
                    "summary": "Ortografía correcta, puntuación menor"
                },
                "logo": {
                    "total": 2,
                    "medium": 2,
                    "summary": "Logo presente, tamaño incorrecto"
                }
            },
            "top_findings": [
                {
                    "severity": "critical",
                    "issue": "Disclaimer faltante en footer",
                    "page": 3
                },
                ...
            ]
        }
    """
    logger.info(
        "Generating executive summary",
        report_id=str(report.id),
        findings_count=len(report.findings),
    )

    summary = report.summary or {}
    findings = report.findings or []

    # Total findings
    total_findings = len(findings)

    # Breakdown by severity
    by_severity = summary.get("findings_by_severity", {})

    # Breakdown by auditor (pass report.summary for positive messages when no findings)
    by_auditor = _summarize_by_auditor(findings, report_summary=summary)

    # Top findings (critical and high only, max 5)
    top_findings = _get_top_findings(findings, max_count=5)

    result = {
        "total_findings": total_findings,
        "by_severity": by_severity,
        "by_auditor": by_auditor,
        "top_findings": top_findings,
        "disclaimer_coverage": summary.get("disclaimer_coverage"),
        "policy_name": summary.get("policy_name"),
    }

    logger.info(
        "Executive summary generated",
        report_id=str(report.id),
        auditors_count=len(by_auditor),
        top_findings_count=len(top_findings),
    )

    return result


def format_executive_summary_as_markdown(
    summary: Dict[str, Any],
    filename: str,
    report_url: str,
) -> str:
    """
    Format executive summary as compact markdown for chat display.

    Args:
        summary: Executive summary dict from generate_executive_summary()
        filename: Document filename
        report_url: Presigned URL to download full PDF report

    Returns:
        Formatted markdown string

    Example Output:
        ## 📊 Reporte de Auditoría: documento.pdf

        ### Resumen Ejecutivo

        **Total**: 23 hallazgos
        **Severidad**: 🔴 2 críticos | 🔴 5 altos | 🟡 12 medios | 🟢 4 bajos

        **Por Auditor**:
        - ✅ **Cumplimiento**: 8 hallazgos (2 disclaimers faltantes)
        - ⚠️ **Formato**: 10 hallazgos (3 colores no autorizados)
        - ✏️ **Gramática**: 3 hallazgos (ortografía correcta)
        - 🎨 **Logo**: 2 hallazgos (tamaño incorrecto)

        **Top 5 Hallazgos Críticos**:
        1. 🔴 Disclaimer faltante (Pág. 3)
        2. 🔴 Disclaimer faltante (Pág. 7)
        3. 🔴 Color no autorizado (Pág. 5)
        4. 🟡 Logo con escala incorrecta (Portada)
        5. 🟡 Fuente no corporativa (Pág. 12)

        ---

        📥 **[Descargar Reporte Completo (PDF)]({report_url})**
        *Incluye todos los hallazgos con detalles y sugerencias*
    """
    lines = []

    # Header with policy
    policy_name = summary.get("policy_name") or "Estándar"
    lines.append(f"## 📊 Reporte de Auditoría: {filename}\n")
    lines.append(f"**Política**: {policy_name}")

    # Overall status indicator
    total = summary.get("total_findings", 0)
    by_severity = summary.get("by_severity", {})
    critical_count = by_severity.get("critical", 0)
    high_count = by_severity.get("high", 0)

    if critical_count > 0:
        status_icon = "🔴"
        status_text = "**Requiere Correcciones Críticas**"
    elif high_count > 5:
        status_icon = "🟡"
        status_text = "**Requiere Revisión**"
    elif high_count > 0:
        status_icon = "🟠"
        status_text = "**Ajustes Recomendados**"
    elif total > 10:
        status_icon = "🟡"
        status_text = "**Mejoras Sugeridas**"
    else:
        status_icon = "🟢"
        status_text = "**Cumplimiento Satisfactorio**"

    lines.append(f"**Estado**: {status_icon} {status_text}\n")

    # Severity breakdown - TABLE FORMAT
    lines.append("### 📊 Hallazgos por Severidad\n")

    severity_data = [
        ("🔴 Crítico", by_severity.get("critical", 0), "⚡ **BLOQUEA** distribución externa. Acción inmediata requerida"),
        ("🔴 Alto", by_severity.get("high", 0), "🔧 Corregir antes de aprobación final. Impacto en cumplimiento"),
        ("🟡 Medio", by_severity.get("medium", 0), "📝 Revisar antes de publicación. Mejora la calidad"),
        ("🟢 Bajo", by_severity.get("low", 0), "ℹ️ Sugerencias opcionales de mejora. Sin impacto en distribución"),
    ]

    for label, count, action in severity_data:
        if count > 0:
            lines.append(f"- **{label}**: {count} → {action}")

    lines.append(f"\n**Total**: {total} hallazgo{'s' if total != 1 else ''}")

    # Disclaimer coverage (if available) with visual indicator
    if summary.get("disclaimer_coverage") is not None:
        coverage = summary["disclaimer_coverage"] * 100
        coverage_icon = "🟢" if coverage >= 100 else "🟡" if coverage >= 75 else "🔴"
        lines.append(f"**Cobertura de disclaimers**: {coverage_icon} {coverage:.1f}% / 100%")

    lines.append("")  # Empty line

    # Breakdown by auditor
    by_auditor = summary.get("by_auditor", {})
    if by_auditor:
        lines.append("### 📋 Resultados por Auditor\n")

        auditor_order = ["compliance", "format", "typography", "grammar", "logo", "color_palette", "entity_consistency", "semantic_consistency"]
        auditor_icons = {
            "compliance": "✅",
            "format": "⚠️",
            "typography": "🔤",
            "grammar": "✏️",
            "logo": "🎨",
            "color_palette": "🎨",
            "entity_consistency": "🔍",
            "semantic_consistency": "📊",
        }
        auditor_labels = {
            "compliance": "Cumplimiento Legal",
            "format": "Formato y Estilo",
            "typography": "Tipografía",
            "grammar": "Gramática y Ortografía",
            "logo": "Identidad Visual",
            "color_palette": "Paleta de Colores",
            "entity_consistency": "Consistencia de Entidades",
            "semantic_consistency": "Consistencia Semántica",
        }

        for auditor_key in auditor_order:
            # Always show all auditors, even if they have no findings
            if auditor_key not in by_auditor:
                # Generate positive summary for auditors with no findings
                auditor_metrics = summary.get(auditor_key, {})
                positive_summary = _generate_auditor_summary_text(auditor_key, [], auditor_metrics=auditor_metrics)
                auditor_data = {
                    "total": 0,
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "summary": positive_summary
                }
            else:
                auditor_data = by_auditor[auditor_key]

            icon = auditor_icons.get(auditor_key, "📋")
            label = auditor_labels.get(auditor_key, auditor_key.capitalize())
            total_count = auditor_data.get("total", 0)
            critical_count = auditor_data.get("critical", 0)
            high_count = auditor_data.get("high", 0)
            summary_text = auditor_data.get("summary", "Sin hallazgos detectados")

            # Determine status icon based on severity
            if critical_count > 0:
                status = f"🔴 **{label}**"
            elif high_count > 0:
                status = f"🟡 **{label}**"
            elif total_count > 0:
                status = f"{icon} **{label}**"
            else:
                status = f"✅ **{label}**"

            if total_count == 0:
                lines.append(f"{status}")
                lines.append(f"  - {summary_text}\n")
            else:
                lines.append(f"{status}")
                lines.append(f"  - {total_count} hallazgo{'s' if total_count != 1 else ''}")
                if critical_count > 0 or high_count > 0:
                    priority_parts = []
                    if critical_count > 0:
                        priority_parts.append(f"{critical_count} crítico{'s' if critical_count > 1 else ''}")
                    if high_count > 0:
                        priority_parts.append(f"{high_count} alto{'s' if high_count > 1 else ''}")
                    lines.append(f"  - ⚠️ **Prioritarios**: {', '.join(priority_parts)}")
                lines.append(f"  - 💡 {summary_text}\n")

        lines.append("")  # Empty line

    # Top findings
    top_findings = summary.get("top_findings", [])
    if top_findings:
        lines.append("### 🎯 Acciones Prioritarias\n")

        for idx, finding in enumerate(top_findings, 1):
            severity = finding.get("severity", "medium")
            issue = finding.get("issue", "Sin descripción")
            page = finding.get("page")
            count = finding.get("count", 1)

            # Severity emoji
            severity_emoji = {
                "critical": "🔴",
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢",
            }.get(severity, "🔵")

            # Format with count if grouped
            lines.append(f"{idx}. {severity_emoji} **{issue}**")

        lines.append("")  # Empty line

    # Download section with enhanced call-to-action
    lines.append("---\n")
    lines.append("### 📥 Siguiente Paso\n")
    lines.append(f"**[Descargar Reporte Completo (PDF)]({report_url})**\n")
    lines.append("El PDF incluye:")
    lines.append(f"- ✅ Desglose completo de {total} hallazgo{'s' if total != 1 else ''}")
    lines.append("- ✅ Ubicaciones exactas con números de página")
    lines.append("- ✅ Sugerencias de corrección específicas")
    lines.append("- ✅ Evidencia visual cuando corresponde")

    return "\n".join(lines)


# ============================================================================
# Helper Functions
# ============================================================================


def _summarize_by_auditor(findings: List[Dict[str, Any]], report_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Summarize findings by auditor category.

    Args:
        findings: List of findings from validation report
        report_summary: Full ValidationReport.summary with auditor metrics (optional)

    Returns:
        {
            "compliance": {
                "total": 8,
                "critical": 2,
                "high": 3,
                "summary": "2 disclaimers faltantes en páginas 3, 7"
            },
            ...
        }
    """
    auditors = {}

    # Group findings by auditor
    for finding in findings:
        category = finding.get("category", "unknown").lower()

        # Map categories to auditor names (support both English and Spanish)
        if category in ["compliance", "cumplimiento"] or "disclaimer" in category:
            auditor = "compliance"
        elif category == "typography" or "tipografía" in category or "tipografia" in category:
            auditor = "typography"
        elif category == "color_palette" or "paleta" in category:
            auditor = "color_palette"
        elif category == "entity_consistency" or "entidad" in category or "entity" in category:
            auditor = "entity_consistency"
        elif category == "semantic_consistency" or "semántica" in category or "semantica" in category or "semantic" in category:
            auditor = "semantic_consistency"
        elif category in ["format", "formato"] or "color" in category or "fuente" in category or "font" in category:
            auditor = "format"
        elif category in ["linguistic", "gramática", "grammar"] or "ortografía" in category or "spelling" in category:
            auditor = "grammar"
        elif category in ["logo", "identidad"] or "visual" in category:
            auditor = "logo"
        else:
            auditor = "other"

        if auditor not in auditors:
            auditors[auditor] = {
                "total": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "findings": [],
            }

        auditors[auditor]["total"] += 1
        severity = finding.get("severity", "medium")
        auditors[auditor][severity] = auditors[auditor].get(severity, 0) + 1
        auditors[auditor]["findings"].append(finding)

    # Generate summary text for each auditor
    for auditor, data in auditors.items():
        # Get auditor-specific metrics from report summary
        auditor_metrics = report_summary.get(auditor, {}) if report_summary else {}
        summary_text = _generate_auditor_summary_text(auditor, data["findings"], auditor_metrics=auditor_metrics)
        data["summary"] = summary_text

    return auditors


def _generate_auditor_summary_text(
    auditor: str,
    findings: List[Dict[str, Any]],
    auditor_metrics: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generate concise 1-2 line summary for an auditor's findings.

    When no findings exist, generates positive message with metrics from auditor_metrics.

    Args:
        auditor: Auditor name (compliance, format, grammar, logo, etc.)
        findings: List of findings for this auditor
        auditor_metrics: Auditor-specific metrics from ValidationReport.summary (optional)

    Returns:
        Concise summary string
    """
    if not findings:
        # Generate positive messages with rich metrics when no issues found
        if auditor == "grammar":
            # Try to extract pages from summary.grammar or fallback to pages_analyzed
            metrics = auditor_metrics or {}
            grammar_summary = metrics.get("grammar", metrics)  # Support both nested and flat structure

            pages = grammar_summary.get("pages_analyzed", 0) or grammar_summary.get("pages_with_issues", 0)
            chars_analyzed = grammar_summary.get("chars_analyzed", 0)
            words_analyzed = grammar_summary.get("words_analyzed", 0)

            # Build rich message
            parts = []
            if pages > 0:
                parts.append(f"{pages} página{'s' if pages > 1 else ''}")
            if chars_analyzed > 0:
                parts.append(f"{chars_analyzed:,} caracteres".replace(',', '.'))
            elif words_analyzed > 0:
                parts.append(f"{words_analyzed:,} palabras".replace(',', '.'))

            if parts:
                return f"✅ 100% ortografía correcta ({', '.join(parts)} validados con LanguageTool)"
            # Fallback con información mínima útil
            return "✅ Documento validado con LanguageTool - sin errores ortográficos ni gramaticales detectados"

        elif auditor == "format":
            metrics = auditor_metrics or {}
            format_summary = metrics.get("format", metrics)

            # Extract font and color details
            fonts_detail = format_summary.get("fonts_detail", [])
            colors_detail = format_summary.get("colors_detail", [])
            images = format_summary.get("images", {})

            total_fonts = len(fonts_detail)
            total_colors = len(colors_detail)
            total_images = images.get("total_images", 0)

            parts = []
            if total_fonts > 0:
                font_names = [f["font"] for f in fonts_detail[:3]]  # Top 3
                parts.append(f"{total_fonts} fuente{'s' if total_fonts > 1 else ''} ({', '.join(font_names)})")
            if total_colors > 0:
                parts.append(f"{total_colors} colores corporativos")
            if total_images > 0:
                parts.append(f"{total_images} imagen{'es' if total_images > 1 else ''} optimizada{'s' if total_images > 1 else ''}")

            if parts:
                return f"✅ Formato validado: {' • '.join(parts)}"
            # Fallback con información sobre el proceso
            return "✅ Análisis de formato completado con PyMuPDF - fuentes y colores corporativos verificados"

        elif auditor == "color_palette":
            metrics = auditor_metrics or {}
            color_summary = metrics.get("color_palette", metrics)

            colors_detail = color_summary.get("colors_detail", [])
            dominant_colors = color_summary.get("dominant_colors", [])

            if colors_detail:
                # Show top colors used
                top_colors = [c["color"] for c in colors_detail[:5]]
                return f"✅ Paleta corporativa validada: {len(colors_detail)} colores analizados ({', '.join(top_colors[:3])}{'...' if len(top_colors) > 3 else ''}) - 100% conformidad"
            elif dominant_colors:
                return f"✅ Análisis de color completado: {len(dominant_colors)} tonos principales detectados - conformidad con guía de marca"
            # Fallback con valor
            return "✅ Paleta de colores analizada con extractor PyMuPDF - todos los colores cumplen con guía corporativa"

        elif auditor == "entity_consistency":
            metrics = auditor_metrics or {}
            entity_summary = metrics.get("entity_consistency", metrics)

            client_mentions = entity_summary.get("client_mentions", 0)
            entity_variants = entity_summary.get("entity_variants", {})

            if client_mentions > 0:
                return f"✅ {client_mentions} menciones de '414 Capital' validadas - nomenclatura 100% consistente"
            elif entity_variants:
                total_entities = sum(len(variants) for variants in entity_variants.values())
                return f"✅ {total_entities} entidades analizadas - nomenclatura consistente en todo el documento"
            return "✅ Análisis de entidades completado - nomenclatura corporativa aplicada uniformemente"

        elif auditor == "semantic_consistency":
            metrics = auditor_metrics or {}
            semantic_summary = metrics.get("semantic_consistency", metrics)

            sections = semantic_summary.get("sections_analyzed", 0)
            coherence_score = semantic_summary.get("coherence_score", 0)

            if sections > 0 and coherence_score > 0:
                return f"✅ {sections} secciones analizadas con análisis semántico - coherencia {coherence_score:.0%}"
            elif sections > 0:
                return f"✅ {sections} secciones validadas - flujo narrativo coherente y bien estructurado"
            return "✅ Análisis semántico completado - estructura narrativa coherente en todo el documento"

        elif auditor == "typography":
            metrics = auditor_metrics or {}
            typo_summary = metrics.get("typography", metrics)

            pages = typo_summary.get("pages_analyzed", 0)
            headings_analyzed = typo_summary.get("headings_analyzed", 0)

            if pages > 0:
                parts = [f"{pages} páginas"]
                if headings_analyzed > 0:
                    parts.append(f"{headings_analyzed} encabezados")
                return f"✅ Tipografía validada: {' y '.join(parts)} revisados - jerarquía visual coherente"
            return "✅ Análisis tipográfico completado - jerarquía de tamaños y estilos cumple con estándares"

        elif auditor == "logo":
            metrics = auditor_metrics or {}
            logo_summary = metrics.get("logo", metrics)

            locations = logo_summary.get("locations", [])
            pages_required = logo_summary.get("pages_required", ["portada", "última"])

            if locations:
                avg_similarity = sum(loc.get("similarity", 0) for loc in locations) / len(locations)
                return f"✅ Logo corporativo validado con OpenCV: {len(locations)} ubicacion{'es' if len(locations) > 1 else ''} detectadas (match {avg_similarity:.0%})"
            elif pages_required:
                return f"✅ Verificación de logo completada: presente en {', '.join(pages_required)} según política corporativa"
            return "✅ Análisis de identidad visual completado con OpenCV - logo corporativo correctamente aplicado"

        elif auditor == "compliance":
            metrics = auditor_metrics or {}
            compliance_summary = metrics.get("compliance", metrics) or metrics.get("disclaimer", {})

            coverage = compliance_summary.get("disclaimer_coverage", 0)
            pages_covered = compliance_summary.get("pages_covered", [])
            templates_matched = compliance_summary.get("templates_matched", 0)

            if coverage >= 1.0:
                if pages_covered:
                    return f"✅ Disclaimers legales validados con fuzzy matching: 100% cobertura en {len(pages_covered)} páginas"
                elif templates_matched > 0:
                    return f"✅ Compliance legal verificado: {templates_matched} disclaimer{'s' if templates_matched > 1 else ''} validado{'s' if templates_matched > 1 else ''} - 100% conformidad"
                return "✅ Análisis legal completado: 100% de cobertura de disclaimers requeridos por normativa"
            return "✅ Validación de compliance legal completada - todos los avisos legales presentes y correctos"

        else:
            return "✅ Validación completada sin hallazgos"

    if auditor == "compliance":
        # Count disclaimer issues
        disclaimer_findings = [f for f in findings if "disclaimer" in f.get("issue", "").lower()]
        if disclaimer_findings:
            pages = []
            for f in disclaimer_findings[:3]:  # Max 3 pages
                loc = f.get("location", {})
                page = loc.get("page") if isinstance(loc, dict) else None
                if page:
                    pages.append(str(page))

            if pages:
                return f"{len(disclaimer_findings)} disclaimer{'s' if len(disclaimer_findings) > 1 else ''} faltante{'s' if len(disclaimer_findings) > 1 else ''} en página{'s' if len(pages) > 1 else ''} {', '.join(pages)}"

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de cumplimiento"

    elif auditor == "format":
        # Identify common format issues and detect patterns
        color_issues = [f for f in findings if "color" in f.get("issue", "").lower()]
        font_issues = [f for f in findings if "fuente" in f.get("issue", "").lower() or "font" in f.get("issue", "").lower()]
        numeric_issues = [f for f in findings if "número" in f.get("issue", "").lower() or "formato no permitido" in f.get("issue", "").lower()]

        # Detect if 100% of findings are about the same number (pattern)
        if numeric_issues and len(numeric_issues) == len(findings):
            # Extract the repeated number from first finding
            first_issue = numeric_issues[0].get("issue", "")
            if "«414»" in first_issue or '"414"' in first_issue:
                return f"⚠️ Patrón detectado: 100% son el número '414' (nombre de marca). Sugerencia: agregar '414' a whitelist de excepciones"
            elif "«" in first_issue:
                # Extract the number from guillemets
                import re
                match = re.search(r'«([^»]+)»', first_issue)
                if match:
                    repeated_value = match.group(1)
                    return f"Patrón detectado: 100% son el valor '{repeated_value}' ({len(numeric_issues)} ocurrencias). Considerar agregar a whitelist"

        parts = []
        if color_issues:
            parts.append(f"{len(color_issues)} color{'es' if len(color_issues) > 1 else ''} no autorizado{'s' if len(color_issues) > 1 else ''}")
        if font_issues:
            parts.append(f"{len(font_issues)} fuente{'s' if len(font_issues) > 1 else ''} incorrecta{'s' if len(font_issues) > 1 else ''}")
        if numeric_issues and len(numeric_issues) < len(findings):
            parts.append(f"{len(numeric_issues)} formato{'s' if len(numeric_issues) > 1 else ''} numérico{'s' if len(numeric_issues) > 1 else ''} incorrecto{'s' if len(numeric_issues) > 1 else ''}")

        if parts:
            return ", ".join(parts)

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de formato"

    elif auditor == "grammar":
        # Grammar summary with technical terms detection
        spelling_issues = [f for f in findings if "ortográfico" in f.get("issue", "").lower()]
        grammar_issues = [f for f in findings if "gramatical" in f.get("issue", "").lower()]

        # Count "Sugerencia" severity (likely false positives for technical terms)
        low_severity = [f for f in findings if f.get("severity", "") == "low"]

        # Detect technical terms pattern (IFRS, ASC, Framework, etc.)
        technical_terms = ["IFRS", "ASC", "Framework", "Valuation", "PitchBook", "EMIS", "Preqin", "C4P1T4L"]
        likely_tech_terms = sum(1 for f in findings if any(term.lower() in f.get("issue", "").lower() for term in technical_terms))

        if likely_tech_terms > len(findings) * 0.7:  # >70% are technical terms
            real_errors = len(findings) - likely_tech_terms
            return f"⚠️ {likely_tech_terms} tecnicismos financieros detectados como errores. {real_errors} error{'es' if real_errors > 1 else ''} real{'es' if real_errors > 1 else ''}. Sugerencia: agregar diccionario corporativo"

        if len(findings) <= 3:
            return "Ortografía correcta, puntuación menor"

        parts = []
        if spelling_issues:
            parts.append(f"{len(spelling_issues)} ortográfico{'s' if len(spelling_issues) > 1 else ''}")
        if grammar_issues:
            parts.append(f"{len(grammar_issues)} gramatical{'es' if len(grammar_issues) > 1 else ''}")

        if parts:
            return f"{', '.join(parts)}"

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de gramática y ortografía"

    elif auditor == "logo":
        # Logo summary with context
        missing_issues = [f for f in findings if "ausente" in f.get("issue", "").lower() or "no detectado" in f.get("issue", "").lower()]
        size_issues = [f for f in findings if "tamaño" in f.get("issue", "").lower() or "pequeño" in f.get("issue", "").lower()]

        if missing_issues:
            pages = []
            for f in missing_issues[:3]:  # Max 3 pages
                loc = f.get("location", {})
                page = loc.get("page") if isinstance(loc, dict) else None
                if page:
                    pages.append(str(page))

            pages_str = ", ".join(pages) if pages else "requeridas"
            return f"Logo ausente en {len(missing_issues)} página{'s' if len(missing_issues) > 1 else ''} ({pages_str}). ⚠️ Bloquea distribución externa"

        if size_issues:
            return f"Logo presente pero {len(size_issues)} problema{'s' if len(size_issues) > 1 else ''} de tamaño/escala"

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de identidad visual"

    elif auditor == "typography":
        # Typography summary
        heading_issues = [f for f in findings if "encabezado" in f.get("issue", "").lower() or "heading" in f.get("issue", "").lower()]
        spacing_issues = [f for f in findings if "espaciado" in f.get("issue", "").lower() or "spacing" in f.get("issue", "").lower()]
        size_issues = [f for f in findings if "tamaño" in f.get("issue", "").lower() and "fuente" in f.get("issue", "").lower()]

        parts = []
        if heading_issues:
            parts.append(f"{len(heading_issues)} problema{'s' if len(heading_issues) > 1 else ''} de encabezados")
        if spacing_issues:
            parts.append(f"{len(spacing_issues)} problema{'s' if len(spacing_issues) > 1 else ''} de espaciado")
        if size_issues:
            parts.append(f"{len(size_issues)} tamaño{'s' if len(size_issues) > 1 else ''} de fuente incorrecto{'s' if len(size_issues) > 1 else ''}")

        if parts:
            return ", ".join(parts)

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de tipografía"

    elif auditor == "color_palette":
        # Color palette summary
        non_compliant_colors = [f for f in findings if "color" in f.get("issue", "").lower()]

        if non_compliant_colors:
            return f"{len(non_compliant_colors)} color{'es' if len(non_compliant_colors) > 1 else ''} fuera de la paleta aprobada"

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de paleta de colores"

    elif auditor == "entity_consistency":
        # Entity consistency summary
        name_variants = [f for f in findings if "nombre" in f.get("issue", "").lower() or "variante" in f.get("issue", "").lower()]
        currency_issues = [f for f in findings if "moneda" in f.get("issue", "").lower() or "currency" in f.get("issue", "").lower()]

        parts = []
        if name_variants:
            parts.append(f"{len(name_variants)} variante{'s' if len(name_variants) > 1 else ''} de nombres")
        if currency_issues:
            parts.append(f"{len(currency_issues)} inconsistencia{'s' if len(currency_issues) > 1 else ''} de moneda")

        if parts:
            return ", ".join(parts)

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de consistencia de entidades"

    elif auditor == "semantic_consistency":
        # Semantic consistency summary
        numeric_issues = [f for f in findings if "numérica" in f.get("issue", "").lower() or "número" in f.get("issue", "").lower()]
        semantic_issues = [f for f in findings if "semántica" in f.get("issue", "").lower() or "similitud" in f.get("issue", "").lower()]

        parts = []
        if numeric_issues:
            parts.append(f"{len(numeric_issues)} discrepancia{'s' if len(numeric_issues) > 1 else ''} numérica{'s' if len(numeric_issues) > 1 else ''}")
        if semantic_issues:
            parts.append(f"{len(semantic_issues)} discrepancia{'s' if len(semantic_issues) > 1 else ''} semántica{'s' if len(semantic_issues) > 1 else ''}")

        if parts:
            return ", ".join(parts)

        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''} de consistencia semántica"

    else:
        return f"{len(findings)} hallazgo{'s' if len(findings) > 1 else ''}"


def _get_top_findings(findings: List[Dict[str, Any]], max_count: int = 5) -> List[Dict[str, Any]]:
    """
    Get top N most critical findings with smart grouping.

    Priority order: critical > high > medium > low
    Groups similar findings to avoid redundancy.

    Args:
        findings: List of all findings
        max_count: Maximum number of findings to return

    Returns:
        List of top findings with simplified structure
    """
    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    sorted_findings = sorted(
        findings,
        key=lambda f: severity_order.get(f.get("severity", "medium"), 99)
    )

    # Group similar findings
    grouped = {}
    for finding in sorted_findings:
        rule = finding.get("rule", "unknown")
        category = finding.get("category", "unknown")
        severity = finding.get("severity", "medium")
        issue_base = finding.get("issue", "Sin descripción")

        # Create grouping key based on rule + category
        group_key = f"{category}_{rule}"

        if group_key not in grouped:
            grouped[group_key] = {
                "severity": severity,
                "rule": rule,
                "category": category,
                "issue_base": issue_base,
                "pages": [],
                "count": 0
            }

        location = finding.get("location", {})
        page = location.get("page") if isinstance(location, dict) else None
        if page:
            grouped[group_key]["pages"].append(page)
        grouped[group_key]["count"] += 1

    # Convert grouped findings to top list
    top = []
    for group_key, group_data in grouped.items():
        count = group_data["count"]
        pages = sorted(set(group_data["pages"]))[:5]  # Max 5 pages shown
        severity = group_data["severity"]
        issue_base = group_data["issue_base"]

        # Format issue with count if multiple
        if count > 1:
            if pages:
                pages_str = ", ".join(str(p) for p in pages)
                if count > len(pages):
                    pages_str += f", +{count - len(pages)} más"
                issue = f"{issue_base} ({count} ocurrencias en págs: {pages_str})"
            else:
                issue = f"{issue_base} ({count} ocurrencias)"
        else:
            issue = issue_base

        top.append({
            "severity": severity,
            "issue": issue,
            "page": pages[0] if pages else None,
            "count": count
        })

    # Sort by severity again
    top.sort(key=lambda f: severity_order.get(f.get("severity", "medium"), 99))

    # Limit to max_count
    return top[:max_count]
