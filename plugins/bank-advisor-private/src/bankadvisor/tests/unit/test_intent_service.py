import pytest
from bankadvisor.services.intent_service import IntentService, AmbiguityResult

# Setup: Ensure sections.yaml is loaded (IntentService does this internally on first call)

def test_disambiguate_exact_match():
    """Caso A: Coincidencia exacta o muy clara."""
    # "Cartera Total" es claro y el sistema prefiere la versión "_cuadro" si hay conflicto con gráfica.
    result = IntentService.disambiguate("Cartera Total")
    
    assert isinstance(result, AmbiguityResult)
    assert result.is_ambiguous is False
    assert result.resolved_id == "cartera_total_cuadro"
    assert not result.options

def test_disambiguate_genuine_ambiguity():
    """Caso B: Término ambiguo que requiere clarificación."""
    # "Cartera Comercial" coincide con "Cartera Comercial" y "Cartera Comercial sin Ent. Gub."
    result = IntentService.disambiguate("Cartera Comercial")
    
    assert result.is_ambiguous is True
    assert len(result.options) >= 2
    # Verificar que las opciones son títulos legibles
    assert "Cartera Comercial" in result.options
    
def test_disambiguate_unknown_term():
    """Caso C: Término desconocido."""
    result = IntentService.disambiguate("receta de cocina")
    
    # El servicio devuelve ambigüedad por defecto con opciones generales
    assert result.is_ambiguous is True
    assert "Cartera Total" in result.options  # Fallback options
    assert result.missing_dimension == "tema desconocido"