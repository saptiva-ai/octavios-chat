"""
Visualization Recommender Service

Automatically determines the best visualization type based on:
- Data characteristics (number of points, series, distribution)
- Query intent (ranking, evolution, comparison)
- Metric type (ratio, currency, count)
"""
import structlog
from typing import Dict, Any, List, Optional

logger = structlog.get_logger(__name__)


class VizRecommender:
    """
    Smart visualization type recommender.

    Analyzes data and context to recommend the most effective chart type.
    """

    @staticmethod
    def recommend(
        data: Dict[str, Any],
        intent: str,
        metric_type: str,
        banks_count: int = 1,
        time_points: int = 0,
        is_ranking: bool = False,
        is_comparison: bool = False
    ) -> Dict[str, Any]:
        """
        Recommend the best visualization type and configuration.

        Args:
            data: Data dictionary with values
            intent: Query intent (evolution, comparison, ranking, point_value)
            metric_type: Type of metric (ratio, currency, count)
            banks_count: Number of banks/entities in the data
            time_points: Number of time points (for time series)
            is_ranking: Whether this is a ranking query
            is_comparison: Whether this is a comparison query

        Returns:
            Dict with recommended chart type and configuration
        """

        # =====================================================================
        # RANKING QUERIES → Horizontal Bar Chart
        # =====================================================================
        if is_ranking or intent == "ranking":
            return {
                "chart_type": "bar",
                "orientation": "h",
                "mode": None,
                "barmode": None,
                "description": "Horizontal bar chart for ranking visualization",
                "reasoning": "Rankings are best displayed as horizontal bars for easy comparison and label readability"
            }

        # =====================================================================
        # TIME SERIES / EVOLUTION → Line Chart
        # =====================================================================
        if intent == "evolution" or time_points > 5:
            # Multiple banks → Multiple line series
            if banks_count > 1:
                return {
                    "chart_type": "scatter",
                    "orientation": None,
                    "mode": "lines+markers",
                    "barmode": None,
                    "description": "Multi-line chart for evolution over time",
                    "reasoning": f"Time series with {banks_count} banks - line chart shows trends clearly"
                }
            # Single bank → Single line
            else:
                return {
                    "chart_type": "scatter",
                    "orientation": None,
                    "mode": "lines+markers",
                    "barmode": None,
                    "description": "Single line chart for temporal evolution",
                    "reasoning": "Single entity evolution - line chart emphasizes trend"
                }

        # =====================================================================
        # COMPARISON (Point-in-time) → Vertical Bar Chart
        # =====================================================================
        if is_comparison or intent == "comparison":
            if banks_count <= 5:
                return {
                    "chart_type": "bar",
                    "orientation": "v",
                    "mode": None,
                    "barmode": "group",
                    "description": "Vertical bar chart for comparison",
                    "reasoning": f"Comparing {banks_count} entities - vertical bars allow easy visual comparison"
                }
            else:
                # Too many banks → Horizontal bar for better label space
                return {
                    "chart_type": "bar",
                    "orientation": "h",
                    "mode": None,
                    "barmode": None,
                    "description": "Horizontal bar chart for multi-entity comparison",
                    "reasoning": f"{banks_count} entities - horizontal bars for better label readability"
                }

        # =====================================================================
        # MARKET SHARE / DISTRIBUTION → Pie Chart or Stacked Bar
        # =====================================================================
        if "market_share" in str(data.get("visualization", "")).lower():
            if banks_count == 1:
                # Single bank share → Line chart showing evolution
                return {
                    "chart_type": "scatter",
                    "orientation": None,
                    "mode": "lines+markers",
                    "barmode": None,
                    "description": "Line chart for market share evolution",
                    "reasoning": "Market share over time - line chart shows trend"
                }
            elif banks_count <= 8:
                # Multiple banks → Pie chart
                return {
                    "chart_type": "pie",
                    "orientation": None,
                    "mode": None,
                    "barmode": None,
                    "description": "Pie chart for market share distribution",
                    "reasoning": f"{banks_count} banks - pie chart shows proportions clearly"
                }
            else:
                # Too many slices → Stacked bar instead
                return {
                    "chart_type": "bar",
                    "orientation": "v",
                    "mode": None,
                    "barmode": "stack",
                    "description": "Stacked bar for market share distribution",
                    "reasoning": f"{banks_count} banks - stacked bar more readable than pie with many slices"
                }

        # =====================================================================
        # SINGLE VALUE → KPI Card
        # =====================================================================
        if intent == "point_value" and banks_count == 1 and time_points <= 1:
            return {
                "chart_type": "indicator",
                "orientation": None,
                "mode": "number+delta",
                "barmode": None,
                "description": "KPI card for single value display",
                "reasoning": "Single point value - indicator/KPI card is most effective"
            }

        # =====================================================================
        # FALLBACK → Vertical Bar Chart (Safe Default)
        # =====================================================================
        return {
            "chart_type": "bar",
            "orientation": "v",
            "mode": None,
            "barmode": "group",
            "description": "Vertical bar chart (default)",
            "reasoning": "Default fallback - vertical bars work for most scenarios"
        }

    @staticmethod
    def enhance_layout(
        layout: Dict[str, Any],
        chart_type: str,
        banks_count: int = 1,
        metric_type: str = "ratio"
    ) -> Dict[str, Any]:
        """
        Enhance Plotly layout based on chart type and data characteristics.

        Args:
            layout: Base Plotly layout dict
            chart_type: Recommended chart type (bar, scatter, pie, etc.)
            banks_count: Number of entities
            metric_type: Type of metric (ratio, currency, count)

        Returns:
            Enhanced layout dict with optimal settings
        """
        enhanced = layout.copy()

        # Always enable autosize for responsive width
        enhanced["autosize"] = True

        # =====================================================================
        # HORIZONTAL BAR CHARTS → Extra left margin for labels
        # =====================================================================
        if chart_type == "bar" and layout.get("orientation") == "h":
            enhanced["margin"] = {"l": 140, "r": 20, "t": 60, "b": 60}
            # Reverse y-axis so #1 is at top
            if "yaxis" not in enhanced:
                enhanced["yaxis"] = {}
            enhanced["yaxis"]["autorange"] = "reversed"

        # =====================================================================
        # LINE CHARTS → Standard margins, add rangeslider for many points
        # =====================================================================
        elif chart_type == "scatter":
            enhanced["margin"] = {"l": 80, "r": 20, "t": 60, "b": 60}
            enhanced["hovermode"] = "x unified"  # Compare all series on hover

        # =====================================================================
        # PIE CHARTS → Centered with legend on right
        # =====================================================================
        elif chart_type == "pie":
            enhanced["margin"] = {"l": 20, "r": 20, "t": 60, "b": 20}
            enhanced["showlegend"] = True
            enhanced["legend"] = {"orientation": "v", "x": 1.05, "y": 0.5}

        # =====================================================================
        # VERTICAL BAR CHARTS → Standard margins
        # =====================================================================
        elif chart_type == "bar":
            enhanced["margin"] = {"l": 80, "r": 20, "t": 60, "b": 80}
            if banks_count > 5:
                # Rotate x-axis labels for many bars
                if "xaxis" not in enhanced:
                    enhanced["xaxis"] = {}
                enhanced["xaxis"]["tickangle"] = -45

        # =====================================================================
        # RESPONSIVE HEIGHT → Adjust based on data points
        # =====================================================================
        if chart_type == "bar" and enhanced.get("margin", {}).get("l", 0) > 100:
            # Horizontal bars: height increases with number of bars
            suggested_height = max(400, min(800, banks_count * 50))
            enhanced["height"] = suggested_height

        return enhanced

    @staticmethod
    def get_chart_config(recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert recommendation to Plotly trace configuration.

        Args:
            recommendation: Output from recommend()

        Returns:
            Plotly trace config dict
        """
        config = {
            "type": recommendation["chart_type"]
        }

        if recommendation["orientation"]:
            config["orientation"] = recommendation["orientation"]

        if recommendation["mode"]:
            config["mode"] = recommendation["mode"]

        return config
