"""Turn the scorecard into the static JSON the site reads.

This module SELECTS and RELABELS. It must never compute a number: if a figure is
not already in the scorecard it does not belong on the page, because the page would
then disagree with `score_eval.py` the first time either changed.

Writes:
  backend/evals/out/metered_buildings.json   the metered-building eval alone
  frontend/public/evals.json                 all evals merged, for Evals.tsx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCORECARD = ROOT / "data/cache/evals/out/scorecard.json"
OUT = ROOT / "backend/evals/out"
SITE_JSON = ROOT / "frontend/public/evals.json"
ARM = "bdg2temp"          # the measured-temperature arm is the headline


def build_payload(card: dict) -> dict:
    """Scorecard -> the metered-building payload. Values are copied, never derived."""
    l3, l4 = card["l3_electricity"][ARM], card["l4_interval"][ARM]
    w = card["weather_decomposition"]

    headline = [
        {"label": "Interval coverage", "value": l4["coverage_pct"], "unit": "%",
         "nominal": l4["nominal_pct"], "ci90": l4["site_clustered_ci90"], "n": l4["n"],
         "note": "How often the metered annual fell inside our stated 10-90 band. "
                 "Nominal is 80%. Lower means the band is too narrow."},
        {"label": "Median absolute error", "value": l3["median_abs_pct"], "unit": "%",
         "nominal": None, "ci90": None, "n": l3["n"],
         "note": "Half of buildings are predicted closer than this, half further."},
        {"label": "Median signed error", "value": l3["median_pct"], "unit": "%",
         "nominal": 0.0, "ci90": None, "n": l3["n"],
         "note": "Near zero: the model is not systematically high or low, it is scattered."},
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
        "question": "How close is our predicted annual electricity to a real meter, "
                    "and does our stated uncertainty band tell the truth?",
        "headline": headline,
        "bins": l4["bins_pct"],
        "bins_note": "Where the metered total fell relative to our band. Truth falls "
                     "below and above in near-equal measure, so the band is too narrow "
                     "rather than biased in one direction.",
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


def _slot(payload: dict | None, title: str, question: str) -> dict:
    """An eval that has not run is an explicit not_run, never a zero and never absent."""
    if payload is not None:
        return payload
    return {"status": "not_run", "title": title, "question": question,
            "note": "This check has not been run yet."}


def merge_site_payload(metered: dict | None, pv: dict | None, cost: dict | None,
                       opensolar: dict | None) -> dict:
    return {
        "metered_buildings": _slot(metered, "Metered buildings",
                                   "How close is our predicted annual electricity to a real meter?"),
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

    site = merge_site_payload(metered=metered,
                              pv=_read(OUT / "pv_crosscheck.json"),
                              cost=_read(OUT / "cost_check.json"),
                              opensolar=_read(OUT / "opensolar_spotcheck.json"))
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
