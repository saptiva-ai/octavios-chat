"""MCP adapter over the legacy audit_file tool."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field

from backend.mcp.base import BaseTool, ToolExecutionError
from backend.mcp.protocol import ToolLimits
from backend.mcp._logging import get_logger

from apps.api.src.services.tools.audit_file_tool import execute_audit_file_tool

logger = get_logger(__name__)


class AuditFileInput(BaseModel):
    doc_id: str = Field(..., description="Document identifier to audit")
    chat_id: str = Field(..., description="Chat session that will receive the audit message")
    policy_id: str = Field(default="auto", description="Policy identifier or 'auto'")
    enable_disclaimer: bool = True
    enable_format: bool = True
    enable_grammar: bool = True
    enable_logo: bool = True


class AuditFileOutput(BaseModel):
    job_id: str
    message_id: str
    validation_report_id: str
    policy_used: str
    total_findings: int
    duration_ms: int
    status: str = Field(default="completed")


class AuditFileTool(BaseTool):
    """Adapter that reuses the existing validation coordinator."""

    name = "audit_file"
    version = "v1"
    description = "Audita un documento PDF y publica el reporte en el chat."
    capabilities = ("documents", "compliance", "chat-response")
    input_model = AuditFileInput
    output_model = AuditFileOutput
    limits = ToolLimits(timeout_ms=180_000, max_payload_kb=8, max_attachment_mb=60)

    async def _execute(self, payload: AuditFileInput, context) -> Dict[str, str]:
        if not context.user_id:
            raise ToolExecutionError(
                "Authenticated user required for audit",
                code="unauthorized",
                retryable=False,
            )

        logger.info(
            "Executing audit_file tool via MCP",
            doc_id=payload.doc_id,
            chat_id=payload.chat_id,
            policy_id=payload.policy_id,
            user_id=context.user_id,
            request_id=context.request_id,
        )

        result = await execute_audit_file_tool(
            doc_id=payload.doc_id,
            user_id=context.user_id,
            chat_id=payload.chat_id,
            policy_id=payload.policy_id,
            enable_disclaimer=payload.enable_disclaimer,
            enable_format=payload.enable_format,
            enable_grammar=payload.enable_grammar,
            enable_logo=payload.enable_logo,
        )

        if not result.get("success"):
            raise ToolExecutionError(
                result.get("error", "Audit failed"),
                code="audit_failed",
                retryable=False,
                details={"job_id": result.get("job_id")},
            )

        response = AuditFileOutput(
            job_id=result["job_id"],
            message_id=result["message_id"],
            validation_report_id=result["validation_report_id"],
            policy_used=result.get("policy_used", payload.policy_id),
            total_findings=result.get("total_findings", 0),
            duration_ms=result.get("duration_ms", 0),
        )

        return response.model_dump()
