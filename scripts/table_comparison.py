"""Utilities for comparing remuneration tables across collective agreements.

The module prepares UI-friendly data structures for:
- heatmaps (cell-wise salary deltas)
- progression graph series (salary development over progression years)
- progression logic visibility (durations and cumulative years)
- objective metrics (mean, median, spread)
- allowance overviews
"""

from __future__ import annotations

from itertools import combinations
import csv
import os
from statistics import mean, median
from typing import Dict, List, Optional, Tuple

from .defs import ps_allowances_path, ps_tables_path


Number = float
Grid = Dict[str, Dict[str, str]]


def _read_key_value_csv(path: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as infile:
        reader = csv.reader(infile)
        headers = next(reader, [])
        if len(headers) < 2:
            return data
        for row in reader:
            if len(row) < 2:
                continue
            data[row[0]] = row[1]
    return data


def _read_grid_csv(path: str) -> Grid:
    data: Grid = {}
    with open(path, "r", encoding="utf-8") as infile:
        reader = csv.reader(infile)
        headers = next(reader)
        stages = headers[1:]
        for row in reader:
            if not row:
                continue
            group = row[0]
            values = {stage: (row[idx + 1] if idx + 1 < len(row) else "") for idx, stage in enumerate(stages)}
            data[group] = values
    return data


def _to_float(value: str) -> Optional[Number]:
    if value is None:
        return None
    value = str(value).strip().replace(",", ".")
    if value == "":
        return None
    return float(value)


def _extract_cells(table_grid: Grid) -> Dict[Tuple[str, str], Number]:
    cells: Dict[Tuple[str, str], Number] = {}
    for group, stage_data in table_grid.items():
        for stage, raw in stage_data.items():
            parsed = _to_float(raw)
            if parsed is not None:
                cells[(group, stage)] = parsed
    return cells


def _allowance_names(meta: Dict[str, str]) -> List[str]:
    return [item.strip() for item in meta.get("allowances", "").split(";") if item.strip()]


def load_table_bundle(table_name: str) -> Dict[str, object]:
    """Load Table.csv, Adv.csv and Meta.csv for one tariff table."""
    base = os.path.join(ps_tables_path, table_name)
    if not os.path.isdir(base):
        raise ValueError(f"Unknown table '{table_name}'")

    return {
        "name": table_name,
        "table": _read_grid_csv(os.path.join(base, "Table.csv")),
        "adv": _read_grid_csv(os.path.join(base, "Adv.csv")),
        "meta": _read_key_value_csv(os.path.join(base, "Meta.csv")),
    }


def build_heatmap(base_table: str, compare_table: str) -> Dict[str, object]:
    """Return cell-wise salary deltas for equal group/stage coordinates."""
    left = load_table_bundle(base_table)
    right = load_table_bundle(compare_table)

    left_cells = _extract_cells(left["table"])
    right_cells = _extract_cells(right["table"])

    common = sorted(set(left_cells.keys()) & set(right_cells.keys()))
    entries = []
    for group, stage in common:
        base = left_cells[(group, stage)]
        compare = right_cells[(group, stage)]
        delta = compare - base
        pct = (delta / base) * 100 if base else 0.0
        entries.append(
            {
                "group": group,
                "stage": stage,
                "base": round(base, 2),
                "compare": round(compare, 2),
                "delta": round(delta, 2),
                "delta_pct": round(pct, 2),
            }
        )

    return {
        "base_table": base_table,
        "compare_table": compare_table,
        "cells": entries,
    }


def _progression_points(bundle: Dict[str, object]) -> Dict[str, List[Dict[str, Number]]]:
    series: Dict[str, List[Dict[str, Number]]] = {}
    for group, salary_row in bundle["table"].items():
        points: List[Dict[str, Number]] = []
        year_cursor = 0.0
        for stage, salary_raw in salary_row.items():
            salary = _to_float(salary_raw)
            if salary is None:
                continue
            duration = _to_float(bundle["adv"].get(group, {}).get(stage, "")) or 0.0
            points.append(
                {
                    "group": group,
                    "stage": stage,
                    "start_year": round(year_cursor, 2),
                    "duration_years": round(duration, 2),
                    "salary": round(salary, 2),
                }
            )
            year_cursor += duration
        if points:
            series[group] = points
    return series


def build_progression_graph_data(base_table: str, compare_table: str) -> Dict[str, object]:
    """Build graph-ready series for progression-based salary development."""
    left = load_table_bundle(base_table)
    right = load_table_bundle(compare_table)

    left_series = _progression_points(left)
    right_series = _progression_points(right)
    common_groups = sorted(set(left_series.keys()) & set(right_series.keys()))

    return {
        "base_table": base_table,
        "compare_table": compare_table,
        "groups": {
            group: {
                "base": left_series[group],
                "compare": right_series[group],
            }
            for group in common_groups
        },
    }


def build_progression_logic_comparison(base_table: str, compare_table: str) -> Dict[str, object]:
    """Expose progression logic differences (stage duration and total years)."""
    left = load_table_bundle(base_table)
    right = load_table_bundle(compare_table)

    left_groups = set(left["adv"].keys())
    right_groups = set(right["adv"].keys())
    common_groups = sorted(left_groups & right_groups)

    groups = {}
    for group in common_groups:
        left_row = left["adv"].get(group, {})
        right_row = right["adv"].get(group, {})
        stages = sorted(set(left_row.keys()) & set(right_row.keys()), key=lambda item: (len(item), item))

        stage_rows = []
        left_total = 0.0
        right_total = 0.0
        for stage in stages:
            left_duration = _to_float(left_row.get(stage, ""))
            right_duration = _to_float(right_row.get(stage, ""))
            if left_duration is None or right_duration is None:
                continue
            left_total += left_duration
            right_total += right_duration
            stage_rows.append(
                {
                    "stage": stage,
                    "base_duration_years": round(left_duration, 2),
                    "compare_duration_years": round(right_duration, 2),
                    "delta_years": round(right_duration - left_duration, 2),
                }
            )

        if stage_rows:
            groups[group] = {
                "stages": stage_rows,
                "base_total_years": round(left_total, 2),
                "compare_total_years": round(right_total, 2),
                "delta_total_years": round(right_total - left_total, 2),
            }

    return {
        "base_table": base_table,
        "compare_table": compare_table,
        "groups": groups,
    }


def calculate_metrics(table_name: str) -> Dict[str, Number]:
    """Compute objective salary distribution metrics for one table."""
    bundle = load_table_bundle(table_name)
    values = list(_extract_cells(bundle["table"]).values())
    if not values:
        raise ValueError(f"Table '{table_name}' has no numeric salary values")

    min_val = min(values)
    max_val = max(values)

    return {
        "table": table_name,
        "count": len(values),
        "mean": round(mean(values), 2),
        "median": round(median(values), 2),
        "min": round(min_val, 2),
        "max": round(max_val, 2),
        "spread": round(max_val - min_val, 2),
    }


def _allowance_label(meta: Dict[str, str]) -> str:
    return meta.get("label_de") or meta.get("label_en") or "(unbenannt)"


def _allowance_summary(allowance_name: str) -> Dict[str, object]:
    allowance_dir = os.path.join(ps_allowances_path, allowance_name)
    meta_path = os.path.join(allowance_dir, "Meta.csv")
    table_path = os.path.join(allowance_dir, "Table.csv")

    if not os.path.isfile(meta_path) or not os.path.isfile(table_path):
        return {
            "allowance": allowance_name,
            "available": False,
        }

    meta = _read_key_value_csv(meta_path)
    table = _read_grid_csv(table_path)

    values: List[Number] = []
    for row in table.values():
        for raw in row.values():
            parsed = _to_float(raw)
            if parsed is not None:
                values.append(parsed)

    return {
        "allowance": allowance_name,
        "available": True,
        "label": _allowance_label(meta),
        "adding_type": meta.get("adding_type", ""),
        "func_type": meta.get("func_type", ""),
        "options": [item.strip() for item in meta.get("options", "").split(";") if item.strip()],
        "min_value": round(min(values), 2) if values else None,
        "max_value": round(max(values), 2) if values else None,
    }


def compare_allowances(table_names: List[str]) -> Dict[str, object]:
    """Compare allowance sets and characteristics across selected tables."""
    table_allowances: Dict[str, List[Dict[str, object]]] = {}
    allowance_sets: Dict[str, set] = {}

    for table_name in table_names:
        bundle = load_table_bundle(table_name)
        names = _allowance_names(bundle["meta"])
        table_allowances[table_name] = [_allowance_summary(name) for name in names]
        allowance_sets[table_name] = set(names)

    all_allowances = sorted(set().union(*allowance_sets.values())) if allowance_sets else []
    presence_matrix = {
        allowance: {table: allowance in allowance_sets[table] for table in table_names}
        for allowance in all_allowances
    }

    return {
        "by_table": table_allowances,
        "presence_matrix": presence_matrix,
    }


def compare_multiple_tables(table_names: List[str], baseline: Optional[str] = None) -> Dict[str, object]:
    """Aggregate comparison payload for multi-select table comparisons in the UI."""
    if len(table_names) < 2:
        raise ValueError("At least two tables are required for comparison")

    unique_tables = list(dict.fromkeys(table_names))
    for table in unique_tables:
        load_table_bundle(table)

    if baseline is None:
        baseline = unique_tables[0]
    if baseline not in unique_tables:
        raise ValueError("Baseline must be included in table_names")

    metrics = {table: calculate_metrics(table) for table in unique_tables}

    baseline_comparisons = []
    for table in unique_tables:
        if table == baseline:
            continue
        baseline_comparisons.append(
            {
                "target": table,
                "heatmap": build_heatmap(baseline, table),
                "graph": build_progression_graph_data(baseline, table),
                "progression_logic": build_progression_logic_comparison(baseline, table),
            }
        )

    pairwise = []
    for left_table, right_table in combinations(unique_tables, 2):
        pairwise.append(
            {
                "a": left_table,
                "b": right_table,
                "heatmap": build_heatmap(left_table, right_table),
                "graph": build_progression_graph_data(left_table, right_table),
                "progression_logic": build_progression_logic_comparison(left_table, right_table),
            }
        )

    return {
        "selected_tables": unique_tables,
        "baseline": baseline,
        "metrics": metrics,
        "baseline_comparisons": baseline_comparisons,
        "pairwise_comparisons": pairwise,
        "allowances": compare_allowances(unique_tables),
    }
