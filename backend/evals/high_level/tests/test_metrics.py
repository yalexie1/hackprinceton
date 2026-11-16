import math

import pytest

from backend.evals.high_level.metrics import score


def row(truth, expected, low=None, high=None):
    return {"truth_elec_kwh": truth, "arms": {"meter": {"elec": {
        "low": expected if low is None else low, "expected": expected,
        "high": expected if high is None else high,
    }}}}


def test_factor_two_counts_both_directions_and_boundaries():
    result = score([row(100, p) for p in [20, 50, 100, 200]], "meter")
    assert result["factor_two_or_more_pct"] == 75
    assert result["absolute_percentage_error_ge_100_pct"] == 25


def test_zero_median_percentage_error_does_not_prove_zero_aggregate_bias():
    result = score([row(10, 5), row(100, 100), row(1000, 1500)], "meter")
    assert result["median_signed_pct"] == 0
    assert result["aggregate_signed_pct"] == pytest.approx(100 * 495 / 1110)
    assert result["weighted_absolute_pct"] == pytest.approx(100 * 505 / 1110)


def test_coverage_is_inclusive_and_reports_each_tail():
    result = score([row(t, 100, 80, 120) for t in [70, 80, 100, 120, 130]], "meter")
    assert result["coverage_pct"] == 60
    assert result["below_low_pct"] == result["above_high_pct"] == 20
    assert result["mean_interval_width_kwh"] == 40


def test_refusals_and_nonpositive_truth_are_explicit_not_zero_predictions():
    result = score([row(100, 100), {"truth_elec_kwh": 100, "arms": {}}, row(0, 10)], "meter")
    assert result["n_input"] == 3
    assert result["n_scored"] == 1
    assert result["n_missing_prediction"] == result["n_nonpositive_truth"] == 1


@pytest.mark.parametrize("bad", [math.nan, math.inf, True])
def test_invalid_numbers_cannot_silently_enter_aggregates(bad):
    with pytest.raises(ValueError):
        score([row(100, bad)], "meter")


def test_inverted_ranges_are_rejected():
    with pytest.raises(ValueError):
        score([row(100, 100, 110, 90)], "meter")


def test_empty_cohort_is_not_a_zero_error_result():
    assert score([], "meter")["status"] == "insufficient_evidence"
