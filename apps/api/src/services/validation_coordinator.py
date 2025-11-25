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
from typing import List, Dict, Any, Optional, AsyncGenerator
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

    TODO [Octavius-2.0 / Phase 3]: Migrate to queue-based worker
    Current implementation: Synchronous execution (blocks chat response)
    Target implementation: Background job with progress updates

    Migration plan:
    1. Create AuditProducer in this file (enqueue validation job)
    2. Implement AuditWorker in workers/audit_worker.py (consumer)
    3. Add job progress tracking for each auditor phase:
       - Disclaimer → Format → Typography → Grammar → Logo
    4. Emit WebSocket/SSE events for real-time canvas updates
    5. Update endpoint to return 202 Accepted + task_id immediately
    6. Add streaming endpoint GET /api/audit/{task_id}/stream

    Benefits:
    - Handle large PDFs without timeout (current limit: ~30s)
    - Real-time progress bar in frontend
    - Retry logic for failed auditors (especially logo detection)
    - Resource throttling for OpenCV operations
    - Parallel processing of multiple documents

    See: apps/api/src/workers/README.md Section 2 (Document Audit Processing)

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
    # 3. Run auditors (Parallel Execution)
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
        "color_palette": None,
        "entity_consistency": None,
        "semantic_consistency": None,
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

    # Define auditor wrappers for parallel execution
    async def run_disclaimer():
        if enable_disclaimer:
            try:
                logger.info("Running disclaimer auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_disclaimers(
                    fragments=fragments, client_name=client_name, config=config
                )
                return "disclaimer", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Disclaimer auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "disclaimer", [], None, 0, str(e)
        return "disclaimer", [], None, 0, None

    async def run_format():
        if enable_format:
            try:
                logger.info("Running format auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_format(
                    fragments=fragments, pdf_path=pdf_path, config=config
                )
                return "format", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Format auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "format", [], None, 0, str(e)
        return "format", [], None, 0, None

    async def run_typography():
        typography_config = config.get("typography", {})
        if enable_typography and typography_config.get("enabled", True):
            try:
                logger.info("Running typography auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_typography(
                    fragments=fragments, config=typography_config
                )
                return "typography", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Typography auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "typography", [], None, 0, str(e)
        return "typography", [], None, 0, None

    async def run_grammar():
        if enable_grammar:
            try:
                logger.info("Running grammar auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_grammar(
                    document=document, config=config
                )
                return "grammar", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Grammar auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "grammar", [], None, 0, str(e)
        return "grammar", [], None, 0, None

    async def run_logo():
        if enable_logo:
            try:
                logger.info("Running logo auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_logo(
                    pdf_path=pdf_path, config=config, total_pages=document.total_pages
                )
                return "logo", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Logo auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "logo", [], None, 0, str(e)
        return "logo", [], None, 0, None

    async def run_color_palette():
        color_config = config.get("color_palette", {})
        if enable_color_palette and color_config.get("enabled", True):
            try:
                logger.info("Running color palette auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_color_palette(
                    pdf_path=pdf_path, config=config
                )
                return "color_palette", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Color palette auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "color_palette", [], None, 0, str(e)
        return "color_palette", [], None, 0, None

    async def run_entity_consistency():
        entity_config = config.get("entity_consistency", {})
        if enable_entity_consistency and entity_config.get("enabled", True):
            try:
                logger.info("Running entity consistency auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_entity_consistency(
                    fragments=fragments, config=config
                )
                return "entity_consistency", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Entity consistency auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "entity_consistency", [], None, 0, str(e)
        return "entity_consistency", [], None, 0, None

    async def run_semantic_consistency():
        semantic_config = config.get("semantic_consistency", {})
        if enable_semantic_consistency and semantic_config.get("enabled", True):
            try:
                logger.info("Running semantic consistency auditor", job_id=job_id)
                start = time.time()
                findings, audit_summary = await audit_semantic_consistency(
                    fragments=fragments, config=config
                )
                return "semantic_consistency", findings, audit_summary, time.time() - start, None
            except Exception as e:
                logger.error("Semantic consistency auditor failed", job_id=job_id, error=str(e), exc_info=True)
                return "semantic_consistency", [], None, 0, str(e)
        return "semantic_consistency", [], None, 0, None

    # Execute all auditors in parallel
    import asyncio
    results = await asyncio.gather(
        run_disclaimer(),
        run_format(),
        run_typography(),
        run_grammar(),
        run_logo(),
        run_color_palette(),
        run_entity_consistency(),
        run_semantic_consistency()
    )

    # Process results
    for name, findings, audit_summary, duration, error in results:
        if error:
            summary[f"{name}_error"] = error
        elif findings is not None: # Check if auditor ran (findings could be empty list)
            all_findings.extend(findings)
            summary["auditors_run"].append(name)
            summary[name] = audit_summary
            summary[f"{name}_duration_ms"] = int(duration * 1000)
            
            logger.info(
                f"{name.capitalize()} auditor completed",
                job_id=job_id,
                findings=len(findings),
                duration_ms=int(duration * 1000),
            )

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


