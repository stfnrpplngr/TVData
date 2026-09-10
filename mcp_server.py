"""Read-only Model Context Protocol server for the TVData repository.

The CSV files in this repository remain the source of truth. This module only
provides a structured MCP interface over those files and never mutates them.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_analytics import AnalyticsError, read_metadata
from mcp_tools import register_analytics_tools

ROOT = Path(__file__).resolve().parent
TABLES_DIR = ROOT / "tables"
ALLOWANCES_DIR = ROOT / "allowances"
PENSIONS_DIR = ROOT / "prv"

mcp = MCPServer("TVData")


@dataclass
class PayTableSummary:
    table_id: str
    name_de: str | None
    name_en: str | None
    valid_from: str | None
    working_time_weekly: str | None
    source: str | None


@dataclass
class PayValue:
    table_id: str
    pay_grade: str
    step: str
    monthly_gross_eur: float
    valid_from: str | None
    source: str | None


@dataclass
class Progression:
    table_id: str
    pay_grade: str
    years_to_next_step: dict[str, str | None]


@dataclass
class AllowanceSummary:
    allowance_id: str
    label_de: str | None
    label_en: str | None
    func_type: str | None
    adding_type: str | None


@dataclass
class AllowanceValue:
    allowance_id: str
    pay_grade: str
    option: str
    value: str
    numeric_value: float | None
    func_type: str | None
    adding_type: str | None
    label_de: str | None
    label_en: str | None


@dataclass
class PensionSummary:
    pension_id: str
    label_de: str | None
    label_en: str | None
    calc_fun: str | None
    source: str | None


def _safe_dir(base: Path, item_id: str, kind: str) -> Path:
    """Resolve exactly one direct child directory and block path traversal."""
    if not item_id or item_id in {".", ".."} or "/" in item_id or "\\" in item_id:
        raise ToolError(f"Invalid {kind} identifier: {item_id!r}.")
    candidate = (base / item_id).resolve()
    if candidate.parent != base.resolve() or not candidate.is_dir():
        raise ToolError(f"Unknown {kind}: {item_id!r}.")
    return candidate


def _read_meta(directory: Path) -> dict[str, str]:
    """Read Meta.csv while accepting both `name,value` and `key,value`."""
    try:
        result, _ = read_metadata(directory)
        return result
    except AnalyticsError as exc:
        raise ToolError(str(exc)) from exc


def _read_matrix(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    if not path.is_file():
        raise ToolError(f"Missing data file: {path.relative_to(ROOT)}.")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ToolError(f"Empty data file: {path.relative_to(ROOT)}.") from exc
        if len(header) < 2:
            raise ToolError(f"Invalid matrix schema: {path.relative_to(ROOT)}.")

        columns = [cell.strip() for cell in header[1:]]
        rows: dict[str, dict[str, str]] = {}
        for raw_row in reader:
            if not raw_row:
                continue
            row_id = raw_row[0].strip()
            if not row_id:
                continue
            values = list(raw_row[1:]) + [""] * max(0, len(columns) - len(raw_row[1:]))
            rows[row_id] = {
                column: values[index].strip() if index < len(values) else ""
                for index, column in enumerate(columns)
            }
    return columns, rows


def _split_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def _matches(query: str | None, *values: str | None) -> bool:
    if not query:
        return True
    needle = query.casefold().strip()
    return any(needle in (value or "").casefold() for value in values)


def _bounded_limit(limit: int) -> int:
    if limit < 1 or limit > 200:
        raise ToolError("limit must be between 1 and 200.")
    return limit


def _to_float(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


@mcp.tool()
def list_pay_tables(query: str | None = None, limit: int = 50) -> list[PayTableSummary]:
    """List available remuneration/pay tables, optionally filtered by id or name."""
    limit = _bounded_limit(limit)
    results: list[PayTableSummary] = []
    directories = sorted((p for p in TABLES_DIR.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
    for directory in directories:
        try:
            meta = _read_meta(directory)
        except ToolError:
            continue
        if not _matches(query, directory.name, meta.get("name_de"), meta.get("name_en")):
            continue
        results.append(
            PayTableSummary(
                table_id=directory.name,
                name_de=meta.get("name_de") or None,
                name_en=meta.get("name_en") or None,
                valid_from=meta.get("valid_from") or None,
                working_time_weekly=meta.get("working_time_weekly") or None,
                source=meta.get("link") or None,
            )
        )
        if len(results) >= limit:
            break
    return results


@mcp.tool()
def get_pay_table_metadata(table_id: str) -> dict[str, str]:
    """Return all metadata for one remuneration/pay table."""
    directory = _safe_dir(TABLES_DIR, table_id, "pay table")
    return _read_meta(directory)


@mcp.tool()
def get_base_pay(table_id: str, pay_grade: str, step: str) -> PayValue:
    """Return monthly gross base pay for an exact table, pay grade and step."""
    directory = _safe_dir(TABLES_DIR, table_id, "pay table")
    _, rows = _read_matrix(directory / "Table.csv")
    if pay_grade not in rows:
        raise ToolError(f"Unknown pay grade {pay_grade!r} in table {table_id!r}.")
    if step not in rows[pay_grade]:
        raise ToolError(f"Unknown step {step!r} in table {table_id!r}.")
    raw_value = rows[pay_grade][step]
    if not raw_value:
        raise ToolError(
            f"No base-pay value exists for table {table_id!r}, grade {pay_grade!r}, step {step!r}."
        )
    numeric = _to_float(raw_value)
    if numeric is None:
        raise ToolError(
            f"Base-pay value {raw_value!r} for table {table_id!r}, grade {pay_grade!r}, step {step!r} is not numeric."
        )
    meta = _read_meta(directory)
    return PayValue(
        table_id=table_id,
        pay_grade=pay_grade,
        step=step,
        monthly_gross_eur=numeric,
        valid_from=meta.get("valid_from") or None,
        source=meta.get("link") or None,
    )


@mcp.tool()
def get_progression(table_id: str, pay_grade: str) -> Progression:
    """Return the documented years required to progress from each step for one pay grade."""
    directory = _safe_dir(TABLES_DIR, table_id, "pay table")
    _, rows = _read_matrix(directory / "Adv.csv")
    if pay_grade not in rows:
        raise ToolError(f"Unknown pay grade {pay_grade!r} in progression table {table_id!r}.")
    return Progression(
        table_id=table_id,
        pay_grade=pay_grade,
        years_to_next_step={step: (value or None) for step, value in rows[pay_grade].items()},
    )


@mcp.tool()
def list_allowances(
    table_id: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[AllowanceSummary]:
    """List allowances globally or only those linked from a remuneration table."""
    limit = _bounded_limit(limit)
    if table_id:
        table_dir = _safe_dir(TABLES_DIR, table_id, "pay table")
        ids = _split_ids(_read_meta(table_dir).get("allowances"))
    else:
        ids = sorted((p.name for p in ALLOWANCES_DIR.iterdir() if p.is_dir()), key=str.casefold)

    results: list[AllowanceSummary] = []
    for allowance_id in ids:
        try:
            directory = _safe_dir(ALLOWANCES_DIR, allowance_id, "allowance")
            meta = _read_meta(directory)
        except ToolError:
            continue
        if not _matches(query, allowance_id, meta.get("label_de"), meta.get("label_en"), meta.get("info_de")):
            continue
        results.append(
            AllowanceSummary(
                allowance_id=allowance_id,
                label_de=meta.get("label_de") or None,
                label_en=meta.get("label_en") or None,
                func_type=meta.get("func_type") or None,
                adding_type=meta.get("adding_type") or None,
            )
        )
        if len(results) >= limit:
            break
    return results


@mcp.tool()
def get_allowance_value(allowance_id: str, pay_grade: str, option: str) -> AllowanceValue:
    """Return one allowance value plus metadata; a '-1' row is treated as applying to all grades."""
    directory = _safe_dir(ALLOWANCES_DIR, allowance_id, "allowance")
    _, rows = _read_matrix(directory / "Table.csv")
    row = rows.get(pay_grade) or rows.get("-1")
    if row is None:
        raise ToolError(f"Allowance {allowance_id!r} has no row for pay grade {pay_grade!r} and no '-1' fallback.")
    if option not in row:
        raise ToolError(f"Unknown option {option!r} for allowance {allowance_id!r}.")
    value = row[option]
    if value == "":
        raise ToolError(
            f"No allowance value exists for {allowance_id!r}, grade {pay_grade!r}, option {option!r}."
        )
    meta = _read_meta(directory)
    return AllowanceValue(
        allowance_id=allowance_id,
        pay_grade=pay_grade,
        option=option,
        value=value,
        numeric_value=_to_float(value),
        func_type=meta.get("func_type") or None,
        adding_type=meta.get("adding_type") or None,
        label_de=meta.get("label_de") or None,
        label_en=meta.get("label_en") or None,
    )


@mcp.tool()
def get_allowance_metadata(allowance_id: str) -> dict[str, str]:
    """Return all metadata for one allowance."""
    directory = _safe_dir(ALLOWANCES_DIR, allowance_id, "allowance")
    return _read_meta(directory)


@mcp.tool()
def list_pension_plans(
    table_id: str | None = None,
    query: str | None = None,
    limit: int = 100,
) -> list[PensionSummary]:
    """List supplementary pension plans globally or only those linked from a pay table."""
    limit = _bounded_limit(limit)
    if table_id:
        table_dir = _safe_dir(TABLES_DIR, table_id, "pay table")
        ids = _split_ids(_read_meta(table_dir).get("prv"))
    else:
        ids = sorted((p.name for p in PENSIONS_DIR.iterdir() if p.is_dir()), key=str.casefold)

    results: list[PensionSummary] = []
    for pension_id in ids:
        try:
            directory = _safe_dir(PENSIONS_DIR, pension_id, "pension plan")
            meta = _read_meta(directory)
        except ToolError:
            continue
        if not _matches(query, pension_id, meta.get("label_de"), meta.get("label_en"), meta.get("info_de")):
            continue
        results.append(
            PensionSummary(
                pension_id=pension_id,
                label_de=meta.get("label_de") or None,
                label_en=meta.get("label_en") or None,
                calc_fun=meta.get("calc_fun") or None,
                source=meta.get("link") or None,
            )
        )
        if len(results) >= limit:
            break
    return results


@mcp.tool()
def get_pension_metadata(pension_id: str) -> dict[str, str]:
    """Return all metadata for one supplementary pension plan."""
    directory = _safe_dir(PENSIONS_DIR, pension_id, "pension plan")
    return _read_meta(directory)


# Register higher-level comparison, ranking, history and provenance tools.
register_analytics_tools(mcp, ROOT)


def main() -> None:
    """Run locally over stdio or remotely over Streamable HTTP."""
    transport = os.getenv("TVDATA_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run()
        return
    if transport in {"http", "streamable-http"}:
        host = os.getenv("TVDATA_MCP_HOST", "127.0.0.1")
        port = int(os.getenv("TVDATA_MCP_PORT", "8000"))
        mcp.run(transport="streamable-http", host=host, port=port)
        return
    raise SystemExit("TVDATA_MCP_TRANSPORT must be 'stdio' or 'streamable-http'.")


if __name__ == "__main__":
    main()
