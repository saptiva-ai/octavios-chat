"""
PDF Report Generator for Capital 414 Audit Reports.

Generates professional PDF reports with:
- Cover page with branding
- Executive summary with statistics
- Detailed findings organized by auditor
- Visual charts and severity indicators
- Recommendations section

Uses reportlab for PDF generation.
"""

from datetime import datetime
from io import BytesIO
from typing import Dict, Any, List
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import structlog

from ..models.validation_report import ValidationReport

logger = structlog.get_logger(__name__)


# ============================================================================
# Color Palette (Capital 414 Branding)
# ============================================================================

COLORS = {
    "primary": colors.HexColor("#1E3A8A"),  # Dark blue
    "secondary": colors.HexColor("#10B981"),  # Emerald
    "critical": colors.HexColor("#EF4444"),  # Red
    "high": colors.HexColor("#F59E0B"),  # Amber
    "medium": colors.HexColor("#FBBF24"),  # Yellow
    "low": colors.HexColor("#10B981"),  # Green
    "gray": colors.HexColor("#6B7280"),  # Gray
    "light_gray": colors.HexColor("#F3F4F6"),  # Light gray
}


# ============================================================================
# PDF Generation
# ============================================================================


async def generate_audit_report_pdf(
    report: ValidationReport,
    filename: str,
    document_name: str = None,
) -> BytesIO:
    """
    Generate professional PDF report from ValidationReport.

    Args:
        report: ValidationReport instance with findings and summary
        filename: Original document filename (for display)
        document_name: Optional document display name

    Returns:
        BytesIO object containing PDF content

    Example:
        report = await ValidationReport.get("report_id_123")
        pdf_buffer = await generate_audit_report_pdf(
            report=report,
            filename="Capital414_presentacion.pdf"
        )

        # Upload to MinIO
        await minio_service.upload_file(
            bucket="artifacts",
            object_name=f"reports/{report.id}.pdf",
            data=pdf_buffer,
            length=pdf_buffer.getbuffer().nbytes
        )
    """
    logger.info(
        "Generating audit report PDF",
        report_id=str(report.id),
        filename=filename,
        findings_count=len(report.findings),
    )

    buffer = BytesIO()

    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    # PDF metadata (avoid default "(anonymous)" values)
    client_name = getattr(report, "client_name", None)
    document_display_name = document_name or filename
    doc.title = f"Reporte de Auditoría - {document_display_name}"
    doc.author = client_name or "Capital 414"
    doc.subject = f"Auditoría de {document_display_name}"
    doc.creator = "Capital 414 · Motor de Auditoría Automática"
    doc.keywords = [
        "Capital 414",
        "Auditoría",
        document_display_name,
    ]

    # Build story (content elements)
    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=COLORS["primary"],
        alignment=TA_CENTER,
        spaceAfter=30,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=COLORS["primary"],
        spaceAfter=12,
    )

    subheading_style = ParagraphStyle(
        "CustomSubHeading",
        parent=styles["Heading3"],
        fontSize=13,
        textColor=COLORS["primary"],
        spaceAfter=8,
    )

    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=14,
        textColor=COLORS["gray"],
    )

    card_title_style = ParagraphStyle(
        "CardTitle",
        parent=styles["BodyText"],
        fontSize=9,
        textColor=COLORS["gray"],
        leading=12,
    )

    card_value_style = ParagraphStyle(
        "CardValue",
        parent=styles["Heading2"],
        fontSize=18,
        textColor=COLORS["primary"],
        leading=20,
    )

    card_meta_style = ParagraphStyle(
        "CardMeta",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        textColor=colors.black,
    )

    chip_style = ParagraphStyle(
        "Chip",
        parent=styles["BodyText"],
        fontSize=10,
        leading=12,
        textColor=colors.black,
    )

    custom_styles = {
        "heading": heading_style,
        "subheading": subheading_style,
        "body": body_style,
        "card_title": card_title_style,
        "card_value": card_value_style,
        "card_meta": card_meta_style,
        "chip": chip_style,
        "title": title_style,
    }

    # ========================================================================
    # 1. COVER PAGE
    # ========================================================================

    story.extend(_generate_cover_page(filename, document_name, report, title_style, styles))
    story.append(PageBreak())

    # ========================================================================
    # 2. RESUMEN EJECUTIVO
    # ========================================================================

    story.extend(_build_summary_section(report, custom_styles))
    story.append(PageBreak())

    # ========================================================================
    # 3. HALLAZGOS POR AUDITOR
    # ========================================================================

    story.extend(_build_auditor_sections(report, custom_styles))

    # Add page break only if findings exist
    if report.findings:
        story.append(PageBreak())

    # ========================================================================
    # 4. ACCIONES RECOMENDADAS
    # ========================================================================

    story.extend(_build_recommendations_section(report, custom_styles))

    # ========================================================================
    # 5. FOOTER
    # ========================================================================

    story.append(Spacer(1, 0.5 * inch))
    footer_text = f"Generado el {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    footer_para = Paragraph(
        footer_text,
        ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=COLORS["gray"],
            alignment=TA_CENTER,
        ),
    )
    story.append(footer_para)

    # Build PDF
    doc.build(story)

    # Reset buffer position
    buffer.seek(0)

    logger.info(
        "PDF report generated successfully",
        report_id=str(report.id),
        pdf_size_bytes=buffer.getbuffer().nbytes,
    )

    return buffer


