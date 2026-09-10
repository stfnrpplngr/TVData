"""P1 application-profile, working-time and source-quality tests."""

from pathlib import Path

from mcp_context import (
    ContextualPayPositionRequest,
    assess_pay_system_sources,
    compare_pay_positions_contextual,
    get_profile_manifest,
    resolve_working_time,
)

ROOT = Path(__file__).resolve().parents[1]


def test_profile_manifest_is_explicitly_versioned():
    manifest = get_profile_manifest(ROOT)
    assert manifest.profile_id == "tvdata-tariff-intelligence"
    assert manifest.profile_version == "0.4.0"
    assert manifest.schema_version == "1.0.0"
    assert manifest.source_of_truth == "repository-csv"
    assert "read-only" in manifest.guardrails


def test_tv_l_requires_jurisdiction_for_working_time():
    result = resolve_working_time(ROOT, "TV-L")
    assert result.status == "unresolved_context_required"
    assert result.weekly_hours is None
    assert "DE-ST" in result.available_jurisdictions


def test_tv_l_saxony_anhalt_resolves_to_40_hours():
    result = resolve_working_time(ROOT, "TV-L", "DE-ST")
    assert result.status == "resolved_context"
    assert result.jurisdiction_name_de == "Sachsen-Anhalt"
    assert result.weekly_hours == 40.0
    assert result.weekly_hours_hhmm == "40:00"
    assert result.evidence_quality == "high"
    assert result.legal_basis_url


def test_tv_l_context_is_not_projected_before_documented_profile_date():
    result = resolve_working_time(ROOT, "TV-L", "DE-ST", as_of="2024-12-31")
    assert result.status == "no_known_record"
    assert result.weekly_hours is None


def test_tvoed_bund_uses_unambiguous_table_default():
    result = resolve_working_time(ROOT, "TVöD-Bund")
    assert result.status == "resolved_table_default"
    assert result.weekly_hours == 39.0
    assert result.evidence_quality == "high"


def test_contextual_comparison_normalizes_tv_l_without_manual_override():
    result = compare_pay_positions_contextual(
        ROOT,
        [
            ContextualPayPositionRequest(
                table_id="TV-L",
                pay_grade="13",
                step="4",
                jurisdiction_code="DE-ST",
            ),
            ContextualPayPositionRequest(
                table_id="TVöD-Bund",
                pay_grade="13",
                step="4",
            ),
        ],
    )
    assert result.comparison.positions[0].monthly_base_eur == 5873.56
    assert result.comparison.positions[0].weekly_hours == 40.0
    assert result.comparison.positions[0].base_per_contract_hour_eur == 33.89
    assert result.comparison.positions[0].weekly_hours_basis == "profile_context"
    assert result.comparison.positions[1].monthly_base_eur == 6177.31
    assert result.comparison.positions[1].weekly_hours == 39.0
    assert result.comparison.positions[1].base_per_contract_hour_eur == 36.55


def test_updated_tv_l_and_tvoed_sources_are_classified_high_quality():
    tv_l = assess_pay_system_sources(ROOT, "TV-L")
    tvoed = assess_pay_system_sources(ROOT, "TVöD-Bund")
    assert tv_l.pay_evidence_quality == "high"
    assert tv_l.working_time_evidence_quality == "high"
    assert tvoed.pay_evidence_quality == "high"
    assert tvoed.working_time_evidence_quality == "high"
