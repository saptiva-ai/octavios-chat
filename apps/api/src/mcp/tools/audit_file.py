"""COPILOTO_414 Document Compliance Validation Tool."""

from typing import Any, Dict, Optional
from pathlib import Path
import structlog

from ..protocol import ToolSpec, ToolCategory, ToolCapability
from..tool import Tool
from ...services.validation_coordinator import validate_document
from ...services.policy_manager import resolve_policy
from ...services.minio_storage import get_minio_storage
from ...models.document import Document

logger = structlog.get_logger(__name__)


class AuditFileTool(Tool):
    """COPILOTO_414 Document Compliance Validation Tool."""

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name="audit_file",
            version="1.0.0",
            display_name="Document Compliance Auditor",
            description=(
                "Validates PDF documents against COPILOTO_414 compliance policies. "
                "Checks disclaimers, formatting, logos, and grammar."
            ),
            category=ToolCategory.COMPLIANCE,
            capabilities=[ToolCapability.ASYNC, ToolCapability.IDEMPOTENT, ToolCapability.CACHEABLE],
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID to validate"},
                    "policy_id": {
                        "type": "string",
                        "enum": ["auto", "414-std", "414-strict", "banamex", "afore-xxi"],
                        "default": "auto",
                        "description": "Compliance policy to apply",
                    },
                    "enable_disclaimer": {"type": "boolean", "default": True},
                    "enable_format": {"type": "boolean", "default": True},
                    "enable_logo": {"type": "boolean", "default": True},
                },
                "required": ["doc_id"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["done", "error"]},
                    "findings": {"type": "array"},
                    "summary": {"type": "object"},
                },
            },
            tags=["compliance", "validation", "copiloto_414", "pdf", "audit"],
            requires_auth=True,
            rate_limit={"calls_per_minute": 10},
            timeout_ms=60000,
            max_payload_size_kb=10,
        )

    async def validate_input(self, payload: Dict[str, Any]) -> None:
        if "doc_id" not in payload:
            raise ValueError("Missing required field: doc_id")
        if not isinstance(payload["doc_id"], str):
            raise ValueError("doc_id must be a string")

    async def execute(self, payload: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        doc_id = payload["doc_id"]
        policy_id = payload.get("policy_id", "auto")
        enable_disclaimer = payload.get("enable_disclaimer", True)
        enable_format = payload.get("enable_format", True)
        enable_logo = payload.get("enable_logo", True)
        user_id = context.get("user_id") if context else None

        logger.info("Audit file tool execution started", doc_id=doc_id, policy_id=policy_id, user_id=user_id)

        doc = await Document.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")

        if user_id and doc.user_id != user_id:
            raise PermissionError(f"User {user_id} not authorized to audit document {doc_id}")

        policy = await resolve_policy(policy_id, document=doc)

        minio_storage = get_minio_storage()
        pdf_path, is_temp = minio_storage.materialize_document(doc.minio_key, filename=doc.filename)

        try:
            report = await validate_document(
                document=doc,
                pdf_path=pdf_path,
                client_name=policy.client_name,
                enable_disclaimer=enable_disclaimer,
                enable_format=enable_format,
                enable_logo=enable_logo,
                policy_config=policy.to_compliance_config(),
                policy_id=policy.id,
                policy_name=policy.name,
            )

            return {
                "job_id": report.job_id,
                "status": report.status,
                "findings": [f.model_dump() for f in report.findings],
                "summary": report.summary,
                "attachments": report.attachments,
            }
        finally:
            if is_temp and pdf_path.exists():
                pdf_path.unlink()
