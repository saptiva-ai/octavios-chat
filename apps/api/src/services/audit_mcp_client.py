"""
MCP Client for Capital 414 Auditor Plugin.

This module provides a client wrapper to invoke the COPILOTO_414
audit system via MCP protocol. It supports:

1. Remote MCP calls to capital414-auditor service
2. Fallback to local implementation (for backward compatibility)

Usage:
    from services.audit_mcp_client import audit_document_via_mcp

    result = await audit_document_via_mcp(
        file_path="/tmp/document.pdf",
        policy_id="414-std",
        client_name="Banamex",
    )
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Configuration
MCP_AUDITOR_URL = os.getenv("CAPITAL414_AUDITOR_URL", "http://capital414-auditor:8002")
MCP_TIMEOUT = int(os.getenv("CAPITAL414_AUDITOR_TIMEOUT", "120"))  # 2 minutes
USE_MCP_AUDITOR = os.getenv("USE_MCP_AUDITOR", "false").lower() == "true"


async def audit_document_via_mcp(
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
    Audit a document via MCP protocol to capital414-auditor service.

    Args:
        file_path: Path to the PDF file
        policy_id: Policy ID (default: "auto")
        client_name: Client name for disclaimer validation
        enable_*: Toggle individual auditors

    Returns:
        Audit result dict with findings, summary, and report paths

    Raises:
        Exception: If MCP call fails and no fallback is available
    """
    if not USE_MCP_AUDITOR:
        logger.info("MCP auditor disabled, using local implementation")
        return await _fallback_local_audit(
            file_path=file_path,
            policy_id=policy_id,
            client_name=client_name,
            enable_disclaimer=enable_disclaimer,
            enable_format=enable_format,
            enable_typography=enable_typography,
            enable_grammar=enable_grammar,
            enable_logo=enable_logo,
            enable_color_palette=enable_color_palette,
            enable_entity_consistency=enable_entity_consistency,
            enable_semantic_consistency=enable_semantic_consistency,
        )

    logger.info(
        "Invoking MCP auditor",
        url=MCP_AUDITOR_URL,
        file_path=file_path,
        policy_id=policy_id,
    )

    try:
        async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
            # MCP tool call via HTTP POST to /tools/audit_document_full
            response = await client.post(
                f"{MCP_AUDITOR_URL}/tools/audit_document_full",
                json={
                    "file_path": file_path,
                    "policy_id": policy_id,
                    "client_name": client_name,
                    "enable_disclaimer": enable_disclaimer,
                    "enable_format": enable_format,
                    "enable_typography": enable_typography,
                    "enable_grammar": enable_grammar,
                    "enable_logo": enable_logo,
                    "enable_color_palette": enable_color_palette,
                    "enable_entity_consistency": enable_entity_consistency,
                    "enable_semantic_consistency": enable_semantic_consistency,
                },
            )
            response.raise_for_status()
            result = response.json()

            logger.info(
                "MCP audit completed",
                job_id=result.get("job_id"),
                total_findings=result.get("total_findings"),
            )

            return result

    except httpx.HTTPStatusError as e:
        logger.error(
            "MCP auditor HTTP error",
            status_code=e.response.status_code,
            detail=e.response.text,
        )
        # Fallback to local implementation
        return await _fallback_local_audit(
            file_path=file_path,
            policy_id=policy_id,
            client_name=client_name,
            enable_disclaimer=enable_disclaimer,
            enable_format=enable_format,
            enable_typography=enable_typography,
            enable_grammar=enable_grammar,
            enable_logo=enable_logo,
            enable_color_palette=enable_color_palette,
            enable_entity_consistency=enable_entity_consistency,
            enable_semantic_consistency=enable_semantic_consistency,
        )

    except httpx.RequestError as e:
        logger.error("MCP auditor connection error", error=str(e))
        # Fallback to local implementation
        return await _fallback_local_audit(
            file_path=file_path,
            policy_id=policy_id,
            client_name=client_name,
            enable_disclaimer=enable_disclaimer,
            enable_format=enable_format,
            enable_typography=enable_typography,
            enable_grammar=enable_grammar,
            enable_logo=enable_logo,
            enable_color_palette=enable_color_palette,
            enable_entity_consistency=enable_entity_consistency,
            enable_semantic_consistency=enable_semantic_consistency,
        )


async def _fallback_local_audit(
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
    Fallback to local audit implementation.

    This is used when:
    - USE_MCP_AUDITOR is false
    - MCP service is unavailable
    """
    logger.info("Using local audit implementation (fallback)")

    # Import local implementation
    from .validation_coordinator import validate_document
    from .policy_manager import resolve_policy
    from ..models.document import Document

    # Create a minimal Document object for the coordinator
    # Note: In the future, the coordinator should accept file_path directly
    pdf_path = Path(file_path)

    # Resolve policy
    policy_config = resolve_policy(policy_id) if policy_id != "auto" else None

    # Create a mock document (the coordinator needs it for some metadata)
    class MockDocument:
        def __init__(self, path: Path):
            self.filename = path.name
            self.id = f"local-{path.stem}"

    mock_doc = MockDocument(pdf_path)

    # Run validation
    result = await validate_document(
        document=mock_doc,
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
        policy_id=policy_id,
        policy_name=policy_config.get("name") if policy_config else "Auto",
    )

    # Convert to dict format matching MCP response
    return {
        "job_id": result.job_id,
        "status": result.status,
        "total_findings": len(result.findings),
        "findings_by_severity": result.summary.get("findings_by_severity", {}),
        "findings_by_category": result.summary.get("findings_by_category", {}),
        "disclaimer_coverage": result.summary.get("disclaimer_coverage"),
        "policy_id": policy_id,
        "policy_name": policy_config.get("name") if policy_config else "Auto",
        "validation_duration_ms": result.summary.get("validation_duration_ms", 0),
        "top_findings": [],  # TODO: Extract top findings
        "executive_summary_markdown": "",  # TODO: Generate summary
        "pdf_report_path": None,
        "findings": [f.model_dump() if hasattr(f, "model_dump") else f for f in result.findings],
        "summary": result.summary,
    }


async def check_mcp_auditor_health() -> bool:
    """
    Check if the MCP auditor service is healthy.

    Returns:
        True if service is available, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{MCP_AUDITOR_URL}/health")
            return response.status_code == 200
    except Exception:
        return False


async def list_policies_via_mcp() -> list:
    """
    List available policies from MCP auditor.

    Returns:
        List of policy configurations
    """
    if not USE_MCP_AUDITOR:
        from .policy_manager import get_policy_manager
        return get_policy_manager().list_policies()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{MCP_AUDITOR_URL}/tools/list_policies")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning("Failed to list policies via MCP", error=str(e))
        from .policy_manager import get_policy_manager
        return get_policy_manager().list_policies()
