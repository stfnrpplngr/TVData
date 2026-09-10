"""MCP contract tests for P2 compensation-component semantics."""

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_compensation_inspection_exposes_encoded_annual_rate():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "inspect_compensation_components",
            {"table_id": "TVöD-Bund", "pay_grade": "13"},
        )
        assert result.is_error is False
        payload = result.structured_content
        annual = next(
            item for item in payload["components"]
            if item["allowance_id"] == "tvoed-bund-annual-bonus"
        )
        yes = next(item for item in annual["values"] if item["option"] == "yes")
        assert yes["represented_annual_rate_pct"] == pytest.approx(75.0, abs=0.001)
        assert annual["calculation_readiness"] == "requires_tariff_assessment_base"
        assert annual["safe_for_total_annual_compensation"] is False


@pytest.mark.anyio
async def test_compensation_audit_is_exposed_through_mcp():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "audit_compensation_component_semantics",
            {"query": "tvoed-bund-annual-bonus"},
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["components_scanned"] == 1
        codes = {item["code"] for item in payload["issues"]}
        assert "assessment_base_required" in codes
