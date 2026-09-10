"""Comparison and data-quality tests for the TVData MCP analytics layer."""

from pathlib import Path

from mcp_analytics import (
    PayPositionRequest,
    compare_positions,
    find_nearest_base_pay,
    get_pay_history,
    get_provenance,
    get_table_structure,
    rank_base_pay,
    read_metadata,
)

ROOT = Path(__file__).resolve().parents[1]


def test_metadata_reader_accepts_key_value_variant():
    meta, key_column = read_metadata(ROOT / "tables" / "Beamte-LSA-A")
    assert key_column == "key"
    assert meta["pay_grad_name"] == "A"
    assert meta["name_de"] == "Landesbesoldungsordnung A Sachsen-Anhalt"


def test_compare_tv_l_with_tvoed_bund_and_working_time_override():
    result = compare_positions(
        ROOT,
        [
            PayPositionRequest(table_id="TV-L", pay_grade="13", step="4", weekly_hours_override=40),
            PayPositionRequest(table_id="TVöD-Bund", pay_grade="13", step="4"),
        ],
    )
    assert result.positions[0].monthly_base_eur == 5873.56
    assert result.positions[1].monthly_base_eur == 6177.31
    assert result.positions[1].difference_from_first_eur == 303.75
    assert result.positions[0].base_per_contract_hour_eur == 33.89
    assert result.positions[1].base_per_contract_hour_eur == 36.55


def test_history_combines_archive_and_current_table():
    history = get_pay_history(ROOT, "TV-L", "13", "4")
    assert len(history.points) >= 2
    assert history.points[0].snapshot_id == "TV-L-2022"
    assert history.points[0].monthly_base_eur == 5215.72
    assert history.points[-1].current is True
    assert history.points[-1].monthly_base_eur == 5873.56


def test_provenance_includes_working_time_source():
    provenance = get_provenance(ROOT, "TVöD-Bund")
    assert provenance.pay_table_source
    assert provenance.working_time.standard_hours == 39
    assert provenance.working_time.source
    assert provenance.provenance_status == "pay_table_and_working_time_sourced"


def test_structure_exposes_valid_dimensions_to_agents():
    structure = get_table_structure(ROOT, "TV-L")
    assert "13" in structure.grades
    assert structure.steps == ["1", "2", "3", "4", "5", "6"]
    assert "tv-l-annual-bonus" in structure.linked_allowances


def test_rank_civil_service_a13_step4_includes_saxony_anhalt():
    ranking = rank_base_pay(
        ROOT,
        pay_grade="13",
        step="4",
        regime="civil_service",
        metric="monthly_base",
        limit=100,
    )
    row = next(item for item in ranking.rows if item.table_id == "Beamte-LSA-A")
    assert row.monthly_base_eur == 5515.26


def test_nearest_pay_search_never_claims_equivalence():
    result = find_nearest_base_pay(
        ROOT,
        PayPositionRequest(table_id="TV-L", pay_grade="13", step="4"),
        candidate_regime="civil_service",
        limit=5,
    )
    assert result.matches
    assert "do not establish equivalent duties" in result.warning
