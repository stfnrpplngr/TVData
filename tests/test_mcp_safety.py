"""Safety-contract tests for every TVData MCP tool."""

import pytest
from mcp import Client

from mcp_server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_all_tools_are_explicitly_read_only_and_closed_world():
    async with Client(mcp, raise_exceptions=True) as client:
        listing = await client.list_tools()
        assert listing.tools, "TVData MCP must expose tools"

        for tool in listing.tools:
            annotations = tool.annotations
            assert annotations is not None, f"{tool.name}: annotations missing"
            assert annotations.read_only_hint is True, f"{tool.name}: read_only_hint must be true"
            assert annotations.open_world_hint is False, f"{tool.name}: open_world_hint must be false"
            assert annotations.destructive_hint is None, (
                f"{tool.name}: destructive_hint should be omitted for read-only tools"
            )
            assert annotations.idempotent_hint is None, (
                f"{tool.name}: idempotent_hint should be omitted for read-only tools"
            )
