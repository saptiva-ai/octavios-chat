"""
Artifact Service for managing user-generated artifacts.

This service handles CRUD operations for artifacts including:
- Bank charts (visualizations)
- Markdown documents
- Code snippets
- Graph diagrams
"""

from typing import List, Optional
from structlog import get_logger

from src.models.artifact import Artifact, ArtifactType
from src.schemas.bank_chart import (
    BankChartArtifactRequest,
    BankChartArtifactResponse,
)

logger = get_logger(__name__)


class ArtifactService:
    """Service for managing artifacts across the application."""

    async def create_bank_chart_artifact(
        self,
        request: BankChartArtifactRequest,
    ) -> Artifact:
        """
        Create a bank_chart artifact from analytics data.

        This method:
        1. Enriches chart_data with sql_query and metric_interpretation
        2. Creates artifact using factory method
        3. Persists to MongoDB
        4. Logs creation for observability

        Args:
            request: BankChartArtifactRequest with user_id, session_id, chart_data, etc.

        Returns:
            Persisted Artifact instance

        Raises:
            ValueError: If chart_data is invalid
            Exception: If MongoDB insert fails

        Example:
            >>> service = ArtifactService()
            >>> artifact = await service.create_bank_chart_artifact(
            ...     BankChartArtifactRequest(
            ...         user_id="user123",
            ...         session_id="session456",
            ...         chart_data={"metric_name": "imor", ...},
            ...         sql_query="SELECT ...",
            ...         metric_interpretation="IMOR representa..."
            ...     )
            ... )
            >>> print(artifact.id)
        """
        # Enrich chart_data with metadata
        enriched_chart_data = {**request.chart_data}

        # Add sql_query and metric_interpretation to metadata
        if "metadata" not in enriched_chart_data:
            enriched_chart_data["metadata"] = {}

        if request.sql_query:
            enriched_chart_data["metadata"]["sql_generated"] = request.sql_query

        if request.metric_interpretation:
            enriched_chart_data["metadata"]["metric_interpretation"] = (
                request.metric_interpretation
            )

        # Create artifact using factory method
        artifact = Artifact.create_bank_chart(
            user_id=request.user_id,
            session_id=request.session_id,
            chart_data=enriched_chart_data,
            title=request.title,
        )

        # Persist to MongoDB
        await artifact.insert()

        logger.info(
            "bank_chart_artifact_created",
            artifact_id=artifact.id,
            session_id=request.session_id,
            user_id=request.user_id,
            metric_name=request.chart_data.get("metric_name"),
            bank_names=request.chart_data.get("bank_names"),
        )

        return artifact

    async def get_charts_by_session(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[Artifact]:
        """
        Get all bank_chart artifacts for a chat session, ordered by most recent.

        Used for:
        - Loading chart history in canvas
        - Multi-chart mode (future)
        - Session cleanup

        Args:
            session_id: Chat session ID
            limit: Maximum number of charts to return (default 10)

        Returns:
            List of Artifact instances, newest first

        Example:
            >>> service = ArtifactService()
            >>> charts = await service.get_charts_by_session("session123", limit=5)
            >>> print(len(charts))  # 5 most recent charts
        """
        charts = (
            await Artifact.find(
                Artifact.chat_session_id == session_id,
                Artifact.type == ArtifactType.BANK_CHART,
            )
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )

        logger.debug(
            "fetched_charts_by_session",
            session_id=session_id,
            count=len(charts),
            limit=limit,
        )

        return charts

    async def get_latest_chart_in_session(
        self,
        session_id: str,
    ) -> Optional[Artifact]:
        """
        Get the most recent bank_chart artifact in a session.

        Useful for:
        - Auto-opening canvas with latest chart
        - Detecting if session has charts

        Args:
            session_id: Chat session ID

        Returns:
            Latest Artifact or None if no charts exist

        Example:
            >>> service = ArtifactService()
            >>> latest = await service.get_latest_chart_in_session("session123")
            >>> if latest:
            ...     print(f"Latest chart: {latest.title}")
        """
        charts = await self.get_charts_by_session(session_id, limit=1)
        return charts[0] if charts else None

    async def get_artifact_by_id(
        self,
        artifact_id: str,
    ) -> Optional[Artifact]:
        """
        Get a single artifact by ID.

        Args:
            artifact_id: Unique artifact ID

        Returns:
            Artifact instance or None if not found

        Example:
            >>> service = ArtifactService()
            >>> artifact = await service.get_artifact_by_id("artifact_abc123")
            >>> if artifact:
            ...     print(artifact.type)  # "bank_chart"
        """
        artifact = await Artifact.get(artifact_id)

        if artifact:
            logger.debug(
                "fetched_artifact_by_id",
                artifact_id=artifact_id,
                type=artifact.type,
            )
        else:
            logger.warning(
                "artifact_not_found",
                artifact_id=artifact_id,
            )

        return artifact

    async def get_artifacts_by_user(
        self,
        user_id: str,
        artifact_type: Optional[ArtifactType] = None,
        limit: int = 20,
    ) -> List[Artifact]:
        """
        Get all artifacts for a user, optionally filtered by type.

        Args:
            user_id: User ID
            artifact_type: Optional type filter (BANK_CHART, MARKDOWN, etc.)
            limit: Maximum number of artifacts to return

        Returns:
            List of Artifact instances, newest first

        Example:
            >>> service = ArtifactService()
            >>> charts = await service.get_artifacts_by_user(
            ...     "user123",
            ...     artifact_type=ArtifactType.BANK_CHART
            ... )
        """
        query = {"user_id": user_id}
        if artifact_type:
            query["type"] = artifact_type

        artifacts = (
            await Artifact.find(query)
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )

        logger.debug(
            "fetched_artifacts_by_user",
            user_id=user_id,
            artifact_type=artifact_type,
            count=len(artifacts),
        )

        return artifacts

    async def delete_artifact(
        self,
        artifact_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete an artifact (with ownership check).

        Args:
            artifact_id: Artifact ID to delete
            user_id: User ID (for ownership verification)

        Returns:
            True if deleted, False if not found or unauthorized

        Example:
            >>> service = ArtifactService()
            >>> deleted = await service.delete_artifact("artifact_abc", "user123")
            >>> print(deleted)  # True
        """
        artifact = await Artifact.get(artifact_id)

        if not artifact:
            logger.warning("artifact_not_found_for_delete", artifact_id=artifact_id)
            return False

        if artifact.user_id != user_id:
            logger.warning(
                "unauthorized_artifact_delete",
                artifact_id=artifact_id,
                user_id=user_id,
                owner_id=artifact.user_id,
            )
            return False

        await artifact.delete()

        logger.info(
            "artifact_deleted",
            artifact_id=artifact_id,
            user_id=user_id,
            type=artifact.type,
        )

        return True

    def to_response(self, artifact: Artifact) -> BankChartArtifactResponse:
        """
        Convert Artifact model to BankChartArtifactResponse.

        Args:
            artifact: Artifact instance

        Returns:
            BankChartArtifactResponse schema

        Example:
            >>> service = ArtifactService()
            >>> artifact = await service.get_artifact_by_id("artifact_123")
            >>> response = service.to_response(artifact)
            >>> print(response.artifact_id)
        """
        return BankChartArtifactResponse(
            artifact_id=artifact.id,
            title=artifact.title,
            type=artifact.type.value,
            created_at=artifact.created_at.isoformat(),
            session_id=artifact.chat_session_id or "",
        )


# Singleton instance for dependency injection
_artifact_service_instance: Optional[ArtifactService] = None


def get_artifact_service() -> ArtifactService:
    """
    Get singleton ArtifactService instance.

    Used as FastAPI dependency:
        @router.post("/artifacts")
        async def create_artifact(
            service: ArtifactService = Depends(get_artifact_service)
        ):
            ...

    Returns:
        ArtifactService singleton
    """
    global _artifact_service_instance
    if _artifact_service_instance is None:
        _artifact_service_instance = ArtifactService()
    return _artifact_service_instance