# ============================================================================
# Helper Functions
# ============================================================================


def _generate_cover_page(
    filename: str,
    document_name: str,
    report: ValidationReport,
    title_style: ParagraphStyle,
    styles: dict,
) -> List:
    """Generate cover page elements."""
    elements = []

    elements.append(Spacer(1, 2 * inch))

    # Title
    elements.append(Paragraph("Reporte de Auditoría", title_style))
    elements.append(Paragraph("Capital 414", title_style))
    elements.append(Spacer(1, 0.5 * inch))

    # Document info
    doc_name = document_name or filename
    elements.append(
        Paragraph(
            f"<b>Documento:</b> {doc_name}",
            ParagraphStyle(
                "DocName",
                parent=styles["Normal"],
                fontSize=14,
                alignment=TA_CENTER,
            ),
        )
    )
    elements.append(Spacer(1, 0.2 * inch))

    # Report metadata
    generated_date = report.created_at.strftime("%Y-%m-%d %H:%M UTC")
    elements.append(
        Paragraph(
            f"<b>Fecha de generación:</b> {generated_date}",
            ParagraphStyle("Meta", parent=styles["Normal"], alignment=TA_CENTER),
        )
    )
    elements.append(Spacer(1, 0.1 * inch))

    elements.append(
        Paragraph(
            f"<b>ID de reporte:</b> {str(report.id)[:8]}...",
            ParagraphStyle("Meta", parent=styles["Normal"], alignment=TA_CENTER),
        )
    )

    return elements


def _build_summary_section(
    report: ValidationReport, styles_dict: Dict[str, ParagraphStyle]
) -> List:
    """Build executive summary section with KPIs and severity overview."""
    flow: List = []
    flow.append(Paragraph("Resumen Ejecutivo", styles_dict["heading"]))
    flow.append(Spacer(1, 0.15 * inch))
    flow.extend(_build_kpi_cards(report, styles_dict))
    flow.append(Spacer(1, 0.2 * inch))
    flow.extend(_build_severity_overview(report, styles_dict))
    flow.append(Spacer(1, 0.2 * inch))

    insights = _build_focus_insights(report, styles_dict)
    if insights:
        flow.extend(insights)

    return flow


