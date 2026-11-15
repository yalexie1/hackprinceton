"""The publish step selects and relabels; it must never recompute a number."""
from __future__ import annotations

import json

from backend.evals.publish import build_payload, merge_site_payload, per_building_rows

SCORECARD = {
    "dataset": "Building Data Genome Project 2",
    "year": 2017,
    "scope": "defaults-path eval",
    "n_sampled": 494, "n_scored": 494, "refused_count": 0,
    "sites": ["Bear", "Cockatoo", "Fox", "Panther", "Rat"], "n_sites": 5,
    "caveats": ["c1", "c2", "c3", "c4", "c5"],
    "l3_electricity": {
        "bdg2temp": {"n": 494, "median_pct": -0.5, "median_abs_pct": 55.5,
                     "mean_pct": 161.9, "p10_pct": -80.5, "p90_pct": 176.5,
                     "within_25pct": 23.5, "within_50pct": 45.1, "off_by_2x_either_way": 19.6},
        "openmeteo": {"n": 494, "median_pct": -1.8, "median_abs_pct": 54.8,
                      "mean_pct": 159.1, "p10_pct": -80.6, "p90_pct": 173.0,
                      "within_25pct": 22.5, "within_50pct": 45.1, "off_by_2x_either_way": 19.4},
    },
    "l4_interval": {
        "bdg2temp": {"n": 494, "coverage_pct": 17.6, "nominal_pct": 80.0,
                     "bins_pct": {"below_low": 38.1, "low_to_expected": 11.7,
                                  "expected_to_high": 5.9, "above_high": 44.3},
                     "mean_width_pct_of_expected": 41.4,
                     "site_clustered_ci90": [13.7, 22.2]},
        "openmeteo": {"n": 494, "coverage_pct": 16.8, "nominal_pct": 80.0,
                      "bins_pct": {"below_low": 38.1, "low_to_expected": 11.3,
                                   "expected_to_high": 5.5, "above_high": 45.1},
                      "mean_width_pct_of_expected": 41.6,
                      "site_clustered_ci90": [13.0, 20.9]},
    },
    "by_usage": {"Office": {"n": 61, "median_sqm": 4920,
                            "bdg2temp": {"n": 61, "median_pct": 8.6, "median_abs_pct": 40.7},
                            "coverage_pct": 13.1}},
    "by_site": {"Rat": {"n": 123, "median_sqm": 5000,
                        "bdg2temp": {"n": 123, "median_pct": 2.6, "median_abs_pct": 36.3},
                        "coverage_pct": 26.8}},
    "weather_decomposition": {
        "elec_shift_pct_of_truth": {"n": 494, "median_pct": -1.0, "median_abs_pct": 1.0},
        "heating_need_shift_pct": {"n": 451, "median_pct": 24.8, "median_abs_pct": 24.8},
        "note": "openmeteo minus bdg2temp.",
    },
    "storey_diagnostic": {
        "floors_ge_4": {"n": 66, "median_abs_pct": 61.7},
        "floors_le_1": {"n": 411, "median_abs_pct": 51.9},
        "note": "single storey limitation",
    },
}


def test_headline_carries_value_nominal_ci_and_n():
    out = build_payload(SCORECARD)
    labels = {r["label"] for r in out["headline"]}
    assert "Interval coverage" in labels
    assert "Median absolute error" in labels
    cov = next(r for r in out["headline"] if r["label"] == "Interval coverage")
    assert cov["value"] == 17.6
    assert cov["nominal"] == 80.0
    assert cov["n"] == 494
    assert cov["ci90"] == [13.7, 22.2]


def test_headline_values_are_copied_not_recomputed():
    # Every headline value must appear verbatim somewhere in the scorecard.
    out = build_payload(SCORECARD)
    flat = json.dumps(SCORECARD)
    for r in out["headline"]:
        assert str(r["value"]) in flat, f"{r['label']} value {r['value']} is not in the scorecard"


def test_caveats_survive_unchanged():
    out = build_payload(SCORECARD)
    assert out["caveats"] == SCORECARD["caveats"]
    assert len(out["caveats"]) >= 5


def test_provenance_names_the_dataset_and_the_sample():
    out = build_payload(SCORECARD)
    assert out["provenance"]["dataset"].startswith("Building Data Genome")
    assert out["provenance"]["n_scored"] == 494
    assert out["provenance"]["n_sites"] == 5
    assert out["provenance"]["refused"] == 0


def test_weather_decomposition_keeps_both_terms():
    out = build_payload(SCORECARD)
    w = out["weather_decomposition"]
    assert w["electricity_median_pct"] == -1.0
    assert w["heating_need_median_pct"] == 24.8


def test_an_eval_that_has_not_run_is_marked_not_run_never_omitted_or_zeroed():
    site = merge_site_payload(metered=build_payload(SCORECARD), pv=None, cost=None,
                              opensolar=None)
    for key in ("pv_crosscheck", "cost_check", "opensolar_spotcheck"):
        assert site[key]["status"] == "not_run", key
        assert "value" not in site[key]
    assert site["metered_buildings"]["status"] == "ok"


RUNS = {
    "year": 2017, "arms": ["bdg2temp", "openmeteo"], "n": 2, "refused_count": 1,
    "runs": [
        {"building_id": "Rat_office_X", "site_id": "Rat", "usage": "Office",
         "sqm": 5000.0, "yearbuilt": 1990, "floors": 3, "climate_zone": "4A",
         "segment": "commercial", "truth_elec_kwh": 1000.0, "elec_completeness": 1.0,
         "truth_gas_kwh": None,
         "arms": {"bdg2temp": {"elec": {"low": 800.0, "expected": 900.0, "high": 1100.0}},
                  "openmeteo": {"elec": {"low": 790.0, "expected": 890.0, "high": 1090.0}}}},
        {"building_id": "Bear_edu_Y", "site_id": "Bear", "usage": "Education",
         "sqm": 2000.0, "yearbuilt": 1960, "floors": None, "climate_zone": "3C",
         "segment": "commercial", "truth_elec_kwh": 500.0, "elec_completeness": 0.95,
         "truth_gas_kwh": 100.0,
         "arms": {"bdg2temp": {"refused": "ValueError: x"},
                  "openmeteo": {"refused": "ValueError: x"}}},
    ],
}


def test_per_building_rows_carry_what_a_rescorer_needs():
    rows = per_building_rows(RUNS)
    row = next(r for r in rows if r["building_id"] == "Rat_office_X")
    assert row["site_id"] == "Rat" and row["usage"] == "Office"
    assert row["measured_elec_kwh"] == 1000.0
    assert row["bdg2temp"] == {"low": 800.0, "expected": 900.0, "high": 1100.0}
    assert row["openmeteo"]["expected"] == 890.0


def test_per_building_rows_keep_refused_buildings_as_null_not_dropped():
    # Dropping them would silently shrink N for anyone rescoring from this file.
    rows = per_building_rows(RUNS)
    assert len(rows) == 2
    refused = next(r for r in rows if r["building_id"] == "Bear_edu_Y")
    assert refused["bdg2temp"] is None
    assert refused["measured_elec_kwh"] == 500.0


def test_per_building_rows_do_not_leak_hourly_series():
    # The file is for rescoring, not for re-running: keep it small and obvious.
    for row in per_building_rows(RUNS):
        assert "monthly_elec_kwh" not in row
        assert "end_use_kwh" not in row
