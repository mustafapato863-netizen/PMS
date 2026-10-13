"""June 2026 scoring method for Pre-Approvals IP Offshore (pure function, synthetic counts)."""
from __future__ import annotations

import math
from datetime import datetime

import pytest

from services.preapprovals_offshore_scoring import (
    DEFAULT_GRADE_THRESHOLDS,
    EFFECTIVE_MONTH,
    EFFECTIVE_YEAR,
    NEW_METHOD_ID,
    OffshoreCounts,
    OffshoreDataError,
    _round_half_up,
    counts_from_mapping,
    derived_raw_values,
    grade_for,
    kpi_values,
    month_number,
    reporting_period_from_row,
    score_counts,
    score_row,
    uses_new_method,
)


def counts(assigned, approved, rejected, policy, within_48h, submitted, errors) -> OffshoreCounts:
    return OffshoreCounts(
        assigned=float(assigned),
        approved=float(approved),
        rejected=float(rejected),
        policy_rejected=float(policy),
        approved_within_48h=float(within_48h),
        submitted=float(submitted),
        errors=float(errors),
    )


# The business workbook's six August 2026 results: raw counts per employee-month and the score it shows.
# Counts only, no identities. Order: assigned, approved, rejected, policy rejected, approved within 48h,
# submitted claims, error claims, expected score, expected grade.
SIX_AUGUST_CASES = [
    (70, 55, 6, 6, 37, 169, 2, 89.32, "B"),
    (28, 23, 3, 3, 19, 112, 1, 97.54, "A"),
    (40, 31, 5, 5, 26, 122, 0, 97.96, "A"),
    (124, 96, 10, 10, 75, 16, 0, 96.04, "A"),
    (53, 44, 4, 4, 35, 69, 0, 96.52, "A"),
    # No submitted claims: the 60/0/40 weights apply and the error KPI is not applicable.
    (94, 89, 5, 0, 89, 0, 8, 51.28, "E"),
]


@pytest.mark.parametrize(
    "assigned, approved, rejected, policy, within_48h, submitted, errors, expected_score, expected_grade",
    SIX_AUGUST_CASES,
)
def test_august_2026_workbook_scores(
    assigned, approved, rejected, policy, within_48h, submitted, errors, expected_score, expected_grade,
):
    result = score_counts(counts_from_mapping({
        "AssignedRequest": assigned,
        "ApprovedRequests": approved,
        "RejectedRequests": rejected,
        "PolicyRej": policy,
        "ApprovalWithin48HR": within_48h,
        "SubmittedClaims": submitted,
        "ErrosClaims": errors,
    }))

    assert float(result.score) == pytest.approx(expected_score, abs=0.005)
    assert result.grade == expected_grade


def test_effective_period_is_june_2026():
    assert (EFFECTIVE_YEAR, EFFECTIVE_MONTH) == (2026, 6)
    assert NEW_METHOD_ID == "preapprovals_offshore_v2"


def test_boundary_may_uses_old_method_june_uses_new_method():
    assert uses_new_method(2026, 5) is False
    assert uses_new_method(2026, 6) is True
    assert uses_new_method(2026, "June") is True
    assert uses_new_method(2025, 12) is False
    assert uses_new_method(2027, 1) is True
    assert uses_new_method(None, 6) is False


def test_month_number_accepts_names_and_numbers():
    assert month_number("June") == 6
    assert month_number("jun") == 6
    assert month_number(6) == 6
    assert month_number("13") is None
    assert month_number("Unknown") is None
    assert month_number(None) is None


def test_typical_row_matches_hand_calculation():
    # F=100, H=5, N=2 -> O=3, Q=0.03 -> rejection achievement 0.01/0.03.
    # V=2/200=0.01 -> error achievement 1. W=85/90 -> submission achievement 1.
    result = score_counts(counts(100, 90, 5, 2, 85, 200, 2))

    assert result.controllable_rejections == pytest.approx(3)
    assert result.controllable_rejection_rate == pytest.approx(0.03)
    assert result.achievements["Rejection"] == pytest.approx(0.01 / 0.03)
    assert result.achievements["InitialError"] == pytest.approx(1.0)
    assert result.achievements["Submission"] == pytest.approx(1.0)
    assert result.weights == {"Rejection": 0.5, "InitialError": 0.2, "Submission": 0.3}
    assert result.score == 66.67
    assert result.grade == "D"


