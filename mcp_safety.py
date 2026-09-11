"""Safety defaults for the read-only TVData MCP application interface."""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations


READ_ONLY_CLOSED_WORLD = ToolAnnotations(
    read_only_hint=True,
    open_world_hint=False,
)


class ReadOnlyMCPServer(MCPServer):
    """MCPServer whose tools default to read-only, closed-world annotations.

    TVData tools inspect versioned repository data and perform deterministic local
    calculations. They do not mutate canonical data or reach arbitrary external
    entities. Centralizing the default prevents separately registered tool families
    from silently omitting the same safety contract.
    """

    def tool(self, *args, **kwargs):
        kwargs.setdefault("annotations", READ_ONLY_CLOSED_WORLD)
        return super().tool(*args, **kwargs)
