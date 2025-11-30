"""
Test suite for 9 priority visualizations.
Validates that each visualization can be generated with correct Plotly config.

Priority visualizations:
1. Cartera Comercial CC
2. Cartera Comercial Sin Gobierno
3. Pérdida Esperada Total
4. Reservas Totales
5. Reservas Totales (Variación)
6. IMOR
7. Cartera Vencida
8. ICOR
9. ICAP
"""
import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from bankadvisor.services.visualization_service import VisualizationService


class TestPriorityVisualizations:
    """Test each of the 9 priority visualizations."""

    @pytest.fixture
    def sample_data_single_month(self):
        """Sample data for comparison charts (single month)."""
        return [
            {
                "month_label": "Sep 2024",
                "data": [
                    {"category": "INVEX", "value": 1500000000},  # 1.5B
                    {"category": "SISTEMA", "value": 2500000000}  # 2.5B
                ]
            }
        ]

    @pytest.fixture
    def sample_data_timeline(self):
        """Sample data for timeline charts (multiple months)."""
        return [
            {
                "month_label": "Jul 2024",
                "data": [
                    {"category": "INVEX", "value": 1400000000},
                    {"category": "SISTEMA", "value": 2400000000}
                ]
            },
            {
                "month_label": "Aug 2024",
                "data": [
                    {"category": "INVEX", "value": 1450000000},
                    {"category": "SISTEMA", "value": 2450000000}
                ]
            },
            {
                "month_label": "Sep 2024",
                "data": [
                    {"category": "INVEX", "value": 1500000000},
                    {"category": "SISTEMA", "value": 2500000000}
                ]
            }
        ]

    @pytest.fixture
    def sample_data_ratios(self):
        """Sample data for ratio-based metrics (IMOR, ICOR, ICAP)."""
        return [
            {
                "month_label": "Jul 2024",
                "data": [
                    {"category": "INVEX", "value": 0.025},  # 2.5%
                    {"category": "SISTEMA", "value": 0.032}  # 3.2%
                ]
            },
            {
                "month_label": "Aug 2024",
                "data": [
                    {"category": "INVEX", "value": 0.024},
                    {"category": "SISTEMA", "value": 0.031}
                ]
            },
            {
                "month_label": "Sep 2024",
                "data": [
                    {"category": "INVEX", "value": 0.023},
                    {"category": "SISTEMA", "value": 0.030}
                ]
            }
        ]

    # =========================================================================
    # Test 1: Cartera Comercial CC
    # =========================================================================
    def test_1_cartera_comercial_cc(self, sample_data_single_month):
        """Test Cartera Comercial CC visualization (bar comparison)."""
        config = {
            "title": "Cartera Comercial CC",
            "unit": "Millones MXN",
            "mode": "dashboard_month_comparison",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(sample_data_single_month, config)

        assert result["data"][0]["type"] == "bar"
        assert "Cartera Comercial CC" in result["layout"]["title"]
        assert len(result["data"][0]["x"]) == 2  # INVEX + SISTEMA
        assert result["data"][0]["y"][0] == 1500000000

    # =========================================================================
    # Test 2: Cartera Comercial Sin Gobierno
    # =========================================================================
    def test_2_cartera_comercial_sin_gob(self, sample_data_single_month):
        """Test Cartera Comercial Sin Gobierno visualization."""
        config = {
            "title": "Cartera Comercial Sin Gobierno",
            "unit": "Millones MXN",
            "mode": "dashboard_month_comparison",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(sample_data_single_month, config)

        assert result["data"][0]["type"] == "bar"
        assert "Cartera Comercial Sin Gobierno" in result["layout"]["title"]

    # =========================================================================
    # Test 3: Pérdida Esperada Total (Timeline)
    # =========================================================================
    def test_3_perdida_esperada_total(self, sample_data_timeline):
        """Test Pérdida Esperada Total visualization (line chart)."""
        config = {
            "title": "Pérdida Esperada Total",
            "unit": "Millones MXN",
            "mode": "timeline_with_summary",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(sample_data_timeline, config)

        assert len(result["data"]) == 2  # INVEX trace + SISTEMA trace
        assert result["data"][0]["type"] == "scatter"
        assert result["data"][0]["mode"] == "lines+markers"
        assert len(result["data"][0]["x"]) == 3  # 3 months

    # =========================================================================
    # Test 4: Reservas Totales
    # =========================================================================
    def test_4_reservas_totales(self, sample_data_single_month):
        """Test Reservas Totales visualization (bar comparison)."""
        config = {
            "title": "Reservas Totales",
            "unit": "Millones MXN",
            "mode": "dashboard_month_comparison",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(sample_data_single_month, config)

        assert result["data"][0]["type"] == "bar"
        assert "Reservas Totales" in result["layout"]["title"]

    # =========================================================================
    # Test 5: Reservas Totales (Variación) - SPECIAL
    # =========================================================================
    def test_5_reservas_variacion(self, sample_data_timeline):
        """Test Reservas Totales (Variación %) visualization."""
        config = {
            "title": "Reservas Totales (Variación %)",
            "unit": "%",
            "mode": "variation_chart",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(sample_data_timeline, config)

        assert result["data"][0]["type"] == "bar"
        assert result["layout"]["barmode"] == "group"
        assert len(result["data"][0]["x"]) == 2  # 3 meses → 2 variaciones

        # Verificar que calcula variación correcta
        # (1450000000 - 1400000000) / 1400000000 * 100 ≈ 3.57%
        assert abs(result["data"][0]["y"][0] - 3.57) < 0.1
        # (1500000000 - 1450000000) / 1450000000 * 100 ≈ 3.45%
        assert abs(result["data"][0]["y"][1] - 3.45) < 0.1

    # =========================================================================
    # Test 6: IMOR (dual mode - timeline)
    # =========================================================================
    def test_6_imor_timeline(self, sample_data_ratios):
        """Test IMOR evolution visualization (line chart)."""
        config = {
            "title": "Índice de Morosidad (IMOR)",
            "unit": "%",
            "mode": "timeline_with_summary",
            "type": "ratio"
        }
        result = VisualizationService.build_plotly_config(sample_data_ratios, config)

        assert len(result["data"]) == 2  # INVEX + SISTEMA traces
        assert result["data"][0]["type"] == "scatter"
        assert result["layout"]["yaxis"]["tickformat"] == ".1%"

    def test_6b_imor_comparison(self, sample_data_ratios):
        """Test IMOR comparison visualization (bar chart)."""
        config = {
            "title": "Índice de Morosidad (IMOR)",
            "unit": "%",
            "mode": "dashboard_month_comparison",
            "type": "ratio"
        }
        result = VisualizationService.build_plotly_config(sample_data_ratios, config)

        assert result["data"][0]["type"] == "bar"

    # =========================================================================
    # Test 7: Cartera Vencida (dual mode)
    # =========================================================================
    def test_7_cartera_vencida(self, sample_data_timeline):
        """Test Cartera Vencida visualization (timeline)."""
        config = {
            "title": "Cartera Vencida",
            "unit": "Millones MXN",
            "mode": "timeline_with_summary",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(sample_data_timeline, config)

        assert result["data"][0]["type"] == "scatter"
        assert "Evolución Cartera Vencida" in result["layout"]["title"]

    # =========================================================================
    # Test 8: ICOR (dual mode)
    # =========================================================================
    def test_8_icor_timeline(self, sample_data_ratios):
        """Test ICOR evolution visualization."""
        config = {
            "title": "Índice de Cobertura (ICOR)",
            "unit": "%",
            "mode": "timeline_with_summary",
            "type": "ratio"
        }
        result = VisualizationService.build_plotly_config(sample_data_ratios, config)

        assert result["data"][0]["type"] == "scatter"
        assert result["layout"]["yaxis"]["tickformat"] == ".1%"

    # =========================================================================
    # Test 9: ICAP (dual mode with enhanced)
    # =========================================================================
    def test_9_icap_enhanced_evolution(self, sample_data_ratios):
        """Test ICAP with enhanced config (evolution intent)."""
        config = {
            "title": "Índice de Capitalización (ICAP)",
            "unit": "%",
            "mode": "dual_mode",
            "type": "ratio"
        }
        result = VisualizationService.build_plotly_config_enhanced(
            sample_data_ratios, config, intent="evolution"
        )

        assert result["data"][0]["type"] == "scatter"
        assert result["data"][0]["mode"] == "lines+markers"

    def test_9b_icap_enhanced_comparison(self, sample_data_ratios):
        """Test ICAP with enhanced config (comparison intent)."""
        config = {
            "title": "Índice de Capitalización (ICAP)",
            "unit": "%",
            "mode": "dual_mode",
            "type": "ratio"
        }
        result = VisualizationService.build_plotly_config_enhanced(
            sample_data_ratios, config, intent="comparison"
        )

        assert result["data"][0]["type"] == "bar"

    # =========================================================================
    # Smoke Test: All 9 visualizations render without errors
    # =========================================================================
    def test_all_9_visualizations_smoke(self):
        """Smoke test: ensure all 9 visualizations can be instantiated."""
        visualizations = [
            ("Cartera Comercial CC", "dashboard_month_comparison", "currency"),
            ("Cartera Comercial Sin Gob", "dashboard_month_comparison", "currency"),
            ("Pérdida Esperada Total", "timeline_with_summary", "currency"),
            ("Reservas Totales", "dashboard_month_comparison", "currency"),
            ("Reservas Totales (Variación)", "variation_chart", "currency"),
            ("IMOR", "timeline_with_summary", "ratio"),
            ("Cartera Vencida", "timeline_with_summary", "currency"),
            ("ICOR", "timeline_with_summary", "ratio"),
            ("ICAP", "timeline_with_summary", "ratio"),
        ]

        dummy_data = [
            {"month_label": "Sep 2024", "data": [{"category": "INVEX", "value": 100}]}
        ]

        for title, mode, vtype in visualizations:
            config = {"title": title, "unit": "%", "mode": mode, "type": vtype}
            result = VisualizationService.build_plotly_config(dummy_data, config)
            assert result is not None
            assert "layout" in result
            assert "data" in result
            print(f"✅ {title} - OK")

    # =========================================================================
    # Edge Cases
    # =========================================================================
    def test_variation_chart_insufficient_data(self):
        """Test variation chart with only 1 month (should handle gracefully)."""
        data_one_month = [
            {"month_label": "Sep 2024", "data": [{"category": "INVEX", "value": 100}]}
        ]
        config = {
            "title": "Reservas (Variación)",
            "unit": "%",
            "mode": "variation_chart",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(data_one_month, config)

        # Should return error/empty state
        assert "Datos insuficientes" in result["layout"]["title"]

    def test_null_values_handling(self):
        """Test that NULL values don't break visualizations."""
        data_with_nulls = [
            {
                "month_label": "Sep 2024",
                "data": [
                    {"category": "INVEX", "value": None},
                    {"category": "SISTEMA", "value": 2500000000}
                ]
            }
        ]
        config = {
            "title": "Test Nulls",
            "unit": "Millones MXN",
            "mode": "dashboard_month_comparison",
            "type": "currency"
        }
        result = VisualizationService.build_plotly_config(data_with_nulls, config)

        # Should not crash, should handle None → 0
        assert result["data"][0]["y"][0] == 0  # None converted to 0
