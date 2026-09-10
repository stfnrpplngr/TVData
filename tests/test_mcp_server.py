"""Contract tests for the read-only TVData MCP interface."""

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_lists_tv_l_and_reads_known_value():
    async with Client(mcp, raise_exceptions=True) as client:
        tables = await client.call_tool("list_pay_tables", {"query": "TV-L"})
        assert tables.is_error is False
        assert any(item["table_id"] == "TV-L" for item in tables.structured_content["result"])

        value = await client.call_tool(
            "get_base_pay",
            {"table_id": "TV-L", "pay_grade": "9b", "step": "3"},
        )
        assert value.is_error is False
        assert value.structured_content["table_id"] == "TV-L"
        assert value.structured_content["monthly_gross_eur"] == 4035.07
        assert value.structured_content["valid_from"] == "2026.04.01"


@pytest.mark.anyio
async def test_compares_tv_l_and_tvoed_bund_through_mcp():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "compare_pay_positions",
            {
                "positions": [
                    {
                        "table_id": "TV-L",
                        "pay_grade": "13",
                        "step": "4",
                        "weekly_hours_override": 40,
                    },
                    {
                        "table_id": "TVöD-Bund",
                        "pay_grade": "13",
                        "step": "4",
                    },
                ]
            },
        )
        assert result.is_error is False
        rows = result.structured_content["positions"]
        assert rows[0]["monthly_base_eur"] == 5873.56
        assert rows[1]["monthly_base_eur"] == 6177.31
        assert rows[1]["difference_from_first_eur"] == 303.75
        assert result.structured_content["comparability"]["total_compensation"] == "not calculated"


@pytest.mark.anyio
async def test_key_value_metadata_table_is_visible():
    async with Client(mcp, raise_exceptions=True) as client:
        tables = await client.call_tool("list_pay_tables", {"query": "Sachsen-Anhalt"})
        assert tables.is_error is False
        assert any(item["table_id"] == "Beamte-LSA-A" for item in tables.structured_content["result"])


@pytest.mark.anyio
async def test_unknown_table_is_model_correctable_error():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "get_base_pay",
            {"table_id": "does-not-exist", "pay_grade": "9b", "step": "3"},
        )
        assert result.is_error is True
        assert "Unknown pay table" in result.content[0].text
