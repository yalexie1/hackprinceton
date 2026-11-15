"""Pin the arithmetic behind the published headline numbers.

These are characterisation tests: the functions already exist and already produced
a number we have published (494 buildings, coverage 17.6%). Their job is to make it
impossible to change that number by accident. Each one was verified to bite by
mutating the function it covers and watching the test fail (see PLAN ledger, Task 2).
"""
from __future__ import annotations

import backend.evals.run_eval as run_eval
from backend.evals.score_eval import (cluster_bootstrap, coverage, describe, err_pct)

BAND = {"low": 100.0, "expected": 150.0, "high": 200.0}


def row(truth: float, band: dict | None = BAND, site: str = "S") -> dict:
    arm = {"elec": band} if band is not None else {"refused": "ValueError: x"}
    return {"site_id": site, "truth_elec_kwh": truth, "arms": {"a": arm}}


def test_coverage_counts_boundaries_as_inside():
    assert coverage([row(100.0), row(150.0), row(200.0)], "a")["coverage_pct"] == 100.0


def test_coverage_assigns_boundary_truths_to_the_lower_bin():
    # The four-bin split is the evidence for "sharpness, not bias", so which side of
    # each boundary a truth lands on is load-bearing, not cosmetic. Truth exactly at
    # `low` or at `expected` belongs to the bin below it.
    assert coverage([row(100.0)], "a")["bins_pct"]["low_to_expected"] == 100.0
    assert coverage([row(150.0)], "a")["bins_pct"]["low_to_expected"] == 100.0
    assert coverage([row(200.0)], "a")["bins_pct"]["expected_to_high"] == 100.0


def test_coverage_splits_outside_by_side():
    out = coverage([row(99.0), row(201.0)], "a")
    assert out["coverage_pct"] == 0.0
    assert out["bins_pct"] == {"below_low": 50.0, "low_to_expected": 0.0,
                               "expected_to_high": 0.0, "above_high": 50.0}


def test_coverage_skips_refused_arms():
    assert coverage([row(150.0), row(150.0, band=None)], "a")["n"] == 1


def test_coverage_width_is_relative_to_expected():
    # (200 - 100) / 150 = 66.7%
    assert coverage([row(150.0)], "a")["mean_width_pct_of_expected"] == 66.7


def test_err_pct_is_none_for_refused_and_for_zero_truth():
    assert err_pct(row(10.0, band=None), "a") is None
    assert err_pct(row(0.0), "a") is None


def test_err_pct_signs_overprediction_positive():
    # expected 150 against a metered 100 is +50%.
    assert err_pct(row(100.0), "a") == 50.0


def test_cluster_bootstrap_with_one_site_is_degenerate_not_a_crash():
    draws = cluster_bootstrap([row(150.0)], "a",
                              lambda rs, x: coverage(rs, x)["coverage_pct"], draws=10)
    assert draws == [100.0] * 10


def test_cluster_bootstrap_resamples_sites_not_buildings():
    # Site A holds two covered buildings, site B one uncovered. Drawing 2 sites with
    # replacement gives [A,A]=100%, [A,B]=2 of 3=66.7%, [B,B]=0%. A building-level
    # bootstrap over the same three rows could also land on 33.3% (1 of 3 covered);
    # its absence is what proves the resampling is clustered on sites.
    rows = [row(150.0, site="A"), row(150.0, site="A"), row(999.0, site="B")]
    drawn = set(cluster_bootstrap(rows, "a",
                                  lambda rs, x: coverage(rs, x)["coverage_pct"], draws=200))
    assert drawn == {0.0, 66.7, 100.0}
    assert 33.3 not in drawn


def test_describe_is_empty_for_no_errors():
    assert describe([]) == {"n": 0}


def test_describe_reports_median_not_mean_for_a_skewed_set():
    # One huge overprediction must not drag the headline: median 10, mean 260.
    out = describe([-10.0, 10.0, 10.0, 20.0, 1270.0])
    assert out["median_pct"] == 10.0
    assert out["mean_pct"] == 260.0
    assert out["median_abs_pct"] == 10.0
    assert out["over_by_2x_plus"] == 20.0


