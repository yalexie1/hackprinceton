"""Rebuild the two weather samples in this folder from NOAA station observations (#325).

Not a test, and nothing imports it. Run from the repository root:

    python specs/examples/weather/build_weather_sample.py [--cache DIR] [--check]

What it writes, for each file (see README.md for the reasoning and the numbers):

* `temp_c`, `rh_pct`, `wind_m_s` from NOAA Global Hourly (ISD) observations, calendar year
  2024, at the station the Data lane's TMYx rule picks for the site (data spec 5.1f):
  Los Angeles Downtown USC (722874-93134) for the Los Angeles file, Houston Hobby
  (722440-12918) for the Houston file. Public domain (U.S. Government work).
* `ghi_w_m2`, `dni_w_m2`, `dhi_w_m2` unchanged from the Open-Meteo archive 2024 request that
  `fetch_weather_sample.py` makes (CC BY 4.0). They are refetched and compared with the
  committed file; `--check` stops if they differ.
* the same 8,784 `time_local` stamps (local standard time, hour-ending, no offset).

Hourly values: for each local-standard hour stamp H (UTC = H - offset), the valid report
nearest to H within 30 minutes, FM-15 (routine METAR) preferred over FM-16 (special),
chosen per variable. Downtown USC reports at :47 and Hobby at :53, so the report of
12:47 or 12:53 stamps 13:00. ISD quality codes 2, 3, 6, 7 (suspect, erroneous) and the
missing sentinels (+9999 temperature, 9999 wind speed) are dropped; calm wind (type C)
is 0 m/s. Relative humidity from T and Td by the Magnus formula with the Alduchov and
Eskridge (1996) constants, a = 17.625, b = 243.04 degC, capped at 100 %.

Gaps: runs of 1 to 3 missing hours are filled by linear interpolation; longer runs take
the Open-Meteo value for that hour.

Downtown USC has no hourly reports after 2024-05-20 14:47 UTC (ISD, GHCNh and the METAR
archive all stop there), but GHCN-Daily has its TMAX and TMIN for every day of 2024. From
local day 2024-05-20 on, the Los Angeles temperature is the hourly series of a donor
station (`DONOR`, chosen by the validation in README.md), rescaled day by day so that its
daily minimum and maximum equal USC's GHCN-Daily TMIN and TMAX; dew point and wind are
the donor's, with Td capped at the rescaled T.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import math
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEAR = 2024
ISD_URL = "https://noaa-global-hourly-pds.s3.amazonaws.com/{year}/{station}.csv"  # NCEI global-hourly/access mirror
GHCND_URL = ("https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations={station}"
             "&startDate={year}-01-01&endDate={year}-12-31&dataTypes=TMAX,TMIN&units=standard&format=csv")
MAGNUS_A, MAGNUS_B = 17.625, 243.04
MAX_INTERP_H = 3
BAD_QC = set("2367")
COLUMNS = ("time_local", "temp_c", "rh_pct", "ghi_w_m2", "dni_w_m2", "dhi_w_m2", "wind_m_s")

# The donor for the Los Angeles gap: Hawthorne Municipal (Jack Northrop Field), 722956-03167,
# 12 km from USC, picked by the Jan-May validation in README.md (lowest hourly RMSE of rescaled
# T and of Td against USC's own reports among eight basin stations).
DONOR = "72295603167"
USC_CUTOVER_LOCAL = pd.Timestamp("2024-05-20T00:00")

# file name, ISD station (USAF+WBAN), GHCN-Daily id, standard UTC offset (h), donor
SITES = (
    ("typical_year_hourly.csv", "72287493134", "USW00093134", -8, DONOR),
    ("typical_year_hourly_houston.csv", "72244012918", "USW00012918", -6, None),
)


def download(url: str, path: Path) -> Path:
    if not path.exists():
        with urllib.request.urlopen(url, timeout=300) as resp:
            path.write_bytes(resp.read())
    return path


def isd_reports(cache: Path, station: str) -> pd.DataFrame:
    """FM-15 and FM-16 reports of `station` for YEAR and the first days of YEAR+1 (the last
    local hours of 31 December are in the next UTC year), parsed to SI units."""
    frames = []
    for year in (YEAR, YEAR + 1):
        path = download(ISD_URL.format(year=year, station=station), cache / f"{station}_{year}.csv")
        f = pd.read_csv(path, usecols=["DATE", "REPORT_TYPE", "TMP", "DEW", "WND"], dtype=str)
        frames.append(f)
    f = pd.concat(frames, ignore_index=True)
    f["type"] = f["REPORT_TYPE"].str.strip()
    f = f[f["type"].isin(["FM-15", "FM-16"])].copy()
    f["utc"] = pd.to_datetime(f["DATE"])

    def temp(col: pd.Series) -> pd.Series:
        parts = col.str.split(",")
        value = pd.to_numeric(parts.str[0], errors="coerce")
        ok = (value != 9999) & ~parts.str[1].isin(BAD_QC)
        return (value / 10.0).where(ok)

    f["t"] = temp(f["TMP"])
    f["td"] = temp(f["DEW"])
    w = f["WND"].str.split(",")
    speed = pd.to_numeric(w.str[3], errors="coerce")
    ok = (speed != 9999) & ~w.str[4].isin(BAD_QC)
    f["wind"] = (speed / 10.0).where(ok)
    f.loc[w.str[2] == "C", "wind"] = 0.0
    return f[["utc", "type", "t", "td", "wind"]]


def hourly(reports: pd.DataFrame, utc_hours: pd.DatetimeIndex) -> pd.DataFrame:
    """Per variable, the valid report nearest each hour within 30 min, FM-15 first."""
    out = pd.DataFrame(index=utc_hours, columns=["t", "td", "wind"], dtype=float)
    for var in out.columns:
        r = reports.dropna(subset=[var]).copy()
        r["hour"] = r["utc"].dt.round("h")
        r["dist"] = (r["utc"] - r["hour"]).abs()
        r = r[r["dist"] <= pd.Timedelta(minutes=30)]
        r["rank"] = (r["type"] != "FM-15").astype(int)
        r = r.sort_values(["hour", "rank", "dist", "utc"]).drop_duplicates("hour")
        out[var] = r.set_index("hour")[var].reindex(utc_hours)
    return out


def runs(missing: np.ndarray) -> list[tuple[int, int]]:
    """(start, length) of each run of True."""
    out, i = [], 0
    while i < len(missing):
        if missing[i]:
            j = i
            while j < len(missing) and missing[j]:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def fill(series: pd.Series, fallback: pd.Series) -> tuple[pd.Series, dict]:
    """Interpolate runs of 1-3 missing hours; longer runs take `fallback`."""
    s = series.copy()
    gaps = runs(s.isna().to_numpy())
    interp = s.interpolate(method="linear", limit_area="inside")
    stats = {"filled_hours": 0, "fallback_hours": 0, "longest_gap_h": max((n for _, n in gaps), default=0),
             "short_runs": 0, "long_runs": 0}
    for start, n in gaps:
        idx = s.index[start:start + n]
        inside = start > 0 and start + n < len(s)
        if n <= MAX_INTERP_H and inside:
            s.loc[idx] = interp.loc[idx]
            stats["filled_hours"] += n
            stats["short_runs"] += 1
        else:
            s.loc[idx] = fallback.loc[idx]
            stats["fallback_hours"] += n
            stats["long_runs"] += 1
    return s, stats


def magnus_rh(t: np.ndarray, td: np.ndarray) -> np.ndarray:
    e = np.exp(MAGNUS_A * td / (MAGNUS_B + td))
    es = np.exp(MAGNUS_A * t / (MAGNUS_B + t))
    return np.minimum(100.0 * e / es, 100.0)


def ghcnd(cache: Path, station: str) -> pd.DataFrame:
    """GHCN-Daily TMAX and TMIN (degC) by local date."""
    path = download(GHCND_URL.format(station=station, year=YEAR), cache / f"ghcnd_{station}_{YEAR}.csv")
    d = pd.read_csv(path, dtype={"STATION": str})
    d.index = pd.to_datetime(d["DATE"]).dt.date
    return pd.DataFrame({"tmax": (d["TMAX"] - 32) / 1.8, "tmin": (d["TMIN"] - 32) / 1.8})


def rescale_to_daily(t: pd.Series, daily: pd.DataFrame) -> pd.Series:
    """Map each local day of `t` linearly so its min and max are the day's TMIN and TMAX."""
    out = t.copy()
    for day, block in t.groupby(t.index.date):
        lo, hi = block.min(), block.max()
        tmin, tmax = daily.loc[day, "tmin"], daily.loc[day, "tmax"]
        if hi - lo < 1e-9:
            out.loc[block.index] = (tmin + tmax) / 2
        else:
            out.loc[block.index] = tmin + (block - lo) * (tmax - tmin) / (hi - lo)
    return out


