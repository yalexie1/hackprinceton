"""The Open-Meteo request behind the weather samples in this folder (work package A1).

Since #322 the committed files are written by `build_weather_sample.py`: it calls
`fetch()` here for the irradiance (and for the hours its station data cannot fill),
and takes temperature, humidity and wind from NOAA station observations. Run alone,
this script writes the earlier Open-Meteo-only files.

Not a test, and nothing imports it. Run from the repository root:

    python specs/examples/weather/fetch_weather_sample.py

It makes the same Open-Meteo archive request as the Data lane's D9
(`backend/data_layer/external.py`: same variables, `timezone=auto`, calendar year
2024, the Data lane's `WEATHER_YEAR`) and writes the same CSV columns, so the sample
has the shape of the file `ClimateSite.weather_path` points at. Open-Meteo is a
public, keyless source (CC BY 4.0); no sponsor data is involved.

It also checks that the response uses one fixed UTC offset equal to the zone's
standard offset, so `time_local` is local standard time with no daylight saving.
"""
from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = (
    "temperature_2m", "relative_humidity_2m", "shortwave_radiation",
    "direct_normal_irradiance", "diffuse_radiation", "wind_speed_10m",
)
CSV_COLUMNS = ("time_local", "temp_c", "rh_pct", "ghi_w_m2", "dni_w_m2", "dhi_w_m2", "wind_m_s")
KMH_TO_MS = 1000.0 / 3600.0
YEAR = 2024

# (file name, latitude, longitude, IANA zone): the golden house (Los Angeles) and
# the golden Houston office, coordinates as in specs/examples/*/property_bundle.json.
SITES = (
    ("typical_year_hourly.csv", 34.0934917, -118.3171, "America/Los_Angeles"),
    ("typical_year_hourly_houston.csv", 29.7452, -95.4567, "America/Chicago"),
)


def fetch(lat: float, lon: float) -> dict:
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": f"{YEAR}-01-01", "end_date": f"{YEAR}-12-31",
        "hourly": ",".join(HOURLY_VARS), "timezone": "auto",
    })
    with urllib.request.urlopen(f"{OPEN_METEO}?{query}", timeout=120) as resp:
        return json.load(resp)


def main() -> int:
    here = Path(__file__).resolve().parent
    for name, lat, lon, zone in SITES:
        payload = fetch(lat, lon)
        standard = ZoneInfo(zone).utcoffset(datetime(YEAR, 1, 15)).total_seconds()
        if payload.get("timezone") != zone or payload.get("utc_offset_seconds") != standard:
            raise SystemExit(f"{name}: unexpected zone or offset in response: "
                             f"{payload.get('timezone')} {payload.get('utc_offset_seconds')}")
        hourly = payload["hourly"]
        with open(here / name, "w", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(CSV_COLUMNS)
            for i, stamp in enumerate(hourly["time"]):
                wind = hourly["wind_speed_10m"][i]
                writer.writerow([
                    stamp,
                    hourly["temperature_2m"][i],
                    hourly["relative_humidity_2m"][i],
                    hourly["shortwave_radiation"][i],
                    hourly["direct_normal_irradiance"][i],
                    hourly["diffuse_radiation"][i],
                    round(wind * KMH_TO_MS, 4) if wind is not None else None,
                ])
        print(f"{name}: {len(hourly['time'])} rows, grid point "
              f"{payload['latitude']}, {payload['longitude']}, elevation {payload['elevation']} m, "
              f"offset {payload['utc_offset_seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