def test_zero_assigned_requests_gives_zero_rate_and_full_rejection_achievement():
    result = score_counts(counts(0, 10, 3, 1, 10, 5, 0))

    assert result.controllable_rejection_rate == 0.0
    assert result.achievements["Rejection"] == 1.0
    assert result.policy_rejection_rate == 0.0
    assert result.score == 100.0


def test_zero_rejections_gives_zero_rates_and_policy_share():
    result = score_counts(counts(100, 90, 0, 0, 90, 10, 0))

    assert result.controllable_rejection_rate == 0.0
    assert result.policy_share == 0.0
    assert result.achievements["Rejection"] == 1.0


def test_policy_rejections_above_rejections_are_clamped_for_the_share_only():
    result = score_counts(counts(100, 90, 2, 5, 90, 10, 0))

    assert result.controllable_rejections == 0.0  # max(H - N, 0)
    assert result.policy_share == 1.0  # clamped to 0..1
    assert result.policy_rejection_rate == pytest.approx(0.05)  # N / F, display only
    assert result.achievements["Rejection"] == 1.0


def test_rejection_rate_at_target_gives_full_achievement():
    # O/F = 1/100 = 0.01 exactly on target.
    result = score_counts(counts(100, 90, 3, 2, 90, 10, 0))

    assert result.controllable_rejection_rate == pytest.approx(0.01)
    assert result.achievements["Rejection"] == pytest.approx(1.0)


def test_zero_claims_uses_fixed_alternative_weights_and_no_error_achievement():
    # Q = 3/100 -> rejection achievement 1/3; W = 90/100 -> submission achievement 1.
    # Error counts are ignored because S is 0.
    result = score_counts(counts(100, 100, 4, 1, 90, 0, 7))

    assert result.claims_submitted is False
    assert result.weights == {"Rejection": 0.60, "InitialError": 0.00, "Submission": 0.40}
    assert result.achievements["InitialError"] is None
    assert result.score == 60.0
    assert result.grade == "E"


def test_zero_errors_gives_full_error_achievement():
    result = score_counts(counts(100, 90, 2, 1, 90, 100, 0))

    assert result.error_rate == 0.0
    assert result.achievements["InitialError"] == 1.0


def test_error_rate_above_target_is_capped_by_target_ratio():
    result = score_counts(counts(100, 90, 2, 1, 90, 100, 4))

    assert result.error_rate == pytest.approx(0.04)
    assert result.achievements["InitialError"] == pytest.approx(0.25)


def test_submission_above_target_is_capped_at_one():
    result = score_counts(counts(100, 100, 2, 1, 100, 10, 0))

    assert result.approval_within_48h_rate == pytest.approx(1.0)
    assert result.achievements["Submission"] == 1.0


def test_every_achievement_is_capped_at_one_for_tiny_rates():
    result = score_counts(counts(1000, 1000, 1, 0, 1000, 1000, 1))

    assert result.controllable_rejection_rate == pytest.approx(0.001)
    for value in result.achievements.values():
        assert value is None or 0.0 <= value <= 1.0
    assert result.achievements["Rejection"] == 1.0
    assert result.achievements["InitialError"] == 1.0
    assert result.score == 100.0


def test_grade_thresholds_are_inclusive_and_fall_through_to_e():
    assert grade_for(95.0) == "A"
    assert grade_for(94.99) == "B"
    assert grade_for(85.0) == "B"
    assert grade_for(75.0) == "C"
    assert grade_for(65.0) == "D"
    assert grade_for(64.99) == "E"
    assert DEFAULT_GRADE_THRESHOLDS == {"A": 95, "B": 85, "C": 75, "D": 65}


def test_grade_uses_supplied_team_thresholds():
    assert grade_for(90.0, {"A": 95, "B": 85, "C": 75, "D": 65}) == "B"
    assert grade_for(90.0, {"A": 99, "B": 95, "C": 75, "D": 65}) == "C"


def test_rounding_is_half_up_to_two_decimals():
    assert _round_half_up(66.665, 2) == 66.67
    assert _round_half_up(66.664, 2) == 66.66
    assert _round_half_up(0.125, 2) == 0.13


def test_score_is_rounded_to_two_decimals():
    result = score_counts(counts(300, 100, 7, 1, 80, 40, 1))

    assert result.score == round(result.score, 2)


