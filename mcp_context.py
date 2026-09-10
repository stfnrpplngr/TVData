"""P1 context, versioning and provenance helpers for the TVData MCP profile."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from mcp_analytics import AnalyticsError, ComparisonResult, PayPositionRequest, compare_positions, read_metadata


class ProfileManifest(BaseModel):
    profile_id: str
    profile_version: str
    schema_version: str
    stability: str
    source_of_truth: str
    mcp_sdk_compatibility: str
    principle: str
    capabilities: list[str]
    guardrails: list[str]
    profile_data: dict[str, str]


class WorkingTimeResolution(BaseModel):
    table_id: str
    jurisdiction_code: str | None
    jurisdiction_name_de: str | None
    employment_context: str
    requested_as_of: str | None
    status: Literal[
        "resolved_context",
        "resolved_table_default",
        "unresolved_context_required",
        "no_known_record",
    ]
    weekly_hours: float | None
    weekly_hours_hhmm: str | None
    valid_from: str | None
    valid_to: str | None
    source_url: str | None
    legal_basis_url: str | None
    evidence_quality: Literal["high", "medium", "unknown"]
    available_jurisdictions: list[str]
    warning: str | None


class ContextualPayPositionRequest(BaseModel):
    table_id: str
    pay_grade: str
    step: str
    jurisdiction_code: str | None = None
    weekly_hours_override: float | None = Field(default=None, gt=0, le=80)


class ContextualComparisonResult(BaseModel):
    comparison: ComparisonResult
    working_time_resolutions: list[WorkingTimeResolution]
    warnings: list[str]


class SourceReferenceAssessment(BaseModel):
    url: str
    domain: str
    source_class: str
    authority_level: str
    role: str
    quality_tier: Literal["high", "medium", "unknown"]
    registry_match: str | None


class PaySystemSourceAssessment(BaseModel):
    table_id: str
    valid_from: str | None
    pay_sources: list[SourceReferenceAssessment]
    working_time_sources: list[SourceReferenceAssessment]
    pay_evidence_quality: Literal["high", "medium", "unknown", "missing"]
    working_time_evidence_quality: Literal["high", "medium", "unknown", "missing"]
    warnings: list[str]


class SourceAuditIssue(BaseModel):
    table_id: str
    severity: Literal["error", "warning", "info"]
    code: str
    message: str


class SourceAuditReport(BaseModel):
    tables_scanned: int
    issue_counts: dict[str, int]
    issues: list[SourceAuditIssue]


def _profile_dir(root: Path) -> Path:
    return root / "profiles" / "tvdata-mcp"


def get_profile_manifest(root: Path) -> ProfileManifest:
    path = _profile_dir(root) / "manifest.json"
    if not path.is_file():
        raise AnalyticsError("Missing TVData MCP profile manifest.")
    try:
        return ProfileManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AnalyticsError(f"Invalid TVData MCP profile manifest: {exc}") from exc


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AnalyticsError(f"Invalid ISO date {value!r}; expected YYYY-MM-DD.") from exc


def _hours_hhmm(hours: float | None) -> str | None:
    if hours is None:
        return None
    whole = int(hours)
    minutes = round((hours - whole) * 60)
    if minutes == 60:
        whole += 1
        minutes = 0
    return f"{whole:02d}:{minutes:02d}"


def _read_context_rows(root: Path) -> list[dict[str, str]]:
    path = _profile_dir(root) / "working-time-context.csv"
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def _read_regular_working_time(root: Path, table_id: str) -> dict[str, str] | None:
    path = root / "docs" / "regular-working-time-sources.csv"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("dataset") or "").strip() == table_id:
                return {key: (value or "").strip() for key, value in row.items()}
    return None


def _parse_unambiguous_hours(raw: str | None) -> float | None:
    if not raw:
        return None
    numbers = [
        float(value.replace(",", "."))
        for value in re.findall(r"(?<!\d)(\d{1,2}(?:[.,]\d+)?)(?!\d)", raw)
    ]
    numbers = [value for value in numbers if 20 <= value <= 60]
    lowered = raw.casefold()
    variable = any(marker in lowered for marker in ("je nach", " / ", "bestimmte", "schicht", "tarifgebiet"))
    if not numbers:
        return None
    if variable and len(set(numbers)) > 1:
        return None
    return numbers[0]


def _quality_from_url(root: Path, url: str | None) -> Literal["high", "medium", "unknown"]:
    if not url:
        return "unknown"
    assessment = assess_source_url(root, url)
    return assessment.quality_tier


def resolve_working_time(
    root: Path,
    table_id: str,
    jurisdiction_code: str | None = None,
    as_of: str | None = None,
    employment_context: str = "general",
) -> WorkingTimeResolution:
    table_dir = root / "tables" / table_id
    if not table_dir.is_dir():
        raise AnalyticsError(f"Unknown pay table: {table_id!r}.")
    requested = _parse_iso(as_of)
    rows = [
        row
        for row in _read_context_rows(root)
        if row.get("table_id") == table_id and row.get("employment_context", "general") == employment_context
    ]
    available = sorted({row["jurisdiction_code"] for row in rows if row.get("jurisdiction_code")})
    if available and not jurisdiction_code and len(available) > 1:
        return WorkingTimeResolution(
            table_id=table_id,
            jurisdiction_code=None,
            jurisdiction_name_de=None,
            employment_context=employment_context,
            requested_as_of=as_of,
            status="unresolved_context_required",
            weekly_hours=None,
            weekly_hours_hhmm=None,
            valid_from=None,
            valid_to=None,
            source_url=None,
            legal_basis_url=None,
            evidence_quality="unknown",
            available_jurisdictions=available,
            warning="This pay system has jurisdiction-dependent working time; provide jurisdiction_code.",
        )
    if jurisdiction_code:
        rows = [row for row in rows if row.get("jurisdiction_code", "").casefold() == jurisdiction_code.casefold()]
    eligible: list[tuple[date, dict[str, str]]] = []
    for row in rows:
        valid_from = _parse_iso(row.get("valid_from"))
        valid_to = _parse_iso(row.get("valid_to"))
        if valid_from is None:
            continue
        if requested and (valid_from > requested or (valid_to and requested > valid_to)):
            continue
        eligible.append((valid_from, row))
    if eligible:
        _, row = max(eligible, key=lambda item: item[0])
        hours = float(row["weekly_hours"])
        quality = max(
            (_quality_from_url(root, row.get("legal_basis_url")), _quality_from_url(root, row.get("source_url"))),
            key=lambda value: {"unknown": 0, "medium": 1, "high": 2}[value],
        )
        return WorkingTimeResolution(
            table_id=table_id,
            jurisdiction_code=row.get("jurisdiction_code") or None,
            jurisdiction_name_de=row.get("jurisdiction_name_de") or None,
            employment_context=employment_context,
            requested_as_of=as_of,
            status="resolved_context",
            weekly_hours=hours,
            weekly_hours_hhmm=_hours_hhmm(hours),
            valid_from=row.get("valid_from") or None,
            valid_to=row.get("valid_to") or None,
            source_url=row.get("source_url") or None,
            legal_basis_url=row.get("legal_basis_url") or None,
            evidence_quality=quality,
            available_jurisdictions=available,
            warning=None,
        )
    record = _read_regular_working_time(root, table_id)
    raw = (record or {}).get("working_time_weekly")
    hours = _parse_unambiguous_hours(raw)
    if hours is not None:
        source = (record or {}).get("source_url") or None
        return WorkingTimeResolution(
            table_id=table_id,
            jurisdiction_code=jurisdiction_code,
            jurisdiction_name_de=None,
            employment_context=employment_context,
            requested_as_of=as_of,
            status="resolved_table_default",
            weekly_hours=hours,
            weekly_hours_hhmm=_hours_hhmm(hours),
            valid_from=None,
            valid_to=None,
            source_url=source,
            legal_basis_url=None,
            evidence_quality=_quality_from_url(root, source),
            available_jurisdictions=available,
            warning=None,
        )
    return WorkingTimeResolution(
        table_id=table_id,
        jurisdiction_code=jurisdiction_code,
        jurisdiction_name_de=None,
        employment_context=employment_context,
        requested_as_of=as_of,
        status="no_known_record",
        weekly_hours=None,
        weekly_hours_hhmm=None,
        valid_from=None,
        valid_to=None,
        source_url=(record or {}).get("source_url") or None,
        legal_basis_url=None,
        evidence_quality=_quality_from_url(root, (record or {}).get("source_url")),
        available_jurisdictions=available,
        warning="No unambiguous working-time value is available for this context.",
    )


def compare_pay_positions_contextual(
    root: Path,
    positions: list[ContextualPayPositionRequest],
) -> ContextualComparisonResult:
    if len(positions) < 2 or len(positions) > 20:
        raise AnalyticsError("positions must contain between 2 and 20 entries.")
    resolutions: list[WorkingTimeResolution] = []
    comparison_requests: list[PayPositionRequest] = []
    warnings: list[str] = []
    for position in positions:
        resolution = resolve_working_time(root, position.table_id, position.jurisdiction_code)
        resolutions.append(resolution)
        hours = position.weekly_hours_override if position.weekly_hours_override is not None else resolution.weekly_hours
        if hours is None:
            warnings.append(f"{position.table_id}: working time unresolved; hourly normalization is omitted.")
        comparison_requests.append(
            PayPositionRequest(
                table_id=position.table_id,
                pay_grade=position.pay_grade,
                step=position.step,
                weekly_hours_override=hours,
            )
        )
    comparison = compare_positions(root, comparison_requests)
    for request, resolution, row in zip(positions, resolutions, comparison.positions):
        if request.weekly_hours_override is not None:
            row.weekly_hours_basis = "caller_override"
        elif resolution.weekly_hours is not None:
            row.weekly_hours_basis = "profile_context"
        else:
            row.weekly_hours_basis = "ambiguous_or_missing"
    return ContextualComparisonResult(
        comparison=comparison,
        working_time_resolutions=resolutions,
        warnings=warnings,
    )


def _read_source_registry(root: Path) -> list[dict[str, str]]:
    path = _profile_dir(root) / "source-registry.csv"
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def assess_source_url(root: Path, url: str) -> SourceReferenceAssessment:
    parsed = urlparse(url)
    domain = (parsed.hostname or "").casefold()
    matches = []
    for row in _read_source_registry(root):
        registered = row.get("domain", "").casefold()
        if registered and (domain == registered or domain.endswith("." + registered)):
            matches.append((len(registered), row))
    if not matches:
        return SourceReferenceAssessment(
            url=url,
            domain=domain,
            source_class="unknown",
            authority_level="unknown",
            role="unknown",
            quality_tier="unknown",
            registry_match=None,
        )
    _, row = max(matches, key=lambda item: item[0])
    quality = row.get("quality_tier", "unknown")
    if quality not in {"high", "medium"}:
        quality = "unknown"
    return SourceReferenceAssessment(
        url=url,
        domain=domain,
        source_class=row.get("source_class") or "unknown",
        authority_level=row.get("authority_level") or "unknown",
        role=row.get("role") or "unknown",
        quality_tier=quality,
        registry_match=row.get("domain") or None,
    )


def _split_urls(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _aggregate_quality(refs: list[SourceReferenceAssessment]) -> Literal["high", "medium", "unknown", "missing"]:
    if not refs:
        return "missing"
    if any(ref.quality_tier == "high" for ref in refs):
        return "high"
    if any(ref.quality_tier == "medium" for ref in refs):
        return "medium"
    return "unknown"


def assess_pay_system_sources(root: Path, table_id: str) -> PaySystemSourceAssessment:
    directory = root / "tables" / table_id
    if not directory.is_dir():
        raise AnalyticsError(f"Unknown pay table: {table_id!r}.")
    meta, _ = read_metadata(directory)
    pay_refs = [assess_source_url(root, url) for url in _split_urls(meta.get("link"))]
    working_record = _read_regular_working_time(root, table_id)
    working_refs = [
        assess_source_url(root, url)
        for url in _split_urls((working_record or {}).get("source_url"))
    ]
    context_rows = [row for row in _read_context_rows(root) if row.get("table_id") == table_id]
    seen = {ref.url for ref in working_refs}
    for row in context_rows:
        for url in _split_urls(row.get("source_url")) + _split_urls(row.get("legal_basis_url")):
            if url not in seen:
                working_refs.append(assess_source_url(root, url))
                seen.add(url)
    pay_quality = _aggregate_quality(pay_refs)
    work_quality = _aggregate_quality(working_refs)
    warnings: list[str] = []
    if pay_quality == "missing":
        warnings.append("No pay-table source is documented.")
    elif pay_quality == "unknown":
        warnings.append("Pay-table source exists but its authority is not classified in the profile registry.")
    elif pay_quality == "medium":
        warnings.append("Pay-table evidence is secondary-only according to the profile registry.")
    if work_quality == "missing":
        warnings.append("No working-time source is documented.")
    elif work_quality == "unknown":
        warnings.append("Working-time source exists but its authority is not classified in the profile registry.")
    return PaySystemSourceAssessment(
        table_id=table_id,
        valid_from=meta.get("valid_from") or None,
        pay_sources=pay_refs,
        working_time_sources=working_refs,
        pay_evidence_quality=pay_quality,
        working_time_evidence_quality=work_quality,
        warnings=warnings,
    )


def audit_source_quality(root: Path, query: str | None = None, limit: int = 300) -> SourceAuditReport:
    if limit < 1 or limit > 1000:
        raise AnalyticsError("limit must be between 1 and 1000.")
    issues: list[SourceAuditIssue] = []
    scanned = 0
    for directory in sorted((path for path in (root / "tables").iterdir() if path.is_dir()), key=lambda path: path.name.casefold()):
        if query and query.casefold() not in directory.name.casefold():
            continue
        scanned += 1
        assessment = assess_pay_system_sources(root, directory.name)
        if assessment.pay_evidence_quality == "missing":
            issues.append(SourceAuditIssue(table_id=directory.name, severity="error", code="missing_pay_source", message="No pay-table source documented."))
        elif assessment.pay_evidence_quality == "unknown":
            issues.append(SourceAuditIssue(table_id=directory.name, severity="warning", code="unclassified_pay_source", message="Pay source domain is not classified."))
        elif assessment.pay_evidence_quality == "medium":
            issues.append(SourceAuditIssue(table_id=directory.name, severity="warning", code="secondary_only_pay_source", message="Only secondary pay-source evidence is classified."))
        if assessment.working_time_evidence_quality == "missing":
            issues.append(SourceAuditIssue(table_id=directory.name, severity="warning", code="missing_working_time_source", message="No working-time source documented."))
        elif assessment.working_time_evidence_quality == "unknown":
            issues.append(SourceAuditIssue(table_id=directory.name, severity="info", code="unclassified_working_time_source", message="Working-time source domain is not classified."))
        if len(issues) >= limit:
            break
    counts = {severity: sum(1 for issue in issues if issue.severity == severity) for severity in ("error", "warning", "info")}
    return SourceAuditReport(tables_scanned=scanned, issue_counts=counts, issues=issues[:limit])
