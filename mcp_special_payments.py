"""Rule-aware annual special-payment calculations for TVData MCP.

The calculator is intentionally conditional: it never derives individual entitlement,
the tariff assessment base or payable twelfths from employment history. Those inputs
must already have been resolved by the caller or by a future dedicated payroll-rule
engine.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from pydantic import BaseModel

from mcp_analytics import AnalyticsError, read_metadata
from mcp_compensation import inspect_compensation_components


class AnnualSpecialPaymentRule(BaseModel):
    table_id: str
    allowance_id: str
    pay_grade: str
    step: str | None
    annual_rate_pct: float
    conditional_rate_applied: bool
    rate_rule: str
    valid_from: str | None
    entitlement_rule: str | None
    entitlement_reference_date: str | None
    assessment_base_rule: str | None
    assessment_months: list[str]
    assessment_exclusions: list[str]
    rate_reference_date: str | None
    late_start_threshold: str | None
    late_start_assessment_rule: str | None
    late_start_rate_rule: str | None
    partial_period_assessment_rule: str | None
    proration_rule: str | None
    payment_month: str | None
    rule_source: str | None
    excluded_contexts: list[str]
    complete_for_confirmed_input_calculation: bool
    warnings: list[str]


class AnnualSpecialPaymentCalculation(BaseModel):
    table_id: str
    allowance_id: str
    pay_grade: str
    step: str | None
    annual_rate_pct: float
    conditional_rate_applied: bool
    confirmed_assessment_base_monthly_eur: float
    payable_twelfths: int
    special_payment_eur: float
    calculation_formula: str
    rule_source: str | None
    warnings: list[str]


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _to_float(value: str | None, field_name: str) -> float:
    if value is None or not value.strip():
        raise AnalyticsError(f"Missing numeric rule field {field_name!r}.")
    try:
        result = float(value.strip().replace(",", "."))
    except ValueError as exc:
        raise AnalyticsError(f"Invalid numeric rule field {field_name!r}: {value!r}.") from exc
    if not math.isfinite(result):
        raise AnalyticsError(f"Non-finite numeric rule field {field_name!r}: {value!r}.")
    return result


def _valid_steps_for_grade(root: Path, table_id: str, pay_grade: str) -> list[str]:
    path = root / "tables" / table_id / "Table.csv"
    if not path.is_file():
        raise AnalyticsError(f"Missing pay table data file: {path}.")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise AnalyticsError(f"Empty pay table data file: {path}.") from exc
        steps = [cell.strip() for cell in header[1:]]
        for row in reader:
            if row and row[0].strip() == pay_grade:
                values = row[1:] + [""] * max(0, len(steps) - len(row[1:]))
                return [
                    step
                    for index, step in enumerate(steps)
                    if index < len(values) and values[index].strip()
                ]
    raise AnalyticsError(f"Unknown pay grade {pay_grade!r} in table {table_id!r}.")


def _annual_component(root: Path, table_id: str, pay_grade: str):
    inspection = inspect_compensation_components(root, table_id, pay_grade)
    matches = []
    for component in inspection.components:
        meta, _ = read_metadata(root / "allowances" / component.allowance_id)
        if meta.get("component_kind") == "annual_special_payment":
            matches.append((component, meta))
    if not matches:
        raise AnalyticsError(
            f"Pay table {table_id!r} has no linked component with component_kind='annual_special_payment'."
        )
    if len(matches) > 1:
        ids = ", ".join(component.allowance_id for component, _ in matches)
        raise AnalyticsError(
            f"Pay table {table_id!r} has multiple annual special-payment components ({ids}); selectivity must be modeled before calculation."
        )
    return matches[0]


def _resolve_annual_rate(
    root: Path,
    table_id: str,
    pay_grade: str,
    step: str | None,
    component,
    meta: dict[str, str],
) -> tuple[float, bool, str]:
    conditional_grade = meta.get("conditional_rate_grade")
    if conditional_grade and pay_grade == conditional_grade:
        if not step:
            raise AnalyticsError(
                f"Pay grade {pay_grade!r} has a step-dependent annual special-payment rate; step is required."
            )
        valid_steps = _valid_steps_for_grade(root, table_id, pay_grade)
        if step not in valid_steps:
            raise AnalyticsError(
                f"Unknown or unavailable step {step!r} for pay grade {pay_grade!r} in table {table_id!r}; valid steps: {valid_steps}."
            )
        matched_steps = set(_split(meta.get("conditional_rate_match_steps")))
        field_name = (
            "conditional_rate_match_pct"
            if step in matched_steps
            else "conditional_rate_other_pct"
        )
        annual_rate = _to_float(meta.get(field_name), field_name)
        return (
            annual_rate,
            True,
            meta.get("conditional_rate_rule") or "conditional_rate_metadata",
        )

    if step is not None:
        valid_steps = _valid_steps_for_grade(root, table_id, pay_grade)
        if step not in valid_steps:
            raise AnalyticsError(
                f"Unknown or unavailable step {step!r} for pay grade {pay_grade!r} in table {table_id!r}; valid steps: {valid_steps}."
            )

    yes_value = next((item for item in component.values if item.option == "yes"), None)
    if yes_value is None or yes_value.represented_annual_rate_pct is None:
        raise AnalyticsError(
            f"Annual special-payment component {component.allowance_id!r} does not expose a reconstructable 'yes' annual rate."
        )
    annual_rate = yes_value.represented_annual_rate_pct
    if not math.isfinite(annual_rate):
        raise AnalyticsError(
            f"Annual special-payment component {component.allowance_id!r} exposes a non-finite annual rate."
        )
    return annual_rate, False, "table_encoded_annual_rate"


def get_annual_special_payment_rule(
    root: Path,
    table_id: str,
    pay_grade: str,
    step: str | None = None,
) -> AnnualSpecialPaymentRule:
    """Return the formalized annual-special-payment rule for one pay position."""
    component, meta = _annual_component(root, table_id, pay_grade)
    annual_rate, conditional_rate_applied, rate_rule = _resolve_annual_rate(
        root,
        table_id,
        pay_grade,
        step,
        component,
        meta,
    )

    required = {
        "entitlement_rule": meta.get("entitlement_rule"),
        "entitlement_reference_date": meta.get("entitlement_reference_date"),
        "assessment_base_rule": meta.get("assessment_base_rule"),
        "assessment_months": meta.get("assessment_months"),
        "rate_reference_date": meta.get("rate_reference_date"),
        "late_start_threshold": meta.get("late_start_threshold"),
        "late_start_assessment_rule": meta.get("late_start_assessment_rule"),
        "partial_period_assessment_rule": meta.get("partial_period_assessment_rule"),
        "proration_rule": meta.get("proration_rule"),
        "payment_month": meta.get("payment_month"),
        "rule_source": meta.get("rule_source"),
    }
    missing = [key for key, value in required.items() if not value]
    warnings: list[str] = []
    if missing:
        warnings.append("Rule metadata is incomplete: " + ", ".join(missing) + ".")
    if component.excluded_contexts:
        warnings.append(
            "This rule excludes employment contexts: " + ", ".join(component.excluded_contexts) + "."
        )
    if conditional_rate_applied:
        warnings.append(
            f"A step-dependent conditional annual rate was applied for pay grade {pay_grade!r}, step {step!r}."
        )
    warnings.append(
        "The rule describes tariff semantics but does not infer individual entitlement, the assessment base or payable twelfths."
    )

    return AnnualSpecialPaymentRule(
        table_id=table_id,
        allowance_id=component.allowance_id,
        pay_grade=pay_grade,
        step=step,
        annual_rate_pct=annual_rate,
        conditional_rate_applied=conditional_rate_applied,
        rate_rule=rate_rule,
        valid_from=component.valid_from,
        entitlement_rule=meta.get("entitlement_rule") or None,
        entitlement_reference_date=meta.get("entitlement_reference_date") or None,
        assessment_base_rule=meta.get("assessment_base_rule") or None,
        assessment_months=_split(meta.get("assessment_months")),
        assessment_exclusions=_split(meta.get("assessment_exclusions")),
        rate_reference_date=meta.get("rate_reference_date") or None,
        late_start_threshold=meta.get("late_start_threshold") or None,
        late_start_assessment_rule=meta.get("late_start_assessment_rule") or None,
        late_start_rate_rule=meta.get("late_start_rate_rule") or None,
        partial_period_assessment_rule=meta.get("partial_period_assessment_rule") or None,
        proration_rule=meta.get("proration_rule") or None,
        payment_month=meta.get("payment_month") or None,
        rule_source=meta.get("rule_source") or None,
        excluded_contexts=component.excluded_contexts,
        complete_for_confirmed_input_calculation=not missing,
        warnings=warnings,
    )


def calculate_annual_special_payment(
    root: Path,
    table_id: str,
    pay_grade: str,
    confirmed_assessment_base_monthly_eur: float,
    payable_twelfths: int,
    entitlement_confirmed: bool,
    step: str | None = None,
    employment_context: str | None = None,
) -> AnnualSpecialPaymentCalculation:
    """Calculate one special payment from explicitly confirmed upstream inputs.

    This function performs arithmetic only. It does not decide whether the employee
    meets the tariff entitlement test, what belongs in the assessment base, or how
    many twelfths remain after exceptions.
    """
    rule = get_annual_special_payment_rule(root, table_id, pay_grade, step)
    if not rule.complete_for_confirmed_input_calculation:
        raise AnalyticsError(
            f"Annual special-payment rule for {rule.allowance_id!r} is incomplete and cannot be calculated safely."
        )
    if not entitlement_confirmed:
        raise AnalyticsError(
            "entitlement_confirmed must be true. TVData MCP does not infer individual entitlement from employment history."
        )
    if not math.isfinite(confirmed_assessment_base_monthly_eur):
        raise AnalyticsError("confirmed_assessment_base_monthly_eur must be finite.")
    if confirmed_assessment_base_monthly_eur < 0:
        raise AnalyticsError("confirmed_assessment_base_monthly_eur must be >= 0.")
    if payable_twelfths < 0 or payable_twelfths > 12:
        raise AnalyticsError("payable_twelfths must be between 0 and 12.")

    if rule.excluded_contexts:
        if not employment_context:
            raise AnalyticsError(
                "employment_context is required because this generic rule excludes special contexts: "
                + ", ".join(rule.excluded_contexts)
                + "."
            )
        if employment_context.casefold() in {item.casefold() for item in rule.excluded_contexts}:
            raise AnalyticsError(
                f"Employment context {employment_context!r} is excluded from generic rule {rule.allowance_id!r}."
            )

    payment = round(
        confirmed_assessment_base_monthly_eur
        * (rule.annual_rate_pct / 100.0)
        * (payable_twelfths / 12.0),
        2,
    )
    warnings = [
        "Arithmetic uses a caller-confirmed tariff assessment base; TVData did not derive it from table pay.",
        "payable_twelfths is caller-confirmed after resolving tariff reductions and exceptions.",
        "entitlement_confirmed is caller-confirmed; the MCP does not evaluate employment-history entitlement.",
        "Result is one gross special-payment component, not total annual compensation or net pay.",
    ]
    if rule.conditional_rate_applied:
        warnings.append(
            f"Conditional annual rate rule {rule.rate_rule!r} was applied for step {step!r}."
        )
    if rule.excluded_contexts:
        warnings.append(f"Calculation used explicit employment_context={employment_context!r}.")

    return AnnualSpecialPaymentCalculation(
        table_id=table_id,
        allowance_id=rule.allowance_id,
        pay_grade=pay_grade,
        step=step,
        annual_rate_pct=rule.annual_rate_pct,
        conditional_rate_applied=rule.conditional_rate_applied,
        confirmed_assessment_base_monthly_eur=confirmed_assessment_base_monthly_eur,
        payable_twelfths=payable_twelfths,
        special_payment_eur=payment,
        calculation_formula="assessment_base_monthly_eur * annual_rate_pct/100 * payable_twelfths/12",
        rule_source=rule.rule_source,
        warnings=warnings,
    )
