"""Solar PV check: our annual AC kWh per kW DC against PVGIS-ERA5, on the buildings of a finished run.
  python -m backend.agent.ebewe_eval.solar [results_file] [--summary out.json]
MODEL vs MODEL (PVGIS is a reference, not measured output). Privacy: property coordinates are rounded to 0.01 degree
(about 1 km) before they leave the machine; no ids or addresses are sent; at most 1 request per second."""
import collections
import json
import statistics as st
import sys
import time
import urllib.request

from backend.agent.ebewe_eval.common import ROOT, WORK

LOSS = 14.08          # the model's own default system losses are 14.0757 percent


def pvgis_kwh_per_kw(lat: float, lon: float, tilt: int, aspect: int, cache: dict, last: list):
    key = (lat, lon, tilt, aspect)
    if key in cache:
        return cache[key]
    url = (f"https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat={lat}&lon={lon}&peakpower=1&loss={LOSS}&angle={tilt}"
           f"&aspect={aspect}&raddatabase=PVGIS-ERA5&outputformat=json")
    for _ in range(2):
        time.sleep(max(0.0, 1.1 - (time.time() - last[0])))
        last[0] = time.time()
        try:
            cache[key] = json.load(urllib.request.urlopen(url, timeout=40))["outputs"]["totals"]["fixed"]["E_y"]
            return cache[key]
        except Exception:
            pass
    cache[key] = None
    return None


def orientation(az: float) -> str:
    a = az % 360
    return "south 135-225" if 135 <= a <= 225 else ("north" if a < 45 or a > 315 else "east/west")


def main(argv: list[str]) -> None:
    results = argv[0] if argv and not argv[0].startswith("--") else "results_none.jsonl"
    sel = {s["sid"]: s for s in json.loads((WORK / "selected.json").read_text())}
    recs = [json.loads(l) for l in (WORK / results).read_text().splitlines()]
    recs = [r for r in recs if r.get("status") == "done" and r["sid"] in sel]
    recs.sort(key=lambda r: sel[r["sid"]]["use_type"] != "office")
    cache, last, rows, nodesign = {}, [0.0], [], 0
    for r in recs[:80]:
        d = ROOT / "data" / "runs" / r["run"]
        try:
            pv = [m for m in json.loads((d / "measures.json").read_text()) if m.get("measure_id") == "PV_ROOF"]
            s = pv[0].get("solar") if pv else None
            if not s or not s.get("system_kw_dc") or not s.get("panels"):
                nodesign += 1
                continue
            model = json.loads((d / "model.json").read_text())
            bundle = json.loads((d / "bundle.json").read_text())
            planes = {p["id"]: p for p in model["roof_planes"]}
            main_plane = planes[collections.Counter(p["plane_id"] for p in s["panels"]).most_common(1)[0][0]]
            tilt, az = main_plane["tilt_deg"]["expected"], main_plane.get("azimuth_deg") or 180.0
            ref = pvgis_kwh_per_kw(round(bundle["summary"]["lat"], 2), round(bundle["summary"]["lon"], 2),
                                   round(tilt), round(((az - 180 + 180) % 360) - 180), cache, last)
            if ref:
                rows.append({"use": sel[r["sid"]]["use_type"], "tilt": tilt, "az": az,
                             "diff": (s["annual_kwh"]["expected"] / s["system_kw_dc"] - ref) / ref})
        except Exception:
            nodesign += 1
    d = sorted(x["diff"] * 100 for x in rows)
    out = {"n": len(rows), "n_no_design": nodesign, "params": {"loss": LOSS, "raddatabase": "PVGIS-ERA5", "coords_rounded_to": 0.01},
           "median_diff_pct": st.median(d) if d else None, "mean_diff_pct": st.mean(d) if d else None,
           "within_10_pct": sum(abs(x) <= 10 for x in d) / len(d) if d else None,
           "by_orientation": dict(collections.Counter(orientation(x["az"]) for x in rows)),
           "note": "model vs model; flat single-plane offices dominate, so orientation is barely exercised"}
    print(json.dumps(out, indent=1))
    if "--summary" in argv:
        open(argv[argv.index("--summary") + 1], "w").write(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
