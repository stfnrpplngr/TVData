"""MCP registration for rule-aware annual special payments."""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from mcp_analytics import AnalyticsError
from mcp_special_payments import (
    AnnualSpecialPaymentCalculation,
    AnnualSpecialPaymentRule,
    calculate_annual_special_payment as calculate_special_payment,
    get_annual_special_payment_rule as get_special_payment_rule,
)


def register_special_payment_tools(mcp, root: Path) -> None:
    """Register P3 read-only annual-special-payment rule and arithmetic tools."""

    @mcp.tool()
    def get_annual_special_payment_rule(
        table_id: str,
        pay_grade: str,
        step: str | None = None,
    ) -> AnnualSpecialPaymentRule:
        """Return formalized entitlement, assessment-base, proration and payment semantics; step is required for step-dependent rates."""
        try:
            return get_special_payment_rule(root, table_id, pay_grade, step)
        except AnalyticsError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def calculate_annual_special_payment(
        table_id: str,
        pay_grade: str,
        confirmed_assessment_base_monthly_eur: float,
        payable_twelfths: int,
        entitlement_confirmed: bool,
        step: str | None = None,
        employment_context: str | None = None,
    ) -> AnnualSpecialPaymentCalculation:
        """Calculate one gross annual special payment from caller-confirmed tariff inputs; never infer entitlement or assessment base."""
        try:
            return calculate_special_payment(
                root,
                table_id,
                pay_grade,
                confirmed_assessment_base_monthly_eur,
                payable_twelfths,
                entitlement_confirmed,
                step,
                employment_context,
            )
        except AnalyticsError as exc:
            raise ToolError(str(exc)) from exc
