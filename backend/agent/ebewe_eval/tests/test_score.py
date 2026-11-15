import pytest

from backend.agent.ebewe_eval.match import norm, truth_for
from backend.agent.ebewe_eval.score import metrics, spearman, two_sided_factor2


def test_two_sided_factor_two_counts_under_and_over_predictions():
    assert two_sided_factor2(2.0) and two_sided_factor2(0.5) and two_sided_factor2(0.2)
    assert not two_sided_factor2(1.9) and not two_sided_factor2(0.6)


def test_constant_predictor_is_reported_beside_the_model():
    rows = [{"use": "office", "truth": t, "pred": 40.0, "lo": 30.0, "hi": 50.0, "area": 100.0} for t in (30, 40, 50, 60)]
    m = metrics(rows)
    assert m["n"] == 4 and m["cohort_median_truth_eui"] == 45
    assert m["constant_predictor_median_abs_error"] == pytest.approx(0.2, abs=0.05)
    assert m["range_contained_truth"] == 0.75                      # 60 is above the range


def test_rank_correlation_is_one_for_a_monotone_prediction():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_address_normalisation_matches_common_variants():
    assert norm("100 S Example Blvd.") == norm("100 South Example Boulevard")


def test_truth_needs_three_usable_years_and_skips_covid_years():
    rows = [{"program_year": y, "site_eui": "50", "property_gfa_1": "50000"} for y in ("2017", "2018", "2019")]
    assert truth_for(rows)[0] == 50
    assert truth_for(rows[:2]) is None
    covid = [{"program_year": y, "site_eui": "50", "property_gfa_1": "50000"} for y in ("2020", "2021", "2019")]
    assert truth_for(covid) is None                                 # only 1 usable year
