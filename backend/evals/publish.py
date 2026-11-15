"""Turn the scorecard into the static JSON the site reads.

This module SELECTS and RELABELS. It must never compute a number: if a figure is
not already in the scorecard it does not belong on the page, because the page would
then disagree with `score_eval.py` the first time either changed.

Writes:
  backend/evals/out/metered_buildings.json   the metered-building eval alone
  frontend/public/evals.json                 all evals merged, for Evals.tsx

Reads, if present: pv_crosscheck.json, cost_check.json, opensolar_spotcheck.json
and calibrated.json, all committed under backend/evals/out/. The calibrated arm
(#430) is committed as AGGREGATE ROWS ONLY: run_calibrated.py writes its
per-building output to the git-ignored cache, and the per-building calibration of
a named BDG2 building is more than the page needs to make the point.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCORECARD = ROOT / "data/cache/evals/out/scorecard.json"
RUNS = ROOT / "data/cache/evals/out/runs.json"
OUT = ROOT / "backend/evals/out"
SITE_JSON = ROOT / "frontend/public/evals.json"
ARM = "bdg2temp"          # the measured-temperature arm is the headline


def supported_zone_block(card: dict) -> dict:
    """The stricter cohort, rendered beside the headline. Selected, never recomputed.

    The headline stays all buildings with each one's climate zone disclosed; this
    block is the same three metrics over only the buildings whose zone the default
    tables actually carry. It carries no confidence interval on purpose.
    """
    sz = card["supported_zones"]
    l3, l4 = sz["l3_electricity"][ARM], sz["l4_interval"][ARM]
    return {
        "title": "Supported climate zones only",
        "zones": sz["zones"],
        "n": sz["n"],
        "sites": sz["sites"],
        "n_sites": sz["n_sites"],
        "headline": [
            {"label": "Interval coverage", "value": l4["coverage_pct"], "unit": "%",
             "nominal": l4["nominal_pct"], "ci90": None, "n": l4["n"]},
            {"label": "Median absolute error", "value": l3["median_abs_pct"], "unit": "%",
             "nominal": None, "ci90": None, "n": l3["n"]},
            {"label": "Median signed error", "value": l3["median_pct"], "unit": "%",
             "nominal": 0.0, "ci90": None, "n": l3["n"]},
        ],
        "bins": l4["bins_pct"],
        "note": "Our default tables only carry two climate zones, 2A and 3B. Buildings "
                "anywhere else are modelled on a blend of them, so these are the "
                "buildings the model was actually built for. We show both readings: the "
                "full sample above is the honest headline, and this narrower one is the "
                "stricter test. It is harder, not easier.",
        "ci_note": sz["ci_note"],
    }


def build_payload(card: dict) -> dict:
    """Scorecard -> the metered-building payload. Values are copied, never derived."""
    l3, l4 = card["l3_electricity"][ARM], card["l4_interval"][ARM]
    w = card["weather_decomposition"]

    headline = [
        {"label": "Interval coverage", "value": l4["coverage_pct"], "unit": "%",
         "nominal": l4["nominal_pct"], "ci90": l4["site_clustered_ci90"], "n": l4["n"],
         "note": "How often the metered total fell inside the low-to-high range we "
                 "report. That range is built by varying our uncertain inputs one at a "
                 "time, and 80% was the design intent; measured, it is far lower, so "
                 "treat the range as input-sensitivity bounds and not as a confidence "
                 "interval."},
        {"label": "Median absolute error", "value": l3["median_abs_pct"], "unit": "%",
         "nominal": None, "ci90": None, "n": l3["n"],
         "note": "Half of buildings are predicted closer than this, half further."},
        {"label": "Median signed error", "value": l3["median_pct"], "unit": "%",
         "nominal": 0.0, "ci90": None, "n": l3["n"],
         "note": "Negative means we estimate less energy than the meter recorded. The "
                 "model underpredicts, and it is also widely scattered: both are true, "
                 "and they need different fixes."},
        {"label": "Within 25%", "value": l3["within_25pct"], "unit": "% of buildings",
         "nominal": None, "ci90": None, "n": l3["n"],
         "note": "Share of buildings predicted within a quarter of the metered total."},
        {"label": "Band width", "value": l4["mean_width_pct_of_expected"], "unit": "% of expected",
         "nominal": None, "ci90": None, "n": l4["n"],
         "note": "Mean width of the low-to-high band, relative to the expected value."},
    ]

    return {
        "status": "ok",
        "title": "Metered buildings",
        "supported_zones": supported_zone_block(card),
        "question": "How close is our predicted annual electricity to a real meter, "
                    "and does our stated uncertainty band tell the truth?",
        "headline": headline,
        "bins": l4["bins_pct"],
        "bins_note": "Where the metered total fell relative to our low and high. Most "
                     "buildings fall outside on one side or the other, which is how we "
                     "know the range is too narrow; more fall above than below, which is "
                     "the same low bias the median signed error shows.",
        "by_usage": card["by_usage"],
        "by_site": card["by_site"],
        "weather_decomposition": {
            "electricity_median_pct": w["elec_shift_pct_of_truth"]["median_pct"],
            "heating_need_median_pct": w["heating_need_shift_pct"]["median_pct"],
            "n_electricity": w["elec_shift_pct_of_truth"]["n"],
            "n_heating": w["heating_need_shift_pct"]["n"],
            "note": "Swapping measured station temperatures for the Open-Meteo "
                    "reanalysis path. The bias is large on heating need and small on "
                    "the electricity meter, because these buildings are dominated by "
                    "cooling, lighting and plug loads.",
            "caveat": "Both arms use the same modelled irradiance, so this isolates "
                      "temperature error only.",
        },
        "storey_diagnostic": card["storey_diagnostic"],
        "scope": card["scope"],
        "caveats": card["caveats"],
        "provenance": {
            "dataset": card["dataset"],
            "year": card["year"],
            "n_scored": card["n_scored"],
            "n_sampled": card["n_sampled"],
            "n_sites": card["n_sites"],
            "sites": card["sites"],
            "refused": card["refused_count"],
            "arm": ARM,
            "manifest": "backend/evals/manifests/bdg2.yaml",
        },
    }


def per_building_rows(runs: dict) -> list[dict]:
    """One record per building, for anyone rescoring our intervals independently.

    Requested by @yalexie1 (fitting a widening factor) and @vinayak-sinha (stage-0
    reproduction). Deliberately carries no hourly or monthly series: this file is
    for rescoring, not for re-running the model. A refused arm stays in the file
    as null rather than being dropped, because dropping it silently shrinks N for
    whoever scores from it.
    """
    rows = []
    for r in runs["runs"]:
        row = {
            "building_id": r["building_id"], "site_id": r["site_id"],
            "usage": r["usage"], "segment": r["segment"], "sqm": r["sqm"],
            "yearbuilt": r["yearbuilt"], "floors": r["floors"],
            "climate_zone": r["climate_zone"],
            "measured_elec_kwh": r["truth_elec_kwh"],
            "measured_gas_kwh": r.get("truth_gas_kwh"),
            "elec_completeness": r.get("elec_completeness"),
        }
        for arm in runs["arms"]:
            e = r["arms"].get(arm, {}).get("elec")
            row[arm] = None if e is None else {"low": e["low"], "expected": e["expected"],
                                               "high": e["high"]}
        rows.append(row)
    return rows


def _slot(payload: dict | None, title: str, question: str) -> dict:
    """An eval that has not run is an explicit not_run, never a zero and never absent."""
    if payload is not None:
        return payload
    return {"status": "not_run", "title": title, "question": question,
            "note": "This check has not been run yet."}


def merge_site_payload(metered: dict | None, pv: dict | None, cost: dict | None,
                       opensolar: dict | None, calibrated: dict | None) -> dict:
    return {
        "metered_buildings": _slot(metered, "Metered buildings",
                                   "How close is our predicted annual electricity to a real meter?"),
        "calibrated_bills": _slot(calibrated, "With a year of utility bills",
                                  "Given one year of bills, how close is our prediction of the "
                                  "next year?"),
        "pv_crosscheck": _slot(pv, "PV yield vs PVGIS",
                               "Does our modelled PV yield agree with an independent estimate?"),
        "cost_check": _slot(cost, "Installed cost vs Tracking the Sun",
                            "Are our installed costs inside the real market distribution?"),
        "opensolar_spotcheck": _slot(opensolar, "OpenSolar spot check",
                                     "Does our system design match a tool the industry trusts?"),
    }


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def main() -> int:
    card = json.loads(SCORECARD.read_text())
    metered = build_payload(card)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metered_buildings.json").write_text(json.dumps(metered, indent=1))

    if RUNS.is_file():
        rows = per_building_rows(json.loads(RUNS.read_text()))
        (OUT / "per_building.json").write_text(json.dumps(rows, indent=1))
        print(f"wrote {OUT / 'per_building.json'}  ({len(rows)} buildings)")

    site = merge_site_payload(metered=metered,
                              pv=_read(OUT / "pv_crosscheck.json"),
                              cost=_read(OUT / "cost_check.json"),
                              opensolar=_read(OUT / "opensolar_spotcheck.json"),
                              calibrated=_read(OUT / "calibrated.json"))
    SITE_JSON.parent.mkdir(parents=True, exist_ok=True)
    SITE_JSON.write_text(json.dumps(site, indent=1))

    ran = [k for k, v in site.items() if v.get("status") == "ok"]
    print(f"wrote {OUT / 'metered_buildings.json'}")
    print(f"wrote {SITE_JSON}")
    print(f"evals with results: {', '.join(ran)}")
    print(f"not run yet: {', '.join(k for k in site if k not in ran) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
