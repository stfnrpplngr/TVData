"""MCP contract tests for P3 annual special-payment tools."""

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_rule_tool_exposes_late_start_semantics():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "get_annual_special_payment_rule",
            {"table_id": "TV-L", "pay_grade": "13"},
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["annual_rate_pct"] == pytest.approx(46.47, abs=0.001)
        assert payload["late_start_threshold"] == "08-31"
        assert payload["late_start_rate_rule"] == "pay_grade_on_start_date"
        assert payload["conditional_rate_applied"] is False


@pytest.mark.anyio
async def test_rule_tool_resolves_tv_l_e13ue_by_step():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "get_annual_special_payment_rule",
            {"table_id": "TV-L", "pay_grade": "13Ü", "step": "4"},
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["annual_rate_pct"] == pytest.approx(32.53, abs=0.001)
        assert payload["conditional_rate_applied"] is True
        assert payload["step"] == "4"


@pytest.mark.anyio
async def test_calculation_tool_uses_confirmed_inputs_only():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "calculate_annual_special_payment",
            {
                "table_id": "TVöD-Bund",
                "pay_grade": "13",
                "confirmed_assessment_base_monthly_eur": 6000.0,
                "payable_twelfths": 12,
                "entitlement_confirmed": True,
            },
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["annual_rate_pct"] == pytest.approx(75.0)
        assert payload["special_payment_eur"] == 4500.0
        assert "not total annual compensation" in payload["warnings"][-1]
