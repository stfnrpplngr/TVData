"""P2 compensation-component semantics and audit tests."""

from pathlib import Path

import pytest

from mcp_compensation import audit_compensation_components, inspect_compensation_components

ROOT = Path(__file__).resolve().parents[1]


def _component(inspection, allowance_id):
    return next(item for item in inspection.components if item.allowance_id == allowance_id)


def _option(component, option):
    return next(item for item in component.values if item.option == option)


def test_tv_l_annual_bonus_reconstructs_encoded_rate_without_calculating_payment():
    inspection = inspect_compensation_components(ROOT, "TV-L", "13")
    component = _component(inspection, "tv-l-annual-bonus")
    yes = _option(component, "yes")
    assert component.encoding == "relative_yearly"
    assert component.calculation_readiness == "requires_tariff_assessment_base"
    assert component.value_semantics == "annual_percentage_divided_by_12"
    assert yes.represented_annual_rate_pct == pytest.approx(46.47, abs=0.001)
    assert component.safe_for_total_annual_compensation is False


def test_tvoed_bund_2026_e13_annual_bonus_rate_is_75_percent():
    inspection = inspect_compensation_components(ROOT, "TVöD-Bund", "13")
    component = _component(inspection, "tvoed-bund-annual-bonus")
    yes = _option(component, "yes")
    assert yes.represented_annual_rate_pct == pytest.approx(75.0, abs=0.001)
    assert component.valid_from == "2026.01.01"
    assert component.source_quality == "high"


def test_tvoed_vka_2026_annual_bonus_rate_is_85_percent():
    inspection = inspect_compensation_components(ROOT, "TVöD-VKA", "13")
    component = _component(inspection, "tvoed-vka-annual-bonus")
    yes = _option(component, "yes")
    assert yes.represented_annual_rate_pct == pytest.approx(85.0, abs=0.001)


def test_generic_sue_profile_is_85_percent_and_excludes_bt_b_bt_k():
    inspection = inspect_compensation_components(ROOT, "TVöD-SuE", "13")
    component = _component(inspection, "tvoed-sue-annual-bonus")
    yes = _option(component, "yes")
    assert yes.represented_annual_rate_pct == pytest.approx(85.0, abs=0.001)
    assert component.scope == "generic-vka-s-table"
    assert component.excluded_contexts == ["TVöD-BT-B", "TVöD-BT-K"]
    assert any("excludes contexts" in warning for warning in component.warnings)


def test_updated_bund_bonus_passes_semantics_source_and_validity_checks():
    report = audit_compensation_components(ROOT, query="tvoed-bund-annual-bonus")
    codes = {issue.code for issue in report.issues}
    assert "relative_yearly_semantics_implicit" not in codes
    assert "missing_component_source" not in codes
    assert "missing_component_valid_from" not in codes
    assert "assessment_base_required" in codes