def test_kpi_values_have_policy_indicator_with_zero_weight_and_no_contribution():
    result = score_counts(counts(100, 90, 5, 2, 85, 200, 2))
    rows = {row["kpi_key"]: row for row in kpi_values(result)}

    assert set(rows) == {"Rejection", "InitialError", "Submission", "PolicyRejection"}
    assert rows["PolicyRejection"]["weight_applied"] == 0
    assert rows["PolicyRejection"]["contribution"] == 0
    assert rows["PolicyRejection"]["tracking_only"] is True
    assert rows["PolicyRejection"]["actual_value"] == pytest.approx(0.02)
    assert rows["Rejection"]["target_value"] == pytest.approx(0.01)
    assert rows["InitialError"]["target_value"] == pytest.approx(0.01)
    assert rows["Submission"]["target_value"] == pytest.approx(0.90)


def test_kpi_values_mark_initial_error_not_applicable_when_no_claims():
    result = score_counts(counts(100, 100, 4, 1, 90, 0, 0))
    rows = {row["kpi_key"]: row for row in kpi_values(result)}

    assert rows["InitialError"]["applicable"] is False
    assert rows["InitialError"]["weight_applied"] == 0.0
    assert rows["InitialError"]["contribution"] == 0.0
    assert rows["Rejection"]["weight_applied"] == 0.60
    assert rows["Submission"]["weight_applied"] == 0.40


def test_derived_raw_values_use_clear_new_keys():
    result = score_counts(counts(100, 90, 5, 2, 85, 200, 2))
    values = derived_raw_values(result)

    assert values == {
        "ControllableRejections": 3.0,
        "ControllableRejectionRate": 0.03,
        "PolicyRejectionRate": 0.02,
        "PolicyShareOfRejections": 0.4,
        "ScoringMethod": NEW_METHOD_ID,
    }


def test_counts_from_mapping_names_a_missing_column():
    row = {"AssignedRequest": 1, "ApprovedRequests": 1, "RejectedRequests": 0, "ApprovalWithin48HR": 1,
           "SubmittedClaims": 1, "ErrosClaims": 0}
    with pytest.raises(OffshoreDataError) as raised:
        counts_from_mapping(row)
    assert raised.value.column == "PolicyRej"
    assert "PolicyRej" in str(raised.value)


@pytest.mark.parametrize("bad", [None, "", "   ", float("nan"), "abc", -1, "-2"])
def test_counts_from_mapping_rejects_blank_non_numeric_and_negative_values(bad):
    row = {
        "AssignedRequest": 10, "ApprovedRequests": 9, "RejectedRequests": 1, "PolicyRej": bad,
        "ApprovalWithin48HR": 8, "SubmittedClaims": 5, "ErrosClaims": 0,
    }
    with pytest.raises(OffshoreDataError) as raised:
        counts_from_mapping(row)
    assert raised.value.column == "PolicyRej"


def test_counts_from_mapping_accepts_numeric_text_with_thousand_separators():
    row = {
        "AssignedRequest": "1,000", "ApprovedRequests": "900", "RejectedRequests": "5", "PolicyRej": "2",
        "ApprovalWithin48HR": "850", "SubmittedClaims": "200", "ErrosClaims": "2",
    }
    result = score_row(row)
    assert result.counts.assigned == 1000.0
    assert result.controllable_rejections == 3.0


def test_reporting_period_comes_from_date_then_month_then_year():
    assert reporting_period_from_row({"Date": datetime(2026, 6, 1)}) == (2026, 6)
    assert reporting_period_from_row({"Date": None, "Month": "June 2026"}) == (2026, 6)
    assert reporting_period_from_row({"Month": "2026-05"}) == (2026, 5)
    assert reporting_period_from_row({"Month": "01/06/2026"}) == (2026, 6)  # day first
    assert reporting_period_from_row({"Month": "June", "Year": 2026}) == (2026, 6)
    assert reporting_period_from_row({"Month": "June"}) is None
    assert reporting_period_from_row({"Month": "Sometime"}) is None
    assert reporting_period_from_row({}) is None


def test_all_zero_row_stays_finite_and_scores_only_the_rejection_part():
    # No claims: rejection achievement 1 at weight 0.60. No approvals: submission 0.
    result = score_counts(counts(0, 0, 0, 0, 0, 0, 0))

    assert math.isfinite(result.score)
    assert result.achievements["Submission"] == 0.0
    assert result.score == 60.0
    assert result.grade == "E"
