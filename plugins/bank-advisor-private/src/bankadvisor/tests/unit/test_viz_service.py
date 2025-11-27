import pytest
from bankadvisor.services.visualization_service import VisualizationService

def test_build_plotly_config_comparison():
    """Test para gráfico de comparación (barras)."""
    
    # Datos dummy simulando respuesta de AnalyticsService
    dummy_data = [
        {
            "month_label": "Jul 2025",
            "data": [
                {"category": "INVEX", "value": 15000},
                {"category": "Sistema Promedio", "value": 12000}
            ]
        }
    ]
    
    config = {
        "mode": "dashboard_month_comparison",
        "title": "Cartera Total",
        "unit": "MM MXN",
        "type": "currency"
    }
    
    result = VisualizationService.build_plotly_config(dummy_data, config)
    
    assert "data" in result
    assert "layout" in result
    
    # Verificar tipo de gráfico
    assert result["data"][0]["type"] == "bar"
    
    # Verificar datos
    categories = result["data"][0]["x"]
    assert "INVEX" in categories
    assert "Sistema Promedio" in categories
    
    # Verificar colores (Invex Red: #E45756)
    colors = result["data"][0]["marker"]["color"]
    assert "#E45756" in colors  # Debe estar el color de Invex

def test_build_plotly_config_timeline():
    """Test para gráfico de línea temporal."""
    
    dummy_data = [
        {"month_label": "Ene", "data": [{"category": "INVEX", "value": 10}, {"category": "SISTEMA", "value": 12}]},
        {"month_label": "Feb", "data": [{"category": "INVEX", "value": 11}, {"category": "SISTEMA", "value": 12.5}]}
    ]
    
    config = {
        "mode": "timeline_with_summary",
        "title": "IMOR Historico",
        "unit": "%",
        "type": "ratio"
    }
    
    result = VisualizationService.build_plotly_config(dummy_data, config)
    
    assert len(result["data"]) == 2  # Dos trazas: Invex y Sistema
    assert result["data"][0]["type"] == "scatter"
    assert result["data"][0]["mode"] == "lines+markers"
    
    # Verificar nombres de series
    names = [trace["name"] for trace in result["data"]]
    assert "INVEX" in names
    assert "Sistema" in names
