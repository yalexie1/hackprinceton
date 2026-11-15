"""Build the ROI map data: `python -m backend.roi_map.build [la|houston ...]`.

Estimated simple payback of rooftop solar on a TYPICAL home, per zip code. Not an audit of any building.

Inputs, all public:
- Zip centroids and the county each zip mostly lies in: US Census 2023 Gazetteer and 2020 ZCTA-county relationship file.
- Retail electricity rate by zip: OpenEI "U.S. Electric Utility Companies and Rates: Look-up by Zipcode (2020)"
  (residential rate, utility name). It is a 2020 figure, so it is scaled by the ratio of the current EIA state
  residential average (the data layer's `get_tariff`) to the unweighted state mean of the same file.
- Solar resource: PVGIS PVcalc (ERA5), 1 kWp, fixed 20 deg tilt facing south, 14 % losses, at the zip centroid.
- Cost: the finance module's `cost_fields` for PV_ROOF, residential, 6 kW DC; incentives as it registers them.
- Payback: the finance module's `simple_payback(net_upfront, first-year savings)`.

Declared assumptions (also in each file's `assumptions`): 6 kW system, 70 % of output used on site at the retail
rate, the rest valued at zero (no export credit assumed), no degradation or rate escalation.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.request import urlopen

from backend.analysis.finance.costs import cost_fields
from backend.analysis.finance.economics.economics import simple_payback
from backend.roi_map.service import CITIES, DATA
from backend.schema import MeasureResult, PropertySummary

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache" / "roi_map"          # git-ignored
SYSTEM_KW = 6.0
SELF_USE = 0.70
COUNTY = {"la": ("06037", "CA", "Los Angeles"), "houston": ("48201", "TX", "Houston")}
GAZ = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_zcta_national.zip"
REL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"
IOU = "https://data.openei.org/files/5650/iou_zipcodes_2020.csv"
NONIOU = "https://data.openei.org/files/5650/non_iou_zipcodes_2020.csv"
PVGIS = ("https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat={lat}&lon={lon}&peakpower=1&loss=14&angle=20&aspect=0"
         "&raddatabase=PVGIS-ERA5&outputformat=json")


def fetch(url: str, name: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.is_file():
        with urlopen(url, timeout=120) as r:
            path.write_bytes(r.read())
    return path.read_bytes()


def zips_in(county: str) -> dict[str, dict]:
    """zip -> {lat, lon} for the zips whose largest land share lies in `county`."""
    best: dict[str, tuple[int, str]] = {}
    rows = csv.DictReader(io.StringIO(fetch(REL, "rel.txt").decode("utf-8-sig")), delimiter="|")
    for r in rows:
        z = r["GEOID_ZCTA5_20"]
        if z and r["GEOID_COUNTY_20"]:
            area = int(r["AREALAND_PART"] or 0)
            if z not in best or area > best[z][0]:
                best[z] = (area, r["GEOID_COUNTY_20"])
    mine = {z for z, (_, c) in best.items() if c == county}
    gaz = zipfile.ZipFile(io.BytesIO(fetch(GAZ, "gaz.zip")))
    text = gaz.read(gaz.namelist()[0]).decode("utf-8")
    out = {}
    for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
        r = {k.strip(): v.strip() for k, v in r.items()}
        if r["GEOID"] in mine:
            out[r["GEOID"]] = {"lat": float(r["INTPTLAT"]), "lon": float(r["INTPTLONG"])}
    return out


def rates() -> tuple[dict[str, tuple[str, float, str]], dict[str, float]]:
    """zip -> (utility, 2020 residential rate, state); and the unweighted state mean of that file."""
    out, by_state = {}, {}
    for url, name in ((IOU, "iou.csv"), (NONIOU, "noniou.csv")):
        for r in csv.DictReader(io.StringIO(fetch(url, name).decode("utf-8-sig"))):
            try:
                rate = float(r["res_rate"])
            except (KeyError, ValueError):
                continue
            if rate > 0:
                out.setdefault(r["zip"].zfill(5), (r["utility_name"], rate, r["state"]))
                by_state.setdefault(r["state"], []).append(rate)
    return out, {s: sum(v) / len(v) for s, v in by_state.items()}


def kwh_per_kw(lat: float, lon: float) -> float:
    key = f"pvgis-{lat:.3f}-{lon:.3f}.json"
    body = fetch(PVGIS.format(lat=lat, lon=lon), key)
    return float(json.loads(body)["outputs"]["totals"]["fixed"]["E_y"])


def eia_residential(state: str) -> float:
    from backend.data_layer.external import get_tariff
    tariff, _ = get_tariff(state, "RES")
    if tariff is None:
        raise SystemExit("no EIA_API_KEY: the current state residential average is needed to scale the 2020 rates")
    return tariff.electricity_usd_per_kwh


def finance(state: str, city: str, utility: str):
    measure = MeasureResult(measure_id="PV_ROOF", title="Rooftop solar", applicable=True)
    summary = PropertySummary(sid="typical", name="Typical home", segment="residential",
                              use_type="single_family", city=city, state=state)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return cost_fields(measure, summary, SYSTEM_KW * 1000.0, utility=utility)


def build(city: str) -> dict:
    county, state, city_name = COUNTY[city]
    places = zips_in(county)
    zip_rates, state_mean = rates()
    current = eia_residential(state)
    scale = current / state_mean[state]
    with ThreadPoolExecutor(4) as pool:
        yields = dict(zip(places, pool.map(lambda z: kwh_per_kw(places[z]["lat"], places[z]["lon"]), places)))
    cost_cache, rows = {}, []
    for z, p in sorted(places.items()):
        if z in zip_rates:
            utility, rate2020, _ = zip_rates[z]
            rate, rate_source = rate2020 * scale, "zip_utility"
        else:     # no zip-level rate (deregulated retail market): the current EIA state average
            utility, rate, rate_source = f"no utility listed ({state} state average rate)", current, "state_average"
        if utility not in cost_cache:
            cost_cache[utility] = finance(state, city_name, utility)
        c = cost_cache[utility]
        kwh = yields[z] * SYSTEM_KW
        savings = kwh * SELF_USE * rate
        payback = simple_payback(c.net_upfront_usd.expected, savings)
        rows.append({"zip": z, **p, "utility": utility, "rate_usd_per_kwh": round(rate, 4), "rate_source": rate_source,
                     "kwh_per_kw_year": round(yields[z]), "annual_kwh": round(kwh),
                     "installed_cost_usd": round(c.installed_cost_usd.expected),
                     "net_upfront_usd": round(c.net_upfront_usd.expected),
                     "annual_savings_usd": round(savings),
                     "payback_years": None if payback is None else round(payback, 1),
                     "basis": "estimate for a typical home, not an audit"})
    return {"city": city, "name": CITIES[city], "built": date.today().isoformat(),
            "label": "Estimated payback of rooftop solar on a typical home. Not an audit of any building.",
            "assumptions": [f"{SYSTEM_KW:g} kW DC rooftop system, fixed 20 degree tilt facing south, 14 % losses (PVGIS ERA5)",
                            f"{SELF_USE:.0%} of the output used on site at the retail rate; the rest valued at zero",
                            "retail rate: OpenEI 2020 zip-level residential rate scaled to the current EIA state average "
                            f"(x{scale:.2f}); one rate per utility service area, not per street",
                            (f"zips with no listed rate (deregulated retail market) use the EIA {state} state average"
                             if any(r["rate_source"] == "state_average" for r in rows)
                             else "every zip has a listed utility rate"),
                            "this differs from a property audit, which uses the EIA state average rate and the utility's "
                            "net-metering rules for exports; here exports earn nothing, so these paybacks are a "
                            "conservative screening estimate, not a quote",
                            "cost from the finance module (PV_ROOF, residential); no incentives apply in 2026, no "
                            "financing, degradation or rate escalation",
                            "payback is simple payback: cost divided by first-year savings"],
            "rows": rows}


def main(argv: list[str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for city in argv or list(CITIES):
        t = time.time()
        out = build(city)
        (DATA / f"{city}.json").write_text(json.dumps(out, indent=1))
        n = len(out["rows"])
        pbs = sorted(r["payback_years"] for r in out["rows"] if r["payback_years"] is not None)
        print(f"{city}: {n} zips, payback {pbs[0]}-{pbs[-1]} y (median {pbs[len(pbs)//2]}), {time.time()-t:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
