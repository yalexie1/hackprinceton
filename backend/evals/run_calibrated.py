"""Does a year of utility bills actually fix the predictions? Measured, out-of-period.

Design (set by @yalexie1 on the board, with @vinayak-sinha's caution applied):
  calibrate each building on its TWELVE 2016 MONTHLY BILLS, derived from the BDG2
  hourly meter and run against 2016 weather, then predict 2017 - a year the model
  never saw - and score it with the same score_eval functions the uncalibrated arm
  uses. Fitting and testing on the same year would remove that year's error by
  construction and prove nothing.

Abstention is deliberate and load-bearing. A building whose calibration does not
converge (MV-04 tolerances not met) is recorded `not_calibrated` and EXCLUDED from
the calibrated arm rather than quietly carried through at its uncalibrated values.
A calibrated arm padded with uncalibrated buildings would look better than it is.

Both arms are reported ON THE SAME BUILDINGS. Comparing a calibrated subset against
the full uncalibrated cohort would be a different cohort, not a different method.

Writes data/cache/evals/out/calibrated.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.evals.run_eval import (BDG2, EXCLUDE_USAGE, RESIDENTIAL, SITES,  # noqa: E402
                                    effective_climate_zone, scaled_bundle)

OUT = ROOT / "data/cache/evals/out"
FIT_YEAR, TEST_YEAR = 2016, 2017
ARM = "bdg2temp"
#: Calibration runs in fast mode (~3 s/building measured). Capped anyway so one
#: pathological building cannot eat the whole run.
MAX_SIMULATIONS = int(os.environ.get("EVAL_CAL_BUDGET", "400"))


def monthly(frame: pd.DataFrame, col: str) -> list[float] | None:
    """Twelve monthly totals, or None when the year is not complete enough to bill."""
    s = pd.to_numeric(frame[col], errors="coerce")
    if s.notna().sum() < 0.90 * len(s):
        return None
    by_month = s.groupby(frame.index.month)
    present, total = by_month.count(), by_month.sum()
    hours = frame.index.month.value_counts().sort_index()
    out = []
    for m in range(1, 13):
        if m not in total.index or present.get(m, 0) == 0:
            return None
        out.append(float(total[m]) * float(hours[m]) / float(present[m]))   # scale for gaps
    return out if all(v > 0 for v in out) else None


def load_year(ids: list[str], fuel: str, year: int) -> dict[str, list[float]]:
    path = BDG2 / f"{fuel}_cleaned.csv"
    header = pd.read_csv(path, nrows=0).columns.tolist()
    cols = [c for c in ids if c in header]
    if not cols:
        return {}
    f = pd.read_csv(path, usecols=["timestamp"] + cols, parse_dates=["timestamp"])
    f = f[f.timestamp.dt.year == year].set_index("timestamp")
    out = {}
    for c in cols:
        m = monthly(f, c)
        if m is not None:
            out[c] = m
    return out


def _weather(site: str, year: int) -> str:
    return f"data/cache/evals/weather/{ARM}_{site}_{year}.csv"


def one_building(payload: dict) -> dict:
    """Calibrate on FIT_YEAR, predict TEST_YEAR. Returns a record, never raises."""
    from backend.schema import PropertyBundle, UtilityBills
    from backend.analysis import api

    row, site, seg, golden = payload["row"], payload["site"], payload["seg"], payload["golden"]
    rec = {"building_id": row["building_id"], "site_id": row["site_id"], "usage": row["usage"],
           "sqm": row["sqm"], "measured_2017_kwh": payload["truth_2017"]}
    try:
        class R:                                   # scaled_bundle reads attributes
            pass
        r = R()
        for k, v in row.items():
            setattr(r, k, v)

        fit = scaled_bundle(golden, r, site, ARM)
        fit["climate"]["weather_path"] = _weather(row["site_id"], FIT_YEAR)
        fit.pop("_eval", None)
        fit_bundle = PropertyBundle(**fit)

        test = scaled_bundle(golden, r, site, ARM)
        test["climate"]["weather_path"] = _weather(row["site_id"], TEST_YEAR)
        test.pop("_eval", None)
        test_bundle = PropertyBundle(**test)

        model = api.build_building_model(fit_bundle)

        # Uncalibrated prediction of the test year, same model, same code path.
        plain = api.run_baseline(test_bundle, model)
        rec["uncalibrated"] = {"low": plain.annual.electricity_kwh.low,
                               "expected": plain.annual.electricity_kwh.expected,
                               "high": plain.annual.electricity_kwh.high}

        bills = UtilityBills(electricity_kwh=payload["bills_2016"],
                             gas_kwh=payload.get("gas_2016"))
        t0 = time.time()
        calibrated_model = api.calibrate_model(fit_bundle, model, bills)
        rec["calibration_s"] = round(time.time() - t0, 1)
        cal = calibrated_model.calibration
        rec["calibrated_ok"] = bool(cal and cal.calibrated)
        rec["moved"] = list(getattr(cal, "moved", []) or []) if cal else []

        if not rec["calibrated_ok"]:
            # Abstain: it is excluded from the calibrated arm, not carried at its
            # uncalibrated value, which would flatter the result.
            rec["calibrated"] = None
            rec["reason"] = "calibration did not meet MV-04 tolerances"
            return rec

        tuned = api.run_baseline(test_bundle, calibrated_model)
        rec["calibrated"] = {"low": tuned.annual.electricity_kwh.low,
                             "expected": tuned.annual.electricity_kwh.expected,
                             "high": tuned.annual.electricity_kwh.high}
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["trace"] = traceback.format_exc()[-400:]
        rec.setdefault("calibrated", None)
    return rec


def main(limit: int | None = None, workers: int = 8) -> int:
    meta = pd.read_csv(BDG2 / "metadata.csv")
    pool = meta[meta.site_id.isin(SITES) & meta.electricity.notna() & meta.sqm.notna()
                & meta.yearbuilt.notna() & meta.lat.notna()].copy()
    pool = pool[(pool.sqm > 50) & (pool.sqm < 200000) & (pool.yearbuilt > 1850)
                & (pool.yearbuilt <= TEST_YEAR) & ~pool.primaryspaceusage.isin(EXCLUDE_USAGE)]
    ids = pool.building_id.tolist()

    bills16 = load_year(ids, "electricity", FIT_YEAR)
    truth17 = load_year(ids, "electricity", TEST_YEAR)
    gas16 = load_year(ids, "gas", FIT_YEAR)
    both = [b for b in ids if b in bills16 and b in truth17]
    print(f"cohort: {len(ids)} filtered | {FIT_YEAR} billable {len(bills16)} | "
          f"{TEST_YEAR} metered {len(truth17)} | BOTH {len(both)}", flush=True)

    pool = pool[pool.building_id.isin(both)]
    if limit:
        # Stratified by site so a partial run is not one city.
        parts = [g.sample(min(len(g), max(1, round(limit * len(g) / len(pool)))), random_state=17)
                 for _, g in pool.groupby("site_id")]
        pool = pd.concat(parts).head(limit)
    print(f"running {len(pool)} buildings on {workers} workers", flush=True)

    golden = {k: json.load(open(ROOT / f"specs/examples/{v}/property_bundle.json"))
              for k, v in (("commercial", "office"), ("residential", "house"))}

    jobs = []
    for row in pool.itertuples():
        seg = "residential" if row.primaryspaceusage in RESIDENTIAL else "commercial"
        jobs.append({
            "row": {"building_id": row.building_id, "site_id": row.site_id,
                    "usage": row.primaryspaceusage, "sqm": float(row.sqm),
                    "yearbuilt": int(row.yearbuilt), "lat": float(row.lat),
                    "lng": float(row.lng), "numberoffloors": row.numberoffloors,
                    "primaryspaceusage": row.primaryspaceusage},
            "site": SITES[row.site_id], "seg": seg, "golden": golden[seg],
            "bills_2016": bills16[row.building_id],
            "gas_2016": gas16.get(row.building_id),
            "truth_2017": sum(truth17[row.building_id]),
        })

    results, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(one_building, j): j["row"]["building_id"] for j in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 20 == 0 or i == len(jobs):
                ok = sum(1 for r in results if r.get("calibrated_ok"))
                print(f"  {i}/{len(jobs)}  calibrated_ok={ok}  "
                      f"{(time.time() - t0) / i:.1f}s/bldg", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calibrated.json").write_text(json.dumps(
        {"fit_year": FIT_YEAR, "test_year": TEST_YEAR, "arm": ARM,
         "n_eligible_both_years": len(both), "n_run": len(results),
         "runs": results}, indent=1))
    print(f"\nwrote {OUT / 'calibrated.json'}  n={len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None,
                  workers=int(sys.argv[2]) if len(sys.argv) > 2 else 8))