def _write_meter_csv(path, rows):
    path.write_text("timestamp,A,B,C\n" + "\n".join(rows) + "\n")


def test_load_truth_scales_for_gaps_and_drops_dead_and_sparse_meters(tmp_path, monkeypatch):
    # Four hourly stamps in YEAR. A reads 3 of 4 (75% < 90%, dropped),
    # B reads 4 of 4 at 2.0 (kept, 8.0), C is a dead meter reading 0.0 (dropped).
    csv = tmp_path / "electricity_cleaned.csv"
    _write_meter_csv(csv, [
        f"{run_eval.YEAR}-01-01 00:00:00,1.0,2.0,0.0",
        f"{run_eval.YEAR}-01-01 01:00:00,1.0,2.0,0.0",
        f"{run_eval.YEAR}-01-01 02:00:00,1.0,2.0,0.0",
        f"{run_eval.YEAR}-01-01 03:00:00,,2.0,0.0",
    ])
    monkeypatch.setattr(run_eval, "BDG2", tmp_path)
    out = run_eval.load_truth(["A", "B", "C"], "electricity")
    assert set(out) == {"B"}
    assert out["B"]["annual_kwh"] == 8.0
    assert out["B"]["completeness"] == 1.0


def test_load_truth_scales_a_building_just_inside_the_completeness_floor(tmp_path, monkeypatch):
    # 9 of 10 hours present at 1.0 each: exactly 90%, kept, and scaled 9 -> 10.
    stamps = [f"{run_eval.YEAR}-01-01 {h:02d}:00:00,1.0,1.0,1.0" for h in range(9)]
    stamps.append(f"{run_eval.YEAR}-01-01 09:00:00,,1.0,1.0")
    csv = tmp_path / "electricity_cleaned.csv"
    _write_meter_csv(csv, stamps)
    monkeypatch.setattr(run_eval, "BDG2", tmp_path)
    out = run_eval.load_truth(["A"], "electricity")
    assert out["A"]["completeness"] == 0.9
    assert out["A"]["annual_kwh"] == 10.0


def test_load_truth_ignores_rows_outside_the_eval_year(tmp_path, monkeypatch):
    csv = tmp_path / "electricity_cleaned.csv"
    _write_meter_csv(csv, [
        f"{run_eval.YEAR - 1}-06-01 00:00:00,5.0,5.0,5.0",
        f"{run_eval.YEAR}-01-01 00:00:00,1.0,1.0,1.0",
    ])
    monkeypatch.setattr(run_eval, "BDG2", tmp_path)
    assert run_eval.load_truth(["A"], "electricity")["A"]["annual_kwh"] == 1.0


def test_describe_counts_2x_errors_on_both_sides():
    # Signed % error e = 100*(pred-truth)/truth, so ratio = 1 + e/100.
    # A 2x OVERprediction is e=+100; a 2x UNDERprediction is e=-50, NOT -100.
    # The old abs(e) >= 100 test could never flag an underprediction at all.
    out = describe([100.0, -50.0, 0.0, 10.0])
    assert out["over_by_2x_plus"] == 25.0
    assert out["under_by_2x_plus"] == 25.0
    assert out["off_by_2x_either_way"] == 50.0
    # The ambiguous old key must be gone, not silently redefined.
    assert "factor_2_plus" not in out


def test_describe_2x_boundaries_are_inclusive():
    assert describe([-50.0])["under_by_2x_plus"] == 100.0
    assert describe([-49.9])["under_by_2x_plus"] == 0.0
    assert describe([100.0])["over_by_2x_plus"] == 100.0
    assert describe([99.9])["over_by_2x_plus"] == 0.0


def test_describe_cannot_report_an_underprediction_worse_than_total():
    # e <= -100 is impossible (you cannot predict less than zero against a
    # positive truth), which is exactly why abs(e) was the wrong test.
    out = describe([-90.0, -99.0])
    assert out["under_by_2x_plus"] == 100.0
