"""
Capital 414 Private Plugin - FastMCP Server.

Exposes the COPILOTO_414 audit system as an MCP tool.

Usage:
    # Run with uvicorn
    uvicorn src.main:app --host 0.0.0.0 --port 8001

    # Or with FastMCP CLI
    fastmcp run plugins/capital414-private/src/main.py

Environment Variables:
    LANGUAGETOOL_URL: URL of LanguageTool server (default: http://languagetool:8010/v2/check)
    MCP_SERVER_NAME: Server name (default: capital414-auditor)
    MCP_SERVER_PORT: Server port (default: 8001)
"""

from __future__ import annotations

import os
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import uuid4

import structlog
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .audit_engine.policy_manager import get_policy_manager, resolve_policy
from .schemas.validation_report import ValidationReport
from .reports import generate_audit_report_pdf, generate_executive_summary, format_executive_summary_as_markdown

logger = structlog.get_logger(__name__)

# Initialize FastMCP server
mcp = FastMCP(
    name=os.getenv("MCP_SERVER_NAME", "capital414-auditor"),
    instructions="""
    Capital 414 Document Compliance Auditor.

    This MCP server validates PDF documents against COPILOTO_414 compliance policies.
    It uses 8 specialized auditors:
    - Disclaimer: Legal disclaimer presence and coverage
    - Format: Number formatting, fonts, colors
    - Typography: Font hierarchy and spacing
    - Grammar: Spelling and grammar (via LanguageTool)
    - Logo: Corporate logo detection (via OpenCV)
    - Color Palette: Brand color compliance
    - Entity Consistency: Consistent naming
    - Semantic Consistency: Document coherence

    Use the audit_document_full tool to validate a PDF file.
    """,
)


# ============================================================================
# Tool Input/Output Models
# ============================================================================


class AuditRequest(BaseModel):
    """Input parameters for audit_document_full tool."""

    file_path: str = Field(..., description="Absolute path to the PDF file to audit")
    policy_id: str = Field(default="auto", description="Policy ID (default: 'auto' for auto-detection)")
    client_name: Optional[str] = Field(None, description="Client name for disclaimer validation")
    enable_disclaimer: bool = Field(default=True, description="Enable disclaimer auditor")
    enable_format: bool = Field(default=True, description="Enable format auditor")
    enable_typography: bool = Field(default=True, description="Enable typography auditor")
    enable_grammar: bool = Field(default=True, description="Enable grammar auditor")
    enable_logo: bool = Field(default=True, description="Enable logo auditor")
    enable_color_palette: bool = Field(default=True, description="Enable color palette auditor")
    enable_entity_consistency: bool = Field(default=True, description="Enable entity consistency auditor")
    enable_semantic_consistency: bool = Field(default=True, description="Enable semantic consistency auditor")


