"""
Empty Response Handler - Centralized fallback system for empty LLM responses.

This module provides a robust fallback mechanism to ensure that the system
NEVER returns empty responses to the user. It includes contextual error messages
based on the failure scenario.

Design Philosophy:
    - Never return empty content to the UI
    - Provide actionable error messages
    - Log empty response incidents for monitoring
    - Support multiple failure scenarios
"""

from typing import Optional, Dict, Any
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class EmptyResponseScenario(Enum):
    """Scenarios that can lead to empty responses."""

    # API/Model failures
    API_NO_CHOICES = "api_no_choices"  # Response has no choices array
    API_EMPTY_CONTENT = "api_empty_content"  # Content field is empty
    API_TIMEOUT = "api_timeout"  # Request timed out
    API_ERROR = "api_error"  # API returned an error

    # Document/RAG failures
    DOCS_PROCESSING = "docs_processing"  # Documents still being processed
    DOCS_NOT_FOUND = "docs_not_found"  # Documents not accessible
    DOCS_EMPTY = "docs_empty"  # Documents have no extractable content

    # Stream failures
    STREAM_INTERRUPTED = "stream_interrupted"  # Stream was interrupted
    STREAM_NO_CHUNKS = "stream_no_chunks"  # Stream produced no chunks

    # Generic
    UNKNOWN = "unknown"  # Unknown reason


