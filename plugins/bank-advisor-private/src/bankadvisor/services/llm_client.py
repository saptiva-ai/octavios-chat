"""
LLM Client for NL2SQL - SAPTIVA Integration

Provides SQL generation capabilities using SAPTIVA's LLM models.
Integrates with the existing SaptivaClient from the main backend.

Architecture:
    - Reuses SaptivaClient from apps/backend
    - Specialized prompts for SQL generation
    - Retry logic and error handling
"""

import os
import sys
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


class SaptivaLlmClient:
    """
    SAPTIVA LLM client for SQL generation.

    Wraps the main backend's SaptivaClient with SQL-specific prompts.
    """

    def __init__(self, model: str = "SAPTIVA_TURBO", temperature: float = 0.0):
        """
        Initialize SAPTIVA LLM client.

        Args:
            model: SAPTIVA model to use (CORTEX, TURBO, etc.)
            temperature: Sampling temperature (0.0 = deterministic)
        """
        self.model = model
        self.temperature = temperature
        self._saptiva_client = None

        logger.info(
            "llm_client.saptiva.initializing",
            model=model,
            temperature=temperature
        )

        # Import SaptivaClient from main backend
        try:
            # Add backend to path if not already there
            backend_path = os.environ.get(
                "BACKEND_SRC_PATH",
                "/home/jazielflo/Proyects/octavios-chat-bajaware_invex/apps/backend/src"
            )

            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)

            from services.saptiva_client import SaptivaClient, SaptivaMessage, SaptivaRequest

            self._saptiva_client = SaptivaClient()
            self._SaptivaMessage = SaptivaMessage
            self._SaptivaRequest = SaptivaRequest

            logger.info(
                "llm_client.saptiva.initialized",
                model=model,
                api_key_configured=bool(self._saptiva_client.api_key)
            )

        except ImportError as e:
            logger.error(
                "llm_client.saptiva.import_failed",
                error=str(e),
                message="Could not import SaptivaClient from main backend"
            )
            raise

    async def generate_sql(
        self,
        user_query: str,
        query_spec: Dict[str, Any],
        rag_context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Generate SQL using SAPTIVA LLM.

        Args:
            user_query: Original natural language query
            query_spec: Structured QuerySpec as dict
            rag_context: RAG context (schema, metrics, examples)

        Returns:
            SQL string or None if generation fails
        """
        if not self._saptiva_client:
            logger.error("llm_client.saptiva.not_initialized")
            return None

        try:
            # Build prompt
            prompt = self._build_sql_prompt(user_query, query_spec, rag_context)

            logger.debug(
                "llm_client.saptiva.calling",
                model=self.model,
                prompt_length=len(prompt)
            )

            # Create SAPTIVA request
            request = self._SaptivaRequest(
                model=self.model,
                messages=[
                    self._SaptivaMessage(
                        role="system",
                        content="Eres un experto en SQL para PostgreSQL. Generas consultas SQL seguras y eficientes basadas en esquemas y requerimientos proporcionados."
                    ),
                    self._SaptivaMessage(
                        role="user",
                        content=prompt
                    )
                ],
                temperature=self.temperature,
                max_tokens=800,
                stream=False  # No streaming for SQL generation
            )

            # Call SAPTIVA API
            response = await self._saptiva_client.create_completion(request)

            # Extract SQL from response
            if not response.choices or len(response.choices) == 0:
                logger.warning("llm_client.saptiva.no_choices")
                return None

            content = response.choices[0].get("message", {}).get("content", "")

            if not content:
                logger.warning("llm_client.saptiva.empty_content")
                return None

            sql = content.strip()

            # Extract SQL if wrapped in markdown
            if "```sql" in sql:
                sql = sql.split("```sql")[1].split("```")[0].strip()
            elif "```" in sql:
                sql = sql.split("```")[1].split("```")[0].strip()

            logger.info(
                "llm_client.saptiva.success",
                sql_length=len(sql),
                model=self.model
            )

            return sql

        except Exception as e:
            logger.error(
                "llm_client.saptiva.failed",
                error=str(e),
                exc_info=True
            )
            return None

    def _build_sql_prompt(
        self,
        user_query: str,
        query_spec: Dict[str, Any],
        rag_context: Dict[str, Any]
    ) -> str:
        """
        Build SQL generation prompt for SAPTIVA.

        Returns:
            Formatted prompt string
        """
        prompt_parts = []

        # Header
        prompt_parts.append("# Tarea: Generar consulta SQL para PostgreSQL")
        prompt_parts.append("")

        # User query
        prompt_parts.append(f"**Consulta del usuario:** {user_query}")
        prompt_parts.append("")

        # Parsed specification
        prompt_parts.append("**Especificación estructurada:**")
        prompt_parts.append(f"- Métrica: {query_spec.get('metric')}")

        bank_names = query_spec.get('bank_names', [])
        if bank_names:
            prompt_parts.append(f"- Bancos: {', '.join(bank_names)}")

        time_range = query_spec.get('time_range', {})
        prompt_parts.append(f"- Rango temporal: {time_range.get('type')}")
        if time_range.get('n'):
            prompt_parts.append(f"  - Cantidad: {time_range.get('n')}")
        if time_range.get('start_date'):
            prompt_parts.append(f"  - Desde: {time_range.get('start_date')}")
        if time_range.get('end_date'):
            prompt_parts.append(f"  - Hasta: {time_range.get('end_date')}")

        prompt_parts.append("")

        # Schema context
        schema_snippets = rag_context.get('schema_snippets', [])
        if schema_snippets:
            prompt_parts.append("**Columnas disponibles:**")
            for snippet in schema_snippets[:5]:
                col_name = snippet.get('column_name')
                col_desc = snippet.get('description', '')
                prompt_parts.append(f"- `{col_name}`: {col_desc}")
            prompt_parts.append("")

        # Metric definitions
        metric_defs = rag_context.get('metric_definitions', [])
        if metric_defs:
            prompt_parts.append("**Definiciones de métricas:**")
            for defn in metric_defs[:3]:
                metric_name = defn.get('metric_name')
                metric_desc = defn.get('description', '')
                preferred_cols = defn.get('preferred_columns', [])
                prompt_parts.append(f"- **{metric_name}**: {metric_desc}")
                if preferred_cols:
                    prompt_parts.append(f"  - Columnas: {', '.join(preferred_cols)}")
            prompt_parts.append("")

        # Example queries
        examples = rag_context.get('example_queries', [])
        if examples:
            prompt_parts.append("**Ejemplos de consultas similares:**")
            for i, example in enumerate(examples[:2], 1):
                nl_query = example.get('natural_language', '')
                sql_example = example.get('sql', '')
                prompt_parts.append(f"\n*Ejemplo {i}:*")
                prompt_parts.append(f"Consulta: {nl_query}")
                prompt_parts.append("```sql")
                prompt_parts.append(sql_example)
                prompt_parts.append("```")
            prompt_parts.append("")

        # Requirements and constraints
        prompt_parts.append("**Requerimientos:**")
        prompt_parts.append("1. Genera ÚNICAMENTE una consulta SELECT de PostgreSQL")
        prompt_parts.append("2. Usa la tabla: `monthly_kpis`")
        prompt_parts.append("3. SIEMPRE incluye: `LIMIT 1000`")
        prompt_parts.append("4. Para series de tiempo, ordena por `fecha ASC`")
        prompt_parts.append("5. Para filtrar bancos, usa la columna `banco_norm`")
        prompt_parts.append("6. No incluyas explicaciones, solo el SQL")
        prompt_parts.append("7. Usa comillas simples para strings ('INVEX', 'SISTEMA')")
        prompt_parts.append("8. Para intervalos de tiempo, usa sintaxis PostgreSQL (INTERVAL '3 months')")
        prompt_parts.append("")

        # Final instruction
        prompt_parts.append("**Genera la consulta SQL:**")

        return "\n".join(prompt_parts)


def get_saptiva_llm_client(model: str = "SAPTIVA_TURBO") -> Optional[SaptivaLlmClient]:
    """
    Factory function to get SAPTIVA LLM client.

    Args:
        model: SAPTIVA model to use

    Returns:
        SaptivaLlmClient instance or None if initialization fails
    """
    try:
        return SaptivaLlmClient(model=model, temperature=0.0)
    except Exception as e:
        logger.error(
            "llm_client.saptiva.creation_failed",
            error=str(e),
            exc_info=True
        )
        return None