class AuditResponse(BaseModel):
    """Output from audit_document_full tool."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="'completed' or 'error'")
    total_findings: int = Field(..., description="Total number of findings")
    findings_by_severity: Dict[str, int] = Field(..., description="Counts by severity level")
    findings_by_category: Dict[str, int] = Field(..., description="Counts by category")
    disclaimer_coverage: Optional[float] = Field(None, description="Disclaimer coverage (0.0-1.0)")
    policy_id: str = Field(..., description="Policy ID used")
    policy_name: str = Field(..., description="Policy name")
    validation_duration_ms: int = Field(..., description="Validation duration in milliseconds")
    top_findings: List[Dict[str, Any]] = Field(..., description="Top 5 most critical findings")
    executive_summary_markdown: str = Field(..., description="Executive summary in Markdown format")
    pdf_report_path: Optional[str] = Field(None, description="Path to generated PDF report")
    error_message: Optional[str] = Field(None, description="Error message if status='error'")


# ============================================================================
# MCP Tools
# ============================================================================


@mcp.tool()
async def audit_document_full(
    file_path: str,
    policy_id: str = "auto",
    client_name: Optional[str] = None,
    enable_disclaimer: bool = True,
    enable_format: bool = True,
    enable_typography: bool = True,
    enable_grammar: bool = True,
    enable_logo: bool = True,
    enable_color_palette: bool = True,
    enable_entity_consistency: bool = True,
    enable_semantic_consistency: bool = True,
) -> Dict[str, Any]:
    """
    Validate a PDF document against COPILOTO_414 compliance policies.

    This tool runs up to 8 specialized auditors on the document:
    - Disclaimer: Checks for legal disclaimers in footers
    - Format: Validates number formatting, fonts, colors
    - Typography: Checks font hierarchy and spacing
    - Grammar: Spelling and grammar validation
    - Logo: Detects corporate logo presence
    - Color Palette: Validates brand color compliance
    - Entity Consistency: Ensures consistent naming
    - Semantic Consistency: Checks document coherence

    Args:
        file_path: Absolute path to the PDF file to audit
        policy_id: Policy ID to use (default: 'auto' for auto-detection)
        client_name: Client name for disclaimer validation (optional)
        enable_*: Toggle individual auditors on/off

    Returns:
        Audit results including findings summary, severity counts, and executive summary
    """
    start_time = time.time()
    job_id = str(uuid4())

    logger.info(
        "Starting document audit",
        job_id=job_id,
        file_path=file_path,
        policy_id=policy_id,
    )

    try:
        # Validate file exists
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            return {
                "job_id": job_id,
                "status": "error",
                "error_message": f"File not found: {file_path}",
                "total_findings": 0,
                "findings_by_severity": {},
                "findings_by_category": {},
                "disclaimer_coverage": None,
                "policy_id": policy_id,
                "policy_name": "N/A",
                "validation_duration_ms": int((time.time() - start_time) * 1000),
                "top_findings": [],
                "executive_summary_markdown": f"Error: File not found: {file_path}",
                "pdf_report_path": None,
            }

        # Resolve policy
        policy_manager = get_policy_manager()
        policy_config = resolve_policy(policy_id) if policy_id != "auto" else None
        resolved_policy_id = policy_id
        resolved_policy_name = policy_config.get("name", "Auto") if policy_config else "Auto-Detection"

        # Import coordinator (lazy import to avoid circular dependencies)
        from .audit_engine.coordinator import validate_document
        from .schemas.models import DocumentInput

        # Create document input
        doc_input = DocumentInput(
            filename=pdf_path.name,
            file_path=str(pdf_path),
        )

        # Run validation
        result = await validate_document(
            document=doc_input,
            pdf_path=pdf_path,
            client_name=client_name,
            enable_disclaimer=enable_disclaimer,
            enable_format=enable_format,
            enable_typography=enable_typography,
            enable_grammar=enable_grammar,
            enable_logo=enable_logo,
            enable_color_palette=enable_color_palette,
            enable_entity_consistency=enable_entity_consistency,
            enable_semantic_consistency=enable_semantic_consistency,
            policy_config=policy_config,
            policy_id=resolved_policy_id,
            policy_name=resolved_policy_name,
        )

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Build ValidationReport for report generation
        report = ValidationReport(
            id=job_id,
            document_id=str(pdf_path),
            job_id=job_id,
            status="completed",
            client_name=client_name,
            findings=[f.model_dump() if hasattr(f, 'model_dump') else f for f in result.findings],
            summary=result.summary,
            validation_duration_ms=duration_ms,
        )

        # Generate executive summary
        exec_summary = generate_executive_summary(report)
        summary_markdown = format_executive_summary_as_markdown(
            exec_summary,
            filename=pdf_path.name,
            report_url=f"/reports/{job_id}.pdf",  # Placeholder URL
        )

        # Generate PDF report (save to temp directory)
        pdf_report_path = None
        try:
            pdf_buffer = await generate_audit_report_pdf(
                report=report,
                filename=pdf_path.name,
                document_name=pdf_path.stem,
            )
            # Save to temp file
            temp_dir = Path(tempfile.gettempdir()) / "capital414-reports"
            temp_dir.mkdir(exist_ok=True)
            pdf_report_path = str(temp_dir / f"{job_id}.pdf")
            with open(pdf_report_path, "wb") as f:
                f.write(pdf_buffer.getvalue())
            logger.info("PDF report generated", path=pdf_report_path)
        except Exception as e:
            logger.warning("Failed to generate PDF report", error=str(e))

        # Extract summary metrics
        summary = result.summary or {}
        findings_by_severity = summary.get("findings_by_severity", {})
        findings_by_category = summary.get("findings_by_category", {})

        # Get top findings
        top_findings = exec_summary.get("top_findings", [])[:5]

        logger.info(
            "Document audit completed",
            job_id=job_id,
            total_findings=len(result.findings),
            duration_ms=duration_ms,
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "total_findings": len(result.findings),
            "findings_by_severity": findings_by_severity,
            "findings_by_category": findings_by_category,
            "disclaimer_coverage": summary.get("disclaimer_coverage"),
            "policy_id": resolved_policy_id,
            "policy_name": resolved_policy_name,
            "validation_duration_ms": duration_ms,
            "top_findings": top_findings,
            "executive_summary_markdown": summary_markdown,
            "pdf_report_path": pdf_report_path,
        }

    except Exception as e:
        logger.exception("Document audit failed", job_id=job_id, error=str(e))
        return {
            "job_id": job_id,
            "status": "error",
            "error_message": str(e),
            "total_findings": 0,
            "findings_by_severity": {},
            "findings_by_category": {},
            "disclaimer_coverage": None,
            "policy_id": policy_id,
            "policy_name": "N/A",
            "validation_duration_ms": int((time.time() - start_time) * 1000),
            "top_findings": [],
            "executive_summary_markdown": f"Error during audit: {str(e)}",
            "pdf_report_path": None,
        }


@mcp.tool()
async def list_policies() -> List[Dict[str, Any]]:
    """
    List all available validation policies.

    Returns:
        List of policy configurations with id, name, and description
    """
    policy_manager = get_policy_manager()
    policies = policy_manager.list_policies()

    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "description": p.get("description"),
            "auto_detect": p.get("auto_detect", False),
        }
        for p in policies
    ]


@mcp.tool()
async def get_policy_details(policy_id: str) -> Dict[str, Any]:
    """
    Get detailed configuration for a specific policy.

    Args:
        policy_id: The policy ID to retrieve

    Returns:
        Full policy configuration including auditor settings
    """
    policy_config = resolve_policy(policy_id)
    if not policy_config:
        return {"error": f"Policy not found: {policy_id}"}
    return policy_config


# ============================================================================
# Health Check Endpoint
# ============================================================================


@mcp.resource("health://status")
async def health_check() -> str:
    """Health check resource."""
    return "OK"


# ============================================================================
# FastAPI Integration (for uvicorn)
# ============================================================================

# Create FastAPI app from FastMCP
app = mcp.get_app()


def run():
    """Entry point for running the server."""
    import uvicorn
    port = int(os.getenv("MCP_SERVER_PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
