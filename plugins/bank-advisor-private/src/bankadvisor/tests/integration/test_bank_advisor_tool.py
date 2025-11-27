import sys
import os
# Ensure /app is in path to resolve 'src' packages correctly
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.mcp.tools.bank_advisor import BankAdvisorTool

@pytest.mark.asyncio
async def test_bank_advisor_tool_run_success():
    """Valida que una query clara devuelva un payload ui_render."""
    
    # Patch IntentService instead of AnalyticsService.resolve_metric_id as per current implementation
    with patch("src.bankadvisor.services.intent_service.IntentService.disambiguate") as mock_disambiguate, \
         patch("src.bankadvisor.services.intent_service.IntentService.get_section_config") as mock_get_config, \
         patch("src.bankadvisor.services.analytics_service.AnalyticsService.get_dashboard_data") as mock_get_data, \
         patch("src.bankadvisor.db.AsyncSessionLocal") as mock_session_cls:
        
        # Configurar Mocks
        # 1. Intent
        mock_intent = MagicMock()
        mock_intent.is_ambiguous = False
        mock_intent.resolved_id = "cartera_total_cuadro"
        mock_disambiguate.return_value = mock_intent
        
        mock_get_config.return_value = {
            "title": "Cartera Total",
            "field": "cartera_total",
            "type": "currency",
            "unit": "MM MXN"
        }

        # 2. Data
        mock_get_data.return_value = {
            "title": "Cartera Total",
            "chart_props": {"colors": ["rose"]},
            "data": {"months": [{"month_label": "Jul 2025", "data": [{"category": "Invex", "value": 100}]}]},
            "data_as_of": "15/08/2025"
        }
        
        # 3. Session
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        # Ejecutar Tool (usando execute y diccionario, no Input object directamente si usamos base Tool)
        tool = BankAdvisorTool()
        result = await tool.execute({"query": "cartera total", "mode": "auto"})

        # Validaciones
        assert result["type"] == "ui_render"
        assert result["component"] == "bank_advisor_dashboard"
        assert result["title"] == "Cartera Total"
        assert "content" in result
        assert result["content"]["data_as_of"] == "15/08/2025"
        
        mock_disambiguate.assert_called_with("cartera total")

@pytest.mark.asyncio
async def test_bank_advisor_tool_ambiguity():
    """Valida que una query ambigua devuelva error/guía."""
    
    with patch("src.bankadvisor.services.intent_service.IntentService.disambiguate") as mock_disambiguate, \
         patch("src.bankadvisor.db.AsyncSessionLocal") as mock_session_cls:
             
        # Simular ambigüedad
        mock_intent = MagicMock()
        mock_intent.is_ambiguous = True
        mock_intent.options = ["Opción A", "Opción B"]
        mock_disambiguate.return_value = mock_intent
        
        tool = BankAdvisorTool()
        result = await tool.execute({"query": "algo raro", "mode": "auto"})

        # Validaciones para flujo de error
        assert "error" in result
        assert result["error"] is True
        assert "ambigua" in result["message"]
        assert "Opción A" in result["message"]
