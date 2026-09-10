"""Semantic-entity and temporal-resolution tests for the TVData MCP layer."""

from pathlib import Path

import pytest

from mcp_analytics import AnalyticsError, read_metadata
from mcp_intelligence import (
    DatedPayPositionRequest,
    compare_pay_positions_as_of,
    get_base_pay_as_of,
    resolve_pay_snapshot,
    resolve_pay_system,
)
from mcp_profile import identity_for_table

ROOT = Path(__file__).resolve().parents[1]


def test_profile_identifies_saxony_anhalt_civil_service_a_scale():
    meta, _ = read_metadata(ROOT / "tables" / "Beamte-LSA-A")
    identity = identity_for_table("Beamte-LSA-A", meta)
    assert identity.regime == "civil_service"
    assert identity.family == "Beamtenbesoldung"
    assert identity.scope == "state"
    assert identity.jurisdiction_code == "DE-ST"
    assert identity.jurisdiction_name_de == "Sachsen-Anhalt"
    assert identity.pay_scale == "A"


def test_resolver_maps_a13_lsa_to_canonical_table():
    result = resolve_pay_system(ROOT, "A13 LSA", limit=3)
    assert result.jurisdiction_context_code == "DE-ST"
    assert result.grade_prefix_hint == "A"
    assert result.candidates[0].identity.table_id == "Beamte-LSA-A"
    assert result.candidates[0].confidence in {"high", "exact"}


def test_resolver_maps_bund_e13_to_tvoed_bund():
    result = resolve_pay_system(ROOT, "Bund E13", limit=3)
    assert result.jurisdiction_context_code == "DE"
    assert result.grade_prefix_hint == "E"
    assert result.candidates[0].identity.table_id == "TVöD-Bund"


def test_resolver_preserves_state_as_context_for_tv_l():
    result = resolve_pay_system(ROOT, "TV-L Sachsen-Anhalt", limit=3)
    assert result.jurisdiction_context_code == "DE-ST"
    assert result.candidates[0].identity.table_id == "TV-L"
    assert result.candidates[0].identity.scope == "multi_state"


def test_as_of_resolver_uses_archived_tv_l_snapshot():
    snapshot = resolve_pay_snapshot(ROOT, "TV-L", "2023-06-01")
    assert snapshot.snapshot_id == "TV-L-2022"
    assert snapshot.current is False
    assert snapshot.snapshot_valid_from == "2022-12-02"
    assert snapshot.resolution_status == "latest_known_archived_snapshot"
    assert snapshot.warning


def test_base_pay_as_of_returns_archived_value():
    result = get_base_pay_as_of(ROOT, "TV-L", "13", "4", "01.06.2023")
    assert result.snapshot.snapshot_id == "TV-L-2022"
    assert result.monthly_base_eur == 5215.72
    assert result.annual_base_eur == 62588.64


def test_as_of_resolver_uses_current_tv_l_after_current_valid_from():
    snapshot = resolve_pay_snapshot(ROOT, "TV-L", "2026-06-01")
    assert snapshot.snapshot_id == "TV-L"
    assert snapshot.current is True
    assert snapshot.snapshot_valid_from == "2026-04-01"


def test_as_of_before_earliest_snapshot_is_model_correctable():
    with pytest.raises(AnalyticsError, match="earliest known valid_from"):
        resolve_pay_snapshot(ROOT, "TV-L", "2020-01-01")


def test_dated_comparison_can_compare_same_position_across_time():
    result = compare_pay_positions_as_of(
        ROOT,
        [
            DatedPayPositionRequest(table_id="TV-L", pay_grade="13", step="4", as_of="2023-06-01"),
            DatedPayPositionRequest(table_id="TV-L", pay_grade="13", step="4", as_of="2026-06-01", weekly_hours_override=40),
        ],
    )
    assert result.positions[0].snapshot_id == "TV-L-2022"
    assert result.positions[0].monthly_base_eur == 5215.72
    assert result.positions[1].snapshot_id == "TV-L"
    assert result.positions[1].monthly_base_eur == 5873.56
    assert result.positions[1].difference_from_first_eur == 657.84
    assert any("Historical resolution" in warning for warning in result.warnings)