def _build_kpi_cards(
    report: ValidationReport, styles_dict: Dict[str, ParagraphStyle]
) -> List:
    """Render KPI cards for top metrics."""
    metrics = _collect_kpi_metrics(report)

    cards = [
        {
            "title": "Total de hallazgos",
            "value": str(metrics["total_findings"]),
            "meta": f"Crítica {metrics['critical']} · Mayor {metrics['high']} · Media {metrics['medium']} · Sugerencia {metrics['low']}",
        },
        {
            "title": "Cobertura de disclaimers",
            "value": metrics["disclaimer_coverage_display"],
            "meta": metrics["disclaimer_meta"],
        },
        {
            "title": "Páginas con imagen dominante",
            "value": metrics["image_coverage_display"],
            "meta": metrics["image_meta"],
        },
        {
            "title": "Hallazgos lingüísticos",
            "value": metrics["linguistic_total_display"],
            "meta": metrics["linguistic_meta"],
        },
    ]

    card_tables: List = []
    for card in cards:
        card_data = [
            [Paragraph(card["title"], styles_dict["card_title"])],
            [Paragraph(card["value"], styles_dict["card_value"])],
            [Paragraph(card["meta"], styles_dict["card_meta"])],
        ]
        card_table = Table(card_data, colWidths=[2.8 * inch])
        card_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, COLORS["light_gray"]),
                    ("INNERPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        card_tables.append(card_table)

    rows = []
    for i in range(0, len(card_tables), 2):
        row = card_tables[i : i + 2]
        if len(row) < 2:
            row.append(Spacer(2.8 * inch, 0))
        rows.append(row)

    cards_grid = Table(rows, colWidths=[3 * inch, 3 * inch], hAlign="LEFT")
    cards_grid.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    return [cards_grid]


def _collect_kpi_metrics(report: ValidationReport) -> Dict[str, Any]:
    """Compute metrics used in KPI cards."""
    summary = report.summary or {}
    findings_by_severity = summary.get("findings_by_severity") or {}
    disclaimer_summary = summary.get("disclaimer") or {}
    format_summary = summary.get("format") or {}
    images_info = format_summary.get("images") or {}
    grammar_summary = summary.get("grammar") or {}

    total_findings = len(report.findings)
    critical = findings_by_severity.get("critical", 0)
    high = findings_by_severity.get("high", 0)
    medium = findings_by_severity.get("medium", 0)
    low = findings_by_severity.get("low", 0)

    coverage = summary.get("disclaimer_coverage")
    if coverage is None:
        coverage = disclaimer_summary.get("disclaimer_coverage")
    coverage_pct = coverage * 100 if coverage is not None else None
    pages_missing = disclaimer_summary.get("pages_missing_disclaimer")
    total_pages = disclaimer_summary.get("total_pages")

    images = images_info.get("images", []) if isinstance(images_info, dict) else []
    large_images = sum(1 for img in images if img.get("area_ratio", 0) >= 0.65)
    large_image_pct = (large_images / len(images) * 100) if images else 0

    linguistic_total = grammar_summary.get("total_issues") if isinstance(grammar_summary, dict) else None
    spelling_issues = grammar_summary.get("spelling_issues") if isinstance(grammar_summary, dict) else None
    grammar_issues = grammar_summary.get("grammar_issues") if isinstance(grammar_summary, dict) else None

    metrics = {
        "total_findings": total_findings,
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
        "disclaimer_coverage_display": "Sin datos",
        "disclaimer_meta": "Cobertura no disponible",
        "image_coverage_display": f"{large_image_pct:.0f}%",
        "image_meta": f"{large_images} de {len(images)} páginas con imagen dominante (>65%)"
        if images
        else "Sin imágenes analizadas",
        "linguistic_total_display": str(linguistic_total or 0),
        "linguistic_meta": (
            f"Ortografía {spelling_issues or 0} · Gramática {grammar_issues or 0}"
        ),
    }

    if coverage_pct is not None:
        metrics["disclaimer_coverage_display"] = f"{coverage_pct:.1f}%"
        missing_label = (
            f"{pages_missing} páginas pendientes" if pages_missing else "Cobertura completa"
        )
        if pages_missing and total_pages:
            missing_label = (
                f"{pages_missing} de {total_pages} páginas sin disclaimer aprobado"
            )
        metrics["disclaimer_meta"] = missing_label

    if summary.get("validation_duration_ms"):
        duration_sec = summary["validation_duration_ms"] / 1000
        metrics["duration_display"] = f"{duration_sec:.1f}s"
    else:
        metrics["duration_display"] = None

    return metrics


SEVERITY_ORDER = ["critical", "high", "medium", "low"]
SEVERITY_LABELS = {
    "critical": ("Crítica", COLORS["critical"]),
    "high": ("Mayor", COLORS["high"]),
    "medium": ("Media", COLORS["medium"]),
    "low": ("Sugerencia", COLORS["low"]),
}


def _build_severity_overview(
    report: ValidationReport, styles_dict: Dict[str, ParagraphStyle]
) -> List:
    """Render severity overview table with textual chips."""
    summary = report.summary or {}
    findings_by_severity = summary.get("findings_by_severity") or {}

    header_style = ParagraphStyle(
        "SeverityHeader",
        parent=styles_dict["body"],
        textColor=colors.white,
        fontSize=10,
        leading=12,
    )

    data = [
        [
            Paragraph("<b>Severidad</b>", header_style),
            Paragraph("<b>Hallazgos</b>", header_style),
        ]
    ]

    for severity in SEVERITY_ORDER:
        label, _ = SEVERITY_LABELS.get(severity, ("Sin clasificar", COLORS["gray"]))
        count = findings_by_severity.get(severity, 0)
        chip = Paragraph(_format_severity_chip(severity), styles_dict["body"])
        data.append([chip, Paragraph(str(count), styles_dict["body"])])

    table = Table(data, colWidths=[3.5 * inch, 1.5 * inch], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, COLORS["light_gray"]),
                ("BOX", (0, 0), (-1, -1), 0.5, COLORS["light_gray"]),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    return [
        Paragraph("Severidad y prioridad", styles_dict["subheading"]),
        table,
    ]


def _build_focus_insights(
    report: ValidationReport, styles_dict: Dict[str, ParagraphStyle]
) -> List:
    """Highlight key focus areas as bullet insights."""
    summary = report.summary or {}
    insights: List = []

    coverage = summary.get("disclaimer_coverage")
    disclaimer_summary = summary.get("disclaimer") or {}
    if coverage is None:
        coverage = disclaimer_summary.get("disclaimer_coverage")

    if coverage is not None:
        pages_missing = disclaimer_summary.get("pages_missing_disclaimer", 0)
        total_pages = disclaimer_summary.get("total_pages")
        insight = (
            f"Cobertura de disclaimers en {coverage*100:.1f}% "
            f"({pages_missing} páginas pendientes de {total_pages or 'N/A'})."
        )
        insights.append(Paragraph(f"• {insight}", styles_dict["body"]))

    format_summary = summary.get("format") or {}
    images_data = format_summary.get("images") or {}
    images = images_data.get("images", []) if isinstance(images_data, dict) else []
    large_images = sum(1 for img in images if img.get("area_ratio", 0) >= 0.65)
    if images:
        insights.append(
            Paragraph(
                f"• {large_images} página{'s' if large_images != 1 else ''} con imagen que ocupa más del 65% del área.",
                styles_dict["body"],
            )
        )

    grammar_summary = summary.get("grammar") or {}
    linguistic_total = grammar_summary.get("total_issues") if isinstance(grammar_summary, dict) else None
    if linguistic_total:
        insights.append(
            Paragraph(
                f"• {linguistic_total} hallazgo{'s' if linguistic_total != 1 else ''} lingüístico{'s' if linguistic_total != 1 else ''} (ortografía y gramática).",
                styles_dict["body"],
            )
        )

    if insights:
        insights.insert(0, Paragraph("KPIs y alertas", styles_dict["subheading"]))

    return insights


AUDITOR_LABELS = {
    "compliance": "Auditor de Disclaimers",
    "format": "Auditor de Formato e Imágenes",
    "typography": "Auditor de Tipografía",
    "grammar": "Auditor Lingüístico",
    "logo": "Auditor de Identidad Visual",
    "color_palette": "Auditor de Paleta de Colores",
    "entity_consistency": "Auditor de Consistencia de Entidades",
    "semantic_consistency": "Auditor de Consistencia Semántica",
    "other": "Otros hallazgos",
}


def _build_auditor_sections(
    report: ValidationReport, styles_dict: Dict[str, ParagraphStyle]
) -> List:
    """Render grouped findings per auditor with actionable tables."""
    flow: List = []
    flow.append(Paragraph("Hallazgos por auditor", styles_dict["heading"]))
    flow.append(Spacer(1, 0.15 * inch))

    if not report.findings:
        flow.append(Paragraph("No se registraron hallazgos para este documento.", styles_dict["body"]))
        return flow

    findings_by_auditor = _group_findings_by_auditor(report.findings)
    order = [key for key in AUDITOR_LABELS.keys() if key in findings_by_auditor]

    for auditor_key in order:
        findings = findings_by_auditor.get(auditor_key, [])
        if not findings:
            continue

        flow.append(Paragraph(AUDITOR_LABELS.get(auditor_key, auditor_key.title()), styles_dict["subheading"]))
        summary_text = _generate_auditor_summary_text(auditor_key, findings)
        flow.append(Paragraph(summary_text, styles_dict["body"]))
        flow.append(Spacer(1, 0.08 * inch))
        flow.append(_render_auditor_table(findings, styles_dict))
        flow.append(Spacer(1, 0.2 * inch))

    return flow


def _render_auditor_table(
    findings: List[Dict[str, Any]], styles_dict: Dict[str, ParagraphStyle]
):
    """Render an accessible table for auditor findings."""
    if not findings:
        return Paragraph("Sin hallazgos registrados para este auditor.", styles_dict["body"])

    header_style = ParagraphStyle(
        "TableHeader",
        parent=styles_dict["body"],
        textColor=colors.white,
        fontSize=9,
        leading=12,
    )

    table_data = [
        [
            Paragraph("<b>#</b>", header_style),
            Paragraph("<b>Severidad</b>", header_style),
            Paragraph("<b>Hallazgo</b>", header_style),
            Paragraph("<b>Sugerencia / Acción</b>", header_style),
            Paragraph("<b>Página</b>", header_style),
        ]
    ]

    def severity_sort_key(finding: Dict[str, Any]) -> int:
        severity = finding.get("severity", "medium")
        try:
            return SEVERITY_ORDER.index(severity)
        except ValueError:
            return len(SEVERITY_ORDER)

    sorted_findings = sorted(findings, key=severity_sort_key)

    for idx, finding in enumerate(sorted_findings, 1):
        severity = finding.get("severity", "medium")
        issue = finding.get("issue") or "Sin descripción"
        suggestion = finding.get("suggestion") or "Sin sugerencia"
        location = finding.get("location") or {}
        page = location.get("page") if isinstance(location, dict) else None
        snippet = None
        if isinstance(location, dict):
            snippet = location.get("text_snippet")
            if snippet and len(snippet) > 140:
                snippet = snippet[:137].rstrip() + "..."

        context_parts = []
        if snippet:
            context_parts.append(snippet)

        if finding.get("category"):
            context_parts.append(f"Categoría: {finding.get('category')}")

        context_html = ""
        if context_parts:
            context_html = "<br/><font color='#6B7280'>" + " · ".join(context_parts) + "</font>"

        issue_paragraph = Paragraph(
            f"<b>{issue}</b>{context_html}",
            styles_dict["body"],
        )

        suggestion_paragraph = Paragraph(
            suggestion,
            styles_dict["body"],
        )

        table_data.append(
            [
                Paragraph(f"{idx:02d}", styles_dict["body"]),
                Paragraph(_format_severity_chip(severity), styles_dict["body"]),
                issue_paragraph,
                suggestion_paragraph,
                Paragraph(f"Pág. {page}" if page else "N/A", styles_dict["body"]),
            ]
        )

    table = Table(
        table_data,
        colWidths=[0.6 * inch, 1.1 * inch, 2.5 * inch, 2.1 * inch, 0.8 * inch],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLORS["primary"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLORS["light_gray"]]),
                ("GRID", (0, 1), (-1, -1), 0.25, COLORS["light_gray"]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
            ]
        )
    )

    return table


