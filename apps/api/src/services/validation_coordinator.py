"""
Validation coordinator for Copiloto 414.

Orchestrates all validation auditors:
- Disclaimer compliance
- Format validation (numbers, fonts, colors)
- Logo presence

Manages:
- Fragment extraction
- Auditor execution
- Finding aggregation
- Metrics collection
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import uuid4

import structlog

from ..models.document import PageFragment, Document
from ..schemas.audit_message import Finding, ValidationReportResponse
# from ..services.document_extraction import extract_fragments_with_bbox  # TODO: Implement this function
from ..services.compliance_auditor import audit_disclaimers, load_compliance_config
from ..services.format_auditor import audit_format
from ..services.typography_auditor import audit_typography
from ..services.logo_auditor import audit_logo
from ..services.grammar_auditor import audit_grammar
from ..services.color_palette_auditor import audit_color_palette
from ..services.entity_consistency_auditor import audit_entity_consistency
from ..services.semantic_consistency_auditor import audit_semantic_consistency

logger = structlog.get_logger(__name__)


# ============================================================================
# Main Validation Orchestrator
# ============================================================================


async def validate_document(
    document: Document,
    pdf_path: Path,
    client_name: Optional[str] = None,
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_typography: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
    enable_color_palette: bool = True,  # NEW: Phase 3
    enable_entity_consistency: bool = True,  # NEW: Phase 4
    enable_semantic_consistency: bool = True,  # NEW: Phase 5 (FINAL)
    policy_config: Optional[Dict[str, Any]] = None,  # NEW: P2.BE.1
    policy_id: Optional[str] = None,  # NEW: P2.BE.1
    policy_name: Optional[str] = None,  # NEW: P2.BE.1
) -> ValidationReportResponse:
    """
    Run complete validation on document.

    Orchestrates all validators and aggregates findings.

    Args:
        document: Document model (for metadata)
        pdf_path: Path to PDF file on disk
        client_name: Expected client name (for disclaimer validation)
        enable_disclaimer: Run disclaimer auditor
        enable_format: Run format auditor
        enable_logo: Run logo auditor
        policy_config: Policy-specific configuration (NEW: V2)
            If provided, overrides default compliance.yaml config

    Returns:
        ValidationReportResponse with all findings and summary

    Example:
        from models.document import Document
        from pathlib import Path

        doc = await Document.get("doc_id_123")
        report = await validate_document(
            document=doc,
            pdf_path=Path("/tmp/report.pdf"),
            client_name="Banamex",
        )

        print(f"Status: {report.status}")
        print(f"Total findings: {len(report.findings)}")
        for finding in report.findings:
            print(f"  {finding.severity.upper()}: {finding.issue}")
    """
    job_id = str(uuid4())
    start_time = time.time()

    logger.info(
        "Starting document validation",
        job_id=job_id,
        document_id=str(document.id),
        pdf_path=str(pdf_path),
        client_name=client_name,
        enable_disclaimer=enable_disclaimer,
        enable_format=enable_format,
        enable_typography=enable_typography,
        enable_logo=enable_logo,
        enable_color_palette=enable_color_palette,
        enable_entity_consistency=enable_entity_consistency,
        enable_semantic_consistency=enable_semantic_consistency,
    )

    # ========================================================================
    # 1. Load configuration (NEW: Support policy_config override)
    # ========================================================================

    # Use policy_config if provided, otherwise load default from compliance.yaml
    if policy_config:
        config = policy_config
        logger.info(
            "Using policy-specific configuration",
            job_id=job_id,
            config_keys=list(config.keys()),
            typography_enabled=config.get("typography", {}).get("enabled", None),
            color_palette_enabled=config.get("color_palette", {}).get("enabled", None),
        )
    else:
        config = load_compliance_config()
        logger.info("Using default compliance configuration", job_id=job_id)

    # ========================================================================
    # 2. Extract fragments with bounding boxes
    # ========================================================================

    try:
        logger.info("Extracting fragments", job_id=job_id)
        fragment_start = time.time()

        # TODO: Implement extract_fragments_with_bbox function
        # fragments: List[PageFragment] = await extract_fragments_with_bbox(pdf_path)
        fragments: List[PageFragment] = []  # Temporary: use fallback below

        # FALLBACK: If PDF is scanned/image (no searchable text), use OCR text from MongoDB
        if len(fragments) == 0 and document.pages:
            logger.info(
                "No fragments from PDF (likely scanned), using OCR text from MongoDB",
                job_id=job_id,
                pages_count=len(document.pages),
            )

            # Create synthetic fragments from MongoDB pages
            # We can't determine exact bounding boxes, but we can create footer fragments
            # by assuming the last 20% of text on each page is the footer

            for page_content in document.pages:
                page_num = page_content.page
                text = page_content.text_md.strip()

                if not text:
                    continue

                # Split text into lines
                lines = text.split('\n')
                total_lines = len(lines)

                if total_lines == 0:
                    continue

                # Last 20% of lines considered as potential footer
                footer_line_threshold = int(total_lines * 0.8)

                # Create a paragraph fragment for main content
                main_text = '\n'.join(lines[:footer_line_threshold]).strip()
                if main_text:
                    fragments.append(
                        PageFragment(
                            fragment_id=f"{page_num}-para-{uuid4().hex[:8]}",
                            page=page_num,
                            kind="paragraph",
                            bbox=[0.0, 0.0, 100.0, 80.0],  # Synthetic bbox (top 80% of page)
                            text=main_text,
                        )
                    )

                # Create footer fragment for bottom content
                footer_text = '\n'.join(lines[footer_line_threshold:]).strip()
                if footer_text:
                    fragments.append(
                        PageFragment(
                            fragment_id=f"{page_num}-footer-{uuid4().hex[:8]}",
                            page=page_num,
                            kind="footer",
                            bbox=[0.0, 80.0, 100.0, 100.0],  # Synthetic bbox (bottom 20% of page)
                            text=footer_text,
                        )
                    )

            logger.info(
                "Created synthetic fragments from OCR text",
                job_id=job_id,
                fragments_count=len(fragments),
            )

        fragment_duration = time.time() - fragment_start

        logger.info(
            "Fragment extraction completed",
            job_id=job_id,
            fragments_count=len(fragments),
            duration_ms=int(fragment_duration * 1000),
        )

    except Exception as exc:
        logger.error(
            "Fragment extraction failed",
            job_id=job_id,
            error=str(exc),
            exc_info=True,
        )

        # Return error report
        return ValidationReportResponse(
            job_id=job_id,
            status="error",
            findings=[],
            summary={
                "error": "Fragment extraction failed",
                "error_detail": str(exc),
            },
            attachments={},
        )

    # ========================================================================
    # 3. Run auditors
    # ========================================================================

    all_findings: List[Finding] = []
    summary: Dict[str, Any] = {
        "auditors_run": [],
        "total_findings": 0,
        "findings_by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
        "findings_by_category": {"compliance": 0, "format": 0, "linguistic": 0},
        "disclaimer": None,
        "format": None,
        "typography": None,
        "grammar": None,
        "logo": None,
    }

    processing_metadata = getattr(document, "processing_metadata", None) or {}
    if processing_metadata:
        summary["processing"] = {
            "ocr_applied": document.ocr_applied,
            "ocr_engines": processing_metadata.get("ocr_engines", []),
            "local_ocr_pages": processing_metadata.get("local_ocr_pages", []),
            "truncated": processing_metadata.get("truncated", False),
        }
        processing_warnings = processing_metadata.get("warnings")
        if processing_warnings:
            summary.setdefault("processing_warnings", []).extend(processing_warnings)

    # ---- Disclaimer Auditor ----
    if enable_disclaimer:
        try:
            logger.info("Running disclaimer auditor", job_id=job_id)
            disclaimer_start = time.time()

            disclaimer_findings, disclaimer_summary = await audit_disclaimers(
                fragments=fragments,
                client_name=client_name,
                config=config,
            )

            disclaimer_duration = time.time() - disclaimer_start

            all_findings.extend(disclaimer_findings)
            summary["auditors_run"].append("disclaimer")
            summary["disclaimer"] = disclaimer_summary
            summary["disclaimer_duration_ms"] = int(disclaimer_duration * 1000)

            logger.info(
                "Disclaimer auditor completed",
                job_id=job_id,
                findings=len(disclaimer_findings),
                duration_ms=int(disclaimer_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Disclaimer auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["disclaimer_error"] = str(exc)

    # ---- Format Auditor ----
    if enable_format:
        try:
            logger.info("Running format auditor", job_id=job_id)
            format_start = time.time()

            format_findings, format_summary = await audit_format(
                fragments=fragments,
                pdf_path=pdf_path,
                config=config,
            )

            format_duration = time.time() - format_start

            all_findings.extend(format_findings)
            summary["auditors_run"].append("format")
            summary["format"] = format_summary
            summary["format_duration_ms"] = int(format_duration * 1000)

            logger.info(
                "Format auditor completed",
                job_id=job_id,
                findings=len(format_findings),
                duration_ms=int(format_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Format auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["format_error"] = str(exc)

    # ---- Typography Auditor ----
    typography_config = config.get("typography", {})
    logger.info(
        "Typography auditor check",
        job_id=job_id,
        enable_typography=enable_typography,
        typography_config=typography_config,
        enabled_in_config=typography_config.get("enabled", True),
        will_run=enable_typography and typography_config.get("enabled", True)
    )
    if enable_typography and typography_config.get("enabled", True):
        try:
            logger.info("Running typography auditor", job_id=job_id)
            typography_start = time.time()

            typography_findings, typography_summary = await audit_typography(
                fragments=fragments,
                config=typography_config,
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
                duration_ms=int(typography_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Typography auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["typography_error"] = str(exc)

    # ---- Grammar Auditor ----
    if enable_grammar:
        try:
            logger.info("Running grammar auditor", job_id=job_id)
            grammar_start = time.time()

            grammar_findings, grammar_summary = await audit_grammar(
                document=document,
                config=config,
            )

            grammar_duration = time.time() - grammar_start

            all_findings.extend(grammar_findings)
            summary["auditors_run"].append("grammar")
            summary["grammar"] = grammar_summary
            summary["grammar_duration_ms"] = int(grammar_duration * 1000)

            logger.info(
                "Grammar auditor completed",
                job_id=job_id,
                findings=len(grammar_findings),
                duration_ms=int(grammar_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Grammar auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["grammar_error"] = str(exc)

    # ---- Logo Auditor ----
    if enable_logo:
        try:
            logger.info("Running logo auditor", job_id=job_id)
            logo_start = time.time()

            logo_findings, logo_summary = await audit_logo(
                pdf_path=pdf_path,
                config=config,
                total_pages=document.total_pages,
            )

            logo_duration = time.time() - logo_start

            all_findings.extend(logo_findings)
            summary["auditors_run"].append("logo")
            summary["logo"] = logo_summary
            summary["logo_duration_ms"] = int(logo_duration * 1000)

            logger.info(
                "Logo auditor completed",
                job_id=job_id,
                findings=len(logo_findings),
                duration_ms=int(logo_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Logo auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["logo_error"] = str(exc)

    # ---- Color Palette Auditor (Phase 3) ----
    color_palette_config = config.get("color_palette", {})
    logger.info(
        "Color palette auditor check",
        job_id=job_id,
        enable_color_palette=enable_color_palette,
        color_palette_config=color_palette_config,
        enabled_in_config=color_palette_config.get("enabled", True),
        will_run=enable_color_palette and color_palette_config.get("enabled", True)
    )
    if enable_color_palette and color_palette_config.get("enabled", True):
        try:
            logger.info("Running color palette auditor", job_id=job_id)
            color_palette_start = time.time()

            color_palette_findings, color_palette_summary = await audit_color_palette(
                pdf_path=pdf_path,
                config=config,
            )

            color_palette_duration = time.time() - color_palette_start

            all_findings.extend(color_palette_findings)
            summary["auditors_run"].append("color_palette")
            summary["color_palette"] = color_palette_summary
            summary["color_palette_duration_ms"] = int(color_palette_duration * 1000)

            logger.info(
                "Color palette auditor completed",
                job_id=job_id,
                findings=len(color_palette_findings),
                duration_ms=int(color_palette_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Color palette auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["color_palette_error"] = str(exc)

    # ---- Entity Consistency Auditor (Phase 4) ----
    entity_consistency_config = config.get("entity_consistency", {})
    if enable_entity_consistency and entity_consistency_config.get("enabled", True):
        try:
            logger.info("Running entity consistency auditor", job_id=job_id)
            entity_consistency_start = time.time()

            entity_consistency_findings, entity_consistency_summary = await audit_entity_consistency(
                fragments=fragments,
                config=config,
            )

            entity_consistency_duration = time.time() - entity_consistency_start

            all_findings.extend(entity_consistency_findings)
            summary["auditors_run"].append("entity_consistency")
            summary["entity_consistency"] = entity_consistency_summary
            summary["entity_consistency_duration_ms"] = int(entity_consistency_duration * 1000)

            logger.info(
                "Entity consistency auditor completed",
                job_id=job_id,
                findings=len(entity_consistency_findings),
                duration_ms=int(entity_consistency_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Entity consistency auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["entity_consistency_error"] = str(exc)

    # ---- Semantic Consistency Auditor (Phase 5 - FINAL) ----
    semantic_consistency_config = config.get("semantic_consistency", {})
    if enable_semantic_consistency and semantic_consistency_config.get("enabled", True):
        try:
            logger.info("Running semantic consistency auditor", job_id=job_id)
            semantic_consistency_start = time.time()

            semantic_consistency_findings, semantic_consistency_summary = await audit_semantic_consistency(
                fragments=fragments,
                config=config,
            )

            semantic_consistency_duration = time.time() - semantic_consistency_start

            all_findings.extend(semantic_consistency_findings)
            summary["auditors_run"].append("semantic_consistency")
            summary["semantic_consistency"] = semantic_consistency_summary
            summary["semantic_consistency_duration_ms"] = int(semantic_consistency_duration * 1000)

            logger.info(
                "Semantic consistency auditor completed",
                job_id=job_id,
                findings=len(semantic_consistency_findings),
                duration_ms=int(semantic_consistency_duration * 1000),
            )

        except Exception as exc:
            logger.error(
                "Semantic consistency auditor failed",
                job_id=job_id,
                error=str(exc),
                exc_info=True,
            )
            summary["semantic_consistency_error"] = str(exc)

    # ========================================================================
    # 4. Aggregate findings and compute metrics
    # ========================================================================

    summary["total_findings"] = len(all_findings)

    # Count by severity (robust: handles any severity level dynamically)
    for finding in all_findings:
        severity = finding.severity
        summary["findings_by_severity"][severity] = summary["findings_by_severity"].get(severity, 0) + 1

    # Count by category (robust: handles any category dynamically)
    for finding in all_findings:
        category = finding.category
        summary["findings_by_category"][category] = summary["findings_by_category"].get(category, 0) + 1

    # Total duration
    total_duration = time.time() - start_time
    summary["total_duration_ms"] = int(total_duration * 1000)

    # Determine status
    status = "done" if len(all_findings) >= 0 else "error"

    logger.info(
        "Document validation completed",
        job_id=job_id,
        status=status,
        total_findings=len(all_findings),
        duration_ms=int(total_duration * 1000),
    )

    # ========================================================================
    # 5. Return validation report
    # ========================================================================

    return ValidationReportResponse(
        job_id=job_id,
        status=status,
        findings=all_findings,
        summary=summary,
        attachments={},
        fragments_count=len(fragments),
    )


# ============================================================================
# Fragment Caching (Future Enhancement)
# ============================================================================


async def cache_fragments(document_id: str, fragments: List[PageFragment]) -> None:
    """
    Cache fragments in Redis for faster subsequent validations.

    Args:
        document_id: Document ID
        fragments: List of PageFragment objects

    Future implementation: Store serialized fragments in Redis with TTL
    """
    # TODO: Implement Redis caching
    logger.debug(
        "Fragment caching not yet implemented",
        document_id=document_id,
        fragments_count=len(fragments),
    )
    pass


async def get_cached_fragments(document_id: str) -> Optional[List[PageFragment]]:
    """
    Retrieve cached fragments from Redis.

    Args:
        document_id: Document ID

    Returns:
        List of PageFragment objects, or None if not cached

    Future implementation: Deserialize from Redis
    """
    # TODO: Implement Redis retrieval
    logger.debug("Fragment cache lookup (not yet implemented)", document_id=document_id)
    return None
