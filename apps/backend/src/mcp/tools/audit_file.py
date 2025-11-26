"""
COPILOTO_414 Document Compliance Validation Tool (MCP Client Wrapper).

This tool implements the COPILOTO_414 audit system by delegating to the
capital414-auditor MCP microservice. The audit logic has been extracted
to plugins/capital414-private.

It validates PDF documents against corporate compliance policies using
8 specialized auditors:
1. Disclaimer - Legal disclaimer validation
2. Format - Font and number format compliance
3. Typography - Typography consistency checks
4. Grammar - Spelling and grammar validation
5. Logo - Logo detection and placement
6. Color Palette - Color palette compliance
7. Entity Consistency - Entity consistency validation
8. Semantic Consistency - Semantic coherence analysis
"""

from typing import Any, Dict, Optional
from pathlib import Path
import structlog
from pydantic import BaseModel, Field
from datetime import datetime

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...services.audit_mcp_client import (
    audit_document_via_mcp,
    MCPAuditorUnavailableError,
)
from ...services.minio_storage import get_minio_storage
from ...models.document import Document, DocumentStatus
from ...models.validation_report import ValidationReport

logger = structlog.get_logger(__name__)


class AuditInput(BaseModel):
    doc_id: str = Field(..., description="ID del documento a auditar")
    user_id: str = Field(..., description="ID del usuario propietario (obligatorio)")
    policy_id: str = Field("auto", description="ID de la política")
    enable_disclaimer: bool = Field(True, description="Activar auditor de disclaimers")
    enable_format: bool = Field(True, description="Activar auditor de formato")
    enable_typography: bool = Field(True, description="Activar auditor de tipografías")
    enable_grammar: bool = Field(True, description="Activar auditor de gramática")
    enable_logo: bool = Field(True, description="Activar auditor de logos")
    enable_color_palette: bool = Field(
        True, description="Activar auditor de paleta de colores"
    )
    enable_entity_consistency: bool = Field(
        True, description="Activar auditor de consistencia de entidades"
    )
    enable_semantic_consistency: bool = Field(
        True, description="Activar auditor de consistencia semántica"
    )


