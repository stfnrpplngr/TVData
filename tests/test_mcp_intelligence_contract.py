"""MCP contract tests for semantic and temporal tariff intelligence."""

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_resolves_human_pay_system_entity():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("resolve_pay_system_entity", {"query": "A13 LSA", "limit": 3})
        assert result.is_error is False
        payload = result.structured_content
        assert payload["jurisdiction_context_code"] == "DE-ST"
        assert payload["grade_prefix_hint"] == "A"
        assert payload["candidates"][0]["identity"]["table_id"] == "Beamte-LSA-A"


@pytest.mark.anyio
async def test_reads_historical_base_pay_by_date():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "get_base_pay_at_date",
            {"table_id": "TV-L", "pay_grade": "13", "step": "4", "as_of": "2023-06-01"},
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["snapshot"]["snapshot_id"] == "TV-L-2022"
        assert payload["monthly_base_eur"] == 5215.72


@pytest.mark.anyio
async def test_temporal_error_is_model_correctable():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "resolve_pay_table_as_of",
            {"table_id": "TV-L", "as_of": "2020-01-01"},
        )
        assert result.is_error is True
        assert "earliest known valid_from" in result.content[0].text
