"""MCP registration for compensation-component inspection and audit."""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from mcp_analytics import AnalyticsError
from mcp_compensation import (
    CompensationAuditReport,
    CompensationInspection,
    audit_compensation_components,
    inspect_compensation_components as inspect_components,
)


def register_compensation_tools(mcp, root: Path) -> None:
    """Register P2 read-only compensation semantics tools."""

    @mcp.tool()
    def inspect_compensation_components(
        table_id: str,
        pay_grade: str,
    ) -> CompensationInspection:
        """Inspect linked compensation components and their calculation readiness without calculating total annual compensation."""
        try:
            return inspect_components(root, table_id, pay_grade)
        except AnalyticsError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def audit_compensation_component_semantics(
        query: str | None = None,
        limit: int = 500,
    ) -> CompensationAuditReport:
        """Audit allowance encoding, options, provenance, temporal metadata and annualization readiness."""
        try:
            return audit_compensation_components(root, query, limit)
        except AnalyticsError as exc:
            raise ToolError(str(exc)) from exc