# ============================================================================
# Streaming Validation (for SSE support)
# ============================================================================


async def validate_document_streaming(
    document: Document,
    pdf_path: Path,
    client_name: Optional[str] = None,
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_typography: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
    enable_color_palette: bool = True,
    enable_entity_consistency: bool = True,
    enable_semantic_consistency: bool = True,
    policy_config: Optional[Dict[str, Any]] = None,
    policy_id: Optional[str] = None,
    policy_name: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream validation progress in real-time (for SSE).

    Yields events for each auditor:
    - auditor_start: {"type": "auditor_start", "auditor": "disclaimer", "total_auditors": 8, "current": 1}
    - auditor_complete: {"type": "auditor_complete", "auditor": "disclaimer", "findings": [...], "summary": {...}, "duration_ms": 123}
    - auditor_error: {"type": "auditor_error", "auditor": "disclaimer", "error": "..."}
    - validation_complete: {"type": "validation_complete", "report": {...}}

    Usage:
        async for event in validate_document_streaming(document, pdf_path):
            if event["type"] == "auditor_start":
                print(f"Starting {event['auditor']}...")
            elif event["type"] == "auditor_complete":
                print(f"Completed {event['auditor']} with {len(event['findings'])} findings")
    """
    job_id = str(uuid4())
    start_time = time.time()

    logger.info(
        "Starting streaming document validation",
        job_id=job_id,
        document_id=str(document.id),
        pdf_path=str(pdf_path),
    )

    # Yield initial metadata
    yield {
        "type": "validation_start",
        "job_id": job_id,
        "document_id": str(document.id),
        "filename": document.filename,
        "total_auditors": 8,
    }

    # Load configuration
    if policy_config:
        config = policy_config
    else:
        config = load_compliance_config()

    # Extract fragments
    try:
        logger.info("Extracting fragments", job_id=job_id)
        fragment_start = time.time()

        fragments: List[PageFragment] = []

        # FALLBACK: Use OCR text from MongoDB
        if len(fragments) == 0 and document.pages:
            logger.info(
                "Using OCR text from MongoDB",
                job_id=job_id,
                pages_count=len(document.pages),
            )

            for page_content in document.pages:
                page_num = page_content.page
                text = page_content.text_md.strip()

                if not text:
                    continue

                lines = text.split('\n')
                total_lines = len(lines)

                if total_lines == 0:
                    continue

                footer_line_threshold = int(total_lines * 0.8)

                main_text = '\n'.join(lines[:footer_line_threshold]).strip()
                if main_text:
                    fragments.append(
                        PageFragment(
                            fragment_id=f"{page_num}-para-{uuid4().hex[:8]}",
                            page=page_num,
                            kind="paragraph",
                            bbox=[0.0, 0.0, 100.0, 80.0],
                            text=main_text,
                        )
                    )

                footer_text = '\n'.join(lines[footer_line_threshold:]).strip()
                if footer_text:
                    fragments.append(
                        PageFragment(
                            fragment_id=f"{page_num}-footer-{uuid4().hex[:8]}",
                            page=page_num,
                            kind="footer",
                            bbox=[0.0, 80.0, 100.0, 100.0],
                            text=footer_text,
                        )
                    )

        fragment_duration = time.time() - fragment_start

        yield {
            "type": "fragments_extracted",
            "fragments_count": len(fragments),
            "duration_ms": int(fragment_duration * 1000),
        }

    except Exception as exc:
        logger.error("Fragment extraction failed", job_id=job_id, error=str(exc))
        yield {
            "type": "validation_error",
            "error": "Fragment extraction failed",
            "error_detail": str(exc),
        }
        return

    # Initialize summary and findings
    all_findings: List[Finding] = []
    summary: Dict[str, Any] = {
        "auditors_run": [],
        "total_findings": 0,
        "findings_by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
        "findings_by_category": {"compliance": 0, "format": 0, "linguistic": 0},
    }

    auditor_index = 0

    # Auditor 1: Disclaimer
    if enable_disclaimer:
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "disclaimer",
            "auditor_name": "Disclaimer Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            disclaimer_findings, disclaimer_summary = await audit_disclaimers(
                fragments=fragments,
                client_name=client_name,
                config=config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(disclaimer_findings)
            summary["auditors_run"].append("disclaimer")
            summary["disclaimer"] = disclaimer_summary

            yield {
                "type": "auditor_complete",
                "auditor": "disclaimer",
                "auditor_name": "Disclaimer Auditor",
                "findings": [f.model_dump() for f in disclaimer_findings],
                "summary": disclaimer_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Disclaimer auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "disclaimer",
                "auditor_name": "Disclaimer Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 2: Format
    if enable_format:
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "format",
            "auditor_name": "Format Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            format_findings, format_summary = await audit_format(
                fragments=fragments,
                pdf_path=pdf_path,
                config=config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(format_findings)
            summary["auditors_run"].append("format")
            summary["format"] = format_summary

            yield {
                "type": "auditor_complete",
                "auditor": "format",
                "auditor_name": "Format Auditor",
                "findings": [f.model_dump() for f in format_findings],
                "summary": format_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Format auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "format",
                "auditor_name": "Format Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 3: Typography
    typography_config = config.get("typography", {})
    if enable_typography and typography_config.get("enabled", True):
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "typography",
            "auditor_name": "Typography Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            typography_findings, typography_summary = await audit_typography(
                fragments=fragments,
                config=typography_config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(typography_findings)
            summary["auditors_run"].append("typography")
            summary["typography"] = typography_summary

            yield {
                "type": "auditor_complete",
                "auditor": "typography",
                "auditor_name": "Typography Auditor",
                "findings": [f.model_dump() for f in typography_findings],
                "summary": typography_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Typography auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "typography",
                "auditor_name": "Typography Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 4: Grammar
    if enable_grammar:
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "grammar",
            "auditor_name": "Grammar Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            grammar_findings, grammar_summary = await audit_grammar(
                document=document,
                config=config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(grammar_findings)
            summary["auditors_run"].append("grammar")
            summary["grammar"] = grammar_summary

            yield {
                "type": "auditor_complete",
                "auditor": "grammar",
                "auditor_name": "Grammar Auditor",
                "findings": [f.model_dump() for f in grammar_findings],
                "summary": grammar_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Grammar auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "grammar",
                "auditor_name": "Grammar Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 5: Logo
    if enable_logo:
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "logo",
            "auditor_name": "Logo Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            logo_findings, logo_summary = await audit_logo(
                pdf_path=pdf_path,
                config=config,
                total_pages=document.total_pages,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(logo_findings)
            summary["auditors_run"].append("logo")
            summary["logo"] = logo_summary

            yield {
                "type": "auditor_complete",
                "auditor": "logo",
                "auditor_name": "Logo Auditor",
                "findings": [f.model_dump() for f in logo_findings],
                "summary": logo_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Logo auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "logo",
                "auditor_name": "Logo Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 6: Color Palette
    color_palette_config = config.get("color_palette", {})
    if enable_color_palette and color_palette_config.get("enabled", True):
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "color_palette",
            "auditor_name": "Color Palette Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            color_palette_findings, color_palette_summary = await audit_color_palette(
                pdf_path=pdf_path,
                config=config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(color_palette_findings)
            summary["auditors_run"].append("color_palette")
            summary["color_palette"] = color_palette_summary

            yield {
                "type": "auditor_complete",
                "auditor": "color_palette",
                "auditor_name": "Color Palette Auditor",
                "findings": [f.model_dump() for f in color_palette_findings],
                "summary": color_palette_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Color palette auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "color_palette",
                "auditor_name": "Color Palette Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 7: Entity Consistency
    entity_consistency_config = config.get("entity_consistency", {})
    if enable_entity_consistency and entity_consistency_config.get("enabled", True):
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "entity_consistency",
            "auditor_name": "Entity Consistency Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            entity_consistency_findings, entity_consistency_summary = await audit_entity_consistency(
                fragments=fragments,
                config=config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(entity_consistency_findings)
            summary["auditors_run"].append("entity_consistency")
            summary["entity_consistency"] = entity_consistency_summary

            yield {
                "type": "auditor_complete",
                "auditor": "entity_consistency",
                "auditor_name": "Entity Consistency Auditor",
                "findings": [f.model_dump() for f in entity_consistency_findings],
                "summary": entity_consistency_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Entity consistency auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "entity_consistency",
                "auditor_name": "Entity Consistency Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Auditor 8: Semantic Consistency
    semantic_consistency_config = config.get("semantic_consistency", {})
    if enable_semantic_consistency and semantic_consistency_config.get("enabled", True):
        auditor_index += 1
        yield {
            "type": "auditor_start",
            "auditor": "semantic_consistency",
            "auditor_name": "Semantic Consistency Auditor",
            "current": auditor_index,
            "total_auditors": 8,
        }

        try:
            auditor_start = time.time()
            semantic_consistency_findings, semantic_consistency_summary = await audit_semantic_consistency(
                fragments=fragments,
                config=config,
            )
            auditor_duration = time.time() - auditor_start

            all_findings.extend(semantic_consistency_findings)
            summary["auditors_run"].append("semantic_consistency")
            summary["semantic_consistency"] = semantic_consistency_summary

            yield {
                "type": "auditor_complete",
                "auditor": "semantic_consistency",
                "auditor_name": "Semantic Consistency Auditor",
                "findings": [f.model_dump() for f in semantic_consistency_findings],
                "summary": semantic_consistency_summary,
                "duration_ms": int(auditor_duration * 1000),
                "current": auditor_index,
                "total_auditors": 8,
            }

        except Exception as exc:
            logger.error("Semantic consistency auditor failed", job_id=job_id, error=str(exc))
            yield {
                "type": "auditor_error",
                "auditor": "semantic_consistency",
                "auditor_name": "Semantic Consistency Auditor",
                "error": str(exc),
                "current": auditor_index,
                "total_auditors": 8,
            }

    # Calculate final summary
    for finding in all_findings:
        summary["total_findings"] += 1
        severity = finding.severity.lower() if hasattr(finding, 'severity') else 'low'
        if severity in summary["findings_by_severity"]:
            summary["findings_by_severity"][severity] += 1
        category = finding.category.lower() if hasattr(finding, 'category') else 'compliance'
        if category in summary["findings_by_category"]:
            summary["findings_by_category"][category] += 1

    total_duration = time.time() - start_time

    # Yield final report
    yield {
        "type": "validation_complete",
        "job_id": job_id,
        "status": "done",
        "findings": [f.model_dump() for f in all_findings],
        "summary": summary,
        "duration_ms": int(total_duration * 1000),
        "policy_id": policy_id,
        "policy_name": policy_name,
    }

    logger.info(
        "Streaming document validation completed",
        job_id=job_id,
        total_findings=len(all_findings),
        duration_ms=int(total_duration * 1000),
    )
