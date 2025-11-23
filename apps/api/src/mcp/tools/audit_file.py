"""
COPILOTO_414 Document Compliance Validation Tool (Class-based Implementation).

This tool implements the COPILOTO_414 audit system, which validates PDF documents
against corporate compliance policies (disclaimers, branding, grammar, etc.).

It is designed to be loaded by the Lazy Registry or used directly by the
ToolExecutionService.
"""

from typing import Any, Dict, Optional
from pathlib import Path
import structlog

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...services.validation_coordinator import validate_document
from ...services.policy_manager import resolve_policy
from ...services.minio_storage import get_minio_storage
from ...models.document import Document, DocumentStatus

logger = structlog.get_logger(__name__)


class AuditFileTool(Tool):
    """
    COPILOTO_414 Document Compliance Validation Tool.
    
    Orchestrates the execution of multiple auditors (Disclaimer, Format, Logo, Grammar)
    via the ValidationCoordinator.
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="audit_file",
            version="1.0.0",
            display_name="Audit File (COPILOTO_414)",
            description=(
                "Validates PDF documents against COPILOTO_414 compliance policies. "
                "Performs checks for disclaimers, corporate formatting, logo usage, "
                "and grammar/spelling."
            ),
            category=ToolCategory.COMPLIANCE,
            capabilities=[
                ToolCapability.ASYNC, 
                ToolCapability.IDEMPOTENT, 
                ToolCapability.CACHEABLE
            ],
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string", 
                        "description": "Document ID to audit"
                    },
                    "policy_id": {
                        "type": "string",
                        "enum": ["auto", "414-std", "414-strict", "banamex", "afore-xxi"],
                        "default": "auto",
                        "description": "Compliance policy to apply (default: auto-detect)"
                    },
                    "enable_disclaimer": {
                        "type": "boolean", 
                        "default": True,
                        "description": "Check for required disclaimers"
                    },
                    "enable_format": {
                        "type": "boolean", 
                        "default": True,
                        "description": "Check font and color compliance"
                    },
                    "enable_logo": {
                        "type": "boolean", 
                        "default": True,
                        "description": "Check logo placement and quality"
                    },
                    "enable_grammar": {
                        "type": "boolean", 
                        "default": True,
                        "description": "Check grammar and spelling"
                    }
                },
                "required": ["doc_id"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "status": {"type": "string"},
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "severity": {"type": "string"},
                                "category": {"type": "string"},
                                "issue": {"type": "string"},
                                "page": {"type": "integer"}
                            }
                        }
                    },
                    "summary": {"type": "object"}
                }
            },
            tags=["compliance", "validation", "copiloto_414", "pdf", "audit"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 5},
            timeout_ms=120000,  # 2 minutes for full audit
            max_payload_size_kb=50,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        if "doc_id" not in payload:
            raise ValueError("Missing required field: doc_id")
        if not isinstance(payload["doc_id"], str):
            raise ValueError("doc_id must be a string")

    async def execute(self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute the audit_file tool.
        
        1. Verify document ownership and status.
        2. Resolve compliance policy.
        3. Materialize PDF from object storage.
        4. Run validation coordinator.
        5. Return structured report.
        """
        doc_id = payload["doc_id"]
        policy_id = payload.get("policy_id", "auto")
        
        # Feature flags for individual auditors
        enable_disclaimer = payload.get("enable_disclaimer", True)
        enable_format = payload.get("enable_format", True)
        enable_logo = payload.get("enable_logo", True)
        enable_grammar = payload.get("enable_grammar", True)

        # ✅ FIX: Read user_id from payload (programmatic) OR context (HTTP request)
        # Programmatic invocations pass user_id in payload, HTTP requests use context
        user_id = payload.get("user_id") or (context.get("user_id") if context else None)

        logger.info(
            "COPILOTO_414: Starting audit execution", 
            doc_id=doc_id, 
            policy_id=policy_id, 
            user_id=user_id
        )

        # 1. Fetch and validate document
        doc = await Document.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        # Validate user_id is provided (required for ownership check)
        if not user_id:
            logger.warning(
                "COPILOTO_414: No user_id provided (dev mode?)",
                doc_id=doc_id,
                context_available=bool(context)
            )
            # In production, this should raise an error
            # For now, we allow it but log the issue
        elif str(doc.user_id) != str(user_id):
            raise PermissionError(f"User {user_id} not authorized to audit document {doc_id}")
            
        # 2. Resolve Policy
        policy = await resolve_policy(policy_id, document=doc)
        logger.info("COPILOTO_414: Policy resolved", policy_name=policy.name)

        # 3. Materialize File
        minio_storage = get_minio_storage()
        pdf_path, is_temp = minio_storage.materialize_document(doc.minio_key, filename=doc.filename)

        try:
            # 4. Run Validation Coordinator
            report = await validate_document(
                document=doc,
                pdf_path=pdf_path,
                client_name=policy.client_name,
                enable_disclaimer=enable_disclaimer,
                enable_format=enable_format,
                enable_logo=enable_logo,
                enable_grammar=enable_grammar,  # Pass grammar flag if supported
                policy_config=policy.to_compliance_config(),
                policy_id=policy.id,
                policy_name=policy.name,
            )

            logger.info(
                "COPILOTO_414: Audit completed", 
                job_id=report.job_id, 
                findings_count=len(report.findings)
            )

            # 5. Construct Response
            return {
                "job_id": report.job_id,
                "status": report.status,
                "policy_used": {
                    "id": policy.id,
                    "name": policy.name
                },
                "findings": [f.model_dump() for f in report.findings],
                "summary": report.summary,
                # Return attachments if any (e.g. corrected PDF path, images)
                "attachments": report.attachments,
            }

        except Exception as e:
            logger.error("COPILOTO_414: Audit execution failed", error=str(e), doc_id=doc_id)
            raise RuntimeError(f"Audit execution failed: {str(e)}") from e
            
        finally:
            # Cleanup temp file
            if is_temp and pdf_path.exists():
                try:
                    pdf_path.unlink()
                except Exception:
                    pass