"""
Document Audit Document Compliance Validation Tool (Class-based Implementation).

This tool implements the Document Audit audit system, which validates PDF documents
against corporate compliance policies (disclaimers, branding, grammar, etc.).

It is designed to be loaded by the Lazy Registry or used directly by the
ToolExecutionService.
"""

from typing import Any, Dict, Optional, Union
from pathlib import Path
import structlog
from pydantic import BaseModel, Field

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from ..tool import Tool
from ...services.validation_coordinator import validate_document
from ...services.policy_manager import resolve_policy
from ...services.minio_storage import get_minio_storage
from ...services.minio_service import minio_service
from ...models.document import Document, DocumentStatus

logger = structlog.get_logger(__name__)


class AuditInput(BaseModel):
    doc_id: str = Field(..., description="ID del documento a auditar")
    user_id: str = Field(..., description="ID del usuario propietario (obligatorio)")
    policy_id: str = Field("auto", description="ID de la política")
    enable_disclaimer: bool = Field(True, description="Activar auditor de disclaimers")
    enable_format: bool = Field(True, description="Activar auditor de formato")
    enable_logo: bool = Field(True, description="Activar auditor de logos")
    enable_grammar: bool = Field(True, description="Activar auditor de gramática")


class AuditFileTool(Tool):
    """
    Document Audit Document Compliance Validation Tool.
    
    Orchestrates the execution of multiple auditors (Disclaimer, Format, Logo, Grammar)
    via the ValidationCoordinator.
    """

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="audit_file",
            version="1.0.0",
            display_name="Audit File (Document Audit)",
            description=(
                "Validates PDF documents against Document Audit compliance policies. "
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
            tags=["compliance", "validation", "document_audit", "pdf", "audit"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 5},
            timeout_ms=120000,  # 2 minutes for full audit
            max_payload_size_kb=50,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        # Validación mínima; Pydantic hará la validación completa en execute
        if "doc_id" not in payload:
            raise ValueError("Missing required field: doc_id")

    async def execute(
        self,
        payload: Union[Dict[str, Any], AuditInput, None] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute the audit_file tool.
        
        1. Verify document ownership and status.
        2. Resolve compliance policy.
        3. Materialize PDF from object storage.
        4. Run validation coordinator.
        5. Return structured report.
        """
        # Normalize payload into Pydantic DTO (supports dict, AuditInput or kwargs)
        base_payload: Dict[str, Any] = payload or {}
        if kwargs:
            base_payload = {**base_payload, **kwargs}
        input_data = payload if isinstance(payload, AuditInput) else AuditInput(**base_payload)

        # 🕵️ SPY LOG: capture raw inputs as soon as execute starts
        logger.info(
            "🕵️ [AUDIT TOOL START]",
            doc_id=input_data.doc_id,
            user_id=input_data.user_id,
            context_keys=list(context.keys()) if context else "None",
        )

        doc_id = input_data.doc_id
        policy_id = input_data.policy_id
        enable_disclaimer = input_data.enable_disclaimer
        enable_format = input_data.enable_format
        enable_logo = input_data.enable_logo
        enable_grammar = input_data.enable_grammar

        # Programmatic invocations pass user_id en payload (obligatorio)
        user_id = input_data.user_id or (context.get("user_id") if context else None)

        logger.info(
            "Document Audit: Starting audit execution", 
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
                "Document Audit: No user_id provided (dev mode?)",
                doc_id=doc_id,
                context_available=bool(context)
            )
            # In production, this should raise an error
            # For now, we allow it but log the issue
        elif str(doc.user_id) != str(user_id):
            logger.warning(
                "Permission denied: Doc Owner mismatch",
                doc_owner=str(doc.user_id),
                doc_owner_type=str(type(doc.user_id)),
                req_user=str(user_id),
                req_user_type=str(type(user_id))
            )
            raise PermissionError(f"User {user_id} not authorized to audit document {doc_id}")

        # Database Latency Handling:
        # We trust user ownership over conversation consistency due to eventual consistency in replicas.
        # If the doc.conversation_id hasn't updated yet, we warn but proceed if user owns the file.
        session_id = context.get("session_id") if context else None
        if session_id and doc.conversation_id and str(doc.conversation_id) != str(session_id):
            logger.warning(
                "Document Audit: Database latency detected - conversation_id mismatch (allowing access)",
                doc_id=doc_id,
                doc_conversation_id=str(doc.conversation_id),
                current_session_id=str(session_id)
            )
            
        # 2. Resolve Policy
        policy = await resolve_policy(policy_id, document=doc)
        logger.info("Document Audit: Policy resolved", policy_name=policy.name)

        # 3. Materialize File
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            pdf_path = Path(temp_file.name)
        is_temp = True

        logger.info(
            "⬇️ Downloading file from MinIO",
            bucket=doc.minio_bucket,
            key=doc.minio_key
        )

        await minio_service.download_to_path(
            doc.minio_bucket,
            doc.minio_key,
            str(pdf_path)
        )

        logger.info("🔍 [AUDIT] File downloaded. Starting validation...")

        try:
            report = await validate_document(
                document=doc,
                pdf_path=pdf_path,
                client_name=policy.client_name,
                enable_disclaimer=enable_disclaimer,
                enable_format=enable_format,
                enable_logo=enable_logo,
                enable_grammar=enable_grammar,
                policy_config=policy.to_compliance_config(),
                policy_id=policy.id,
                policy_name=policy.name,
            )

            logger.info(
                "✅ [AUDIT] Validation success",
                job_id=report.job_id,
                findings_count=len(report.findings),
                summary_keys=list(report.summary.keys()) if getattr(report, "summary", None) else "None"
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
                "attachments": report.attachments,
                "validation_report_id": str(report.job_id)
            }

        except Exception as e:
            logger.error("🚨 [AUDIT CRASH] Error during processing logic", error=str(e), doc_id=doc_id)
            raise
        finally:
            if is_temp and pdf_path.exists():
                try:
                    pdf_path.unlink()
                except Exception:
                    pass
