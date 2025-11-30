"""
PlotlyGenerator - Single Responsibility: Generate Plotly visualizations from HU3 data.

Principles Applied:
- Single Responsibility: Only handles Plotly generation
- Open/Closed: Extensible for new visualization types
- Dependency Inversion: Depends on abstractions (config), not concretions
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import structlog

from bankadvisor.config_service import get_config
from bankadvisor.services.visualization_service import VisualizationService

logger = structlog.get_logger(__name__)


class PlotlyGenerator:
    """
    Generates Plotly configurations from HU3 pipeline data.

    Converts HU3 format (data.values) to Plotly config using VisualizationService.
    """

    @staticmethod
    def generate(
        metric_id: str,
        data: Dict[str, Any],
        intent: str,
        metric_display: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate Plotly config from HU3 data.values format.

        Args:
            metric_id: Metric identifier (e.g., 'imor', 'cartera_total')
            data: HU3 data dict with 'values' key
            intent: Query intent (evolution, comparison, ranking, point_value)
            metric_display: Display name for metric (fallback if not in config)

        Returns:
            Plotly config dict or None if generation fails

        Raises:
            ValueError: If data format is invalid
        """
        if not data or "values" not in data:
            logger.warning(
                "plotly_generator.no_values",
                metric=metric_id,
                data_keys=list(data.keys()) if data else []
            )
            return None

        if not data["values"]:
            logger.debug("plotly_generator.empty_values", metric=metric_id)
            return None

        try:
            # Convert HU3 format to legacy format
            legacy_data = PlotlyGenerator._convert_hu3_to_legacy(data["values"])

            # Get visualization config
            viz_config = PlotlyGenerator._get_viz_config(metric_id, metric_display)

            # Generate plotly using VisualizationService
            plotly_config = VisualizationService.build_plotly_config_enhanced(
                data=legacy_data,
                section_config=viz_config,
                intent=intent
            )

            logger.debug(
                "plotly_generator.success",
                metric=metric_id,
                intent=intent,
                trace_count=len(plotly_config.get("data", [])) if plotly_config else 0
            )

            return plotly_config

        except Exception as e:
            logger.warning(
                "plotly_generator.failed",
                metric=metric_id,
                error=str(e),
                error_type=type(e).__name__
            )
            return None

    @staticmethod
    def _convert_hu3_to_legacy(values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert HU3 data.values format to legacy format.

        HU3 format:
            [{"date": "2024-01-01", "bank_name": "INVEX", "metric_value": 123}, ...]

        Legacy format:
            [{"month_label": "Jan 2024", "data": [{"category": "INVEX", "value": 123}]}, ...]

        Args:
            values: List of value dicts from HU3

        Returns:
            List of month dicts for VisualizationService
        """
        df = pd.DataFrame(values)
        df['date'] = pd.to_datetime(df['date'])
        df['month_label'] = df['date'].dt.strftime('%b %Y')

        # Group by month
        legacy_data = []
        for month_label, group in df.groupby('month_label', sort=False):
            month_data = {
                "month_label": month_label,
                "data": [
                    {"category": row["bank_name"], "value": row["metric_value"]}
                    for _, row in group.iterrows()
                ]
            }
            legacy_data.append(month_data)

        return legacy_data

    @staticmethod
    def _get_viz_config(metric_id: str, metric_display: Optional[str] = None) -> Dict[str, Any]:
        """
        Get visualization config for a metric.

        Args:
            metric_id: Metric identifier
            metric_display: Optional display name fallback

        Returns:
            Visualization config dict
        """
        config = get_config()

        # Try to get from visualizations.yaml
        viz_config = config.visualizations.get(metric_id)

        if viz_config:
            return viz_config

        # Fallback: create default config
        metric_config = config.metrics.get(metric_id, {})
        metric_type = metric_config.get("type", "currency")

        return {
            "title": metric_display or metric_id.replace("_", " ").title(),
            "mode": "dual_mode",  # Let intent decide
            "type": metric_type,
            "unit": "%" if metric_type == "ratio" else ""
        }
