"""Weather file reader (A1).

Reads the hourly CSV that `ClimateSite.weather_path` points at. Format: data spec
section 5.1a, reference sample `specs/examples/weather/typical_year_hourly.csv`.

| Column | Unit | Required |
|---|---|---|
| `time_local` | ISO 8601, local standard time, no offset (or with an explicit offset) | yes |
| `temp_c` | degC | yes |
| `ghi_w_m2` | W/m2 | yes |
| `dni_w_m2`, `dhi_w_m2` | W/m2 | no; without both, IRR-02 splits GHI (fallback) |
| `rh_pct` | % | no |
| `wind_m_s` | m/s at 10 m | no |
| `albedo` | 0..1 | no; IRR-09 uses it when present |

Timestamps without an offset are read as local *standard* time of
`ClimateSite.timezone` (physics 01 section 0.1; Open-Meteo returns one fixed offset,
the zone's standard one). A file that instead follows the wall clock (a missing hour
in spring and a repeated hour in autumn) is detected, read as such, and flagged.

A leap year's 29 February is dropped, so a full year is always 8,760 hours (the
typical-year convention of SAM and NSRDB). Gaps are filled by linear interpolation and
flagged. Reading is pure: no network, no writes.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from backend.schema import ClimateSite

HOURS_PER_YEAR = 8760
REQUIRED_COLUMNS = ("time_local", "temp_c", "ghi_w_m2")
OPTIONAL_COLUMNS = ("rh_pct", "dni_w_m2", "dhi_w_m2", "wind_m_s", "albedo")
CONVENTIONS = ("hour_end", "hour_start", "hour_centre")
#: Used when `ClimateSite.weather_time_convention` is None: the convention the Data
#: lane verified for Open-Meteo (data spec 5.1a).
DEFAULT_CONVENTION = "hour_end"

_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Weather:
    """One year of hourly weather. Arrays share the index `stamps` (timezone-aware)."""
    stamps: pd.DatetimeIndex
    temp_c: np.ndarray
    ghi_w_m2: np.ndarray
    dni_w_m2: np.ndarray | None
    dhi_w_m2: np.ndarray | None
    rh_pct: np.ndarray | None
    wind_m_s: np.ndarray | None
    albedo: np.ndarray | None
    timezone: str
    convention: str
    source: str
    warnings: tuple[str, ...] = field(default=())

    def __len__(self) -> int:
        return len(self.stamps)

    @property
    def has_direct_diffuse(self) -> bool:
        return self.dni_w_m2 is not None and self.dhi_w_m2 is not None


def standard_offset(timezone: str, year: int) -> dt.timezone:
    """The zone's standard-time UTC offset (no daylight saving) as a fixed timezone."""
    zone = ZoneInfo(timezone)
    probe = dt.datetime(year, 1, 15, 12)
    offset = zone.utcoffset(probe) - (zone.dst(probe) or dt.timedelta(0))
    return dt.timezone(offset)


def _hourly_except_leap_day(stamps: pd.DatetimeIndex) -> bool:
    """True if every step is one hour, allowing a typical-year file that already omits 29 February."""
    if len(stamps) < 2:
        return True
    steps = stamps[1:] - stamps[:-1]
    hourly = steps == pd.Timedelta(hours=1)
    skips_leap_day = ((steps == pd.Timedelta(hours=25)) & (stamps[:-1].month == 2)
                      & (stamps[:-1].day == 28) & (stamps[:-1].hour == 23))
    return bool(np.all(hourly | skips_leap_day))


def _parse_times(raw: pd.Series, timezone: str, warnings: list[str]) -> pd.DatetimeIndex:
    stamps = pd.DatetimeIndex(pd.to_datetime(raw, format="ISO8601"))
    if stamps.tz is not None:
        return stamps
    if _hourly_except_leap_day(stamps):
        return stamps.tz_localize(standard_offset(timezone, stamps[0].year))
    try:
        wall = stamps.tz_localize(ZoneInfo(timezone), ambiguous="infer", nonexistent="raise")
    except Exception as exc:  # noqa: BLE001 - re-raised with context
        raise ValueError(f"weather time stamps are not hourly: {exc}") from exc
    utc = wall.tz_convert("UTC")
    if not bool(np.all((utc[1:] - utc[:-1]) == pd.Timedelta(hours=1))):
        raise ValueError("weather time stamps are not a contiguous hourly series")
    warnings.append("time_local follows the wall clock with daylight saving, not local standard time; "
                    "read as wall-clock time in " + timezone)
    return wall.tz_convert(standard_offset(timezone, stamps[0].year))


def read_weather(path, timezone: str, convention: str | None = DEFAULT_CONVENTION,
                 source: str | None = None) -> Weather:
    """Read an hourly weather CSV. See the module docstring for the format."""
    warnings: list[str] = []
    if convention is None:
        convention = DEFAULT_CONVENTION
        warnings.append(f"weather_time_convention not stated; assumed {DEFAULT_CONVENTION} (data spec 5.1a)")
    if convention not in CONVENTIONS:
        raise ValueError(f"unknown weather_time_convention {convention!r}; expected one of {CONVENTIONS}")

    frame = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"weather file {path} lacks required columns {missing}")

    stamps = _parse_times(frame["time_local"], timezone, warnings)
    frame = frame.drop(columns="time_local")
    frame.index = stamps

    leap = (stamps.month == 2) & (stamps.day == 29)
    if leap.any():
        frame = frame.loc[~leap]
        warnings.append(f"dropped {int(leap.sum())} hours of 29 February so the year has 8,760 hours")
    if len(frame) != HOURS_PER_YEAR:
        warnings.append(f"weather file has {len(frame)} hours, not {HOURS_PER_YEAR}")

    def column(name: str, required: bool) -> np.ndarray | None:
        if name not in frame.columns:
            return None
        values = pd.to_numeric(frame[name], errors="coerce")
        gaps = int(values.isna().sum())
        if gaps == len(values):
            if required:
                raise ValueError(f"weather column {name} is empty")
            warnings.append(f"weather column {name} is empty; ignored")
            return None
        if gaps:
            values = values.interpolate(method="linear", limit_direction="both")
            warnings.append(f"{gaps} missing values in {name} filled by linear interpolation")
        return values.to_numpy(dtype=float)

    dni = column("dni_w_m2", False)
    dhi = column("dhi_w_m2", False)
    if (dni is None) != (dhi is None):
        warnings.append("only one of dni_w_m2 and dhi_w_m2 is present; both ignored, GHI will be split (IRR-02)")
        dni = dhi = None

    return Weather(
        stamps=pd.DatetimeIndex(frame.index),
        temp_c=column("temp_c", True),
        ghi_w_m2=column("ghi_w_m2", True),
        dni_w_m2=dni,
        dhi_w_m2=dhi,
        rh_pct=column("rh_pct", False),
        wind_m_s=column("wind_m_s", False),
        albedo=column("albedo", False),
        timezone=timezone,
        convention=convention,
        source=source or str(path),
        warnings=tuple(warnings),
    )


def resolve_weather_path(site: ClimateSite, root=None) -> Path:
    """`ClimateSite.weather_path`, made absolute against the repository root (or `root`)."""
    p = Path(site.weather_path)
    return p if p.is_absolute() else Path(root or _REPO_ROOT) / p


def read_site_weather(site: ClimateSite, root=None) -> Weather:
    """Read the weather file of a `ClimateSite` with its timezone and time convention."""
    return read_weather(resolve_weather_path(site, root), site.timezone,
                        site.weather_time_convention, source=site.weather_source)
