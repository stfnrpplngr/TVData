"""P3 annual special-payment rule and conditional-arithmetic tests."""

from pathlib import Path

import pytest

from mcp_analytics import AnalyticsError
from mcp_special_payments import (
    calculate_annual_special_payment,
    get_annual_special_payment_rule,
)

ROOT = Path(__file__).resolve().parents[1]


def test_tv_l_and_tvoed_have_distinct_late_start_thresholds():
    tv_l = get_annual_special_payment_rule(ROOT, "TV-L", "13")
    bund = get_annual_special_payment_rule(ROOT, "TVöD-Bund", "13")
    assert tv_l.late_start_threshold == "08-31"
    assert tv_l.late_start_rate_rule == "pay_grade_on_start_date"
    assert bund.late_start_threshold == "09-30"
    assert bund.late_start_rate_rule is None


def test_tv_l_e13ue_requires_step_for_conditional_rate():
    with pytest.raises(AnalyticsError, match="step-dependent"):
        get_annual_special_payment_rule(ROOT, "TV-L", "13Ü")


def test_tv_l_e13ue_steps_2_and_3_use_e13_rate():
    for step in ("2", "3"):
        rule = get_annual_special_payment_rule(ROOT, "TV-L", "13Ü", step=step)
        assert rule.annual_rate_pct == pytest.approx(46.47, abs=0.001)
        assert rule.conditional_rate_applied is True
        assert rule.step == step


def test_tv_l_e13ue_other_valid_steps_use_e14_rate():
    for step in ("4", "5", "6"):
        rule = get_annual_special_payment_rule(ROOT, "TV-L", "13Ü", step=step)
        assert rule.annual_rate_pct == pytest.approx(32.53, abs=0.001)
        assert rule.conditional_rate_applied is True


def test_tv_l_e13ue_rejects_unavailable_step():
    with pytest.raises(AnalyticsError, match="valid steps"):
        get_annual_special_payment_rule(ROOT, "TV-L", "13Ü", step="1")


def test_bund_e13_full_special_payment_from_confirmed_inputs():
    result = calculate_annual_special_payment(
        ROOT,
        "TVöD-Bund",
        "13",
        confirmed_assessment_base_monthly_eur=6000.0,
        payable_twelfths=12,
        entitlement_confirmed=True,
    )
    assert result.annual_rate_pct == pytest.approx(75.0)
    assert result.special_payment_eur == 4500.0
    assert "assessment_base_monthly_eur" in result.calculation_formula


def test_bund_proration_uses_caller_confirmed_twelfths_only():
    result = calculate_annual_special_payment(
        ROOT,
        "TVöD-Bund",
        "13",
        confirmed_assessment_base_monthly_eur=6000.0,
        payable_twelfths=9,
        entitlement_confirmed=True,
    )
    assert result.special_payment_eur == 3375.0
    assert any("caller-confirmed" in warning for warning in result.warnings)


def test_calculation_refuses_to_infer_entitlement():
    with pytest.raises(AnalyticsError, match="entitlement_confirmed"):
        calculate_annual_special_payment(
            ROOT,
            "TVöD-Bund",
            "13",
            confirmed_assessment_base_monthly_eur=6000.0,
            payable_twelfths=12,
            entitlement_confirmed=False,
        )


def test_calculation_rejects_non_finite_assessment_base():
    with pytest.raises(AnalyticsError, match="must be finite"):
        calculate_annual_special_payment(
            ROOT,
            "TVöD-Bund",
            "13",
            confirmed_assessment_base_monthly_eur=float("nan"),
            payable_twelfths=12,
            entitlement_confirmed=True,
        )


def test_generic_sue_requires_context_and_rejects_bt_b():
    with pytest.raises(AnalyticsError, match="employment_context is required"):
        calculate_annual_special_payment(
            ROOT,
            "TVöD-SuE",
            "13",
            confirmed_assessment_base_monthly_eur=6000.0,
            payable_twelfths=12,
            entitlement_confirmed=True,
        )

    with pytest.raises(AnalyticsError, match="excluded"):
        calculate_annual_special_payment(
            ROOT,
            "TVöD-SuE",
            "13",
            confirmed_assessment_base_monthly_eur=6000.0,
            payable_twelfths=12,
            entitlement_confirmed=True,
            employment_context="TVöD-BT-B",
        )


def test_generic_sue_general_vka_context_can_be_calculated():
    result = calculate_annual_special_payment(
        ROOT,
        "TVöD-SuE",
        "13",
        confirmed_assessment_base_monthly_eur=6000.0,
        payable_twelfths=12,
        entitlement_confirmed=True,
        employment_context="general-vka",
    )
    assert result.annual_rate_pct == pytest.approx(85.0)
    assert result.special_payment_eur == 5100.0


def test_generic_vka_requires_context_and_rejects_bt_k():
    with pytest.raises(AnalyticsError, match="employment_context is required"):
        calculate_annual_special_payment(
            ROOT,
            "TVöD-VKA",
            "13",
            confirmed_assessment_base_monthly_eur=6000.0,
            payable_twelfths=12,
            entitlement_confirmed=True,
        )

    with pytest.raises(AnalyticsError, match="excluded"):
        calculate_annual_special_payment(
            ROOT,
            "TVöD-VKA",
            "13",
            confirmed_assessment_base_monthly_eur=6000.0,
            payable_twelfths=12,
            entitlement_confirmed=True,
            employment_context="TVöD-BT-K",
        )


def test_rule_exposes_assessment_and_proration_semantics():
    rule = get_annual_special_payment_rule(ROOT, "TVöD-Bund", "13")
    assert rule.entitlement_reference_date == "12-01"
    assert rule.assessment_months == ["07", "08", "09"]
    assert rule.assessment_base_rule == "average_paid_monthly_entgelt"
    assert rule.rate_reference_date == "09-01"
    assert rule.payment_month == "11"
    assert rule.complete_for_confirmed_input_calculation is True
    assert "260119_TVoeD-AT_und_BT-V_Bund_und_VKA.pdf" in (rule.rule_source or "")