class AuditFileTool(Tool):
    """
    COPILOTO_414 Document Compliance Validation Tool.

    Delegates to the capital414-auditor MCP microservice which orchestrates
    8 specialized auditors:
    1. Disclaimer - Legal disclaimer validation
    2. Format - Font and number format compliance
    3. Typography - Typography consistency checks
    4. Grammar - Spelling and grammar validation
    5. Logo - Logo detection and placement
    6. Color Palette - Color palette compliance
    7. Entity Consistency - Entity consistency validation
    8. Semantic Consistency - Semantic coherence analysis
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="audit_file",
            version="2.0.0",
            display_name="Audit File (COPILOTO_414)",
            description=(
                "Validates PDF documents against COPILOTO_414 compliance policies. "
                "Delegates to capital414-auditor MCP microservice which performs "
                "8 specialized checks: disclaimers, format validation, "
                "typography consistency, grammar/spelling, logo detection, "
                "color palette compliance, entity consistency, and semantic coherence."
            ),
            category=ToolCategory.COMPLIANCE,
            capabilities=[
                ToolCapability.ASYNC,
                ToolCapability.IDEMPOTENT,
                ToolCapability.CACHEABLE,
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID to audit"},
                    "policy_id": {
                        "type": "string",
                        "enum": ["auto", "414-std", "414-strict", "banamex", "afore-xxi"],
                        "default": "auto",
                        "description": "Compliance policy to apply (default: auto-detect)",
                    },
                    "enable_disclaimer": {
                        "type": "boolean",
                        "default": True,
                        "description": "Check for required disclaimers",
                    },
                    "enable_format": {
                        "type": "boolean",
                        "default": True,
                        "description": "Validate number formats and fonts",
                    },
                    "enable_typography": {
                        "type": "boolean",
                        "default": True,
                        "description": "Check typography consistency",
                    },
                    "enable_grammar": {
                        "type": "boolean",
                        "default": True,
                        "description": "Check spelling and grammar",
                    },
                    "enable_logo": {
                        "type": "boolean",
                        "default": True,
                        "description": "Detect and validate logo placement",
                    },
                    "enable_color_palette": {
                        "type": "boolean",
                        "default": True,
                        "description": "Validate color palette compliance",
                    },
                    "enable_entity_consistency": {
                        "type": "boolean",
                        "default": True,
                        "description": "Check entity naming consistency",
                    },
                    "enable_semantic_consistency": {
                        "type": "boolean",
                        "default": True,
                        "description": "Validate semantic coherence",
                    },
                },
                "required": ["doc_id"],
            },
            example_invocations=[
                {"doc_id": "doc-123", "policy_id": "auto"},
                {
                    "doc_id": "doc-456",
                    "policy_id": "banamex",
                    "enable_grammar": False,
                },
            ],
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute the audit via MCP client to capital414-auditor microservice.

        Args:
            arguments: Tool arguments including doc_id and auditor flags
            context: Optional execution context with user_id

        Returns:
            Audit results with findings, summary, and optional PDF report path
        """
        # Extract arguments
        doc_id = arguments.get("doc_id")
        user_id = arguments.get("user_id") or (context or {}).get("user_id")
        policy_id = arguments.get("policy_id", "auto")

        if not doc_id:
            return {"error": "doc_id is required", "status": "error"}

        if not user_id:
            return {"error": "user_id is required", "status": "error"}

        logger.info(
            "AuditFileTool executing via MCP",
            doc_id=doc_id,
            user_id=user_id,
            policy_id=policy_id,
        )

        try:
            # Fetch document from MongoDB
            document = await Document.get(doc_id)

            if not document:
                return {
                    "error": f"Document not found: {doc_id}",
                    "status": "error",
                }

            # Verify ownership
            if document.user_id != user_id:
                return {
                    "error": "Access denied: document belongs to another user",
                    "status": "error",
                }

            # Check document status
            if document.status != DocumentStatus.READY:
                return {
                    "error": f"Document not ready: status is {document.status}",
                    "status": "error",
                }

            # Materialize PDF if needed
            pdf_path = Path(document.minio_key)
            is_temp = False

            if not pdf_path.exists():
                minio_storage = get_minio_storage()
                if minio_storage:
                    pdf_path, is_temp = minio_storage.materialize_document(
                        document.minio_key,
                        filename=document.filename,
                        bucket=document.minio_bucket,
                    )
                else:
                    return {
                        "error": "Storage unavailable - cannot access document file",
                        "status": "error",
                    }

            # Call MCP auditor microservice
            result = await audit_document_via_mcp(
                file_path=str(pdf_path),
                policy_id=policy_id,
                client_name=None,  # Auto-detected from policy
                enable_disclaimer=arguments.get("enable_disclaimer", True),
                enable_format=arguments.get("enable_format", True),
                enable_typography=arguments.get("enable_typography", True),
                enable_grammar=arguments.get("enable_grammar", True),
                enable_logo=arguments.get("enable_logo", True),
                enable_color_palette=arguments.get("enable_color_palette", True),
                enable_entity_consistency=arguments.get("enable_entity_consistency", True),
                enable_semantic_consistency=arguments.get("enable_semantic_consistency", True),
            )

            # Save ValidationReport to MongoDB
            try:
                validation_report = ValidationReport(
                    document_id=doc_id,
                    user_id=user_id,
                    job_id=result.get("job_id"),
                    status=result.get("status", "done"),
                    client_name=result.get("policy_name"),
                    auditors_enabled={
                        "disclaimer": arguments.get("enable_disclaimer", True),
                        "format": arguments.get("enable_format", True),
                        "typography": arguments.get("enable_typography", True),
                        "grammar": arguments.get("enable_grammar", True),
                        "logo": arguments.get("enable_logo", True),
                        "color_palette": arguments.get("enable_color_palette", True),
                        "entity_consistency": arguments.get("enable_entity_consistency", True),
                        "semantic_consistency": arguments.get("enable_semantic_consistency", True),
                    },
                    findings=result.get("top_findings", []),
                    summary={
                        "total_findings": result.get("total_findings", 0),
                        "findings_by_severity": result.get("findings_by_severity", {}),
                        "findings_by_category": result.get("findings_by_category", {}),
                        "disclaimer_coverage": result.get("disclaimer_coverage"),
                        "policy_id": result.get("policy_id"),
                        "policy_name": result.get("policy_name"),
                        "validation_duration_ms": result.get("validation_duration_ms"),
                    },
                    attachments={
                        "pdf_report_path": result.get("pdf_report_path"),
                    } if result.get("pdf_report_path") else {},
                )
                await validation_report.insert()

                # Update document with link to validation report
                document.validation_report_id = str(validation_report.id)
                await document.save()

                logger.info(
                    "ValidationReport saved via MCP audit",
                    report_id=str(validation_report.id),
                    doc_id=doc_id,
                    total_findings=result.get("total_findings", 0),
                )

                # Add report ID to result
                result["validation_report_id"] = str(validation_report.id)

            except Exception as save_exc:
                logger.warning(
                    "Failed to save ValidationReport (audit still succeeded)",
                    error=str(save_exc),
                    exc_type=type(save_exc).__name__,
                )

            # Clean up temp file
            if is_temp and pdf_path.exists():
                try:
                    pdf_path.unlink()
                except Exception:
                    pass

            logger.info(
                "AuditFileTool completed via MCP",
                doc_id=doc_id,
                job_id=result.get("job_id"),
                total_findings=result.get("total_findings", 0),
            )

            return result

        except MCPAuditorUnavailableError as mcp_err:
            logger.error(
                "MCP auditor unavailable",
                error=str(mcp_err),
                doc_id=doc_id,
            )
            return {
                "error": f"Audit service unavailable: {str(mcp_err)}",
                "status": "error",
            }

        except Exception as e:
            logger.exception(
                "AuditFileTool execution failed",
                error=str(e),
                exc_type=type(e).__name__,
                doc_id=doc_id,
            )
            return {
                "error": f"Audit failed: {str(e)}",
                "status": "error",
            }
