"""
BankAnalyticsOrchestrator - Main Workflow Coordinator

Este módulo implementa el patrón Orchestrator para coordinar el flujo
completo de analytics, siguiendo SRP (Single Responsibility Principle)
y DIP (Dependency Inversion Principle).

Responsabilidades:
- Coordinar servicios (no implementar lógica de negocio)
- Manejar errores globalmente
- Logging de eventos
"""
from typing import Dict, Any
import structlog

from .protocols import (
    IBankAnalyticsOrchestrator,
    IIntentService,
    IMetricsRepository,
    IVisualizationFactory,
    IQueryValidator,
    IResponseFormatter,
    MetricQuery,
    ErrorType
)


logger = structlog.get_logger(__name__)


class BankAnalyticsOrchestrator(IBankAnalyticsOrchestrator):
    """
    Orchestrates the complete analytics workflow.

    This class follows:
    - SRP: Only coordinates, doesn't implement business logic
    - DIP: Depends on abstractions (protocols), not concrete classes
    - OCP: Can extend by adding new services without modifying this class

    Dependencies are injected via constructor (Dependency Injection pattern).
    """

    def __init__(
        self,
        intent_service: IIntentService,
        metrics_repository: IMetricsRepository,
        visualization_factory: IVisualizationFactory,
        query_validator: IQueryValidator,
        response_formatter: IResponseFormatter
    ):
        """
        Initialize orchestrator with injected dependencies.

        Args:
            intent_service: NLP disambiguation service
            metrics_repository: Data access layer
            visualization_factory: Creates visualization strategies
            query_validator: Validates queries
            response_formatter: Formats responses
        """
        self.intent = intent_service
        self.repository = metrics_repository
        self.viz_factory = visualization_factory
        self.validator = query_validator
        self.formatter = response_formatter

    async def execute(self, query: MetricQuery) -> Dict[str, Any]:
        """
        Execute complete analytics workflow.

        Workflow (Chain of Responsibility pattern):
            1. Validate query → QueryValidator
            2. Disambiguate intent → IntentService
            3. Fetch data → MetricsRepository
            4. Generate visualization → VisualizationStrategy
            5. Format response → ResponseFormatter

        Args:
            query: User's metric query

        Returns:
            Formatted response dictionary
        """
        logger.info(
            "orchestrator.execute_started",
            query=query.raw_query,
            mode=query.mode
        )

        try:
            # Step 1: Validate query
            self.validator.validate(query)

            # Step 2: Disambiguate intent
            intent = self.intent.disambiguate(query.raw_query)

            if intent.is_ambiguous:
                logger.warning(
                    "orchestrator.ambiguous_query",
                    query=query.raw_query,
                    options=intent.options[:3]
                )
                return self.formatter.format_error(
                    ErrorType.AMBIGUOUS_QUERY,
                    f"Query '{query.raw_query}' es ambigua",
                    options=intent.options[:5]
                )

            # Step 3: Get metric configuration
            config = self.intent.get_section_config(intent.resolved_id)

            # Step 4: Fetch data from repository
            data = await self.repository.get_dashboard_data(
                metric_field=config.field,
                mode=query.mode
            )

            # Step 5: Generate visualization using Factory pattern
            viz_strategy = self.viz_factory.create(query.mode)
            visualization = viz_strategy.build_config(data.months, config)

            # Step 6: Format success response
            response = self.formatter.format_success(
                data=data,
                visualization=visualization,
                title=config.title,
                data_as_of=data.metadata.get("data_as_of", "N/A")
            )

            logger.info(
                "orchestrator.execute_completed",
                metric=config.field,
                months_returned=len(data.months)
            )

            return response

        except ValueError as ve:
            # Business validation error (invalid metric, etc.)
            logger.warning("orchestrator.validation_error", error=str(ve))
            return self.formatter.format_error(
                ErrorType.VALIDATION_FAILED,
                str(ve)
            )

        except Exception as e:
            # Unexpected error
            logger.error("orchestrator.unexpected_error", error=str(e), exc_info=True)
            return self.formatter.format_error(
                ErrorType.INTERNAL_ERROR,
                "Error interno procesando la consulta"
            )