def _format_severity_chip(severity: str) -> str:
    """Return HTML string representing severity chip."""
    label, color = SEVERITY_LABELS.get(severity, ("Sin clasificar", COLORS["gray"]))
    hex_color = color.hexval()
    if not hex_color.startswith("#"):
        hex_color = f"#{hex_color}"
    return f'<font color="{hex_color}">•</font> {label}'


def _build_recommendations_section(
    report: ValidationReport, styles_dict: Dict[str, ParagraphStyle]
) -> List:
    """Render recommendations section."""
    flow: List = []
    flow.append(Paragraph("Acciones recomendadas", styles_dict["heading"]))
    flow.append(Spacer(1, 0.15 * inch))

    recommendations = _generate_recommendations(report)
    if not recommendations:
        flow.append(Paragraph("No se identificaron acciones adicionales.", styles_dict["body"]))
        return flow

    for rec in recommendations:
        flow.append(Paragraph(f"• {rec}", styles_dict["body"]))
        flow.append(Spacer(1, 0.08 * inch))

    return flow


def _group_findings_by_auditor(findings: List[Dict[str, Any]]) -> Dict[str, List]:
    """Group findings by auditor category."""
    grouped = {}

    for finding in findings:
        category = finding.get("category", "unknown").lower()

        # Map categories to auditor names (aligned with summary_formatter.py)
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
        elif category in ["format", "formato"] or any(
            keyword in category for keyword in ["fuente", "font", "imagen", "image", "numero"]
        ):
            auditor = "format"
        elif category in ["grammar", "linguistic", "gramática"] or any(
            keyword in category for keyword in ["ortografía", "spelling", "gramatica"]
        ):
            auditor = "grammar"
        elif "logo" in category or "identidad" in category or "marca" in category:
            auditor = "logo"
        else:
            auditor = "other"

        if auditor not in grouped:
            grouped[auditor] = []

        grouped[auditor].append(finding)

    return grouped


