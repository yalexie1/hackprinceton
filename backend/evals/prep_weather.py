"""Build the two weather arms for the BDG2 defaults-path eval.

Arm A ("bdg2temp"): BDG2's measured site air temperature + Open-Meteo irradiance.
Arm B ("openmeteo"): Open-Meteo temperature + the same Open-Meteo irradiance.

BDG2 ships no irradiance (airTemperature, cloudCoverage, dewTemperature, precip,
pressure, wind only), so irradiance has to come from Open-Meteo in both arms. The
A-vs-B difference therefore isolates the *temperature* error of the reanalysis path,
which is the term the HDD bias lives in; it does not test irradiance.

Writes data/cache/evals/weather/<arm>_<site>.csv in the schema backend/analysis
expects: time_local,temp_c,rh_pct,ghi_w_m2,dni_w_m2,dhi_w_m2,wind_m_s
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BDG2 = ROOT / "data/cache/evals/bdg2"
OUT = ROOT / "data/cache/evals/weather"
YEAR = 2017

# US sites only: UK/Canada sites would hit state-keyed paths (eGRID subregion,
# the CA/TX weather fallback in analysis.api._climate).
SITES = {
    "Bear":     ("CA", "US/Pacific"),
    "Cockatoo": ("NY", "US/Eastern"),
    "Fox":      ("AZ", "US/Mountain"),
    "Panther":  ("FL", "US/Eastern"),
    "Rat":      ("DC", "US/Eastern"),
}

HOURLY = ["temperature_2m", "relativehumidity_2m", "windspeed_10m",
          "shortwave_radiation", "direct_normal_irradiance", "diffuse_radiation"]


def fetch_openmeteo(lat: float, lon: float, tz: str) -> pd.DataFrame:
    q = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "start_date": f"{YEAR}-01-01", "end_date": f"{YEAR}-12-31",
        "hourly": ",".join(HOURLY), "timezone": tz,
    })
    url = f"https://archive-api.open-meteo.com/v1/archive?{q}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                h = json.load(r)["hourly"]
            break
        except Exception as exc:                      # transient 429/5xx
            if attempt == 3:
                raise
            print(f"    retry {attempt + 1} ({exc})", flush=True)
            time.sleep(5 * (attempt + 1))
    return pd.DataFrame({
        "time_local": pd.to_datetime(h["time"]),
        "temp_c": h["temperature_2m"],
        "rh_pct": h["relativehumidity_2m"],
        "wind_m_s": h["windspeed_10m"],
        "ghi_w_m2": h["shortwave_radiation"],
        "dni_w_m2": h["direct_normal_irradiance"],
        "dhi_w_m2": h["diffuse_radiation"],
    }).set_index("time_local")


def bdg2_temps(weather: pd.DataFrame, site: str) -> pd.Series:
    s = weather[weather.site_id == site].copy()
    s["time_local"] = pd.to_datetime(s["timestamp"])
    s = s.set_index("time_local").sort_index()
    s = s[~s.index.duplicated(keep="first")]
    return s["airTemperature"]


def write_arm(frame: pd.DataFrame, path: Path) -> None:
    cols = ["temp_c", "rh_pct", "ghi_w_m2", "dni_w_m2", "dhi_w_m2", "wind_m_s"]
    out = frame[cols].copy()
    out.index.name = "time_local"
    out = out.reset_index()
    out["time_local"] = out["time_local"].dt.strftime("%Y-%m-%dT%H:%M")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, float_format="%.3f")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = pd.read_csv(BDG2 / "metadata.csv")
    weather = pd.read_csv(BDG2 / "weather.csv")
    index = pd.date_range(f"{YEAR}-01-01 00:00", f"{YEAR}-12-31 23:00", freq="h")

    report = {}
    for site, (state, tz) in SITES.items():
        rows = meta[(meta.site_id == site) & meta.lat.notna()]
        lat, lon = float(rows.lat.mean()), float(rows.lng.mean())
        print(f"{site} ({state}) lat={lat:.3f} lon={lon:.3f}", flush=True)

        om = fetch_openmeteo(lat, lon, tz).reindex(index)
        om = om.interpolate(limit_direction="both")
        write_arm(om, OUT / f"openmeteo_{site}.csv")

        meas = bdg2_temps(weather, site).reindex(index)
        gaps = int(meas.isna().sum())
        meas = meas.interpolate(limit_direction="both")
        arm_a = om.copy()
        arm_a["temp_c"] = meas
        write_arm(arm_a, OUT / f"bdg2temp_{site}.csv")

        # Degree days on NOAA's method: daily (Tmax+Tmin)/2 against 65 degF.
        def hdd_cdd(series: pd.Series) -> tuple[float, float]:
            f = series * 9 / 5 + 32
            daily = f.resample("D").agg(["max", "min"]).mean(axis=1)
            return (float((65 - daily).clip(lower=0).sum()),
                    float((daily - 65).clip(lower=0).sum()))

        h_om, c_om = hdd_cdd(om["temp_c"])
        h_bd, c_bd = hdd_cdd(arm_a["temp_c"])
        report[site] = {
            "state": state, "lat": lat, "lon": lon, "timezone": tz,
            "bdg2_temp_gaps_h": gaps,
            "hdd65_f_openmeteo": round(h_om), "hdd65_f_bdg2": round(h_bd),
            "cdd65_f_openmeteo": round(c_om), "cdd65_f_bdg2": round(c_bd),
            "hdd_bias_pct": round(100 * (h_om - h_bd) / h_bd, 1) if h_bd else None,
            "cdd_bias_pct": round(100 * (c_om - c_bd) / c_bd, 1) if c_bd else None,
            "ghi_kwh_m2_year": round(float(om["ghi_w_m2"].sum()) / 1000, 1),
        }
        print(f"    HDD65 om={h_om:.0f} bdg2={h_bd:.0f} "
              f"({report[site]['hdd_bias_pct']}%)  gaps={gaps} h", flush=True)

    (OUT / "weather_report.json").write_text(json.dumps(report, indent=2))
    print(f"\nwrote {OUT}/weather_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
