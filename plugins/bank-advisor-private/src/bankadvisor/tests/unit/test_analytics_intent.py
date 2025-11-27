import pytest
from bankadvisor.services.analytics_service import AnalyticsService

class TestIntentService:
    
    def test_exact_match_detection(self):
        """Caso A: El usuario pide algo exacto que existe en el mapa."""
        query = "cartera comercial"
        # Nota: AnalyticsService.resolve_metric_id usa el mapa interno.
        # Según el código actual: "cartera comercial" -> "cartera_comercial_total"
        # Ajusta la aserción según tu TOPIC_MAP real en analytics_service.py
        resolved_id = AnalyticsService.resolve_metric_id(query)
        assert resolved_id == "cartera_comercial_total", f"Esperado 'cartera_comercial_total', recibido '{resolved_id}'"

    def test_fuzzy_match_detection(self):
        """Caso A (Variante): El usuario tiene un typo leve o usa sinónimos."""
        query = "morosidad" 
        resolved_id = AnalyticsService.resolve_metric_id(query)
        # Según TOPIC_MAP actual: "morosidad" -> "imor"
        assert resolved_id == "imor", f"Esperado 'imor', recibido '{resolved_id}'"

    def test_unknown_term(self):
        """Caso C: El usuario pide algo fuera del dominio financiero."""
        query = "receta de pastel"
        resolved_id = AnalyticsService.resolve_metric_id(query)
        assert resolved_id is None, "Debería retornar None para términos desconocidos"