def _generate_auditor_summary_text(auditor: str, findings: List[Dict[str, Any]]) -> str:
    """Generate concise summary text for an auditor."""
    if not findings:
        return "Sin hallazgos"

    if auditor == "compliance":
        disclaimer_findings = [
            f for f in findings if "disclaimer" in (f.get("issue", "") or "").lower()
        ]
        if disclaimer_findings:
            pages = []
            for finding in disclaimer_findings[:4]:
                location = finding.get("location") or {}
                page = location.get("page") if isinstance(location, dict) else None
                if page:
                    pages.append(str(page))
            if pages:
                return (
                    f"{len(disclaimer_findings)} disclaimer"
                    f"{'s' if len(disclaimer_findings) != 1 else ''} faltante"
                    f"{'s' if len(disclaimer_findings) != 1 else ''} en páginas {', '.join(pages)}"
                )
        return f"{len(findings)} hallazgo{'s' if len(findings) != 1 else ''} de cumplimiento"

    if auditor == "format":
        color_issues = [
            f for f in findings if "color" in (f.get("issue", "") or "").lower()
        ]
        font_issues = [
            f
            for f in findings
            if "fuente" in (f.get("issue", "") or "").lower()
            or "font" in (f.get("issue", "") or "").lower()
        ]
        parts: List[str] = []
        if color_issues:
            parts.append(
                f"{len(color_issues)} color{'es' if len(color_issues) != 1 else ''} fuera de guía"
            )
        if font_issues:
            parts.append(
                f"{len(font_issues)} fuente{'s' if len(font_issues) != 1 else ''} incorrecta{'s' if len(font_issues) != 1 else ''}"
            )
        if parts:
            return ", ".join(parts)
        return f"{len(findings)} hallazgo{'s' if len(findings) != 1 else ''} de formato"

    if auditor == "grammar":
        spelling = [
            f for f in findings if "ortografía" in (f.get("issue", "") or "").lower()
        ]
        grammar = [
            f for f in findings if "gramática" in (f.get("issue", "") or "").lower()
        ]
        return (
            f"Ortografía {len(spelling)} · Gramática {len(grammar)}"
            if spelling or grammar
            else f"{len(findings)} hallazgo{'s' if len(findings) != 1 else ''} lingüístico{'s' if len(findings) != 1 else ''}"
        )

    if auditor == "logo":
        logo_missing = [
            f for f in findings if "logo" in (f.get("issue", "") or "").lower()
        ]
        size_issues = [
            f
            for f in findings
            if "tamaño" in (f.get("issue", "") or "").lower()
            or "escala" in (f.get("issue", "") or "").lower()
        ]
        if logo_missing:
            return "Logo faltante o no detectado"
        if size_issues:
            return f"{len(size_issues)} hallazgo{'s' if len(size_issues) != 1 else ''} de escala/posición"
        return f"{len(findings)} hallazgo{'s' if len(findings) != 1 else ''} de identidad visual"

    return f"{len(findings)} hallazgo{'s' if len(findings) != 1 else ''}"


