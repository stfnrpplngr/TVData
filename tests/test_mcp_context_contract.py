"""MCP contract tests for P1 context, manifest and provenance tools."""

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_manifest_is_exposed_through_mcp():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("get_application_profile_manifest", {})
        assert result.is_error is False
        payload = result.structured_content
        assert payload["profile_id"] == "tvdata-tariff-intelligence"
        assert payload["profile_version"] == "0.4.0"


@pytest.mark.anyio
async def test_tv_l_working_time_uses_jurisdiction_context():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "resolve_weekly_working_time",
            {"table_id": "TV-L", "jurisdiction_code": "DE-ST"},
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["status"] == "resolved_context"
        assert payload["weekly_hours"] == 40.0
        assert payload["jurisdiction_name_de"] == "Sachsen-Anhalt"


@pytest.mark.anyio
async def test_contextual_comparison_resolves_working_time_automatically():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(
            "compare_pay_positions_with_context",
            {
                "positions": [
                    {"table_id": "TV-L", "pay_grade": "13", "step": "4", "jurisdiction_code": "DE-ST"},
                    {"table_id": "TVöD-Bund", "pay_grade": "13", "step": "4"},
                ]
            },
        )
        assert result.is_error is False
        payload = result.structured_content
        assert payload["comparison"]["positions"][0]["weekly_hours"] == 40.0
        assert payload["comparison"]["positions"][1]["weekly_hours"] == 39.0
        assert payload["comparison"]["positions"][1]["monthly_base_eur"] == 6177.31


@pytest.mark.anyio
async def test_provenance_assessment_classifies_updated_tvoed_source():
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool("assess_pay_system_provenance", {"table_id": "TVöD-Bund"})
        assert result.is_error is False
        payload = result.structured_content
        assert payload["pay_evidence_quality"] == "high"
        assert payload["pay_sources"][0]["registry_match"] == "dbb.de"
