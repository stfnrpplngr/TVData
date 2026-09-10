"""Semantic and temporal intelligence for the TVData MCP application profile.

This layer resolves human terminology to canonical table ids and resolves an
``as_of`` date to the latest *known* repository snapshot.  It deliberately does
not claim that repository snapshots form a legally complete historical record.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mcp_analytics import AnalyticsError, read_metadata
from mcp_profile import (
    PaySystemIdentity,
    grade_prefix_from_query,
    identity_for_table,
    jurisdiction_from_query,
    normalize_text,
)


class PaySystemMatch(BaseModel):
    identity: PaySystemIdentity
    score: float
    confidence: Literal["exact", "high", "medium", "low"]
    reasons: list[str]


class PaySystemResolution(BaseModel):
    query: str
    jurisdiction_context_code: str | None
    jurisdiction_context_name_de: str | None
    grade_prefix_hint: str | None
    candidates: list[PaySystemMatch]
    ambiguity_warning: str | None


class SnapshotResolution(BaseModel):
    table_id: str
    snapshot_id: str
    requested_as_of: str
    snapshot_valid_from: str
    current: bool
    resolution_status: Literal[
        "exact_current_valid_from",
        "current_latest_known",
        "exact_archived_valid_from",
        "latest_known_archived_snapshot",
    ]
    next_known_valid_from: str | None
    source: str | None
    warning: str | None


class BasePayAsOf(BaseModel):
    table_id: str
    pay_grade: str
    step: str
    requested_as_of: str
    snapshot: SnapshotResolution
    monthly_base_eur: float
    annual_base_eur: float


class DatedPayPositionRequest(BaseModel):
    table_id: str
    pay_grade: str
    step: str
    as_of: str
    weekly_hours_override: float | None = Field(default=None, gt=0, le=80)


class DatedComparisonItem(BaseModel):
    table_id: str
    snapshot_id: str
    pay_grade: str
    step: str
    requested_as_of: str
    snapshot_valid_from: str
    resolution_status: str
    name_de: str | None
    regime: str
    monthly_base_eur: float
    annual_base_eur: float
    weekly_hours: float | None
    weekly_hours_basis: str
    base_per_contract_hour_eur: float | None
    difference_from_first_eur: float
    difference_from_first_pct: float | None
    source: str | None


class DatedComparisonResult(BaseModel):
    positions: list[DatedComparisonItem]
    warnings: list[str]


class DatedRankingItem(BaseModel):
    rank: int
    table_id: str
    snapshot_id: str
    name_de: str | None
    regime: str
    pay_grade: str
    step: str
    requested_as_of: str
    snapshot_valid_from: str
    monthly_base_eur: float
    annual_base_eur: float
    source: str | None


class DatedRankingResult(BaseModel):
    requested_as_of: str
    pay_grade: str
    step: str
    rows: list[DatedRankingItem]
    tables_evaluated: int
    positions_found: int
    skipped_no_snapshot: int
    skipped_missing_position: int
    warning: str


def _safe_table_dir(root: Path, table_id: str) -> Path:
    if not table_id or table_id in {".", ".."} or "/" in table_id or "\\" in table_id:
        raise AnalyticsError(f"Invalid pay table identifier: {table_id!r}.")
    candidate = (root / "tables" / table_id).resolve()
    if candidate.parent != (root / "tables").resolve() or not candidate.is_dir():
        raise AnalyticsError(f"Unknown pay table: {table_id!r}.")
    return candidate


def _parse_date(value: str) -> date:
    raw = value.strip()
    patterns = (
        (r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$", (1, 2, 3)),
        (r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", (3, 2, 1)),
    )
    for pattern, order in patterns:
        match = re.match(pattern, raw)
        if not match:
            continue
        parts = [int(match.group(index)) for index in order]
        try:
            return date(parts[0], parts[1], parts[2])
        except ValueError as exc:
            raise AnalyticsError(f"Invalid calendar date: {value!r}.") from exc
    raise AnalyticsError("as_of must use YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD or DD.MM.YYYY.")


def _iso(value: date) -> str:
    return value.isoformat()


def _read_pay(directory: Path, pay_grade: str, step: str) -> float:
    path = directory / "Table.csv"
    if not path.is_file():
        raise AnalyticsError(f"Missing data file: {path}.")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise AnalyticsError(f"Empty data file: {path}.") from exc
        steps = [cell.strip() for cell in header[1:]]
        if step not in steps:
            raise AnalyticsError(f"Unknown step {step!r} in table {directory.name!r}.")
        step_index = steps.index(step) + 1
        for row in reader:
            if not row or row[0].strip() != pay_grade:
                continue
            raw = row[step_index].strip() if step_index < len(row) else ""
            if not raw:
                raise AnalyticsError(
                    f"No base-pay value exists for table {directory.name!r}, grade {pay_grade!r}, step {step!r}."
                )
            try:
                return float(raw.replace(",", "."))
            except ValueError as exc:
                raise AnalyticsError(
                    f"Base-pay value {raw!r} for table {directory.name!r}, grade {pay_grade!r}, step {step!r} is not numeric."
                ) from exc
    raise AnalyticsError(f"Unknown pay grade {pay_grade!r} in table {directory.name!r}.")


def list_pay_system_catalog(
    root: Path,
    query: str | None = None,
    regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
    jurisdiction_code: str | None = None,
    family: str | None = None,
    limit: int = 100,
) -> list[PaySystemIdentity]:
    """List current pay systems using canonical semantic profile fields."""
    if limit < 1 or limit > 200:
        raise AnalyticsError("limit must be between 1 and 200.")
    normalized_query = normalize_text(query) if query else None
    normalized_family = normalize_text(family) if family else None
    normalized_jurisdiction = jurisdiction_code.casefold() if jurisdiction_code else None
    results: list[PaySystemIdentity] = []
    for directory in sorted((p for p in (root / "tables").iterdir() if p.is_dir()), key=lambda p: p.name.casefold()):
        try:
            meta, _ = read_metadata(directory)
        except AnalyticsError:
            continue
        identity = identity_for_table(directory.name, meta)
        if regime and identity.regime != regime:
            continue
        if normalized_jurisdiction and (identity.jurisdiction_code or "").casefold() != normalized_jurisdiction:
            continue
        if normalized_family and normalize_text(identity.family) != normalized_family:
            continue
        if normalized_query:
            haystack = " ".join(normalize_text(value) for value in [identity.table_id, identity.name_de or "", identity.name_en or "", *identity.aliases])
            if normalized_query not in haystack:
                continue
        results.append(identity)
        if len(results) >= limit:
            break
    return results


def _score_identity(query: str, identity: PaySystemIdentity) -> tuple[float, list[str]]:
    q = normalize_text(query)
    q_tokens = set(q.split())
    alias_norms = [normalize_text(alias) for alias in identity.aliases if normalize_text(alias)]
    score = 0.0
    reasons: list[str] = []

    if q == normalize_text(identity.table_id) or q in alias_norms:
        score += 100
        reasons.append("exact canonical id or alias")
    else:
        contained = [alias for alias in alias_norms if len(alias) >= 3 and re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", q)]
        if contained:
            best = max(contained, key=len)
            score += 45
            reasons.append(f"alias phrase match: {best}")
        alias_tokens = set(" ".join(alias_norms).split())
        if q_tokens:
            overlap = len(q_tokens & alias_tokens) / len(q_tokens)
            if overlap:
                score += round(overlap * 30, 2)
                reasons.append(f"token overlap {overlap:.0%}")

    jurisdiction = jurisdiction_from_query(query)
    if jurisdiction:
        if identity.jurisdiction_code == jurisdiction.code:
            score += 35
            reasons.append(f"jurisdiction match: {jurisdiction.code}")
        elif identity.scope == "multi_state" and identity.family in {"TV-L", "TV-Ärzte"}:
            score += 15
            reasons.append(f"jurisdiction context supported by multi-state system: {jurisdiction.code}")
        elif identity.jurisdiction_code and identity.jurisdiction_code not in {"DE", "DE-LAENDER"}:
            score -= 20
            reasons.append("different jurisdiction")

    grade_prefix = grade_prefix_from_query(query)
    if grade_prefix:
        candidates = {value.upper() for value in (identity.pay_grade_prefix, identity.pay_scale) if value}
        if grade_prefix in candidates:
            score += 30
            reasons.append(f"grade/pay-scale prefix match: {grade_prefix}")
        elif candidates:
            score -= 20
            reasons.append(f"grade/pay-scale prefix mismatch: requested {grade_prefix}")

    family = normalize_text(identity.family)
    if family and family in q and "exact canonical id or alias" not in reasons:
        score += 20
        reasons.append(f"family match: {identity.family}")

    return max(score, 0.0), reasons


def resolve_pay_system(root: Path, query: str, limit: int = 5) -> PaySystemResolution:
    """Resolve human tariff/besoldung terminology to ranked canonical table ids."""
    if not query.strip():
        raise AnalyticsError("query must not be empty.")
    if limit < 1 or limit > 20:
        raise AnalyticsError("limit must be between 1 and 20.")
    candidates: list[PaySystemMatch] = []
    for identity in list_pay_system_catalog(root, limit=200):
        score, reasons = _score_identity(query, identity)
        if score <= 0:
            continue
        confidence: Literal["exact", "high", "medium", "low"]
        if score >= 100:
            confidence = "exact"
        elif score >= 70:
            confidence = "high"
        elif score >= 45:
            confidence = "medium"
        else:
            confidence = "low"
        candidates.append(PaySystemMatch(identity=identity, score=round(score, 2), confidence=confidence, reasons=reasons))
    candidates.sort(key=lambda item: (-item.score, item.identity.table_id.casefold()))
    selected = candidates[:limit]
    warning = None
    if not selected:
        warning = "No plausible pay-system match was found. Use list_pay_system_catalog to inspect canonical systems."
    elif selected[0].confidence == "low":
        warning = "The best match is weak; do not select it automatically without additional context."
    elif len(selected) > 1 and selected[0].score - selected[1].score < 15:
        warning = "The leading candidates are close; treat the resolution as ambiguous and ask for context before consequential use."
    jurisdiction = jurisdiction_from_query(query)
    return PaySystemResolution(
        query=query,
        jurisdiction_context_code=jurisdiction.code if jurisdiction else None,
        jurisdiction_context_name_de=jurisdiction.name_de if jurisdiction else None,
        grade_prefix_hint=grade_prefix_from_query(query),
        candidates=selected,
        ambiguity_warning=warning,
    )


def _snapshot_candidates(root: Path, table_id: str) -> list[tuple[date, Path, bool, dict[str, str]]]:
    current = _safe_table_dir(root, table_id)
    directories: list[tuple[Path, bool]] = [(current, True)]
    archive = root / "archive"
    pattern = re.compile(rf"^{re.escape(table_id)}-(?:19|20)\d{{2}}$")
    if archive.is_dir():
        directories.extend((path, False) for path in archive.iterdir() if path.is_dir() and pattern.match(path.name))
    result: list[tuple[date, Path, bool, dict[str, str]]] = []
    for directory, current_flag in directories:
        try:
            meta, _ = read_metadata(directory)
            valid_raw = meta.get("valid_from")
            if not valid_raw:
                continue
            valid = _parse_date(valid_raw)
        except AnalyticsError:
            continue
        result.append((valid, directory, current_flag, meta))
    result.sort(key=lambda item: (item[0], item[1].name))
    return result


def _resolve_snapshot_dir(root: Path, table_id: str, as_of: str) -> tuple[Path, SnapshotResolution, dict[str, str]]:
    requested = _parse_date(as_of)
    candidates = _snapshot_candidates(root, table_id)
    if not candidates:
        raise AnalyticsError(f"No dated current/archive snapshot is available for pay table {table_id!r}.")
    eligible = [item for item in candidates if item[0] <= requested]
    if not eligible:
        earliest = candidates[0][0]
        raise AnalyticsError(
            f"No known snapshot for {table_id!r} exists on or before {_iso(requested)}; earliest known valid_from is {_iso(earliest)}."
        )
    selected = eligible[-1]
    selected_date, directory, is_current, meta = selected
    later = [item[0] for item in candidates if item[0] > selected_date]
    next_known = min(later) if later else None

    if is_current:
        status = "exact_current_valid_from" if requested == selected_date else "current_latest_known"
        warning = None
        if requested > selected_date:
            warning = (
                "Resolved to the latest known current snapshot. TVData does not prove that no newer, unrecorded remuneration change applies by the requested date."
            )
    else:
        status = "exact_archived_valid_from" if requested == selected_date else "latest_known_archived_snapshot"
        warning = (
            "Historical resolution uses the latest known repository snapshot on or before the requested date. "
            "Archive coverage is not a legal completeness guarantee; intermediate tariff/besoldung changes may be absent."
        )

    return directory, SnapshotResolution(
        table_id=table_id,
        snapshot_id=directory.name,
        requested_as_of=_iso(requested),
        snapshot_valid_from=_iso(selected_date),
        current=is_current,
        resolution_status=status,  # type: ignore[arg-type]
        next_known_valid_from=_iso(next_known) if next_known else None,
        source=meta.get("link") or None,
        warning=warning,
    ), meta


def resolve_pay_snapshot(root: Path, table_id: str, as_of: str) -> SnapshotResolution:
    """Resolve a canonical pay table and date to the latest known repository snapshot."""
    _, resolution, _ = _resolve_snapshot_dir(root, table_id, as_of)
    return resolution


def get_base_pay_as_of(root: Path, table_id: str, pay_grade: str, step: str, as_of: str) -> BasePayAsOf:
    directory, snapshot, _ = _resolve_snapshot_dir(root, table_id, as_of)
    monthly = _read_pay(directory, pay_grade, step)
    return BasePayAsOf(
        table_id=table_id,
        pay_grade=pay_grade,
        step=step,
        requested_as_of=snapshot.requested_as_of,
        snapshot=snapshot,
        monthly_base_eur=monthly,
        annual_base_eur=round(monthly * 12, 2),
    )


def _working_hours_from_meta(meta: dict[str, str]) -> float | None:
    raw = meta.get("working_time_weekly") or ""
    numbers = [float(value.replace(",", ".")) for value in re.findall(r"(?<!\d)(\d{1,2}(?:[.,]\d+)?)(?!\d)", raw)]
    numbers = [value for value in numbers if 20 <= value <= 60]
    variable = any(marker in raw.casefold() for marker in ("je nach", " / ", "bestimmte", "schicht", "tarifgebiet")) or len(set(numbers)) > 1
    return numbers[0] if numbers and not variable else None


def compare_pay_positions_as_of(root: Path, positions: list[DatedPayPositionRequest]) -> DatedComparisonResult:
    """Compare exact positions at explicit dates using resolved repository snapshots."""
    if len(positions) < 2 or len(positions) > 20:
        raise AnalyticsError("positions must contain between 2 and 20 entries.")
    rows: list[DatedComparisonItem] = []
    warnings: list[str] = []
    for request in positions:
        directory, snapshot, meta = _resolve_snapshot_dir(root, request.table_id, request.as_of)
        monthly = _read_pay(directory, request.pay_grade, request.step)
        hours = request.weekly_hours_override
        basis = "caller_override" if hours is not None else "snapshot_metadata" if snapshot.current else "historical_context_unresolved"
        if hours is None and snapshot.current:
            hours = _working_hours_from_meta(meta)
            if hours is None:
                basis = "ambiguous_or_missing"
        hourly = round((monthly * 12) / (hours * 52), 2) if hours else None
        identity = identity_for_table(request.table_id, read_metadata(_safe_table_dir(root, request.table_id))[0])
        rows.append(
            DatedComparisonItem(
                table_id=request.table_id,
                snapshot_id=snapshot.snapshot_id,
                pay_grade=request.pay_grade,
                step=request.step,
                requested_as_of=snapshot.requested_as_of,
                snapshot_valid_from=snapshot.snapshot_valid_from,
                resolution_status=snapshot.resolution_status,
                name_de=identity.name_de,
                regime=identity.regime,
                monthly_base_eur=monthly,
                annual_base_eur=round(monthly * 12, 2),
                weekly_hours=hours,
                weekly_hours_basis=basis,
                base_per_contract_hour_eur=hourly,
                difference_from_first_eur=0.0,
                difference_from_first_pct=0.0,
                source=snapshot.source,
            )
        )
        if snapshot.warning:
            warnings.append(f"{request.table_id}: {snapshot.warning}")
    anchor = rows[0].monthly_base_eur
    for row in rows:
        row.difference_from_first_eur = round(row.monthly_base_eur - anchor, 2)
        row.difference_from_first_pct = round((row.monthly_base_eur / anchor - 1) * 100, 2) if anchor else None
    if len({row.requested_as_of for row in rows}) > 1:
        warnings.append("Compared positions use different requested as_of dates.")
    if len({row.regime for row in rows}) > 1:
        warnings.append("Mixed employment regimes: nominal pay proximity is not employment or total-compensation equivalence.")
    if any(row.weekly_hours is None for row in rows):
        warnings.append("Historical/context-dependent working time is unresolved for at least one position; hourly normalization is omitted there.")
    return DatedComparisonResult(positions=rows, warnings=list(dict.fromkeys(warnings)))


def rank_pay_positions_as_of(
    root: Path,
    pay_grade: str,
    step: str,
    as_of: str,
    table_ids: list[str] | None = None,
    query: str | None = None,
    regime: Literal["civil_service", "collective_agreement", "unknown"] | None = None,
    family: str | None = None,
    jurisdiction_code: str | None = None,
    limit: int = 20,
) -> DatedRankingResult:
    """Rank nominal base pay across systems at the latest known snapshots on/before one date."""
    if limit < 1 or limit > 100:
        raise AnalyticsError("limit must be between 1 and 100.")
    requested_iso = _iso(_parse_date(as_of))
    if table_ids:
        identities = []
        for table_id in table_ids:
            directory = _safe_table_dir(root, table_id)
            meta, _ = read_metadata(directory)
            identities.append(identity_for_table(table_id, meta))
    else:
        identities = list_pay_system_catalog(root, query=query, regime=regime, jurisdiction_code=jurisdiction_code, family=family, limit=200)
    rows: list[tuple[float, DatedRankingItem]] = []
    no_snapshot = 0
    missing_position = 0
    for identity in identities:
        if regime and identity.regime != regime:
            continue
        if family and normalize_text(identity.family) != normalize_text(family):
            continue
        if jurisdiction_code and (identity.jurisdiction_code or "").casefold() != jurisdiction_code.casefold():
            continue
        if query and normalize_text(query) not in normalize_text(" ".join([identity.table_id, identity.name_de or "", *identity.aliases])):
            continue
        try:
            directory, snapshot, _ = _resolve_snapshot_dir(root, identity.table_id, as_of)
        except AnalyticsError as exc:
            if "No known snapshot" in str(exc) or "No dated current/archive snapshot" in str(exc):
                no_snapshot += 1
                continue
            raise
        try:
            monthly = _read_pay(directory, pay_grade, step)
        except AnalyticsError as exc:
            if "Unknown pay grade" in str(exc) or "Unknown step" in str(exc) or "No base-pay value" in str(exc):
                missing_position += 1
                continue
            raise
        item = DatedRankingItem(
            rank=0,
            table_id=identity.table_id,
            snapshot_id=snapshot.snapshot_id,
            name_de=identity.name_de,
            regime=identity.regime,
            pay_grade=pay_grade,
            step=step,
            requested_as_of=requested_iso,
            snapshot_valid_from=snapshot.snapshot_valid_from,
            monthly_base_eur=monthly,
            annual_base_eur=round(monthly * 12, 2),
            source=snapshot.source,
        )
        rows.append((monthly, item))
    rows.sort(key=lambda pair: (-pair[0], pair[1].table_id.casefold()))
    ranked: list[DatedRankingItem] = []
    for index, (_, item) in enumerate(rows[:limit], start=1):
        item.rank = index
        ranked.append(item)
    return DatedRankingResult(
        requested_as_of=requested_iso,
        pay_grade=pay_grade,
        step=step,
        rows=ranked,
        tables_evaluated=len(identities),
        positions_found=len(rows),
        skipped_no_snapshot=no_snapshot,
        skipped_missing_position=missing_position,
        warning=(
            "Rankings use latest known repository snapshots on or before the requested date. Historical archive coverage may be incomplete, and nominal base pay is not total-compensation equivalence."
        ),
    )