def _generate_recommendations(report: ValidationReport) -> List[str]:
    """Generate actionable recommendations based on findings."""
    recommendations = []

    summary = report.summary or {}
    findings_by_sev = summary.get("findings_by_severity") or {}

    critical_count = findings_by_sev.get("critical", 0)
    high_count = findings_by_sev.get("high", 0)

    if critical_count > 0:
        recommendations.append(
            f"Abordar de inmediato los {critical_count} hallazgos críticos antes de distribución externa."
        )

    if high_count > 0:
        recommendations.append(
            f"Revisar y corregir los {high_count} hallazgos de severidad alta."
        )

    # Disclaimer coverage
    coverage = summary.get("disclaimer_coverage")
    if coverage is None:
        coverage = (summary.get("disclaimer") or {}).get("disclaimer_coverage")
    if coverage is not None and coverage < 1:
        recommendations.append(
            f"Mejorar cobertura de disclaimers (actual: {coverage*100:.1f}%, objetivo: 100%)."
        )

    format_summary = summary.get("format") or {}
    images_data = format_summary.get("images") or {}
    images = images_data.get("images", []) if isinstance(images_data, dict) else []
    large_images = sum(1 for img in images if img.get("area_ratio", 0) >= 0.65)
    if large_images:
        recommendations.append(
            f"Reducir imágenes dominantes en {large_images} página{'s' if large_images != 1 else ''} (>65% del slide)."
        )

    grammar_summary = summary.get("grammar") or {}
    linguistic_total = (
        grammar_summary.get("total_issues") if isinstance(grammar_summary, dict) else None
    )
    if linguistic_total:
        recommendations.append(
            f"Revisar vocabulario corporativo y gramática: {linguistic_total} hallazgo{'s' if linguistic_total != 1 else ''} pendiente{'s' if linguistic_total != 1 else ''}."
        )

    # Generic recommendations
    if len(report.findings) > 10:
        recommendations.append(
            "Considerar revisión exhaustiva del documento dado el alto número de hallazgos."
        )

    recommendations = list(dict.fromkeys(recommendations))

    if not recommendations:
        recommendations.append(
            "El documento cumple con todos los estándares de Capital 414. ¡Excelente trabajo!"
        )

    return recommendations
