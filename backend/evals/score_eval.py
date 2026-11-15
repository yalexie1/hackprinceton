"""Score the BDG2 defaults-path eval: L3 error distribution, L4 interval calibration.

Note on metrics. Truth here is one ANNUAL metered total per building, so this is a
cross-sectional error distribution across buildings, not a time-series goodness of fit.
ASHRAE Guideline 14's NMBE / CV(RMSE) bands are defined for a fit against 12 or 8760
points of ONE building and are deliberately not quoted as pass/fail here.

L4 note. The model emits only (low, expected, high), not a full predictive distribution,
so a true PIT histogram is not available. The four-bin position of truth relative to
those three numbers is reported instead; for a calibrated 10-90 band with the expected
value near the median, the bins should be about 10 / 40 / 40 / 10 per cent.

Clustering. Weather is site-level and there are only FIVE sites, so weather-driven error
is perfectly correlated within a site. Confidence intervals come from a bootstrap over
SITES, not buildings; with 5 clusters they are wide and are reported as such.

Writes data/cache/evals/out/scorecard.json
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/cache/evals/out"
ARMS = ("bdg2temp", "openmeteo")
NOMINAL_COVERAGE = 0.80
# backend/analysis/model/registry/tables.py ships DEF tables for these zones only;
# anything else is blended or defaulted. Mirrors run_eval.SUPPORTED_CLIMATES, kept
# here so scoring does not depend on the runner.
SUPPORTED_ZONES = ("2A", "3B")


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]


def describe(errs: list[float]) -> dict:
    """Signed % errors -> a distribution summary. Median-first: ratio errors are skewed."""
    if not errs:
        return {"n": 0}
    return {
        "n": len(errs),
        "median_pct": round(st.median(errs), 1),
        "median_abs_pct": round(st.median([abs(e) for e in errs]), 1),
        "mean_pct": round(st.fmean(errs), 1),
        "p10_pct": round(pct(errs, 0.10), 1),
        "p90_pct": round(pct(errs, 0.90), 1),
        "within_25pct": round(100 * sum(abs(e) <= 25 for e in errs) / len(errs), 1),
        "within_50pct": round(100 * sum(abs(e) <= 50 for e in errs) / len(errs), 1),
        # ratio = pred/truth = 1 + e/100. A 2x OVERprediction is e = +100; a 2x
        # UNDERprediction is e = -50, not -100. An earlier abs(e) >= 100 test
        # therefore counted only overpredictions and could never flag an
        # underprediction at all (e <= -100 is impossible). Both sides, named.
        "over_by_2x_plus": round(100 * sum(e >= 100 for e in errs) / len(errs), 1),
        "under_by_2x_plus": round(100 * sum(e <= -50 for e in errs) / len(errs), 1),
        "off_by_2x_either_way": round(
            100 * sum(e >= 100 or e <= -50 for e in errs) / len(errs), 1),
    }


def coverage(rows: list[dict], arm: str) -> dict:
    """L4: does the 10-90 band contain the metered annual?"""
    bins = {"below_low": 0, "low_to_expected": 0, "expected_to_high": 0, "above_high": 0}
    inside = 0
    widths = []
    for r in rows:
        a = r["arms"].get(arm, {})
        if "elec" not in a:
            continue
        t, e = r["truth_elec_kwh"], a["elec"]
        widths.append(100 * (e["high"] - e["low"]) / e["expected"] if e["expected"] else float("nan"))
        if t < e["low"]:
            bins["below_low"] += 1
        elif t <= e["expected"]:
            bins["low_to_expected"] += 1
            inside += 1
        elif t <= e["high"]:
            bins["expected_to_high"] += 1
            inside += 1
        else:
            bins["above_high"] += 1
    n = sum(bins.values())
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "coverage_pct": round(100 * inside / n, 1),
        "nominal_pct": round(100 * NOMINAL_COVERAGE, 1),
        "bins_pct": {k: round(100 * v / n, 1) for k, v in bins.items()},
        "mean_width_pct_of_expected": round(st.fmean([w for w in widths if w == w]), 1),
    }


def cluster_bootstrap(rows: list[dict], arm: str, stat, draws: int = 2000) -> list[float]:
    """Resample SITES with replacement (weather is site-level, only 5 clusters)."""
    by_site: dict[str, list[dict]] = {}
    for r in rows:
        by_site.setdefault(r["site_id"], []).append(r)
    sites = list(by_site)
    rng = random.Random(17)
    out = []
    for _ in range(draws):
        pick = [by_site[rng.choice(sites)] for _ in sites]
        flat = [r for g in pick for r in g]
        v = stat(flat, arm)
        if v == v:
            out.append(v)
    return out


def err_pct(r: dict, arm: str) -> float | None:
    a = r["arms"].get(arm, {})
    if "elec" not in a:
        return None
    t = r["truth_elec_kwh"]
    return 100 * (a["elec"]["expected"] - t) / t if t else None


def constant_eui_errors(rows: list[dict]) -> list[float]:
    """Signed % errors of the naive predictor: cohort median intensity x floor area.

    No model in it at all - one number times the one input every building has. It is
    the floor any physics has to clear to be worth running, and it is deliberately
    computed from the SAME rows being scored, which makes it an oracle and therefore
    a hard floor rather than a fair one. `skill_section` says so in its note.
    """
    usable = [r for r in rows if r.get("sqm") and r.get("truth_elec_kwh")]
    if not usable:
        return []
    median_eui = st.median([r["truth_elec_kwh"] / r["sqm"] for r in usable])
    return [100 * (median_eui * r["sqm"] - r["truth_elec_kwh"]) / r["truth_elec_kwh"]
            for r in usable]


def skill_section(rows: list[dict], arm: str) -> dict:
    """Does the model beat a predictor with no model in it? Reported, never implied.

    An error figure on its own reads as an accuracy claim. We published "median
    absolute error 52.9%" for hours and stratified it, bootstrapped it and wrote a
    diagnosis of it before anyone asked what a constant scores: 42.5%, better than
    the model on the same 494 and on every usage class in it. @Sri-SriPod hit the
    same wall independently on a different dataset against a different ground truth.

    Pooled and PER USAGE, because pooled error cancels between classes biased in
    opposite directions - a model can look adequate overall and be beaten everywhere.
    """
    model = describe([e for e in (err_pct(r, arm) for r in rows) if e is not None])
    const = describe(constant_eui_errors(rows))

    def compare(m: dict, c: dict) -> dict:
        if not m.get("n") or not c.get("n"):
            return {"beats_constant": None, "margin_pct_points": None,
                    "verdict": "not enough rows to compare against the constant"}
        margin = round(c["median_abs_pct"] - m["median_abs_pct"], 1)
        beats = margin > 0
        return {
            "beats_constant": beats,
            "margin_pct_points": margin,
            "verdict": (f"the model is {abs(margin)} points "
                        f"{'better' if beats else 'WORSE'} than the constant "
                        f"(cohort median intensity x floor area)"),
        }

    out: dict = {"model": model, "constant_eui": const, **compare(model, const)}
    out["by_usage"] = {}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get("usage")), []).append(r)
    for name, rs in sorted(groups.items()):
        m = describe([e for e in (err_pct(r, arm) for r in rs) if e is not None])
        c = describe(constant_eui_errors(rs))
        out["by_usage"][name] = {"n": m.get("n", 0), "model_median_abs_pct":
                                 m.get("median_abs_pct"),
                                 "constant_median_abs_pct": c.get("median_abs_pct"),
                                 **compare(m, c)}
    out["note"] = (
        "The constant is fitted on the same truth it is scored against, so it is an "
        "ORACLE and a harder floor than a deployable baseline would be. The fair "
        "version uses published reference medians (CBECS/RECS): measured separately "
        "on the 61 BDG2 offices, the public CBECS table scored 39.8% median absolute "
        "against this model's 44.1%, so the model loses to that too. Quote the "
        "comparison, never the error alone."
    )
    return out


def supported_zone_section(rows: list[dict]) -> dict:
    """The stricter cohort: only buildings in a climate zone the DEF tables carry.

    Published BESIDE the all-building headline, never instead of it. Same metrics,
    same functions, a smaller set of rows. No confidence interval: every qualifying
    building sits at one site, and a site-clustered bootstrap over a single cluster
    would return the point estimate dressed up as an interval.
    """
    sub = [r for r in rows if r.get("climate_zone") in SUPPORTED_ZONES]
    sites = sorted({r["site_id"] for r in sub})
    section: dict = {
        "zones": list(SUPPORTED_ZONES),
        "n": len(sub),
        "sites": sites,
        "n_sites": len(sites),
        "l3_electricity": {},
        "l4_interval": {},
        "note": "Buildings whose ASHRAE climate zone (2A or 3B) is one the DEF default "
                "tables actually carry. Every other zone in the sample falls back to a "
                "blend, so this cohort is the model read on its own terms.",
        "ci_note": "No site-clustered CI is reported: the qualifying buildings come from "
                   f"{len(sites)} site(s) ({', '.join(sites) or 'none'}), and a bootstrap "
                   "over one cluster cannot produce a real interval.",
    }
    for arm in ARMS:
        errs = [e for e in (err_pct(r, arm) for r in sub) if e is not None]
        section["l3_electricity"][arm] = describe(errs)
        section["l4_interval"][arm] = coverage(sub, arm)
    return section


def main() -> int:
    data = json.loads((OUT / "runs.json").read_text())
    rows = data["runs"]
    ok = [r for r in rows if all("elec" in r["arms"].get(a, {}) for a in ARMS)]

    card: dict = {
        "dataset": "Building Data Genome Project 2",
        "year": data["year"],
        "scope": "defaults-path eval: 5R1C zone model + DEF-* defaults, given area/vintage/type. "
                 "Excludes geometry extraction, vision, daylight, PV (no scan or roof inputs in BDG2). "
                 "Energy only; cost and CO2 not scored (state forced to CA by the contract Literal).",
        "n_sampled": data["n"],
        "n_scored": len(ok),
        "refused_count": data["refused_count"],
        "sites": sorted({r["site_id"] for r in ok}),
        "n_sites": len({r["site_id"] for r in ok}),
        "caveats": [
            "Truth is one annual total per building: this is a cross-sectional error "
            "distribution, not a Guideline 14 time-series fit.",
            "Weather is site-level across only 5 sites, so the effective N for the "
            "weather-driven error term is 5, not the building count. CIs are bootstrapped "
            "over sites and are wide.",
            "Every building is modelled as a single zone at a single storey scaled to its "
            "floor area, so a tall building's surface-to-volume ratio is wrong by construction.",
            "Non-office uses (Education, Lodging, Entertainment, Public services, Healthcare) "
            "are run on office or residential defaults; type mismatch is inside the reported error.",
            "The DEF default tables carry only climate zones 2A and 3B; the other four "
            "sites fall back to a blend. Each building's zone is recorded in the run "
            "record, and the supported-zone cohort is scored separately below.",
            "Irradiance is Open-Meteo in BOTH arms (BDG2 ships none), so the arm difference "
            "isolates temperature error only, not irradiance error.",
            "The model does not beat a constant predictor (cohort median intensity x "
            "floor area) on this cohort, nor on any usage class in it. See the `skill` "
            "section: an error figure without that comparison is not an accuracy claim.",
        ],
        "l3_electricity": {},
        "l4_interval": {},
        "supported_zones": {},
        "skill": {},
        "by_usage": {},
        "by_site": {},
        "weather_decomposition": {},
    }

    for arm in ARMS:
        errs = [e for e in (err_pct(r, arm) for r in ok) if e is not None]
        card["l3_electricity"][arm] = describe(errs)
        cov = coverage(ok, arm)
        boot = cluster_bootstrap(ok, arm, lambda rs, a: coverage(rs, a).get("coverage_pct", float("nan")))
        if boot:
            cov["site_clustered_ci90"] = [round(pct(boot, 0.05), 1), round(pct(boot, 0.95), 1)]
        card["l4_interval"][arm] = cov

    # The stricter reading, published beside the all-building headline, not instead.
    card["supported_zones"] = supported_zone_section(ok)

    # "Better than what?" - answered on every run, not when someone remembers to ask.
    card["skill"] = skill_section(ok, ARMS[0])

    # Stratify.
    for key, field in (("by_usage", "usage"), ("by_site", "site_id")):
        groups: dict[str, list[dict]] = {}
        for r in ok:
            groups.setdefault(str(r[field]), []).append(r)
        for name, rs in sorted(groups.items()):
            card[key][name] = {
                "n": len(rs),
                "median_sqm": round(st.median([r["sqm"] for r in rs])),
                "bdg2temp": describe([e for e in (err_pct(r, "bdg2temp") for r in rs) if e is not None]),
                "coverage_pct": coverage(rs, "bdg2temp").get("coverage_pct"),
            }

    # Weather: what swapping measured temps for the reanalysis path does.
    shifts, heat_shifts = [], []
    for r in ok:
        a, b = r["arms"]["bdg2temp"], r["arms"]["openmeteo"]
        t = r["truth_elec_kwh"]
        if t:
            shifts.append(100 * (b["elec"]["expected"] - a["elec"]["expected"]) / t)
        ha, hb = a.get("heating_need_kwh"), b.get("heating_need_kwh")
        if ha and hb and ha > 0:
            heat_shifts.append(100 * (hb - ha) / ha)
    card["weather_decomposition"] = {
        "elec_shift_pct_of_truth": describe(shifts),
        "heating_need_shift_pct": describe(heat_shifts),
        "note": "openmeteo minus bdg2temp. Positive = the reanalysis path predicts more than "
                "the measured-temperature path. Heating need is the thermal need before "
                "system efficiency, where the temperature bias lands hardest.",
    }

    # Diagnostic: does error track the single-storey simplification?
    tall = [r for r in ok if (r.get("floors") or 1) >= 4]
    low = [r for r in ok if (r.get("floors") or 1) <= 1]
    card["storey_diagnostic"] = {
        "floors_ge_4": describe([e for e in (err_pct(r, "bdg2temp") for r in tall) if e is not None]),
        "floors_le_1": describe([e for e in (err_pct(r, "bdg2temp") for r in low) if e is not None]),
        "note": "Known limitation: all buildings are modelled as one storey scaled to total "
                "floor area. If the 4+ storey group is biased differently, that is the cause.",
    }

    (OUT / "scorecard.json").write_text(json.dumps(card, indent=1))
    print(json.dumps({k: card[k] for k in
                      ("n_scored", "refused_count", "n_sites", "l3_electricity",
                       "l4_interval", "supported_zones", "skill",
                       "weather_decomposition", "storey_diagnostic")}, indent=1))
    print(f"\nwrote {OUT}/scorecard.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
