"""
Audit File Tool Handler for Document Audit.

Handles tool invocations from chat to audit documents and post results as messages.

P2.BE.3: Tool auditor integration with chat.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

import structlog

from ...models.chat import ChatSession as ChatSessionModel, MessageRole
from ...models.document import Document, DocumentStatus
from ...models.user import User
from ...models.validation_report import ValidationReport
from ...schemas.audit_message import (
    AuditMessagePayload,
    AuditSummary,
    AuditAction,
    AuditContextSummary,
    Finding,
)
from ...services.policy_manager import resolve_policy
from ...services.validation_coordinator import validate_document
from ...services.minio_service import minio_service
import tempfile

logger = structlog.get_logger(__name__)


# ============================================================================
# Tool Handler
# ============================================================================


async def execute_audit_file_tool(
    doc_id: str,
    user_id: str,
    chat_id: str,
    policy_id: str = "auto",
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
) -> Dict[str, Any]:
    """
    Execute audit_file tool: validate document and post result as chat message.

    This is the main entry point when user invokes "Auditar Archivo" from chat.

    Flow:
    1. Validate document ownership and status
    2. Resolve policy (auto-detection or explicit)
    3. Run validation
    4. Save ValidationReport to MongoDB
    5. Format result as AuditMessagePayload
    6. Create ChatMessage with payload
    7. Return message

    Args:
        doc_id: Document ID to audit
        user_id: User requesting audit
        chat_id: Chat session ID
        policy_id: Policy to apply (default: "auto")
        enable_disclaimer: Run disclaimer auditor
        enable_format: Run format auditor
        enable_logo: Run logo auditor

    Returns:
        Dict with:
            - success: bool
            - message_id: str (created message ID)
            - validation_report_id: str
            - error: str (if failed)

    Example:
        result = await execute_audit_file_tool(
            doc_id="abc123",
            user_id="user456",
            chat_id="chat789",
            policy_id="auto"
        )

        if result["success"]:
            print(f"Audit message posted: {result['message_id']}")
    """
    start_time = time.time()
    job_id = str(uuid4())

    logger.info(
        "Audit file tool invoked",
        job_id=job_id,
        doc_id=doc_id,
        user_id=user_id,
        chat_id=chat_id,
        policy_id=policy_id,
    )

    try:
        # ====================================================================
        # 1. Validate document
        # ====================================================================

        doc = await Document.get(doc_id)

        if not doc:
            error_msg = "Document not found"
            logger.error("Audit tool: document not found", doc_id=doc_id)
            return {
                "success": False,
                "error": error_msg,
                "job_id": job_id,
            }

        if doc.user_id != user_id:
            error_msg = "Not authorized to audit this document"
            logger.error(
                "Audit tool: permission denied",
                doc_id=doc_id,
                user_id=user_id,
                doc_user_id=doc.user_id,
            )
            return {
                "success": False,
                "error": error_msg,
                "job_id": job_id,
            }

        if doc.status != DocumentStatus.READY:
            error_msg = f"Document not ready for audit. Status: {doc.status}"
            logger.error(
                "Audit tool: document not ready",
                doc_id=doc_id,
                status=doc.status,
            )
            return {
                "success": False,
                "error": error_msg,
                "job_id": job_id,
            }

        # ====================================================================
        # 2. Resolve policy
        # ====================================================================

        policy = await resolve_policy(policy_id, document=doc)

        logger.info(
            "Policy resolved for audit tool",
            job_id=job_id,
            policy_id=policy.id,
            policy_name=policy.name,
        )

        # Use policy client_name if available
        effective_client_name = policy.client_name

        # Override enable flags based on policy
        policy_disclaimers = policy.disclaimers or {}
        policy_logo = policy.logo or {}
        policy_format = policy.format or {}
        policy_grammar = policy.grammar or {}

        effective_enable_disclaimer = enable_disclaimer and policy_disclaimers.get("enabled", True)
        effective_enable_format = enable_format and policy_format.get("enabled", True)
        effective_enable_grammar = enable_grammar and policy_grammar.get("enabled", True)
        effective_enable_logo = enable_logo and policy_logo.get("enabled", True)

        # ====================================================================
        # 3. Get PDF path
        # ====================================================================

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                pdf_path = Path(temp_file.name)

            # Always use the persisted bucket/key from the document (source of truth)
            await minio_service.download_to_path(
                doc.minio_bucket,
                doc.minio_key,
                str(pdf_path)
            )
        except Exception as e:
            error_msg = f"Failed to get PDF from storage: {e}"
            logger.error(
                "Audit tool: Failed to get PDF from storage",
                doc_id=doc_id,
                minio_key=doc.minio_key,
                minio_bucket=doc.minio_bucket,
                error=str(e),
            )
            return {
                "success": False,
                "error": error_msg,
                "job_id": job_id,
            }

        if not pdf_path.exists():
            error_msg = f"PDF file not found at {pdf_path}"
            logger.error(
                "Audit tool: PDF not found",
                doc_id=doc_id,
                pdf_path=str(pdf_path),
            )
            return {
                "success": False,
                "error": error_msg,
                "job_id": job_id,
            }

        # ====================================================================
        # 4. Run validation
        # ====================================================================

        validation_start = time.time()

        report = await validate_document(
            document=doc,
            pdf_path=pdf_path,
            client_name=effective_client_name,
            enable_disclaimer=effective_enable_disclaimer,
            enable_format=effective_enable_format,
            enable_grammar=effective_enable_grammar,
            enable_logo=effective_enable_logo,
            policy_config=policy.to_compliance_config(),
            policy_id=policy.id,
            policy_name=policy.name,
        )

        validation_duration = (time.time() - validation_start) * 1000

        # Add policy info to summary
        if hasattr(report, 'summary') and isinstance(report.summary, dict):
            report.summary["policy_id"] = policy.id
            report.summary["policy_name"] = policy.name

        logger.info(
            "Validation completed for audit tool",
            job_id=job_id,
            doc_id=doc_id,
            total_findings=len(report.findings),
            validation_duration_ms=int(validation_duration),
        )

        # ====================================================================
        # 5. Save ValidationReport to MongoDB
        # ====================================================================

        validation_report = ValidationReport(
            document_id=doc_id,
            user_id=user_id,
            job_id=report.job_id,
            status="completed" if report.status == "done" else "error",
            client_name=effective_client_name,
            auditors_enabled={
                "disclaimer": effective_enable_disclaimer,
                "format": effective_enable_format,
                "grammar": effective_enable_grammar,
                "logo": effective_enable_logo,
            },
            findings=[f.model_dump() for f in report.findings],
            summary=report.summary,
            attachments=report.attachments,
            validation_duration_ms=int(validation_duration),
        )

        await validation_report.insert()

        # Update document with link to validation report
        doc.validation_report_id = str(validation_report.id)
        await doc.save()

        logger.info(
            "Validation report saved",
            job_id=job_id,
            validation_report_id=str(validation_report.id),
            doc_id=doc_id,
        )

        # ====================================================================
        # 6. Format as AuditMessagePayload
        # ====================================================================

        audit_payload = _format_audit_payload(
            report=report,
            validation_report_id=str(validation_report.id),
            document=doc,
            policy_id=policy.id,
            policy_name=policy.name,
        )

        # ====================================================================
        # 7. Create ChatMessage with payload
        # ====================================================================

        chat_session = await ChatSessionModel.get(chat_id)

        if not chat_session:
            error_msg = "Chat session not found"
            logger.error("Audit tool: chat not found", chat_id=chat_id)
            return {
                "success": False,
                "error": error_msg,
                "job_id": job_id,
            }

        # Format text summary for message content
        text_summary = _format_text_summary(audit_payload)

        # Create message
        message = await chat_session.add_message(
            role=MessageRole.ASSISTANT,
            content=text_summary,
            metadata=audit_payload.model_dump(),
            validation_report_id=str(validation_report.id),
        )

        logger.info(
            "Audit message posted to chat",
            job_id=job_id,
            message_id=message.id,
            chat_id=chat_id,
            validation_report_id=str(validation_report.id),
        )

        # ====================================================================
        # 8. Return success
        # ====================================================================

        total_duration = (time.time() - start_time) * 1000

        return {
            "success": True,
            "message_id": message.id,
            "validation_report_id": str(validation_report.id),
            "job_id": job_id,
            "total_findings": len(report.findings),
            "policy_used": policy.id,
            "duration_ms": int(total_duration),
        }

    except Exception as exc:
        logger.error(
            "Audit tool execution failed",
            job_id=job_id,
            doc_id=doc_id,
            error=str(exc),
            exc_info=True,
        )

        return {
            "success": False,
            "error": f"Audit failed: {exc}",
            "job_id": job_id,
        }


# ============================================================================
# Formatting Helpers
# ============================================================================


def _format_audit_payload(
    report,
    validation_report_id: str,
    document: Document,
    policy_id: str,
    policy_name: str,
) -> AuditMessagePayload:
    """Format validation report as AuditMessagePayload for frontend."""

    # Extract summary metrics
    summary_dict = report.summary if isinstance(report.summary, dict) else {}

    findings_by_severity = summary_dict.get("findings_by_severity", {})
    findings_by_category = summary_dict.get("findings_by_category", {})
    format_summary = summary_dict.get("format", {}) or {}
    grammar_summary = summary_dict.get("grammar", {}) or {}

    fonts_detail = format_summary.get("fonts_detail", []) or []
    colors_detail = format_summary.get("colors_detail", []) or []

    fonts_sorted = sorted(
        fonts_detail,
        key=lambda item: item.get("count", 0),
        reverse=True,
    )
    top_fonts = [
        f"{item.get('font')} ({', '.join(f'{size}pt' for size in item.get('sizes', [])[:3])})"
        for item in fonts_sorted[:5]
        if item.get("font")
    ]

    dominant_colors = format_summary.get("dominant_colors", []) or [
        item.get("color") for item in colors_detail[:5] if item.get("color")
    ]

    image_overview = format_summary.get("images")

    audit_summary = AuditSummary(
        total_findings=len(report.findings),
        findings_by_severity=findings_by_severity,
        findings_by_category=findings_by_category,
        disclaimer_coverage=summary_dict.get("disclaimer", {}).get("disclaimer_coverage"),
        logo_detected=summary_dict.get("logo", {}).get("found"),
        total_pages=document.total_pages,
        fonts_used=top_fonts,
        colors_detected=dominant_colors[:6],
        grammar_issues=grammar_summary.get("grammar_issues", 0),
        spelling_issues=grammar_summary.get("spelling_issues", 0),
        pages_with_grammar_issues=grammar_summary.get("pages_with_issues", []),
        image_overview=image_overview,
        policy_id=policy_id,
        policy_name=policy_name,
        validation_duration_ms=summary_dict.get("total_duration_ms", 0),
    )

    # Sample top 5 findings (most severe first)
    sorted_findings = sorted(
        report.findings,
        key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f.severity, 4)
    )
    sample_findings = sorted_findings[:5]

    # Available actions
    actions = [
        AuditAction(
            action="view_full",
            label="Ver reporte completo",
            icon="expand",
            enabled=True,
        ),
        AuditAction(
            action="re_audit",
            label="Re-auditar",
            icon="refresh",
            enabled=True,
        ),
        AuditAction(
            action="export_pdf",
            label="Exportar PDF",
            icon="download",
            enabled=False,  # TODO: Implement PDF export
        ),
    ]

    return AuditMessagePayload(
        validation_report_id=validation_report_id,
        job_id=report.job_id,
        status="completed" if report.status == "done" else "error",
        document_id=str(document.id),
        filename=document.filename,
        summary=audit_summary,
        sample_findings=sample_findings,
        actions=actions,
    )


def _format_text_summary(payload: AuditMessagePayload) -> str:
    """
    Format audit payload as plain text summary for message content.

    This is what users see in the chat before expanding the card.
    """
    summary = payload.summary

    lines = [
        f"✅ **Auditoría completada** - {payload.filename}",
        "",
        f"📊 **Resultados:** {summary.total_findings} hallazgos encontrados",
        "",
        f"**Política aplicada:** {summary.policy_name}",
    ]

    if summary.disclaimer_coverage is not None:
        lines.append(f"📄 Cobertura de disclaimers: {summary.disclaimer_coverage:.0%}")

    # Severity breakdown
    severity_lines = []
    for severity in ["critical", "high", "medium", "low"]:
        count = summary.findings_by_severity.get(severity, 0)
        if count > 0:
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}[severity]
            severity_lines.append(f"{emoji} {count} {severity}")

    if severity_lines:
        lines.append("")
        lines.append("**Por severidad:**")
        lines.extend([f"- {line}" for line in severity_lines])

    # Top critical findings
    critical_findings = [
        f for f in payload.sample_findings if f.severity == "critical"
    ]

    if critical_findings:
        lines.append("")
        lines.append("**⚠️ Hallazgos críticos:**")
        for finding in critical_findings[:2]:
            lines.append(f"- {finding.issue} (página {finding.location.page})")

    if summary.grammar_issues or summary.spelling_issues:
        lines.append("")
        lines.append("**📝 Calidad de texto:**")
        lines.append(f"- Errores gramaticales: {summary.grammar_issues}")
        lines.append(f"- Errores ortográficos: {summary.spelling_issues}")
        if summary.pages_with_grammar_issues:
            pages = ", ".join(str(p) for p in summary.pages_with_grammar_issues[:8])
            lines.append(f"- Páginas con hallazgos: {pages}")
    else:
        lines.append("")
        lines.append("📝 Texto revisado sin incidencias gramaticales relevantes.")

    if summary.fonts_used:
        lines.append("")
        lines.append("**🔤 Tipografías detectadas:**")
        for font in summary.fonts_used[:3]:
            lines.append(f"- {font}")

    if summary.colors_detected:
        lines.append("")
        lines.append("**🎨 Colores dominantes:**")
        color_badges = ", ".join(summary.colors_detected[:6])
        lines.append(f"- {color_badges}")

    if summary.image_overview:
        image_info = summary.image_overview
        total_images = image_info.get("total_images", 0)
        largest_ratio = image_info.get("largest_image_ratio", 0.0)
        if total_images:
            lines.append("")
            lines.append("**🖼️ Imágenes:**")
            lines.append(f"- Total: {total_images}")
            lines.append(f"- Mayor proporción: {largest_ratio:.1%} del área de página")
        else:
            lines.append("")
            lines.append("🖼️ No se detectaron imágenes en el documento.")

    lines.append("")
    lines.append("_Haz clic en 'Ver reporte completo' para más detalles._")

    return "\n".join(lines)
