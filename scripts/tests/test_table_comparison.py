import os
import sys

scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from scripts.table_comparison import (
    build_heatmap,
    build_progression_graph_data,
    build_progression_logic_comparison,
    calculate_metrics,
    compare_allowances,
    compare_multiple_tables,
)


def test_heatmap_has_known_cells():
    data = build_heatmap("TV-L", "TVöD-VKA")
    assert data["base_table"] == "TV-L"
    assert data["compare_table"] == "TVöD-VKA"
    assert len(data["cells"]) > 0
    first = data["cells"][0]
    assert {"group", "stage", "base", "compare", "delta", "delta_pct"}.issubset(first.keys())


def test_progression_graph_contains_common_groups():
    graph = build_progression_graph_data("TV-L", "TVöD-VKA")
    assert graph["groups"]
    sample_group = next(iter(graph["groups"]))
    assert graph["groups"][sample_group]["base"]
    assert graph["groups"][sample_group]["compare"]
    assert "duration_years" in graph["groups"][sample_group]["base"][0]


def test_progression_logic_deltas_are_present():
    logic = build_progression_logic_comparison("TV-L", "TVöD-VKA")
    assert logic["groups"]
    sample_group = next(iter(logic["groups"]))
    sample_stage = logic["groups"][sample_group]["stages"][0]
    assert "delta_years" in sample_stage


def test_metrics_output_shape():
    metrics = calculate_metrics("TV-L")
    assert metrics["count"] > 0
    assert metrics["spread"] >= 0
    assert metrics["max"] >= metrics["min"]


def test_allowance_comparison_resolves_entries():
    allowances = compare_allowances(["TV-L", "TVöD-VKA"])
    assert "by_table" in allowances
    assert "presence_matrix" in allowances
    assert "TV-L" in allowances["by_table"]


def test_compare_multiple_tables_payload():
    payload = compare_multiple_tables(["TV-L", "TVöD-VKA", "TV-H"], baseline="TV-L")
    assert payload["baseline"] == "TV-L"
    assert len(payload["baseline_comparisons"]) == 2
    assert len(payload["pairwise_comparisons"]) == 3
    assert "progression_logic" in payload["baseline_comparisons"][0]
