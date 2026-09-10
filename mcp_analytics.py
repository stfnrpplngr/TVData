"""Analytical comparison layer for the TVData MCP server.

This module keeps analytics deterministic and read-only. It derives comparisons
from the repository CSV files; it does not introduce a second datastore or infer
legal/financial equivalence from nominal pay proximity.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AnalyticsError(ValueError):
    """Model-correctable error raised by pure analytics helpers."""


class PayPositionRequest(BaseModel):
    table_id: str
    pay_grade: str
    step: str
    weekly_hours_override: float | None = Field(default=None, gt=0, le=80)


class PayGradeRequest(BaseModel):
    table_id: str
    pay_grade: str


class WorkingTimeInfo(BaseModel):
    table_id: str
    raw_value: str | None
    standard_hours: float | None
    observed_hours: list[float]
    context_dependent: bool
    source: str | None
    notes: str | None
    accessed_on: str | None


class ComparisonItem(BaseModel):
    table_id: str
    pay_grade: str
    step: str
    regime: str
    name_de: str | None
    valid_from: str | None
    monthly_base_eur: float
    annual_base_eur: float
    weekly_hours: float | None
    weekly_hours_basis: str
    base_per_contract_hour_eur: float | None
    difference_from_first_eur: float
    difference_from_first_pct: float | None
    source: str | None


class ComparabilityAssessment(BaseModel):
    nominal_base_pay: str
    working_time: str
    total_compensation: str
    net_income: str
    employment_regime: str
    same_valid_from: bool
    warnings: list[str]


class ComparisonResult(BaseModel):
    positions: list[ComparisonItem]
    comparability: ComparabilityAssessment


class RankingItem(BaseModel):
    rank: int
    table_id: str
    name_de: str | None
    regime: str
    pay_grade: str
    step: str
    monthly_base_eur: float
    annual_base_eur: float
    weekly_hours: float | None
    base_per_contract_hour_eur: float | None
    metric_value: float
    valid_from: str | None
    source: str | None


class RankingResult(BaseModel):
    metric: str
    pay_grade: str
    step: str
    rows: list[RankingItem]
    tables_evaluated: int
    positions_found: int
    skipped_missing_position: int
    skipped_ambiguous_working_time: int
    warning: str | None


class TableStructure(BaseModel):
    table_id: str
    name_de: str | None
    pay_grade_prefix: str | None
    valid_from: str | None
    grades: list[str]
    steps: list[str]
    numeric_cells: int
    linked_allowances: list[str]
    linked_pensions: list[str]


class ProgressionComparison(BaseModel):
    table_id: str
    pay_grade: str
    steps: list[str]
    years_to_next_step: dict[str, float | None]
    cumulative_years_to_step: dict[str, float | None]


class ProgressionComparisonResult(BaseModel):
    rows: list[ProgressionComparison]
    warning: str


class HistoryPoint(BaseModel):
    snapshot_id: str
    current: bool
    valid_from: str | None
    monthly_base_eur: float
    change_from_previous_eur: float | None
    change_from_previous_pct: float | None
    source: str | None


class HistoryResult(BaseModel):
    table_id: str
    pay_grade: str
    step: str
    points: list[HistoryPoint]
    warning: str | None


class ProvenanceResult(BaseModel):
    table_id: str
    valid_from: str | None
    pay_table_source: str | None
    working_time: WorkingTimeInfo
    linked_allowances: list[str]
    linked_pensions: list[str]
    metadata_key_column: str
    provenance_status: str


class NearestPayMatch(BaseModel):
    rank: int
    table_id: str
    name_de: str | None
    regime: str
    pay_grade: str
    step: str
    monthly_base_eur: float
    difference_eur: float
    difference_pct: float
    valid_from: str | None


class NearestPayResult(BaseModel):
    reference: ComparisonItem
    matches: list[NearestPayMatch]
    warning: str


class DataQualityIssue(BaseModel):
    table_id: str
    severity: Literal["error", "warning", "info"]
    code: str
    message: str


class DataQualityReport(BaseModel):
    tables_scanned: int
    issue_counts: dict[str, int]
    issues: list[DataQualityIssue]


def _safe_dir(base: Path, item_id: str, kind: str) -> Path:
    if not item_id or item_id in {".", ".."} or "/" in item_id or "\\" in item_id:
        raise AnalyticsError(f"Invalid {kind} identifier: {item_id!r}.")
    candidate = (base / item_id).resolve()
    if candidate.parent != base.resolve() or not candidate.is_dir():
        raise AnalyticsError(f"Unknown {kind}: {item_id!r}.")
    return candidate


def read_metadata(directory: Path) -> tuple[dict[str, str], str]:
    """Read Meta.csv, accepting the repository's `name` and `key` variants."""
    path = directory / "Meta.csv"
    if not path.is_file():
        raise AnalyticsError(f"Missing metadata file for {directory.name!r}.")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = [field.strip() for field in (reader.fieldnames or [])]
        key_column = "name" if "name" in fields else "key" if "key" in fields else ""
        if not key_column or "value" not in fields:
            raise AnalyticsError(f"Invalid Meta.csv schema for {directory.name!r}: expected name/key,value.")
        result: dict[str, str] = {}
        for row in reader:
            key = (row.get(key_column) or "").strip()
            if key:
                result[key] = (row.get("value") or "").strip()
    return result, key_column


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
                column: (values[index].strip() if index < len(values) else "")
                for index, column in enumerate(columns)
            }
    return columns, rows


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def _split_ids(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def _regime(table_id: str) -> str:
    if table_id.casefold().startswith("beamte-"):
        return "civil_service"
    if table_id.casefold().startswith(("tv", "mtv")):
        return "collective_agreement"
    return "unknown"


def _date_key(value: str | None) -> tuple[int, int, int]:
    if not value:
        return (0, 0, 0)
    match = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$", value.strip())
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _working_time_records(root: Path) -> dict[str, dict[str, str]]:
    path = root / "docs" / "regular-working-time-sources.csv"
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            (row.get("dataset") or "").strip(): {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
            if (row.get("dataset") or "").strip()
        }


def _working_time(root: Path, table_id: str, meta: dict[str, str]) -> WorkingTimeInfo:
    record = _working_time_records(root).get(table_id, {})
    raw = record.get("working_time_weekly") or meta.get("working_time_weekly") or None
    values: list[float] = []
    if raw:
        for number in re.findall(r"(?<!\d)(\d{1,2}(?:[.,]\d+)?)(?!\d)", raw):
            numeric = float(number.replace(",", "."))
            if 20 <= numeric <= 60 and numeric not in values:
                values.append(numeric)

    lowered = (raw or "").casefold()
    explicitly_variable = any(
        marker in lowered
        for marker in ("je nach", " / ", "bestimmte", "schicht", "tarifgebiet")
    ) or bool(re.search(r"\d(?:[.,]\d+)?\s*[-–]\s*\d", raw or ""))

    if not values:
        standard = None
    elif explicitly_variable and len(values) > 1:
        standard = None
    else:
        # For rules such as "41 (40 auf Antrag...)" the first value is the
        # regular standard; alternatives remain visible in observed_hours.
        standard = values[0]

    return WorkingTimeInfo(
        table_id=table_id,
        raw_value=raw,
        standard_hours=standard,
        observed_hours=values,
        context_dependent=explicitly_variable or len(values) > 1,
        source=record.get("source_url") or None,
        notes=record.get("notes") or None,
        accessed_on=record.get("accessed_on") or None,
    )


def _read_pay(directory: Path, pay_grade: str, step: str) -> float:
    _, rows = _read_matrix(directory / "Table.csv")
    if pay_grade not in rows:
        raise AnalyticsError(f"Unknown pay grade {pay_grade!r} in table {directory.name!r}.")
    if step not in rows[pay_grade]:
        raise AnalyticsError(f"Unknown step {step!r} in table {directory.name!r}.")
    raw = rows[pay_grade][step]
    if not raw:
        raise AnalyticsError(
            f"No base-pay value exists for table {directory.name!r}, grade {pay_grade!r}, step {step!r}."
        )
    value = _to_float(raw)
    if value is None:
        raise AnalyticsError(
            f"Base-pay value {raw!r} for table {directory.name!r}, grade {pay_grade!r}, step {step!r} is not numeric."
        )
    return value


def _position_item(root: Path, request: PayPositionRequest) -> ComparisonItem:
    table_dir = _safe_dir(root / "tables", request.table_id, "pay table")
    meta, _ = read_metadata(table_dir)
    monthly = _read_pay(table_dir, request.pay_grade, request.step)
    work = _working_time(root, request.table_id, meta)
    hours = request.weekly_hours_override if request.weekly_hours_override is not None else work.standard_hours
    basis = "caller_override" if request.weekly_hours_override is not None else "dataset_standard" if hours else "ambiguous_or_missing"
    hourly = round((monthly * 12) / (hours * 52), 2) if hours else None
    return ComparisonItem(
        table_id=request.table_id,
        pay_grade=request.pay_grade,
        step=request.step,
        regime=_regime(request.table_id),
        name_de=meta.get("name_de") or None,
        valid_from=meta.get("valid_from") or None,
        monthly_base_eur=monthly,
        annual_base_eur=round(monthly * 12, 2),
        weekly_hours=hours,
        weekly_hours_basis=basis,
        base_per_contract_hour_eur=hourly,
        difference_from_first_eur=0.0,
        difference_from_first_pct=0.0,
        source=meta.get("link") or None,
    )


def compare_positions(root: Path, positions: list[PayPositionRequest]) -> ComparisonResult:
    if len(positions) < 2 or len(positions) > 20:
        raise AnalyticsError("positions must contain between 2 and 20 entries.")
    rows = [_position_item(root, position) for position in positions]
    anchor = rows[0].monthly_base_eur
    for row in rows:
        row.difference_from_first_eur = round(row.monthly_base_eur - anchor, 2)
        row.difference_from_first_pct = round((row.monthly_base_eur / anchor - 1) * 100, 2) if anchor else None

    regimes = {row.regime for row in rows if row.regime != "unknown"}
    valid_dates = {row.valid_from for row in rows if row.valid_from}
    warnings = [
        "Only nominal base pay is compared; allowances, pensions, taxes and social-insurance effects are excluded."
    ]
    if len(regimes) > 1:
        warnings.append(
            "Civil-service and collective-agreement positions have different employment, pension and social-insurance regimes; pay proximity is not employment equivalence."
        )
    if len(valid_dates) > 1:
        warnings.append("The compared tables have different valid-from dates.")
    if any(row.weekly_hours is None for row in rows):
        warnings.append(
            "At least one weekly-working-time value is context-dependent or missing; hourly normalization is omitted for that position unless an override is supplied."
        )

    return ComparisonResult(
        positions=rows,
        comparability=ComparabilityAssessment(
            nominal_base_pay="direct nominal gross comparison",
            working_time="normalized where one standard/override is available; otherwise unresolved",
            total_compensation="not calculated",
            net_income="not comparable without a separate tax/social-insurance model",
            employment_regime="mixed" if len(regimes) > 1 else "same_or_unknown",
            same_valid_from=len(valid_dates) <= 1,
            warnings=warnings,
        ),
    )


def get_table_structure(root: Path, table_id: str) -> TableStructure:
    table_dir = _safe_dir(root / "tables", table_id, "pay table")
    meta, _ = read_metadata(table_dir)
    steps, rows = _read_matrix(table_dir / "Table.csv")
    numeric_cells = sum(1 for row in rows.values() for value in row.values() if _to_float(value) is not None)
    return TableStructure(
        table_id=table_id,
        name_de=meta.get("name_de") or None,
        pay_grade_prefix=meta.get("pay_grad_name") or None,
        valid_from=meta.get("valid_from") or None,
        grades=list(rows.keys()),
        steps=steps,
        numeric_cells=numeric_cells,
        linked_allowances=_split_ids(meta.get("allowances")),
        linked_pensions=_split_ids(meta.get("prv")),
    )


def compare_progressions(root: Path, positions: list[PayGradeRequest]) -> ProgressionComparisonResult:
    if len(positions) < 2 or len(positions) > 20:
        raise AnalyticsError("positions must contain between 2 and 20 entries.")
    output: list[ProgressionComparison] = []
    for position in positions:
        directory = _safe_dir(root / "tables", position.table_id, "pay table")
        steps, rows = _read_matrix(directory / "Adv.csv")
        if position.pay_grade not in rows:
            raise AnalyticsError(f"Unknown pay grade {position.pay_grade!r} in progression table {position.table_id!r}.")
        durations = {step: _to_float(rows[position.pay_grade].get(step)) for step in steps}
        cumulative: dict[str, float | None] = {}
        elapsed: float | None = 0.0
        for index, step in enumerate(steps):
            cumulative[step] = elapsed
            duration = durations[step]
            if index < len(steps) - 1:
                elapsed = (elapsed + duration) if elapsed is not None and duration is not None else None
        output.append(
            ProgressionComparison(
                table_id=position.table_id,
                pay_grade=position.pay_grade,
                steps=steps,
                years_to_next_step=durations,
                cumulative_years_to_step=cumulative,
            )
        )
    return ProgressionComparisonResult(
        rows=output,
        warning="Progression compares documented step waiting times only; recognition of prior experience and exceptional advancement rules are not modeled.",
    )


def rank_base_pay(
    root: Path,
    pay_grade: str,
    step: str,
    table_ids: list[str] | None = None,
    query: str | None = None,
    regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
    metric: Literal["monthly_base", "annual_base", "base_per_contract_hour"] = "monthly_base",
    weekly_hours_overrides: dict[str, float] | None = None,
    limit: int = 20,
) -> RankingResult:
    if limit < 1 or limit > 100:
        raise AnalyticsError("limit must be between 1 and 100.")
    overrides = weekly_hours_overrides or {}
    for table_id, value in overrides.items():
        if value <= 0 or value > 80:
            raise AnalyticsError(f"Invalid weekly-hours override for {table_id!r}: {value}.")

    if table_ids:
        directories = [_safe_dir(root / "tables", table_id, "pay table") for table_id in table_ids]
    else:
        directories = sorted((p for p in (root / "tables").iterdir() if p.is_dir()), key=lambda p: p.name.casefold())

    candidates: list[tuple[float, ComparisonItem]] = []
    evaluated = 0
    missing = 0
    ambiguous = 0
    for directory in directories:
        if query and query.casefold() not in directory.name.casefold():
            try:
                meta_for_query, _ = read_metadata(directory)
            except AnalyticsError:
                continue
            if query.casefold() not in (meta_for_query.get("name_de") or "").casefold() and query.casefold() not in (meta_for_query.get("name_en") or "").casefold():
                continue
        if regime and _regime(directory.name) != regime:
            continue
        evaluated += 1
        try:
            request = PayPositionRequest(
                table_id=directory.name,
                pay_grade=pay_grade,
                step=step,
                weekly_hours_override=overrides.get(directory.name),
            )
            item = _position_item(root, request)
        except AnalyticsError as exc:
            if "Unknown pay grade" in str(exc) or "Unknown step" in str(exc) or "No base-pay value" in str(exc):
                missing += 1
                continue
            raise
        if metric == "monthly_base":
            metric_value = item.monthly_base_eur
        elif metric == "annual_base":
            metric_value = item.annual_base_eur
        else:
            if item.base_per_contract_hour_eur is None:
                ambiguous += 1
                continue
            metric_value = item.base_per_contract_hour_eur
        candidates.append((metric_value, item))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    rows = [
        RankingItem(
            rank=index + 1,
            table_id=item.table_id,
            name_de=item.name_de,
            regime=item.regime,
            pay_grade=item.pay_grade,
            step=item.step,
            monthly_base_eur=item.monthly_base_eur,
            annual_base_eur=item.annual_base_eur,
            weekly_hours=item.weekly_hours,
            base_per_contract_hour_eur=item.base_per_contract_hour_eur,
            metric_value=metric_value,
            valid_from=item.valid_from,
            source=item.source,
        )
        for index, (metric_value, item) in enumerate(candidates[:limit])
    ]
    warning = None
    if metric == "base_per_contract_hour":
        warning = (
            "The hourly figure is an analytical normalization: 12 monthly base salaries divided by 52 contractual weeks. "
            "It is not a payroll hourly wage and excludes leave, holidays, allowances and overtime."
        )
    return RankingResult(
        metric=metric,
        pay_grade=pay_grade,
        step=step,
        rows=rows,
        tables_evaluated=evaluated,
        positions_found=len(candidates),
        skipped_missing_position=missing,
        skipped_ambiguous_working_time=ambiguous,
        warning=warning,
    )


def get_pay_history(root: Path, table_id: str, pay_grade: str, step: str) -> HistoryResult:
    current_dir = _safe_dir(root / "tables", table_id, "pay table")
    snapshot_dirs: list[tuple[Path, bool]] = []
    archive = root / "archive"
    pattern = re.compile(rf"^{re.escape(table_id)}-(?:19|20)\d{{2}}$")
    if archive.is_dir():
        snapshot_dirs.extend((p, False) for p in archive.iterdir() if p.is_dir() and pattern.match(p.name))
    snapshot_dirs.append((current_dir, True))

    raw_points: list[tuple[tuple[int, int, int], HistoryPoint]] = []
    for directory, is_current in snapshot_dirs:
        try:
            monthly = _read_pay(directory, pay_grade, step)
            meta, _ = read_metadata(directory)
        except AnalyticsError:
            continue
        valid_from = meta.get("valid_from") or None
        raw_points.append(
            (
                _date_key(valid_from),
                HistoryPoint(
                    snapshot_id=directory.name,
                    current=is_current,
                    valid_from=valid_from,
                    monthly_base_eur=monthly,
                    change_from_previous_eur=None,
                    change_from_previous_pct=None,
                    source=meta.get("link") or None,
                ),
            )
        )
    raw_points.sort(key=lambda pair: (pair[0], pair[1].snapshot_id))
    points = [point for _, point in raw_points]
    for previous, current in zip(points, points[1:]):
        current.change_from_previous_eur = round(current.monthly_base_eur - previous.monthly_base_eur, 2)
        current.change_from_previous_pct = (
            round((current.monthly_base_eur / previous.monthly_base_eur - 1) * 100, 2)
            if previous.monthly_base_eur
            else None
        )
    warning = None if len(points) > 1 else "No matching archived snapshot with this grade/step was found."
    return HistoryResult(table_id=table_id, pay_grade=pay_grade, step=step, points=points, warning=warning)


def get_provenance(root: Path, table_id: str) -> ProvenanceResult:
    directory = _safe_dir(root / "tables", table_id, "pay table")
    meta, key_column = read_metadata(directory)
    working = _working_time(root, table_id, meta)
    source = meta.get("link") or None
    if source and working.source:
        status = "pay_table_and_working_time_sourced"
    elif source:
        status = "pay_table_sourced_working_time_source_missing"
    else:
        status = "pay_table_source_missing"
    return ProvenanceResult(
        table_id=table_id,
        valid_from=meta.get("valid_from") or None,
        pay_table_source=source,
        working_time=working,
        linked_allowances=_split_ids(meta.get("allowances")),
        linked_pensions=_split_ids(meta.get("prv")),
        metadata_key_column=key_column,
        provenance_status=status,
    )


def compare_working_time(root: Path, table_ids: list[str]) -> list[WorkingTimeInfo]:
    if not table_ids or len(table_ids) > 50:
        raise AnalyticsError("table_ids must contain between 1 and 50 entries.")
    output: list[WorkingTimeInfo] = []
    for table_id in table_ids:
        directory = _safe_dir(root / "tables", table_id, "pay table")
        meta, _ = read_metadata(directory)
        output.append(_working_time(root, table_id, meta))
    return output


def find_nearest_base_pay(
    root: Path,
    reference: PayPositionRequest,
    candidate_table_ids: list[str] | None = None,
    candidate_query: str | None = None,
    candidate_regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
    candidate_grade_prefix: str | None = None,
    limit: int = 10,
) -> NearestPayResult:
    if limit < 1 or limit > 50:
        raise AnalyticsError("limit must be between 1 and 50.")
    reference_item = _position_item(root, reference)
    if candidate_table_ids:
        directories = [_safe_dir(root / "tables", table_id, "pay table") for table_id in candidate_table_ids]
    else:
        directories = sorted((p for p in (root / "tables").iterdir() if p.is_dir()), key=lambda p: p.name.casefold())

    matches: list[tuple[float, str, str, str, float, dict[str, str]]] = []
    for directory in directories:
        if candidate_query and candidate_query.casefold() not in directory.name.casefold():
            continue
        if candidate_regime and _regime(directory.name) != candidate_regime:
            continue
        try:
            meta, _ = read_metadata(directory)
            steps, rows = _read_matrix(directory / "Table.csv")
        except AnalyticsError:
            continue
        for grade, row in rows.items():
            if candidate_grade_prefix and not grade.casefold().startswith(candidate_grade_prefix.casefold()):
                continue
            for step in steps:
                value = _to_float(row.get(step))
                if value is None:
                    continue
                if directory.name == reference.table_id and grade == reference.pay_grade and step == reference.step:
                    continue
                delta = value - reference_item.monthly_base_eur
                matches.append((abs(delta), directory.name, grade, step, value, meta))
    matches.sort(key=lambda entry: (entry[0], entry[1].casefold(), entry[2], entry[3]))
    output = [
        NearestPayMatch(
            rank=index + 1,
            table_id=table_id,
            name_de=meta.get("name_de") or None,
            regime=_regime(table_id),
            pay_grade=grade,
            step=step,
            monthly_base_eur=value,
            difference_eur=round(value - reference_item.monthly_base_eur, 2),
            difference_pct=round((value / reference_item.monthly_base_eur - 1) * 100, 2),
            valid_from=meta.get("valid_from") or None,
        )
        for index, (_, table_id, grade, step, value, meta) in enumerate(matches[:limit])
    ]
    return NearestPayResult(
        reference=reference_item,
        matches=output,
        warning=(
            "Matches are nearest nominal monthly base-pay values only. They do not establish equivalent duties, qualification levels, legal status, total compensation or net income."
        ),
    )


def audit_pay_data(root: Path, query: str | None = None, limit: int = 200) -> DataQualityReport:
    if limit < 1 or limit > 500:
        raise AnalyticsError("limit must be between 1 and 500.")
    directories = sorted((p for p in (root / "tables").iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
    issues: list[DataQualityIssue] = []
    scanned = 0
    for directory in directories:
        if query and query.casefold() not in directory.name.casefold():
            continue
        scanned += 1
        try:
            meta, key_column = read_metadata(directory)
        except AnalyticsError as exc:
            issues.append(DataQualityIssue(table_id=directory.name, severity="error", code="invalid_metadata", message=str(exc)))
            continue
        if key_column != "name":
            issues.append(
                DataQualityIssue(
                    table_id=directory.name,
                    severity="info",
                    code="alternate_metadata_key_column",
                    message=f"Meta.csv uses {key_column!r} instead of the repository's predominant 'name' header; MCP accepts both.",
                )
            )
        if not meta.get("valid_from"):
            issues.append(DataQualityIssue(table_id=directory.name, severity="warning", code="missing_valid_from", message="No valid_from metadata."))
        if not meta.get("link"):
            issues.append(DataQualityIssue(table_id=directory.name, severity="warning", code="missing_pay_source", message="No source link for the pay table."))
        working = _working_time(root, directory.name, meta)
        if not working.raw_value:
            issues.append(DataQualityIssue(table_id=directory.name, severity="warning", code="missing_working_time", message="No weekly working-time value."))
        if not working.source:
            issues.append(DataQualityIssue(table_id=directory.name, severity="info", code="missing_working_time_source", message="No dedicated working-time provenance source."))
        try:
            _, rows = _read_matrix(directory / "Table.csv")
        except AnalyticsError as exc:
            issues.append(DataQualityIssue(table_id=directory.name, severity="error", code="invalid_pay_table", message=str(exc)))
            continue
        invalid = sum(1 for row in rows.values() for value in row.values() if value and _to_float(value) is None)
        if invalid:
            issues.append(DataQualityIssue(table_id=directory.name, severity="error", code="nonnumeric_pay_values", message=f"{invalid} non-empty pay cells are non-numeric."))
        if len(issues) >= limit:
            break
    counts = Counter(issue.severity for issue in issues)
    return DataQualityReport(
        tables_scanned=scanned,
        issue_counts={severity: counts.get(severity, 0) for severity in ("error", "warning", "info")},
        issues=issues[:limit],
    )


def register_analytics_tools(mcp, root: Path) -> None:
    """Register analytical tools on an existing MCPServer instance."""
    from mcp.server.mcpserver.exceptions import ToolError

    def convert_errors(fn):
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except AnalyticsError as exc:
                raise ToolError(str(exc)) from exc

        wrapped.__name__ = fn.__name__
        wrapped.__doc__ = fn.__doc__
        wrapped.__annotations__ = fn.__annotations__
        return wrapped

    @mcp.tool()
    @convert_errors
    def get_pay_table_structure(table_id: str) -> TableStructure:
        """Discover valid pay grades, steps and linked components before querying a table."""
        return get_table_structure(root, table_id)

    @mcp.tool()
    @convert_errors
    def compare_pay_positions(positions: list[PayPositionRequest]) -> ComparisonResult:
        """Compare 2-20 exact pay positions with explicit comparability caveats and optional working-time overrides."""
        return compare_positions(root, positions)

    @mcp.tool()
    @convert_errors
    def rank_pay_positions(
        pay_grade: str,
        step: str,
        table_ids: list[str] | None = None,
        query: str | None = None,
        regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
        metric: Literal["monthly_base", "annual_base", "base_per_contract_hour"] = "monthly_base",
        weekly_hours_overrides: dict[str, float] | None = None,
        limit: int = 20,
    ) -> RankingResult:
        """Rank the same grade/step across matching current tables by base pay or a transparent working-time normalization."""
        return rank_base_pay(root, pay_grade, step, table_ids, query, regime, metric, weekly_hours_overrides, limit)

    @mcp.tool()
    @convert_errors
    def compare_step_progressions(positions: list[PayGradeRequest]) -> ProgressionComparisonResult:
        """Compare step waiting times and cumulative years-to-step for 2-20 table/grade pairs."""
        return compare_progressions(root, positions)

    @mcp.tool()
    @convert_errors
    def get_pay_history_series(table_id: str, pay_grade: str, step: str) -> HistoryResult:
        """Return current plus matching archived yearly snapshots for an exact table/grade/step."""
        return get_pay_history(root, table_id, pay_grade, step)

    @mcp.tool()
    @convert_errors
    def get_pay_provenance(table_id: str) -> ProvenanceResult:
        """Return pay-table and working-time provenance, validity and linked compensation components."""
        return get_provenance(root, table_id)

    @mcp.tool()
    @convert_errors
    def compare_weekly_working_time(table_ids: list[str]) -> list[WorkingTimeInfo]:
        """Compare documented regular weekly working time and its provenance across pay systems."""
        return compare_working_time(root, table_ids)

    @mcp.tool()
    @convert_errors
    def find_nearest_pay_positions(
        reference: PayPositionRequest,
        candidate_table_ids: list[str] | None = None,
        candidate_query: str | None = None,
        candidate_regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
        candidate_grade_prefix: str | None = None,
        limit: int = 10,
    ) -> NearestPayResult:
        """Find nearest nominal base-pay cells without claiming job, grade or status equivalence."""
        return find_nearest_base_pay(
            root,
            reference,
            candidate_table_ids,
            candidate_query,
            candidate_regime,
            candidate_grade_prefix,
            limit,
        )

    @mcp.tool()
    @convert_errors
    def audit_pay_data_quality(query: str | None = None, limit: int = 200) -> DataQualityReport:
        """Audit current pay-table metadata, provenance and numeric matrix integrity for comparison readiness."""
        return audit_pay_data(root, query, limit)
