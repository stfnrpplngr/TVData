"""Compensation-component semantics and audit layer for TVData MCP.

This module inspects allowance encodings and calculation readiness. It does not
calculate total annual compensation unless component semantics and assessment
bases are explicitly modeled.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from mcp_analytics import AnalyticsError, read_metadata
from mcp_context import assess_source_url


Encoding = Literal[
    "absolute_monthly",
    "absolute_yearly",
    "relative_monthly",
    "relative_yearly",
    "unknown",
]
Readiness = Literal[
    "arithmetic_only_if_entitled_full_year",
    "direct_annual_value_if_entitled",
    "requires_defined_base",
    "requires_tariff_assessment_base",
    "unsupported",
]


class ComponentOptionValue(BaseModel):
    option: str
    raw_value: str | None
    numeric_value: float | None
    represented_annual_rate_pct: float | None


class CompensationComponentProfile(BaseModel):
    allowance_id: str
    label_de: str | None
    label_en: str | None
    pay_grade: str
    func_type: str | None
    adding_type: str | None
    value_semantics: str | None
    encoding: Encoding
    calculation_readiness: Readiness
    default_option: str | None
    options: list[str]
    values: list[ComponentOptionValue]
    valid_from: str | None
    scope: str | None
    excluded_contexts: list[str]
    source: str | None
    source_quality: Literal["high", "medium", "unknown", "missing"]
    safe_for_total_annual_compensation: bool
    warnings: list[str]


class CompensationInspection(BaseModel):
    table_id: str
    pay_grade: str
    linked_components: int
    components: list[CompensationComponentProfile]
    warnings: list[str]


class CompensationAuditIssue(BaseModel):
    allowance_id: str
    severity: Literal["error", "warning", "info"]
    code: str
    message: str


class CompensationAuditReport(BaseModel):
    components_scanned: int
    issue_counts: dict[str, int]
    issues: list[CompensationAuditIssue]


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _to_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def _read_matrix(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    if not path.is_file():
        raise AnalyticsError(f"Missing data file: {path}.")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise AnalyticsError(f"Empty data file: {path}.") from exc
        if len(header) < 2:
            raise AnalyticsError(f"Invalid matrix schema: {path}.")
        columns = [cell.strip() for cell in header[1:]]
        rows: dict[str, dict[str, str]] = {}
        for raw in reader:
            if not raw or not raw[0].strip():
                continue
            values = raw[1:] + [""] * max(0, len(columns) - len(raw[1:]))
            rows[raw[0].strip()] = {
                column: values[index].strip() if index < len(values) else ""
                for index, column in enumerate(columns)
            }
    return columns, rows


def _encoding(func_type: str | None, adding_type: str | None) -> Encoding:
    mapping: dict[tuple[str, str], Encoding] = {
        ("fabsolute", "monthly"): "absolute_monthly",
        ("fabsolute", "yearly"): "absolute_yearly",
        ("frelative", "monthly"): "relative_monthly",
        ("frelative", "yearly"): "relative_yearly",
    }
    return mapping.get(((func_type or "").casefold(), (adding_type or "").casefold()), "unknown")


def _readiness(encoding: Encoding) -> Readiness:
    return {
        "absolute_monthly": "arithmetic_only_if_entitled_full_year",
        "absolute_yearly": "direct_annual_value_if_entitled",
        "relative_monthly": "requires_defined_base",
        "relative_yearly": "requires_tariff_assessment_base",
        "unknown": "unsupported",
    }[encoding]


def _quality(root: Path, source: str | None) -> Literal["high", "medium", "unknown", "missing"]:
    if not source:
        return "missing"
    assessments = [assess_source_url(root, url) for url in _split(source)]
    if any(item.quality_tier == "high" for item in assessments):
        return "high"
    if any(item.quality_tier == "medium" for item in assessments):
        return "medium"
    return "unknown"


def _component_profile(
    root: Path,
    allowance_id: str,
    pay_grade: str,
) -> CompensationComponentProfile:
    directory = root / "allowances" / allowance_id
    if not directory.is_dir():
        raise AnalyticsError(f"Unknown allowance: {allowance_id!r}.")
    meta, _ = read_metadata(directory)
    columns, rows = _read_matrix(directory / "Table.csv")
    row = rows.get(pay_grade) or rows.get("-1")
    values: list[ComponentOptionValue] = []
    semantics = meta.get("value_semantics") or None
    if row is not None:
        for option in columns:
            raw = row.get(option) or None
            numeric = _to_float(raw)
            annual_rate = (
                round(numeric * 12, 6)
                if numeric is not None and semantics == "annual_percentage_divided_by_12"
                else None
            )
            values.append(
                ComponentOptionValue(
                    option=option,
                    raw_value=raw,
                    numeric_value=numeric,
                    represented_annual_rate_pct=annual_rate,
                )
            )

    encoding = _encoding(meta.get("func_type"), meta.get("adding_type"))
    readiness = _readiness(encoding)
    warnings: list[str] = []
    if row is None:
        warnings.append(
            f"No allowance row exists for pay grade {pay_grade!r} and no '-1' fallback is defined."
        )
    if encoding == "relative_yearly":
        warnings.append(
            "Relative yearly components require the tariff-specific assessment base; the stored factor alone is insufficient for exact annual compensation."
        )
    if semantics == "annual_percentage_divided_by_12":
        warnings.append(
            "represented_annual_rate_pct reconstructs the encoded tariff percentage only; it does not calculate the payment amount."
        )
    excluded = _split(meta.get("excluded_contexts"))
    if excluded:
        warnings.append(
            "This generic component explicitly excludes contexts: " + ", ".join(excluded) + "."
        )
    if not meta.get("link"):
        warnings.append("No component-specific source link is documented.")
    if not meta.get("valid_from") and encoding == "relative_yearly":
        warnings.append("No component-specific valid_from date is documented.")

    return CompensationComponentProfile(
        allowance_id=allowance_id,
        label_de=meta.get("label_de") or None,
        label_en=meta.get("label_en") or None,
        pay_grade=pay_grade,
        func_type=meta.get("func_type") or None,
        adding_type=meta.get("adding_type") or None,
        value_semantics=semantics,
        encoding=encoding,
        calculation_readiness=readiness,
        default_option=meta.get("default_option") or None,
        options=_split(meta.get("options")) or columns,
        values=values,
        valid_from=meta.get("valid_from") or None,
        scope=meta.get("scope") or None,
        excluded_contexts=excluded,
        source=meta.get("link") or None,
        source_quality=_quality(root, meta.get("link")),
        safe_for_total_annual_compensation=False,
        warnings=warnings,
    )


def inspect_compensation_components(
    root: Path,
    table_id: str,
    pay_grade: str,
) -> CompensationInspection:
    table_dir = root / "tables" / table_id
    if not table_dir.is_dir():
        raise AnalyticsError(f"Unknown pay table: {table_id!r}.")
    meta, _ = read_metadata(table_dir)
    allowance_ids = _split(meta.get("allowances"))
    components: list[CompensationComponentProfile] = []
    warnings: list[str] = []
    for allowance_id in allowance_ids:
        try:
            components.append(_component_profile(root, allowance_id, pay_grade))
        except AnalyticsError as exc:
            warnings.append(f"{allowance_id}: {exc}")
    if not allowance_ids:
        warnings.append("No allowance components are linked from this pay table.")
    if any(component.safe_for_total_annual_compensation is False for component in components):
        warnings.append(
            "At least one linked component is not safe for automatic inclusion in total annual compensation."
        )
    return CompensationInspection(
        table_id=table_id,
        pay_grade=pay_grade,
        linked_components=len(allowance_ids),
        components=components,
        warnings=warnings,
    )


def _explicit_years(meta: dict[str, str]) -> set[int]:
    text = " ".join(meta.get(key, "") for key in ("info", "info_de", "info_en"))
    return {int(value) for value in re.findall(r"\b20\d{2}\b", text)}


def audit_compensation_components(
    root: Path,
    query: str | None = None,
    limit: int = 500,
) -> CompensationAuditReport:
    if limit < 1 or limit > 2000:
        raise AnalyticsError("limit must be between 1 and 2000.")
    issues: list[CompensationAuditIssue] = []
    scanned = 0
    allowance_root = root / "allowances"
    for directory in sorted(
        (path for path in allowance_root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    ):
        if query and query.casefold() not in directory.name.casefold():
            continue
        scanned += 1
        allowance_id = directory.name
        try:
            meta, _ = read_metadata(directory)
        except AnalyticsError as exc:
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="error",
                    code="invalid_metadata",
                    message=str(exc),
                )
            )
            continue
        try:
            columns, rows = _read_matrix(directory / "Table.csv")
        except AnalyticsError as exc:
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="error",
                    code="invalid_component_table",
                    message=str(exc),
                )
            )
            continue

        encoding = _encoding(meta.get("func_type"), meta.get("adding_type"))
        if encoding == "unknown":
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="error",
                    code="unknown_encoding",
                    message=f"Unsupported func_type/adding_type combination: {meta.get('func_type')!r}/{meta.get('adding_type')!r}.",
                )
            )

        declared_options = _split(meta.get("options"))
        if declared_options and declared_options != columns:
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="warning",
                    code="option_schema_mismatch",
                    message=f"Meta options {declared_options!r} differ from table columns {columns!r}.",
                )
            )
        default = meta.get("default_option")
        if default and default not in columns:
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="error",
                    code="invalid_default_option",
                    message=f"default_option {default!r} is not a table option.",
                )
            )

        nonnumeric = sum(
            1
            for row in rows.values()
            for value in row.values()
            if value and _to_float(value) is None
        )
        if nonnumeric:
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="error",
                    code="nonnumeric_values",
                    message=f"{nonnumeric} non-empty component values are non-numeric.",
                )
            )

        if encoding == "relative_yearly":
            if not meta.get("value_semantics"):
                issues.append(
                    CompensationAuditIssue(
                        allowance_id=allowance_id,
                        severity="warning",
                        code="relative_yearly_semantics_implicit",
                        message="Relative yearly encoding lacks an explicit value_semantics declaration.",
                    )
                )
            if not meta.get("link"):
                issues.append(
                    CompensationAuditIssue(
                        allowance_id=allowance_id,
                        severity="warning",
                        code="missing_component_source",
                        message="Relative yearly component has no component-specific source URL.",
                    )
                )
            if not meta.get("valid_from"):
                issues.append(
                    CompensationAuditIssue(
                        allowance_id=allowance_id,
                        severity="warning",
                        code="missing_component_valid_from",
                        message="Relative yearly component has no component-specific valid_from date.",
                    )
                )
            if meta.get("value_semantics") == "annual_percentage_divided_by_12":
                issues.append(
                    CompensationAuditIssue(
                        allowance_id=allowance_id,
                        severity="info",
                        code="assessment_base_required",
                        message="Encoded annual percentage is reconstructable, but payment amount still requires the tariff-specific assessment base.",
                    )
                )

        source = meta.get("link")
        quality = _quality(root, source)
        if source and quality == "unknown":
            issues.append(
                CompensationAuditIssue(
                    allowance_id=allowance_id,
                    severity="info",
                    code="unclassified_component_source",
                    message="Component source domain is not classified in the MCP source registry.",
                )
            )

        valid_from = meta.get("valid_from")
        years = _explicit_years(meta)
        if valid_from and years:
            try:
                valid_year = int(valid_from[:4])
            except ValueError:
                valid_year = 0
            if valid_year and max(years) < valid_year:
                issues.append(
                    CompensationAuditIssue(
                        allowance_id=allowance_id,
                        severity="warning",
                        code="possibly_stale_description",
                        message=f"Description mentions years through {max(years)}, earlier than valid_from year {valid_year}.",
                    )
                )

        if len(issues) >= limit:
            break

    counts = {
        severity: sum(1 for issue in issues if issue.severity == severity)
        for severity in ("error", "warning", "info")
    }
    return CompensationAuditReport(
        components_scanned=scanned,
        issue_counts=counts,
        issues=issues[:limit],
    )
