from typing import Dict, Any, List
import pandas as pd

# Colores oficiales (Hardcoded para eficiencia, extraídos de legacy_styles.py)
COLOR_INVEX = "#E45756"
COLOR_SISTEMA = "#AAB0B3"
COLOR_ETAPA_1 = "#2E8B57"
COLOR_ETAPA_2 = "#FFD700"
COLOR_ETAPA_3 = "#DC143C"

class VisualizationService:
    
    @staticmethod
    def build_plotly_config(
        data: List[Dict[str, Any]], 
        section_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convierte datos planos a configuración de Plotly.js.
        
        Args:
            data: Lista de diccionarios [{'month_label': '...', 'data': [{'category': 'INVEX', 'value': 100}, ...]}, ...]
            section_config: Configuración de la sección desde YAML.
        """
        mode = section_config.get("mode", "dashboard_month_comparison")
        title = section_config.get("title", "Gráfico")
        unit = section_config.get("unit", "")
        is_ratio = section_config.get("type") == "ratio"
        
        if mode == "dashboard_month_comparison":
            return VisualizationService._build_comparison_chart(data, title, unit, is_ratio)
        elif mode == "timeline_with_summary":
            return VisualizationService._build_timeline_chart(data, title, unit, is_ratio)
        
        # Default fallback
        return VisualizationService._build_timeline_chart(data, title, unit, is_ratio)

    @staticmethod
    def _build_comparison_chart(data: List[Dict], title: str, unit: str, is_ratio: bool) -> Dict[str, Any]:
        """Gráfico de barras agrupadas para comparar Invex vs Sistema en el último mes."""
        if not data:
            return {}
            
        # Usamos el último mes disponible
        latest_month = data[-1]
        month_label = latest_month["month_label"]
        values = latest_month["data"]
        
        categories = [item["category"] for item in values]
        vals = [item["value"] for item in values]
        colors = [COLOR_INVEX if "INVEX" in c.upper() else COLOR_SISTEMA for c in categories]
        
        return {
            "data": [
                {
                    "type": "bar",
                    "x": categories,
                    "y": vals,
                    "marker": {"color": colors},
                    "text": [f"{v:.2f}%" if is_ratio else f"{v:,.0f}" for v in vals],
                    "textposition": "auto"
                }
            ],
            "layout": {
                "title": f"{title} - {month_label}",
                "yaxis": {
                    "title": unit,
                    "tickformat": ".1%" if is_ratio else "s"
                },
                "margin": {"l": 50, "r": 50, "t": 50, "b": 50},
                "autosize": True
            }
        }

    @staticmethod
    def _build_timeline_chart(data: List[Dict], title: str, unit: str, is_ratio: bool) -> Dict[str, Any]:
        """Gráfico de líneas para evolución histórica."""
        
        months = [d["month_label"] for d in data]
        
        # Separar series
        invex_data = []
        sistema_data = []
        
        for month in data:
            for item in month["data"]:
                if "INVEX" in item["category"].upper():
                    invex_data.append(item["value"])
                elif "SISTEMA" in item["category"].upper():
                    sistema_data.append(item["value"])
        
        traces = []
        if invex_data:
            traces.append({
                "type": "scatter",
                "mode": "lines+markers",
                "name": "INVEX",
                "x": months,
                "y": invex_data,
                "line": {"color": COLOR_INVEX, "width": 3}
            })
            
        if sistema_data:
            traces.append({
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Sistema",
                "x": months,
                "y": sistema_data,
                "line": {"color": COLOR_SISTEMA, "width": 2, "dash": "dot"}
            })
            
        return {
            "data": traces,
            "layout": {
                "title": f"Evolución {title}",
                "hovermode": "x unified",
                "yaxis": {
                    "title": unit,
                    "tickformat": ".1%" if is_ratio else "s" # 's' es SI prefix para miles/millones
                },
                "legend": {"orientation": "h", "y": -0.2},
                "margin": {"l": 50, "r": 50, "t": 50, "b": 50},
                "autosize": True
            }
        }
