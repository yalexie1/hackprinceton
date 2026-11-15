"""BDG2 defaults-path eval: run the physics on N metered buildings, two weather arms.

What this grades: the 5R1C zone model, the DEF-* default tables, LGT/INF/HVAC, given
correct floor area, vintage and (approximate) use type. What it does NOT grade:
geometry extraction, vision, daylight, PV/shading - those need scan and roof inputs
that BDG2 does not carry. Geometry error is excluded by construction.

Energy only. PropertySummary.state is Literal["CA","TX"] in the contract, so every
building is labelled CA; that affects eGRID emissions, tariff and incentives but not
the energy physics (DEF tables key off vintage and climate zone; roof code needs
Vexcel, which is absent here). Cost and CO2 are therefore not scored.

Writes data/cache/evals/out/runs.json
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from copy import deepcopy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BDG2 = ROOT / "data/cache/evals/bdg2"
WX = ROOT / "data/cache/evals/weather"
OUT = ROOT / "data/cache/evals/out"
YEAR = 2017
DEFAULT_TARGET_N = 500
ARMS = ("bdg2temp", "openmeteo")

# ASHRAE 169 climate zones for the five US sites.
SITES = {
    "Bear":     {"state": "CA", "tz": "US/Pacific",  "zone": "3C"},
    "Cockatoo": {"state": "NY", "tz": "US/Eastern",  "zone": "6A"},
    "Fox":      {"state": "AZ", "tz": "US/Mountain", "zone": "2B"},
    "Panther":  {"state": "FL", "tz": "US/Eastern",  "zone": "2A"},
    "Rat":      {"state": "DC", "tz": "US/Eastern",  "zone": "4A"},
}
RESIDENTIAL = {"Lodging/residential"}
# Parking structures are unconditioned and have no defaults path in DEF-*; modelling one
# as an office overstates it by an order of magnitude (measured: +1650% on a smoke test).
# Excluded as out of scope rather than carried as model error.
EXCLUDE_USAGE = {"Parking"}


def load_truth(ids: list[str], fuel: str) -> dict[str, dict]:
    """Annual metered kWh for YEAR, per building, with completeness."""
    path = BDG2 / f"{fuel}_cleaned.csv"
    header = pd.read_csv(path, nrows=0).columns.tolist()
    cols = [c for c in ids if c in header]
    if not cols:
        return {}
    frame = pd.read_csv(path, usecols=["timestamp"] + cols, parse_dates=["timestamp"])
    frame = frame[frame.timestamp.dt.year == YEAR].set_index("timestamp")
    hours = len(frame)
    out = {}
    for c in cols:
        s = pd.to_numeric(frame[c], errors="coerce")
        present = int(s.notna().sum())
        if present < 0.90 * hours:
            continue
        total = float(s.sum()) * hours / present      # scale up for the gaps
        if total <= 0:
            continue
        out[c] = {"annual_kwh": total, "completeness": present / hours}
    return out


def scaled_bundle(golden: dict, row, site: dict, arm: str) -> dict:
    """Golden bundle with the plan scaled to the BDG2 floor area and the vintage set."""
    b = deepcopy(golden)
    current = sum(r.get("area_m2") or 0.0 for r in b["matterport"]["rooms"])
    if current <= 0:
        raise ValueError("golden bundle has no room areas to scale from")
    k = float(row.sqm) / current
    s = k ** 0.5                                      # plan dimensions scale as sqrt(area)

    for fl in b["matterport"]["floors"]:
        for v in fl["vertices"]:
            v["x"] *= s
            v["y"] *= s
        for e in fl["edges"]:
            for op in e.get("openings") or []:
                if op.get("width_m"):
                    op["width_m"] *= s                # windows grow with the wall, WWR held
    for r in b["matterport"]["rooms"]:
        for key in ("width_m", "depth_m"):
            if r.get(key):
                r[key] *= s
        if r.get("area_m2"):
            r["area_m2"] *= k
        r["polygon"] = [[x * s, y * s] for x, y in (r.get("polygon") or [])]

    # One shared sid per (site, arm) so the 8760-hour SPA climate load is cached;
    # _zone_key still hashes the geometry, so buildings do not share zone runs.
    b["summary"]["sid"] = f"EVAL_{row.site_id}_{arm}"
    b["summary"]["name"] = str(row.building_id)
    b["summary"]["state"] = "CA"                      # contract Literal; see module docstring
    b["summary"]["lat"], b["summary"]["lon"] = float(row.lat), float(row.lng)

    residential = row.primaryspaceusage in RESIDENTIAL
    b["summary"]["segment"] = "residential" if residential else "commercial"
    b["summary"]["use_type"] = "multifamily_unit" if residential else "office"

    b["climate"].update({
        "lat": float(row.lat), "lon": float(row.lng), "timezone": site["tz"],
        "climate_zone": site["zone"],
        "weather_path": f"data/cache/evals/weather/{arm}_{row.site_id}.csv",
        "weather_source": f"eval arm {arm}, site {row.site_id}, {YEAR}",
        "weather_time_convention": "hour_end",
    })
    if b.get("costar"):
        b["costar"]["year_built"] = int(row.yearbuilt)
    return b


def main(target_n: int = DEFAULT_TARGET_N) -> int:
    from backend.schema import PropertyBundle
    from backend.analysis import api

    OUT.mkdir(parents=True, exist_ok=True)
    meta = pd.read_csv(BDG2 / "metadata.csv")
    pool = meta[meta.site_id.isin(SITES) & meta.electricity.notna()
                & meta.sqm.notna() & meta.yearbuilt.notna() & meta.lat.notna()].copy()
    pool = pool[(pool.sqm > 50) & (pool.sqm < 200000)
                & (pool.yearbuilt > 1850) & (pool.yearbuilt <= YEAR)
                & ~pool.primaryspaceusage.isin(EXCLUDE_USAGE)]
    print(f"pool after filters: {len(pool)} buildings, {pool.site_id.nunique()} sites", flush=True)

    truth = load_truth(pool.building_id.tolist(), "electricity")
    gas = load_truth(pool.building_id.tolist(), "gas")
    pool = pool[pool.building_id.isin(truth)]
    print(f"with >=90% metered {YEAR} electricity: {len(pool)}  (gas too: "
          f"{len(pool[pool.building_id.isin(gas)])})", flush=True)

    # Stratified by site, proportional, seeded.
    n = min(target_n, len(pool))
    frac = n / len(pool)
    parts = []
    for site_id, group in pool.groupby("site_id"):
        take = min(len(group), max(1, round(len(group) * frac)))
        parts.append(group.sample(take, random_state=17))
    sample = pd.concat(parts).sample(frac=1.0, random_state=17).head(n)
    print(f"sampled {len(sample)}:\n{sample.site_id.value_counts().to_string()}", flush=True)

    golden = {
        "commercial": json.load(open(ROOT / "specs/examples/office/property_bundle.json")),
        "residential": json.load(open(ROOT / "specs/examples/house/property_bundle.json")),
    }

    runs, refused, t0 = [], [], time.time()
    for i, row in enumerate(sample.itertuples(), 1):
        site = SITES[row.site_id]
        seg = "residential" if row.primaryspaceusage in RESIDENTIAL else "commercial"
        rec = {
            "building_id": row.building_id, "site_id": row.site_id,
            "usage": row.primaryspaceusage, "sqm": float(row.sqm),
            "yearbuilt": int(row.yearbuilt),
            "floors": None if pd.isna(row.numberoffloors) else int(row.numberoffloors),
            "climate_zone": site["zone"], "segment": seg,
            "truth_elec_kwh": truth[row.building_id]["annual_kwh"],
            "elec_completeness": truth[row.building_id]["completeness"],
            "truth_gas_kwh": gas.get(row.building_id, {}).get("annual_kwh"),
            "arms": {},
        }
        for arm in ARMS:
            try:
                bundle = PropertyBundle(**scaled_bundle(golden[seg], row, site, arm))
                model = api.build_building_model(bundle)
                res = api.run_baseline(bundle, model)
                e, g = res.annual.electricity_kwh, res.annual.gas_kwh
                rec["arms"][arm] = {
                    "elec": {"low": e.low, "expected": e.expected, "high": e.high},
                    "gas": {"low": g.low, "expected": g.expected, "high": g.high},
                    "end_use_kwh": res.end_use_kwh,
                    "monthly_elec_kwh": res.monthly_electricity_kwh,
                    "model_area_m2": sum(z.floor_area_m2 for z in model.zones),
                    "heating_need_kwh": res.heating_need_kwh,
                    "cooling_need_kwh": res.cooling_need_kwh,
                }
            except Exception as exc:
                rec["arms"][arm] = {"refused": f"{type(exc).__name__}: {exc}"}
                refused.append({"building_id": row.building_id, "arm": arm,
                                "error": f"{type(exc).__name__}: {exc}",
                                "trace": traceback.format_exc()[-800:]})
        runs.append(rec)
        if i % 25 == 0 or i == len(sample):
            rate = (time.time() - t0) / i
            print(f"  {i}/{len(sample)}  {rate:.2f}s/bldg  "
                  f"refused={len(refused)}  eta={(len(sample) - i) * rate / 60:.1f}min", flush=True)

    (OUT / "runs.json").write_text(json.dumps(
        {"year": YEAR, "arms": list(ARMS), "n": len(runs),
         "refused_count": len(refused), "runs": runs}, indent=1))
    (OUT / "refused.json").write_text(json.dumps(refused, indent=1))
    print(f"\nwrote {OUT}/runs.json  n={len(runs)}  refused={len(refused)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET_N))
