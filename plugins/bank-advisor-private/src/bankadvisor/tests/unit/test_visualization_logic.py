import pytest
from bankadvisor.services.visualization_service import VisualizationService

class TestVisualizationService:

    def test_chart_props_colors_invex(self):
        """Valida que los colores corporativos de INVEX se respeten en la generación de Plotly."""
        
        # Datos dummy
        data = [
            {"month_label": "Jul 2025", "data": [{"category": "INVEX", "value": 100}]}
        ]
        config = {"mode": "dashboard_month_comparison", "title": "Test", "unit": "$"}
        
        # Ejecutar
        result = VisualizationService.build_plotly_config(data, config)
        
        # Verificar estructura
        assert "data" in result
        trace = result["data"][0]
        
        # Verificar color (INVEX debe ser #E45756)
        # La lógica actual asigna colores dinámicamente basado en la categoría
        assert trace["marker"]["color"][0] == "#E45756"

    def test_layout_type_determination(self):
        """Valida que se elija el layout correcto según la configuración."""
        
        data = []
        
        # Caso 1: Dashboard
        config_dash = {"mode": "dashboard_month_comparison"}
        # build_plotly_config delega a _build_comparison_chart
        # No podemos inspeccionar la función interna fácilmente sin spy, 
        # pero podemos verificar la estructura de salida típica de ese modo (barras)
        
        # Nota: Con data vacía devuelve {}, así que probamos con datos mínimos
        data_mock = [{"month_label": "X", "data": [{"category": "A", "value": 1}]}]
        
        res_dash = VisualizationService.build_plotly_config(data_mock, config_dash)
        assert res_dash["data"][0]["type"] == "bar"
        
        # Caso 2: Timeline
        config_time = {"mode": "timeline_with_summary"}
        res_time = VisualizationService.build_plotly_config(data_mock, config_time)
        # Timeline genera scatter plots (lines+markers)
        # Si hay datos, debería haber trazas scatter
        # Nota: La lógica actual filtra por "INVEX" o "SISTEMA" en timeline. 
        # Agreguemos datos que cumplan esa condición
        data_mock_timeline = [{"month_label": "X", "data": [{"category": "INVEX", "value": 1}]}]
        res_time = VisualizationService.build_plotly_config(data_mock_timeline, config_time)
        
        assert res_time["data"][0]["type"] == "scatter"
