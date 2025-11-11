"""
Audit Command Handler - Client-specific message handler.

This handler is only present in client-specific branches (e.g., client/capital414).
It processes "Auditar archivo:" commands and delegates to the audit system.

Architecture:
    - Extends MessageHandler from message_handlers.py
    - Uses Chain of Responsibility pattern
    - Only included in builds with audit system enabled

Note:
    This file should NOT exist in the main/develop branches of the open-source repository.
    It's specific to clients that have the audit system feature.
"""

import time
import json
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta

import structlog

from .message_handlers import MessageHandler
from .chat_context import ChatContext, ChatProcessingResult, MessageMetadata
from ..models.document import Document, DocumentStatus
from ..models.validation_report import ValidationReport
from ..services.validation_coordinator import validate_document
from ..services.policy_manager import resolve_policy
from ..services.minio_storage import get_minio_storage
from ..services.report_generator import generate_audit_report_pdf
from ..services.summary_formatter import generate_executive_summary, format_executive_summary_as_markdown

logger = structlog.get_logger(__name__)


class AuditCommandHandler(MessageHandler):
    """
    Handler for audit commands in chat.

    Detects messages starting with "Auditar archivo:" and executes
    document validation using the COPILOTO_414 audit system.

    This handler is client-specific and only exists in branches with audit support.
    """

    AUDIT_COMMAND_PREFIX = "Auditar archivo:"

    async def can_handle(self, context: ChatContext) -> bool:
        """
        Check if message is an audit command.

        Args:
            context: ChatContext with message

        Returns:
            True if message starts with "Auditar archivo:", False otherwise
        """
        return context.message.strip().startswith(self.AUDIT_COMMAND_PREFIX)

    async def process(
        self,
        context: ChatContext,
        chat_service,
        **kwargs
    ) -> ChatProcessingResult:
        """
        Process audit command and generate validation report.

        Args:
            context: ChatContext with request data
            chat_service: ChatService instance for adding messages
            **kwargs: Additional dependencies (user_id, chat_session, user_message, etc.)

        Returns:
            ChatProcessingResult with audit report
        """
        start_time = time.time()

        logger.info(
            "Processing audit command",
            message=context.message,
            user_id=context.user_id,
            session_id=context.session_id,
            file_ids=context.document_ids
        )

        # Extract dependencies from kwargs
        user_id = kwargs.get('user_id', context.user_id)
        chat_session = kwargs.get('chat_session')
        user_message = kwargs.get('user_message')
        current_file_ids = kwargs.get('current_file_ids', context.document_ids or [])

        try:
            # Extract filename from command
            filename_from_message = context.message.replace(self.AUDIT_COMMAND_PREFIX, "").strip()

            # Find matching document from attached files
            target_doc = await self._find_target_document(filename_from_message, current_file_ids)

            if not target_doc:
                return await self._create_error_response(
                    f"No se encontró el archivo '{filename_from_message}' en los archivos adjuntos.",
                    "file_not_found",
                    chat_service,
                    chat_session,
                    context,
                    start_time,
                    user_message
                )

            # Validate document status
            if target_doc.status != DocumentStatus.READY:
                return await self._create_error_response(
                    f"El archivo '{target_doc.filename}' no está listo para auditoría. Estado actual: {target_doc.status.value}",
                    "document_not_ready",
                    chat_service,
                    chat_session,
                    context,
                    start_time,
                    user_message
                )

            # Get PDF path (materialize from MinIO if needed)
            pdf_path, temp_pdf_path = await self._get_pdf_path(target_doc)

            if not pdf_path:
                return await self._create_error_response(
                    "No se pudo recuperar el PDF para auditoría.",
                    "pdf_not_found",
                    chat_service,
                    chat_session,
                    context,
                    start_time,
                    user_message
                )

            # Execute validation
            validation_report = await self._execute_validation(
                target_doc, pdf_path, user_id, chat_session
            )

            # Generate report URL (MinIO or on-demand endpoint)
            report_url = await self._generate_report_url(validation_report, target_doc)

            # Generate executive summary
            executive_summary = generate_executive_summary(validation_report)
            formatted_summary = format_executive_summary_as_markdown(
                summary=executive_summary,
                filename=target_doc.filename,
                report_url=report_url
            )

            # Save assistant message with summary
            audit_assistant_message = await chat_service.add_assistant_message(
                chat_session=chat_session,
                content=formatted_summary,
                model=context.model,
                metadata={
                    "audit": True,
                    "document_id": str(target_doc.id),
                    "validation_report_id": str(validation_report.id),
                    "findings_count": len(validation_report.findings),
                    "report_pdf_url": report_url,
                }
            )

            # Cleanup temp PDF if created
            if temp_pdf_path and temp_pdf_path.exists():
                try:
                    temp_pdf_path.unlink()
                    logger.debug("Temporary PDF cleaned up", doc_id=str(target_doc.id))
                except Exception as cleanup_exc:
                    logger.warning("Failed to cleanup temporary PDF", error=str(cleanup_exc))

            logger.info(
                "Audit completed successfully",
                doc_id=str(target_doc.id),
                findings_count=len(validation_report.findings),
                message_id=str(audit_assistant_message.id)
            )

            # Build ChatProcessingResult
            processing_time = (time.time() - start_time) * 1000
            metadata = MessageMetadata(
                message_id=str(audit_assistant_message.id),
                chat_id=str(chat_session.id),
                user_message_id=str(user_message.id) if user_message else "",
                assistant_message_id=str(audit_assistant_message.id),
                model_used=context.model,
                tokens_used=None,
                latency_ms=int(processing_time),
                decision_metadata={
                    "audit": True,
                    "validation_report_id": str(validation_report.id),
                    "findings_count": len(validation_report.findings),
                    "report_pdf_url": report_url
                }
            )

            return ChatProcessingResult(
                content=formatted_summary,
                sanitized_content=formatted_summary,
                metadata=metadata,
                processing_time_ms=processing_time,
                strategy_used="audit_command",
                research_triggered=False,
                session_updated=False
            )

        except Exception as exc:
            logger.error(
                "Audit command failed",
                error=str(exc),
                exc_type=type(exc).__name__,
                exc_info=True
            )

            return await self._create_error_response(
                f"Error al ejecutar la auditoría: {str(exc)}",
                "audit_execution_failed",
                chat_service,
                chat_session,
                context,
                start_time,
                user_message
            )

    async def _find_target_document(self, filename: str, file_ids: list) -> Optional[Document]:
        """Find document by filename from attached files."""
        if not file_ids:
            return None

        for file_id in file_ids:
            doc = await Document.get(file_id)
            if doc and doc.filename == filename:
                return doc

        return None

    async def _get_pdf_path(self, document: Document) -> tuple[Optional[Path], Optional[Path]]:
        """Get PDF path, materializing from MinIO if needed."""
        pdf_path = Path(document.minio_key)
        temp_pdf_path = None

        if not pdf_path.exists():
            minio_storage = get_minio_storage()
            try:
                pdf_path, is_temp = minio_storage.materialize_document(
                    document.minio_key,
                    filename=document.filename,
                )
                if is_temp:
                    temp_pdf_path = pdf_path
            except Exception as storage_exc:
                logger.error(
                    "Failed to materialize PDF",
                    doc_id=str(document.id),
                    error=str(storage_exc)
                )
                return None, None

        return pdf_path, temp_pdf_path

    async def _execute_validation(
        self,
        document: Document,
        pdf_path: Path,
        user_id: str,
        chat_session
    ) -> ValidationReport:
        """Execute document validation and save report."""
        # Resolve policy
        policy = await resolve_policy("auto", document=document)

        # Run validation
        logger.info(
            "Running validation",
            doc_id=str(document.id),
            filename=document.filename,
            policy_id=policy.id
        )

        report = await validate_document(
            document=document,
            pdf_path=pdf_path,
            client_name=policy.client_name,
            enable_disclaimer=True,
            enable_format=True,
            enable_typography=True,
            enable_grammar=True,
            enable_logo=True,
            enable_color_palette=True,
            enable_entity_consistency=True,
            enable_semantic_consistency=True,
            policy_config=policy.to_compliance_config(),
            policy_id=policy.id,
            policy_name=policy.name
        )

        # Save validation report to MongoDB
        validation_report = ValidationReport(
            document_id=str(document.id),
            user_id=user_id,
            job_id=report.job_id,
            status="done" if report.status == "done" else "error",
            client_name=policy.client_name,
            auditors_enabled={
                "disclaimer": True,
                "format": True,
                "typography": True,
                "grammar": True,
                "logo": True,
                "color_palette": True,
                "entity_consistency": True,
                "semantic_consistency": True,
            },
            findings=[f.model_dump() for f in (report.findings or [])],
            summary=report.summary or {},
            attachments=report.attachments or {},
        )
        await validation_report.insert()

        # Link validation report to document
        await document.update({"$set": {
            "validation_report_id": str(validation_report.id),
            "updated_at": datetime.utcnow()
        }})

        logger.info(
            "Validation report saved",
            report_id=str(validation_report.id),
            findings_count=len(report.findings)
        )

        return validation_report

    async def _generate_report_url(self, validation_report: ValidationReport, document: Document) -> str:
        """Generate PDF report and upload to MinIO or fallback to on-demand endpoint."""
        minio_storage = get_minio_storage()

        if minio_storage:
            try:
                logger.info("Generating and uploading PDF report to MinIO", report_id=str(validation_report.id))

                # Generate full PDF report
                pdf_buffer = await generate_audit_report_pdf(
                    report=validation_report,
                    filename=document.filename,
                    document_name=document.filename
                )

                # Upload to MinIO
                report_key = f"reports/{validation_report.id}_{int(time.time())}.pdf"

                await minio_storage.upload_file(
                    bucket_name="audit-reports",
                    object_name=report_key,
                    data=pdf_buffer,
                    length=pdf_buffer.getbuffer().nbytes,
                    content_type="application/pdf"
                )

                # Get presigned URL (24h expiration)
                report_url = minio_storage.get_presigned_url(
                    object_name=report_key,
                    bucket="audit-reports",
                    expires=timedelta(hours=24)
                )

                # Save URL in ValidationReport
                validation_report.attachments = {
                    "full_report_pdf": {
                        "url": report_url,
                        "key": report_key,
                        "generated_at": datetime.utcnow().isoformat(),
                        "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                        "storage": "minio"
                    }
                }
                await validation_report.save()

                logger.info("PDF report uploaded to MinIO successfully", report_url=report_url)
                return report_url

            except Exception as pdf_exc:
                logger.error("Failed to generate/upload PDF report", error=str(pdf_exc), exc_type=type(pdf_exc).__name__)
                # Fallback to on-demand endpoint
                return f"/api/reports/audit/{validation_report.id}/download"
        else:
            # MinIO disabled - use on-demand endpoint
            report_url = f"/api/reports/audit/{validation_report.id}/download"
            logger.info("MinIO disabled, using on-demand PDF endpoint", report_url=report_url)
            return report_url

    async def _create_error_response(
        self,
        error_message: str,
        error_code: str,
        chat_service,
        chat_session,
        context: ChatContext,
        start_time: float,
        user_message
    ) -> ChatProcessingResult:
        """Create error response and save to chat."""
        logger.warning(f"Audit error: {error_code}", message=error_message)

        # Save error message
        error_assistant_message = await chat_service.add_assistant_message(
            chat_session=chat_session,
            content=error_message,
            model=context.model,
            metadata={"error": error_code}
        )

        processing_time = (time.time() - start_time) * 1000
        metadata = MessageMetadata(
            message_id=str(error_assistant_message.id),
            chat_id=str(chat_session.id),
            user_message_id=str(user_message.id) if user_message else "",
            assistant_message_id=str(error_assistant_message.id),
            model_used=context.model,
            tokens_used=None,
            latency_ms=int(processing_time),
            decision_metadata={"error": error_code}
        )

        return ChatProcessingResult(
            content=error_message,
            sanitized_content=error_message,
            metadata=metadata,
            processing_time_ms=processing_time,
            strategy_used="audit_command_error",
            research_triggered=False,
            session_updated=False
        )