def load_open_meteo(name: str) -> pd.DataFrame:
    """The Open-Meteo 2024 year for the site, as strings exactly as fetch_weather_sample.py writes them."""
    spec = importlib.util.spec_from_file_location("fetch_weather_sample", HERE / "fetch_weather_sample.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    site = next(s for s in mod.SITES if s[0] == name)
    hourly_om = mod.fetch(site[1], site[2])["hourly"]
    wind = [None if w is None else round(w * mod.KMH_TO_MS, 4) for w in hourly_om["wind_speed_10m"]]
    frame = pd.DataFrame({
        "time_local": hourly_om["time"],
        "temp_c": hourly_om["temperature_2m"], "rh_pct": hourly_om["relative_humidity_2m"],
        "ghi_w_m2": hourly_om["shortwave_radiation"], "dni_w_m2": hourly_om["direct_normal_irradiance"],
        "dhi_w_m2": hourly_om["diffuse_radiation"], "wind_m_s": wind,
    })
    return frame.astype(object).map(lambda v: "" if v is None else str(v))


def station_year(cache: Path, station: str, local: pd.DatetimeIndex, offset_h: int,
                 om: pd.DataFrame, part: np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Hourly t, td, wind of `station` on the local-standard stamps where `part` is True,
    gaps filled (Open-Meteo for long ones); the statistics count those hours only."""
    utc = pd.DatetimeIndex(local - pd.Timedelta(hours=offset_h))
    obs = hourly(isd_reports(cache, station), utc)
    obs.index = local
    om_t = pd.to_numeric(om["temp_c"]).set_axis(local)
    om_rh = pd.to_numeric(om["rh_pct"]).set_axis(local)
    gamma = np.log(om_rh / 100) + MAGNUS_A * om_t / (MAGNUS_B + om_t)
    om_td = MAGNUS_B * gamma / (MAGNUS_A - gamma)
    om_w = pd.to_numeric(om["wind_m_s"]).set_axis(local)
    obs = obs[part]
    stats = {"hours": int(part.sum()), "observed": {v: int(obs[v].notna().sum()) for v in obs.columns}}
    out = pd.DataFrame(index=obs.index)
    for var, fb in (("t", om_t), ("td", om_td), ("wind", om_w)):
        out[var], stats[var] = fill(obs[var], fb[part])
    return out, stats


def build(cache: Path, check: bool) -> dict:
    report = {}
    for name, station, ghcn, offset_h, donor in SITES:
        current = pd.read_csv(HERE / name, dtype=str, keep_default_na=False)
        om = load_open_meteo(name)
        if list(om["time_local"]) != list(current["time_local"]):
            raise SystemExit(f"{name}: Open-Meteo stamps differ from the committed file")
        solar = ["ghi_w_m2", "dni_w_m2", "dhi_w_m2"]
        if not om[solar].equals(current[solar]):
            msg = f"{name}: refetched Open-Meteo irradiance differs from the committed file"
            if check:
                raise SystemExit(msg)
            print("warning:", msg)
        local = pd.DatetimeIndex(pd.to_datetime(current["time_local"]))
        everything = np.ones(len(local), dtype=bool)
        if donor is None:
            data, stats = station_year(cache, station, local, offset_h, om, everything)
            stats = {station: stats}
        else:
            # USC's hourly record ends 2024-05-20; from that local day on, the donor station
            # rescaled to USC's daily extremes (README, "The Los Angeles gap").
            after = np.asarray(local >= USC_CUTOVER_LOCAL)
            own, own_stats = station_year(cache, station, local, offset_h, om, ~after)
            d, d_stats = station_year(cache, donor, local, offset_h, om, after)
            t = rescale_to_daily(d["t"], ghcnd(cache, ghcn))
            d = pd.DataFrame({"t": t, "td": np.minimum(d["td"], t), "wind": d["wind"]})
            data = pd.concat([own, d])
            stats = {station: own_stats, donor: d_stats}
        rh = magnus_rh(data["t"].to_numpy(), data["td"].to_numpy())
        new = current.copy()
        new["temp_c"] = [f"{v:.1f}" for v in data["t"]]
        new["rh_pct"] = [str(int(round(v))) for v in rh]
        new["wind_m_s"] = [f"{v:.1f}" for v in data["wind"]]
        new[solar] = om[solar]
        with open(HERE / name, "w", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(COLUMNS)
            writer.writerows(new[list(COLUMNS)].itertuples(index=False, name=None))
        print(name, stats)
        report[name] = stats
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache", type=Path, help="download folder (default: a new temporary folder)")
    parser.add_argument("--check", action="store_true", help="stop if refetched irradiance differs")
    args = parser.parse_args()
    cache = args.cache or Path(tempfile.mkdtemp(prefix="noaa-weather-"))
    cache.mkdir(parents=True, exist_ok=True)
    build(cache, args.check)
    return 0


if __name__ == "__main__":
    sys.exit(main())
