"""Pin the arithmetic behind the published headline numbers.

These are characterisation tests: the functions already exist and already produced
a number we have published (494 buildings, coverage 17.6%). Their job is to make it
impossible to change that number by accident. Each one was verified to bite by
mutating the function it covers and watching the test fail (see PLAN ledger, Task 2).
"""
from __future__ import annotations

import json

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


# --- supported-zone cohort (lead decision "Option A") ---------------------------
# The DEF tables carry only 2A and 3B; every other zone silently falls back. The
# headline stays all 494 with per-building zone disclosure, and this cohort is
# published beside it as the stricter reading.
from backend.evals.score_eval import SUPPORTED_ZONES, supported_zone_section  # noqa: E402


def zrow(truth: float, zone: str, band: dict | None = BAND, site: str = "S") -> dict:
    r = row(truth, band=band, site=site)
    r["climate_zone"] = zone
    r["arms"] = {"bdg2temp": r["arms"]["a"], "openmeteo": r["arms"]["a"]}
    return r


def test_supported_zones_are_the_two_the_def_tables_carry():
    assert SUPPORTED_ZONES == ("2A", "3B")


def test_supported_zone_section_keeps_only_supported_zones():
    rows = [zrow(150.0, "2A"), zrow(150.0, "3B"), zrow(150.0, "4A"), zrow(150.0, None)]
    out = supported_zone_section(rows)
    assert out["n"] == 2
    assert out["l3_electricity"]["bdg2temp"]["n"] == 2
    assert out["l4_interval"]["bdg2temp"]["n"] == 2


def test_supported_zone_section_metrics_match_the_same_functions_on_the_subset():
    rows = [zrow(100.0, "2A"), zrow(300.0, "3B"), zrow(100.0, "6A")]
    sub = [r for r in rows if r["climate_zone"] in SUPPORTED_ZONES]
    out = supported_zone_section(rows)
    for arm in ("bdg2temp", "openmeteo"):
        errs = [e for e in (err_pct(r, arm) for r in sub) if e is not None]
        assert out["l3_electricity"][arm] == describe(errs)
        assert out["l4_interval"][arm] == coverage(sub, arm)


def test_supported_zone_section_lists_its_sites():
    rows = [zrow(150.0, "2A", site="Panther"), zrow(150.0, "2A", site="Panther"),
            zrow(150.0, "4A", site="Rat")]
    out = supported_zone_section(rows)
    assert out["sites"] == ["Panther"]
    assert out["n_sites"] == 1


def test_supported_zone_section_emits_no_ci_because_it_is_one_site():
    # A site-clustered CI over a single cluster is not computable; a number there
    # would be a fake. The absence must be explicit, not silent.
    out = supported_zone_section([zrow(150.0, "2A", site="Panther")])
    assert "site_clustered_ci90" not in json.dumps(out)
    assert "Panther" in out["ci_note"]
    assert out["note"]


def test_supported_zone_section_is_empty_but_shaped_when_nothing_qualifies():
    out = supported_zone_section([zrow(150.0, "4A")])
    assert out["n"] == 0
    assert out["sites"] == []
    assert out["l3_electricity"]["bdg2temp"] == {"n": 0}


# --- skill against a naive baseline (#446) ---------------------------------------
# An error figure alone is not an accuracy claim. These pin the comparison that
# answers "better than what?", which the published 52.9% never did.
from backend.evals.score_eval import constant_eui_errors, skill_section  # noqa: E402


def srow(truth: float, expected: float, sqm: float, usage: str = "Office",
         site: str = "S") -> dict:
    return {"site_id": site, "usage": usage, "sqm": sqm, "truth_elec_kwh": truth,
            "arms": {"a": {"elec": {"low": expected * 0.8, "expected": expected,
                                    "high": expected * 1.2}}}}


def test_constant_predictor_uses_the_cohort_median_intensity():
    # Truth intensities 10, 20, 30 kWh/m2 -> median 20. The constant predicts
    # 20 * area for everyone, so the middle building is exact.
    rows = [srow(100.0, 1.0, 10.0), srow(200.0, 1.0, 10.0), srow(300.0, 1.0, 10.0)]
    errs = constant_eui_errors(rows)
    assert len(errs) == 3
    assert errs[1] == 0.0                      # 20 * 10 = 200, exactly the meter
    assert errs[0] > 0 and errs[2] < 0         # over the small one, under the big one


def test_constant_predictor_skips_rows_it_cannot_score():
    rows = [srow(100.0, 1.0, 10.0), srow(0.0, 1.0, 10.0), srow(100.0, 1.0, 0.0)]
    assert len(constant_eui_errors(rows)) == 1


def test_skill_section_reports_the_model_and_the_baseline_side_by_side():
    rows = [srow(100.0, 110.0, 10.0), srow(200.0, 220.0, 10.0), srow(300.0, 330.0, 10.0)]
    out = skill_section(rows, "a")
    assert out["model"]["median_abs_pct"] == 10.0
    assert "constant_eui" in out
    assert out["constant_eui"]["n"] == 3


def test_skill_section_names_the_winner_rather_than_leaving_it_to_the_reader():
    """The whole point: a number with no comparator reads as an accuracy claim."""
    # A model that is exact must beat the constant on this spread-out cohort.
    rows = [srow(100.0, 100.0, 10.0), srow(200.0, 200.0, 10.0), srow(300.0, 300.0, 10.0)]
    out = skill_section(rows, "a")
    assert out["beats_constant"] is True
    assert "constant" in out["verdict"].lower()


def test_skill_section_says_so_when_the_baseline_wins():
    # Model is wildly wrong; the constant is exact for the middle building.
    rows = [srow(100.0, 1000.0, 10.0), srow(200.0, 2000.0, 10.0), srow(300.0, 3000.0, 10.0)]
    out = skill_section(rows, "a")
    assert out["beats_constant"] is False
    assert out["margin_pct_points"] < 0


def test_skill_section_is_computed_per_group_not_only_pooled():
    """Pooled error cancels between groups biased in opposite directions, so a model
    can look adequate overall while being beaten in every single class."""
    rows = ([srow(100.0, 300.0, 10.0, usage="Office") for _ in range(3)]
            + [srow(100.0, 10.0, 10.0, usage="Lodging/residential") for _ in range(3)])
    out = skill_section(rows, "a")
    assert set(out["by_usage"]) == {"Office", "Lodging/residential"}
    for group in out["by_usage"].values():
        assert "beats_constant" in group
