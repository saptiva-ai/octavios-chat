"""
Adapters - Connect existing services to protocols (Adapter Pattern)

Este módulo implementa el patrón Adapter para conectar los servicios
existentes (IntentService, AnalyticsService, etc.) con las interfaces
definidas en protocols.py.

Esto permite mantener compatibilidad con código existente mientras
aplicamos arquitectura limpia.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .protocols import (
    IIntentService,
    IMetricsRepository,
    IVisualizationStrategy,
    IVisualizationFactory,
    IQueryValidator,
    IResponseFormatter,
    DisambiguationResult,
    MetricConfig,
    AnalyticsData,
    VisualizationConfig,
    MetricQuery,
    ErrorType
)

# Import existing services
from ..services.intent_service import IntentService as ConcreteIntentService
from ..services.analytics_service import AnalyticsService as ConcreteAnalyticsService
from ..services.visualization_service import VisualizationService as ConcreteVizService


# ============================================================================
# INTENT SERVICE ADAPTER
# ============================================================================

class IntentServiceAdapter(IIntentService):
    """
    Adapts ConcreteIntentService to IIntentService protocol.
    """

    def __init__(self, concrete_service: ConcreteIntentService):
        self._service = concrete_service

    def disambiguate(self, query: str) -> DisambiguationResult:
        """Delegate to concrete service and adapt result"""
        result = self._service.disambiguate(query)

        return DisambiguationResult(
            is_ambiguous=result.is_ambiguous,
            resolved_id=result.resolved_id,
            options=result.options
        )

    def get_section_config(self, section_id: str) -> MetricConfig:
        """Delegate to concrete service and adapt result"""
        config = self._service.get_section_config(section_id)

        return MetricConfig(
            field=config["field"],
            title=config.get("title", "Análisis Bancario"),
            unit=config.get("unit", ""),
            mode=config.get("mode", "dashboard")
        )


# ============================================================================
# METRICS REPOSITORY ADAPTER
# ============================================================================

class MetricsRepositoryAdapter(IMetricsRepository):
    """
    Adapts ConcreteAnalyticsService to IMetricsRepository protocol.

    Uses Factory Method pattern to create session.
    """

    def __init__(self, session_factory):
        """
        Initialize with session factory.

        Args:
            session_factory: Callable that returns AsyncSession context manager
        """
        self._session_factory = session_factory

    async def get_dashboard_data(
        self,
        metric_field: str,
        mode: str
    ) -> AnalyticsData:
        """Fetch data using concrete analytics service"""
        async with self._session_factory() as session:
            result = await ConcreteAnalyticsService.get_dashboard_data(
                session,
                metric_or_query=metric_field,
                mode=mode
            )

            return AnalyticsData(
                months=result["data"]["months"],
                metadata=result["metadata"]
            )


# ============================================================================
# VISUALIZATION STRATEGIES (Strategy Pattern)
# ============================================================================

class DashboardVisualizationStrategy(IVisualizationStrategy):
    """
    Strategy for dashboard (bar chart) visualization.
    """

    def build_config(
        self,
        data: List[Dict[str, Any]],
        config: MetricConfig
    ) -> VisualizationConfig:
        """Build dashboard visualization using concrete service"""
        # Convert MetricConfig back to dict for existing service
        config_dict = {
            "field": config.field,
            "title": config.title,
            "unit": config.unit,
            "mode": "dashboard_month_comparison"
        }

        plotly = ConcreteVizService.build_plotly_config(data, config_dict)

        return VisualizationConfig(
            data=plotly["data"],
            layout=plotly["layout"]
        )


class TimelineVisualizationStrategy(IVisualizationStrategy):
    """
    Strategy for timeline (line chart) visualization.
    """

    def build_config(
        self,
        data: List[Dict[str, Any]],
        config: MetricConfig
    ) -> VisualizationConfig:
        """Build timeline visualization using concrete service"""
        config_dict = {
            "field": config.field,
            "title": config.title,
            "unit": config.unit,
            "mode": "timeline_with_summary"
        }

        plotly = ConcreteVizService.build_plotly_config(data, config_dict)

        return VisualizationConfig(
            data=plotly["data"],
            layout=plotly["layout"]
        )


# ============================================================================
# VISUALIZATION FACTORY (Factory Pattern)
# ============================================================================

class VisualizationFactory(IVisualizationFactory):
    """
    Factory for creating visualization strategies.

    Implements Factory Pattern to create appropriate strategy based on mode.
    Follows OCP: Can add new strategies without modifying this class.
    """

    def __init__(self):
        self._strategies = {
            "dashboard": DashboardVisualizationStrategy,
            "timeline": TimelineVisualizationStrategy
        }

    def create(self, mode: str) -> IVisualizationStrategy:
        """
        Create visualization strategy for given mode.

        Args:
            mode: Visualization mode

        Returns:
            Concrete strategy instance

        Raises:
            ValueError: If mode is unsupported
        """
        strategy_class = self._strategies.get(mode)

        if not strategy_class:
            raise ValueError(
                f"Unsupported visualization mode: {mode}. "
                f"Available: {list(self._strategies.keys())}"
            )

        return strategy_class()

    def register_strategy(
        self,
        mode: str,
        strategy_class: type[IVisualizationStrategy]
    ):
        """
        Register a new visualization strategy (for extensibility).

        Args:
            mode: Mode identifier
            strategy_class: Strategy class to register
        """
        self._strategies[mode] = strategy_class


# ============================================================================
# QUERY VALIDATOR
# ============================================================================

class QueryValidator(IQueryValidator):
    """
    Validates metric queries.

    Implements:
    - SRP: Only validates, doesn't execute
    - OCP: Can add new validation rules without modifying
    """

    def __init__(self, allowed_modes: Optional[List[str]] = None):
        self.allowed_modes = allowed_modes or ["dashboard", "timeline"]

    def validate(self, query: MetricQuery) -> None:
        """
        Validate query.

        Args:
            query: Query to validate

        Raises:
            ValueError: If query is invalid
        """
        if not query.raw_query or not query.raw_query.strip():
            raise ValueError("Query cannot be empty")

        if query.mode not in self.allowed_modes:
            raise ValueError(
                f"Invalid mode: {query.mode}. "
                f"Allowed: {self.allowed_modes}"
            )


# ============================================================================
# RESPONSE FORMATTER
# ============================================================================

class ResponseFormatter(IResponseFormatter):
    """
    Formats responses consistently.

    Implements:
    - SRP: Only formats, doesn't generate data
    - ISP: Interface segregated (success vs error)
    """

    def format_success(
        self,
        data: AnalyticsData,
        visualization: VisualizationConfig,
        title: str,
        data_as_of: str
    ) -> Dict[str, Any]:
        """Format successful response"""
        return {
            "data": {
                "months": data.months,
            },
            "metadata": {
                **data.metadata,
                "data_as_of": data_as_of
            },
            "plotly_config": {
                "data": visualization.data,
                "layout": visualization.layout
            },
            "title": title
        }

    def format_error(
        self,
        error_type: ErrorType,
        message: str,
        options: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Format error response"""
        response = {
            "error": error_type.value,
            "message": message
        }

        if options:
            response["options"] = options
            response["suggestion"] = "Por favor, especifica: " + ", ".join(options[:3])

        return response
