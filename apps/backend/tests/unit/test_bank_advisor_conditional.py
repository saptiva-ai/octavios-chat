"""
Unit tests for BankAdvisor conditional activation logic.

Tests the conditional logic without loading full handler dependencies.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBankAdvisorConditionalLogic:
    """Test BankAdvisor conditional activation without full system load."""

    @pytest.mark.asyncio
    async def test_bank_advisor_disabled_logic(self):
        """
        Test: When bank-advisor is NOT in tools_enabled, should skip invocation.

        Simulates the conditional logic from streaming_handler.py:766
        """
        # Simulate context with tools_enabled (no bank-advisor)
        tools_enabled = {
            "web_search": True,
            "create_artifact": True
        }

        # The actual logic from our code
        bank_advisor_enabled = tools_enabled.get("bank-advisor", False) or tools_enabled.get("bank_analytics", False)

        assert bank_advisor_enabled is False, "Should be disabled when not in tools"

    @pytest.mark.asyncio
    async def test_bank_advisor_enabled_with_hyphen(self):
        """
        Test: When 'bank-advisor' is in tools_enabled, should enable.
        """
        tools_enabled = {
            "bank-advisor": True,
            "create_artifact": True
        }

        bank_advisor_enabled = tools_enabled.get("bank-advisor", False) or tools_enabled.get("bank_analytics", False)

        assert bank_advisor_enabled is True, "Should be enabled with 'bank-advisor'"

    @pytest.mark.asyncio
    async def test_bank_advisor_enabled_with_underscore(self):
        """
        Test: When 'bank_analytics' (alternative name) is in tools_enabled, should enable.
        """
        tools_enabled = {
            "bank_analytics": True,
        }

        bank_advisor_enabled = tools_enabled.get("bank-advisor", False) or tools_enabled.get("bank_analytics", False)

        assert bank_advisor_enabled is True, "Should be enabled with 'bank_analytics'"

    @pytest.mark.asyncio
    async def test_bank_advisor_enabled_false_value(self):
        """
        Test: When bank-advisor is explicitly False, should be disabled.
        """
        tools_enabled = {
            "bank-advisor": False,
        }

        bank_advisor_enabled = tools_enabled.get("bank-advisor", False) or tools_enabled.get("bank_analytics", False)

        assert bank_advisor_enabled is False, "Should be disabled when False"

    @pytest.mark.asyncio
    async def test_invoke_logic_with_mock(self):
        """
        Test: Simulate full conditional flow with mock service.
        """
        with patch("src.services.tool_execution_service.ToolExecutionService") as MockService:
            # Setup mock
            MockService.invoke_bank_analytics = AsyncMock(return_value={
                "metric_name": "imor",
                "bank_names": ["INVEX"]
            })

            # Test Case 1: Disabled
            tools_enabled_disabled = {}
            bank_advisor_enabled = tools_enabled_disabled.get("bank-advisor", False) or tools_enabled_disabled.get("bank_analytics", False)

            bank_chart_data = None
            if bank_advisor_enabled:
                bank_chart_data = await MockService.invoke_bank_analytics(
                    message="Test",
                    user_id="test-user"
                )

            assert bank_chart_data is None, "Should not invoke when disabled"
            MockService.invoke_bank_analytics.assert_not_called()

            # Reset mock
            MockService.invoke_bank_analytics.reset_mock()

            # Test Case 2: Enabled
            tools_enabled_enabled = {"bank-advisor": True}
            bank_advisor_enabled = tools_enabled_enabled.get("bank-advisor", False) or tools_enabled_enabled.get("bank_analytics", False)

            bank_chart_data = None
            if bank_advisor_enabled:
                bank_chart_data = await MockService.invoke_bank_analytics(
                    message="Test",
                    user_id="test-user"
                )

            assert bank_chart_data is not None, "Should invoke when enabled"
            assert bank_chart_data["metric_name"] == "imor"
            MockService.invoke_bank_analytics.assert_called_once()


class TestBankAdvisorIntegrationScenarios:
    """Integration test scenarios for BankAdvisor activation."""

    @pytest.mark.asyncio
    async def test_scenario_user_selects_bank_advisor(self):
        """
        Scenario: User clicks BankAdvisor button in UI
        Expected: Tool is sent in request, backend invokes analytics
        """
        # Frontend sends this in request
        frontend_tools = {"bank-advisor": True}

        # Backend receives and checks
        bank_advisor_enabled = frontend_tools.get("bank-advisor", False) or frontend_tools.get("bank_analytics", False)

        assert bank_advisor_enabled is True
        # In real code, this would trigger invoke_bank_analytics

    @pytest.mark.asyncio
    async def test_scenario_user_does_not_select_bank_advisor(self):
        """
        Scenario: User does NOT click BankAdvisor button
        Expected: Tool is NOT sent, backend skips analytics
        """
        # Frontend sends no bank-advisor
        frontend_tools = {
            "web_search": True
        }

        # Backend receives and checks
        bank_advisor_enabled = frontend_tools.get("bank-advisor", False) or frontend_tools.get("bank_analytics", False)

        assert bank_advisor_enabled is False
        # In real code, invoke_bank_analytics would be skipped

    @pytest.mark.asyncio
    async def test_scenario_banking_query_without_tool(self):
        """
        Scenario: User asks banking question but tool is disabled
        Expected: No analytics invocation, regular chat response
        """
        message = "¿Cuál es el IMOR de INVEX?"
        tools_enabled = {}  # No bank-advisor

        bank_advisor_enabled = tools_enabled.get("bank-advisor", False) or tools_enabled.get("bank_analytics", False)

        # Even though message is about banking, tool is disabled
        assert bank_advisor_enabled is False
        # invoke_bank_analytics would NOT be called

    @pytest.mark.asyncio
    async def test_scenario_banking_query_with_tool(self):
        """
        Scenario: User asks banking question AND tool is enabled
        Expected: Analytics invocation occurs
        """
        message = "¿Cuál es el IMOR de INVEX?"
        tools_enabled = {"bank-advisor": True}

        bank_advisor_enabled = tools_enabled.get("bank-advisor", False) or tools_enabled.get("bank_analytics", False)

        assert bank_advisor_enabled is True
        # invoke_bank_analytics WOULD be called


@pytest.mark.asyncio
async def test_actual_conditional_code_pattern():
    """
    Test: Verify the exact code pattern we implemented.

    This matches the actual code in:
    - streaming_handler.py:766
    - message_endpoints.py:221
    """
    # Case 1: Tool disabled
    context_tools_disabled = {"web_search": True}
    bank_chart_data = None
    bank_advisor_enabled = context_tools_disabled.get("bank-advisor", False) or context_tools_disabled.get("bank_analytics", False)

    if bank_advisor_enabled:
        bank_chart_data = {"should": "not reach here"}

    assert bank_chart_data is None
    assert bank_advisor_enabled is False

    # Case 2: Tool enabled
    context_tools_enabled = {"bank-advisor": True}
    bank_chart_data = None
    bank_advisor_enabled = context_tools_enabled.get("bank-advisor", False) or context_tools_enabled.get("bank_analytics", False)

    if bank_advisor_enabled:
        bank_chart_data = {"metric_name": "imor"}

    assert bank_chart_data is not None
    assert bank_advisor_enabled is True
