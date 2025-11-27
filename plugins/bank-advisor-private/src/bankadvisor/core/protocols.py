"""
Core Protocols - Abstract Interfaces (DIP Compliance)

Este módulo define las abstracciones (interfaces) del sistema siguiendo
el principio de Inversión de Dependencias (DIP).

Los módulos de alto nivel (Orchestrator) dependen de estas abstracciones,
no de implementaciones concretas.
"""
from typing import Protocol, Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# VALUE OBJECTS (Domain Models)
# ============================================================================

@dataclass(frozen=True)
class MetricQuery:
    """Value object representing a user's metric query"""
    raw_query: str
    mode: str = "dashboard"


@dataclass(frozen=True)
class DisambiguationResult:
    """Result of NLP disambiguation"""
    is_ambiguous: bool
    resolved_id: Optional[str]
    options: List[str]


@dataclass(frozen=True)
class MetricConfig:
    """Configuration for a specific metric"""
    field: str
    title: str
    unit: str
    mode: str


@dataclass(frozen=True)
class AnalyticsData:
    """Raw analytics data from database"""
    months: List[Dict[str, Any]]
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class VisualizationConfig:
    """Plotly visualization configuration"""
    data: List[Dict[str, Any]]
    layout: Dict[str, Any]


class ErrorType(Enum):
    """Standard error types"""
    AMBIGUOUS_QUERY = "ambiguous_query"
    VALIDATION_FAILED = "validation_failed"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class AnalyticsResponse:
    """Complete analytics response"""
    data: Optional[AnalyticsData]
    visualization: Optional[VisualizationConfig]
    title: str
    data_as_of: str
    error: Optional[ErrorType] = None
    error_message: Optional[str] = None


# ============================================================================
# PROTOCOLS (Abstract Interfaces)
# ============================================================================

class IIntentService(Protocol):
    """
    Interface for NLP intent disambiguation service.

    Responsible for:
    - Understanding user queries
    - Resolving ambiguities
    - Mapping to metric IDs
    """

    def disambiguate(self, query: str) -> DisambiguationResult:
        """
        Disambiguate a user query to a specific metric.

        Args:
            query: Natural language query (e.g., "cartera comercial")

        Returns:
            DisambiguationResult with resolved ID or list of options
        """
        ...

    def get_section_config(self, section_id: str) -> MetricConfig:
        """
        Get configuration for a specific section/metric.

        Args:
            section_id: Resolved metric ID

        Returns:
            MetricConfig with field, title, unit, etc.
        """
        ...


class IMetricsRepository(Protocol):
    """
    Interface for metrics data access.

    Responsible for:
    - Querying database
    - Applying security filters
    - Returning raw data
    """

    async def get_dashboard_data(
        self,
        metric_field: str,
        mode: str
    ) -> AnalyticsData:
        """
        Fetch analytics data for a specific metric.

        Args:
            metric_field: Database column name (validated)
            mode: Visualization mode

        Returns:
            AnalyticsData with months and metadata

        Raises:
            ValueError: If metric is invalid
            DatabaseError: If query fails
        """
        ...


class IVisualizationStrategy(Protocol):
    """
    Interface for visualization strategies.

    Responsible for:
    - Building Plotly configs
    - Applying mode-specific logic
    """

    def build_config(
        self,
        data: List[Dict[str, Any]],
        config: MetricConfig
    ) -> VisualizationConfig:
        """
        Build visualization configuration from data.

        Args:
            data: Raw monthly data points
            config: Metric configuration

        Returns:
            VisualizationConfig ready for Plotly.js
        """
        ...


class IVisualizationFactory(Protocol):
    """
    Interface for creating visualization strategies.

    Responsible for:
    - Selecting appropriate strategy based on mode
    - Instantiating strategy objects
    """

    def create(self, mode: str) -> IVisualizationStrategy:
        """
        Create visualization strategy for given mode.

        Args:
            mode: Visualization mode ("dashboard", "timeline", etc.)

        Returns:
            Concrete IVisualizationStrategy implementation

        Raises:
            ValueError: If mode is unsupported
        """
        ...


class IQueryValidator(Protocol):
    """
    Interface for query validation.

    Responsible for:
    - Pre-validation checks
    - Security checks
    - Business rule validation
    """

    def validate(self, query: MetricQuery) -> None:
        """
        Validate a metric query.

        Args:
            query: MetricQuery to validate

        Raises:
            ValueError: If query is invalid
        """
        ...


class IResponseFormatter(Protocol):
    """
    Interface for response formatting.

    Responsible for:
    - Transforming domain objects to DTOs
    - Applying consistent structure
    """

    def format_success(
        self,
        data: AnalyticsData,
        visualization: VisualizationConfig,
        title: str,
        data_as_of: str
    ) -> Dict[str, Any]:
        """Format successful response"""
        ...

    def format_error(
        self,
        error_type: ErrorType,
        message: str,
        options: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Format error response"""
        ...


# ============================================================================
# ORCHESTRATOR INTERFACE
# ============================================================================

class IBankAnalyticsOrchestrator(Protocol):
    """
    Interface for the main analytics orchestrator.

    Responsible for:
    - Coordinating all services
    - Managing workflow
    - Handling errors globally
    """

    async def execute(self, query: MetricQuery) -> Dict[str, Any]:
        """
        Execute complete analytics workflow.

        Args:
            query: User's metric query

        Returns:
            Formatted response dictionary

        Workflow:
            1. Validate query
            2. Disambiguate intent
            3. Fetch data from repository
            4. Generate visualization
            5. Format response
        """
        ...
