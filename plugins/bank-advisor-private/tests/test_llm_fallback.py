"""
LLM Fallback Tests

Tests the hybrid intent classification strategy:
1. Rules-first classification
2. LLM fallback when rules are uncertain
3. Graceful degradation when LLM fails

Uses mocks to simulate LLM responses without actual API calls.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json

from bankadvisor.services.intent_service import NlpIntentService, Intent, ParsedIntent
from bankadvisor.entity_service import ExtractedEntities


class TestRulesFirstClassification:
    """Test that high-confidence rules bypass LLM."""

    @pytest.mark.asyncio
    async def test_comparison_keyword_bypasses_llm(self):
        """Test that comparison keywords get high confidence and skip LLM."""
        query = "IMOR de INVEX vs sistema"
        entities = ExtractedEntities(metric_id="imor")

        # Mock LLM to track if it's called
        with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
            result = await NlpIntentService.classify(query, entities, None)

            # Should be comparison with high confidence
            assert result.intent == Intent.COMPARISON
            assert result.confidence >= 0.9

            # LLM should NOT be called for high-confidence rules
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_date_range_bypasses_llm(self):
        """Test that date range queries get high confidence evolution intent."""
        query = "IMOR de INVEX en 2024"
        entities = ExtractedEntities(
            metric_id="imor",
            date_start="2024-01-01",
            date_end="2024-12-31"
        )

        with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
            result = await NlpIntentService.classify(query, entities, None)

            assert result.intent == Intent.EVOLUTION
            assert result.confidence >= 0.9
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_ranking_keyword_bypasses_llm(self):
        """Test that ranking keywords get high confidence."""
        query = "top 5 bancos por IMOR"
        entities = ExtractedEntities(metric_id="imor")

        with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
            result = await NlpIntentService.classify(query, entities, None)

            assert result.intent == Intent.RANKING
            assert result.confidence >= 0.9
            mock_llm.assert_not_called()


class TestLLMFallback:
    """Test that LLM is called for uncertain queries."""

    @pytest.mark.asyncio
    async def test_ambiguous_query_calls_llm(self):
        """Test that ambiguous queries trigger LLM fallback."""
        query = "IMOR de INVEX"  # No date, no comparison -> ambiguous
        entities = ExtractedEntities(metric_id="imor")

        # Mock rules to return low confidence
        rule_result = ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.5,
            explanation="Low confidence default"
        )

        # Mock LLM to return evolution
        llm_result = ParsedIntent(
            intent=Intent.EVOLUTION,
            confidence=0.85,
            explanation="LLM detected evolution intent"
        )

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock, return_value=llm_result):
                with patch.dict('os.environ', {'SAPTIVA_API_KEY': 'test-key'}):
                    result = await NlpIntentService.classify(query, entities, None)

                    # Should use LLM result since it has higher confidence
                    assert result.intent == Intent.EVOLUTION
                    assert result.confidence == 0.85


class TestLLMFailureGracefulDegradation:
    """Test graceful degradation when LLM fails."""

    @pytest.mark.asyncio
    async def test_llm_timeout_uses_rules(self):
        """Test that LLM timeout falls back to rules."""
        query = "IMOR de INVEX"
        entities = ExtractedEntities(metric_id="imor")

        rule_result = ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.6,
            explanation="Rule-based fallback"
        )

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
                # Simulate timeout
                import asyncio
                mock_llm.side_effect = asyncio.TimeoutError()

                with patch.dict('os.environ', {'SAPTIVA_API_KEY': 'test-key'}):
                    result = await NlpIntentService.classify(query, entities, None)

                    # Should fall back to rule result
                    assert result.intent == Intent.POINT_VALUE
                    assert result.confidence == 0.6

    @pytest.mark.asyncio
    async def test_llm_error_uses_rules(self):
        """Test that LLM errors fall back to rules."""
        query = "IMOR de INVEX"
        entities = ExtractedEntities(metric_id="imor")

        rule_result = ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.6,
            explanation="Rule-based fallback"
        )

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
                # Simulate API error
                mock_llm.side_effect = Exception("API Error: 500")

                with patch.dict('os.environ', {'SAPTIVA_API_KEY': 'test-key'}):
                    result = await NlpIntentService.classify(query, entities, None)

                    # Should fall back to rule result
                    assert result.intent == Intent.POINT_VALUE

    @pytest.mark.asyncio
    async def test_llm_invalid_response_uses_rules(self):
        """Test that invalid LLM response falls back to rules."""
        query = "IMOR de INVEX"
        entities = ExtractedEntities(metric_id="imor")

        rule_result = ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.6,
            explanation="Rule-based fallback"
        )

        # Mock LLM to return invalid intent
        llm_result = ParsedIntent(
            intent=Intent.UNKNOWN,
            confidence=0.3,
            explanation="Could not determine intent"
        )

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock, return_value=llm_result):
                with patch.dict('os.environ', {'SAPTIVA_API_KEY': 'test-key'}):
                    result = await NlpIntentService.classify(query, entities, None)

                    # Should prefer rule result since it has higher confidence
                    assert result.intent == Intent.POINT_VALUE
                    assert result.confidence == 0.6


class TestNoAPIKey:
    """Test behavior when no LLM API key is configured."""

    @pytest.mark.asyncio
    async def test_no_api_key_uses_rules(self):
        """Test that missing API key falls back to rules."""
        query = "IMOR de INVEX"
        entities = ExtractedEntities(metric_id="imor")

        rule_result = ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.5,
            explanation="Rule-based only"
        )

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
                # No API key in environment
                with patch.dict('os.environ', {'SAPTIVA_API_KEY': ''}, clear=True):
                    result = await NlpIntentService.classify(query, entities, None)

                    # Should use rules, LLM not called
                    assert result.intent == Intent.POINT_VALUE
                    mock_llm.assert_not_called()


class TestLLMFallbackDisabled:
    """Test behavior when LLM fallback is disabled in config."""

    @pytest.mark.asyncio
    async def test_llm_disabled_uses_rules(self):
        """Test that disabled LLM fallback uses rules only."""
        query = "IMOR de INVEX"
        entities = ExtractedEntities(metric_id="imor")

        rule_result = ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.5,
            explanation="Rule-based only"
        )

        # Mock runtime config to disable LLM
        mock_config = MagicMock()
        mock_config.rules_confidence_threshold = 0.9
        mock_config.llm_fallback_enabled = False

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
                with patch('bankadvisor.services.intent_service.get_runtime_config', return_value=mock_config):
                    result = await NlpIntentService.classify(query, entities, None)

                    # Should use rules, LLM not called
                    assert result.intent == Intent.POINT_VALUE
                    mock_llm.assert_not_called()


class TestConfidenceThreshold:
    """Test that confidence threshold is respected."""

    @pytest.mark.asyncio
    async def test_custom_confidence_threshold(self):
        """Test that custom confidence threshold works."""
        query = "IMOR de INVEX"
        entities = ExtractedEntities(metric_id="imor")

        # Rules return 0.85 confidence
        rule_result = ParsedIntent(
            intent=Intent.EVOLUTION,
            confidence=0.85,
            explanation="Medium confidence"
        )

        # Mock config with low threshold (0.8)
        mock_config = MagicMock()
        mock_config.rules_confidence_threshold = 0.8  # Lower threshold
        mock_config.llm_fallback_enabled = True

        with patch.object(NlpIntentService, '_classify_with_rules', return_value=rule_result):
            with patch.object(NlpIntentService, '_classify_with_llm', new_callable=AsyncMock) as mock_llm:
                with patch('bankadvisor.services.intent_service.get_runtime_config', return_value=mock_config):
                    result = await NlpIntentService.classify(query, entities, None)

                    # 0.85 >= 0.8, so should use rules without LLM
                    assert result.intent == Intent.EVOLUTION
                    mock_llm.assert_not_called()


# =============================================================================
# Integration Tests
# =============================================================================

class TestHybridStrategyIntegration:
    """Integration tests for the full hybrid strategy."""

    @pytest.mark.asyncio
    async def test_full_flow_comparison(self):
        """Test full flow for comparison query."""
        query = "IMOR de INVEX vs sistema"
        entities = ExtractedEntities(metric_id="imor")

        result = await NlpIntentService.classify(query, entities, None)

        assert result.intent == Intent.COMPARISON
        assert result.confidence >= 0.9
        assert "comparison" in result.explanation.lower() or "vs" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_full_flow_evolution(self):
        """Test full flow for evolution query."""
        query = "IMOR de INVEX en 2024"
        entities = ExtractedEntities(
            metric_id="imor",
            date_start="2024-01-01",
            date_end="2024-12-31"
        )

        result = await NlpIntentService.classify(query, entities, None)

        assert result.intent == Intent.EVOLUTION
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    async def test_full_flow_ranking(self):
        """Test full flow for ranking query."""
        query = "mejores bancos por ICAP en 2024"
        entities = ExtractedEntities(metric_id="icap")

        result = await NlpIntentService.classify(query, entities, None)

        assert result.intent == Intent.RANKING
        assert result.confidence >= 0.9