class EmptyResponseHandler:
    """
    Handles empty response scenarios with contextual fallback messages.

    This class provides a centralized way to generate user-friendly error
    messages when the LLM fails to produce content.
    """

    # Default fallback messages by scenario
    FALLBACK_MESSAGES = {
        EmptyResponseScenario.API_NO_CHOICES: (
            "❌ **Error de conexión con el modelo de IA**\n\n"
            "El servidor no pudo obtener una respuesta del modelo. Esto puede deberse a:\n"
            "- Sobrecarga temporal del servicio\n"
            "- Problema de conectividad con la API\n\n"
            "**Solución**: Intenta nuevamente en unos segundos. Si el problema persiste, "
            "contacta al equipo de soporte."
        ),

        EmptyResponseScenario.API_EMPTY_CONTENT: (
            "❌ **El modelo no generó contenido**\n\n"
            "El modelo de IA procesó tu solicitud pero no generó una respuesta. "
            "Esto puede ocurrir cuando:\n"
            "- El prompt es ambiguo o demasiado corto\n"
            "- El modelo aplicó un filtro de seguridad\n"
            "- Hay un problema con la configuración del modelo\n\n"
            "**Solución**: Intenta reformular tu pregunta con más detalles."
        ),

        EmptyResponseScenario.API_TIMEOUT: (
            "⏱️ **Tiempo de espera agotado**\n\n"
            "La solicitud tardó demasiado tiempo y se canceló automáticamente. "
            "Esto puede deberse a:\n"
            "- Documentos muy grandes adjuntos\n"
            "- Pregunta muy compleja que requiere mucho procesamiento\n"
            "- Sobrecarga del servidor\n\n"
            "**Solución**: Intenta con documentos más pequeños o simplifica la pregunta."
        ),

        EmptyResponseScenario.API_ERROR: (
            "❌ **Error en el servicio de IA**\n\n"
            "Ocurrió un error al procesar tu solicitud. El equipo técnico ha sido notificado.\n\n"
            "**Solución**: Intenta nuevamente en unos momentos. Si el error persiste, "
            "contacta al equipo de soporte con el ID de esta conversación."
        ),

        EmptyResponseScenario.DOCS_PROCESSING: (
            "⏳ **Documentos en procesamiento**\n\n"
            "Los documentos adjuntos aún se están procesando. Este proceso puede tomar "
            "entre 10 segundos y 2 minutos dependiendo del tamaño.\n\n"
            "**Solución**: Espera unos segundos y vuelve a intentar. Verás una notificación "
            "cuando los documentos estén listos."
        ),

        EmptyResponseScenario.DOCS_NOT_FOUND: (
            "📄 **Documentos no encontrados**\n\n"
            "No se pudieron acceder a los documentos adjuntos. Esto puede deberse a:\n"
            "- Los documentos expiraron (TTL de 1 hora)\n"
            "- Error en el sistema de almacenamiento\n"
            "- Problema de permisos\n\n"
            "**Solución**: Vuelve a subir los documentos e intenta nuevamente."
        ),

        EmptyResponseScenario.DOCS_EMPTY: (
            "📄 **Documentos sin contenido extraíble**\n\n"
            "Los documentos adjuntos no contienen texto que pueda ser analizado. "
            "Esto ocurre con:\n"
            "- PDFs escaneados sin OCR\n"
            "- Imágenes de baja calidad\n"
            "- Archivos corruptos\n\n"
            "**Solución**: Asegúrate de que los documentos contengan texto legible o "
            "usa PDFs con texto seleccionable."
        ),

        EmptyResponseScenario.STREAM_INTERRUPTED: (
            "⚠️ **Conexión interrumpida**\n\n"
            "La conexión con el servidor se interrumpió antes de completar la respuesta.\n\n"
            "**Solución**: Verifica tu conexión a internet e intenta nuevamente."
        ),

        EmptyResponseScenario.STREAM_NO_CHUNKS: (
            "❌ **Sin respuesta del modelo**\n\n"
            "El modelo de IA no generó ningún contenido. Esto es inusual y puede indicar "
            "un problema técnico.\n\n"
            "**Solución**: Intenta nuevamente. Si el problema persiste, contacta al "
            "equipo de soporte."
        ),

        EmptyResponseScenario.UNKNOWN: (
            "❌ **Error inesperado**\n\n"
            "Ocurrió un error inesperado al procesar tu solicitud. El equipo técnico "
            "ha sido notificado.\n\n"
            "**Solución**: Intenta nuevamente en unos momentos. Si el error persiste, "
            "contacta al equipo de soporte con el ID de esta conversación."
        ),
    }

    @staticmethod
    def get_fallback_message(
        scenario: EmptyResponseScenario = EmptyResponseScenario.UNKNOWN,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get a contextual fallback message for an empty response scenario.

        Args:
            scenario: The scenario that caused the empty response
            context: Optional context dict with additional info (user_id, chat_id, etc.)

        Returns:
            A user-friendly error message with actionable guidance

        Example:
            >>> handler = EmptyResponseHandler()
            >>> message = handler.get_fallback_message(
            ...     scenario=EmptyResponseScenario.DOCS_PROCESSING,
            ...     context={"file_count": 2}
            ... )
            >>> print(message)
            ⏳ **Documentos en procesamiento**
            ...
        """
        base_message = EmptyResponseHandler.FALLBACK_MESSAGES.get(
            scenario,
            EmptyResponseHandler.FALLBACK_MESSAGES[EmptyResponseScenario.UNKNOWN]
        )

        # Log the empty response incident
        logger.warning(
            "Empty response detected - using fallback message",
            scenario=scenario.value,
            context=context or {},
            fallback_length=len(base_message)
        )

        # Add context-specific information if available
        if context:
            context_info = []

            if "file_count" in context:
                context_info.append(f"📎 Archivos adjuntos: {context['file_count']}")

            if "model" in context:
                context_info.append(f"🤖 Modelo usado: {context['model']}")

            if "error_detail" in context:
                context_info.append(f"💬 Detalle técnico: {context['error_detail']}")

            if context_info:
                base_message += "\n\n---\n\n" + "\n".join(context_info)

        return base_message

    @staticmethod
    def ensure_non_empty(
        content: Optional[str],
        scenario: EmptyResponseScenario = EmptyResponseScenario.UNKNOWN,
        context: Optional[Dict[str, Any]] = None,
        min_length: int = 1
    ) -> str:
        """
        Ensure content is non-empty, replacing with fallback if needed.

        This is the main method to use throughout the codebase. It guarantees
        that the returned string is never empty.

        Args:
            content: The content to validate
            scenario: The scenario if content is empty
            context: Optional context for better error messages
            min_length: Minimum acceptable length (default: 1)

        Returns:
            Either the original content (if non-empty) or a fallback message

        Example:
            >>> content = ""  # Empty response from API
            >>> safe_content = EmptyResponseHandler.ensure_non_empty(
            ...     content=content,
            ...     scenario=EmptyResponseScenario.API_EMPTY_CONTENT,
            ...     context={"model": "Saptiva Turbo"}
            ... )
            >>> assert len(safe_content) > 0  # Guaranteed non-empty
        """
        # Check if content is None, empty, or too short
        if not content or len(content.strip()) < min_length:
            logger.error(
                "CRITICAL: Empty or insufficient content detected",
                content_length=len(content) if content else 0,
                scenario=scenario.value,
                context=context or {},
                min_length=min_length
            )

            return EmptyResponseHandler.get_fallback_message(scenario, context)

        return content

    @staticmethod
    def log_empty_response_incident(
        scenario: EmptyResponseScenario,
        context: Dict[str, Any],
        stack_trace: Optional[str] = None
    ):
        """
        Log an empty response incident for monitoring and alerting.

        This method should be called whenever an empty response is detected
        to help track the frequency and causes of these incidents.

        Args:
            scenario: The scenario that caused the empty response
            context: Full context dict (user_id, chat_id, model, etc.)
            stack_trace: Optional stack trace if an exception occurred
        """
        logger.error(
            "🚨 EMPTY RESPONSE INCIDENT",
            scenario=scenario.value,
            user_id=context.get("user_id", "unknown"),
            chat_id=context.get("chat_id", "unknown"),
            session_id=context.get("session_id", "unknown"),
            model=context.get("model", "unknown"),
            has_documents=context.get("has_documents", False),
            document_count=context.get("document_count", 0),
            stream_mode=context.get("stream_mode", False),
            error_type=context.get("error_type"),
            error_message=context.get("error_message"),
            stack_trace=stack_trace
        )


# Convenience functions for common scenarios

def ensure_non_empty_content(
    content: Optional[str],
    scenario: EmptyResponseScenario = EmptyResponseScenario.UNKNOWN,
    **context_kwargs
) -> str:
    """
    Convenience function to ensure content is non-empty.

    Example:
        >>> from services.empty_response_handler import ensure_non_empty_content, EmptyResponseScenario
        >>> content = api_response.get("content")
        >>> safe_content = ensure_non_empty_content(
        ...     content,
        ...     scenario=EmptyResponseScenario.API_EMPTY_CONTENT,
        ...     model="Saptiva Turbo"
        ... )
    """
    return EmptyResponseHandler.ensure_non_empty(content, scenario, context_kwargs)


def get_docs_processing_message(file_count: int = 0) -> str:
    """Get message for documents still processing."""
    return EmptyResponseHandler.get_fallback_message(
        EmptyResponseScenario.DOCS_PROCESSING,
        {"file_count": file_count}
    )


def get_api_error_message(error_detail: str = "") -> str:
    """Get message for API errors."""
    return EmptyResponseHandler.get_fallback_message(
        EmptyResponseScenario.API_ERROR,
        {"error_detail": error_detail} if error_detail else None
    )
