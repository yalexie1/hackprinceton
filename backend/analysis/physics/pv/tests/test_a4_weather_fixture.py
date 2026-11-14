"""A4 acceptance on the `weather` fixture (workplan 2.3, written by A1).

Annual yield on the fixture against pvlib ModelChain with the PV-06 settings,
within the physics 01 section 7 tolerance (1e-4 relative annual AC, 0.01 W per
hour). Skipped, with the reason, while the fixture is not on the branch.

The fixture is read here with pandas only to drive the test; the package
itself takes arrays and never reads files.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pvlib")
from pvlib.location import Location  # noqa: E402

from a4_reference import modelchain, ours  # noqa: E402

from backend.analysis.physics.pv import annual_energy  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
WEATHER = EXAMPLES / "weather"

# Fixture file -> the bundle whose ClimateSite it was fetched for.
SITES = {
    "typical_year_hourly.csv": "house",
    "typical_year_hourly_houston.csv": "office_houston",
}
# Standard-time offset of each zone as a fixed-offset zone (no daylight saving).
STANDARD_TZ = {"America/Los_Angeles": "Etc/GMT+8", "America/Chicago": "Etc/GMT+6"}
# Column aliases, so a rename in the fixture does not silently break the test.
COLUMNS = {
    "time": ("time_local", "time", "timestamp"),
    "ghi": ("ghi_w_m2", "ghi"),
    "dni": ("dni_w_m2", "dni"),
    "dhi": ("dhi_w_m2", "dhi"),
    "temp_air": ("temp_c", "temp_air", "air_temp_c"),
    "wind_speed": ("wind_m_s", "wind_speed"),
}
ANNUAL_REL = 1e-4
HOURLY_W = 0.01


def _load(name):
    path = WEATHER / name
    if not path.exists():
        pytest.skip(f"weather fixture {path.relative_to(EXAMPLES.parent.parent)} not present yet "
                    "(written by work package A1)")
    climate = json.loads((EXAMPLES / SITES[name] / "property_bundle.json").read_text())["climate"]
    raw = pd.read_csv(path)
    cols = {}
    for key, aliases in COLUMNS.items():
        hit = next((a for a in aliases if a in raw.columns), None)
        if hit is None:
            pytest.skip(f"weather fixture {name} has no column for {key} (looked for {aliases})")
        cols[key] = hit
    tz = STANDARD_TZ.get(climate["timezone"])
    if tz is None:
        pytest.skip(f"no standard-time zone mapped for {climate['timezone']}")
    stamps = pd.DatetimeIndex(pd.to_datetime(raw[cols["time"]]))
    stamps = stamps.tz_localize(tz) if stamps.tz is None else stamps.tz_convert(tz)
    convention = climate.get("weather_time_convention") or "hour_end"
    # SOL-07: evaluate the sun at the middle of the hour each row covers.
    shift = {"hour_end": "-30min", "hour_start": "30min", "hour_centre": "0min"}[convention]
    w = pd.DataFrame({k: raw[c].to_numpy(dtype=float) for k, c in cols.items() if k != "time"},
                     index=stamps + pd.Timedelta(shift))
    # PV-06 sums 8,760 hours: drop 29 February from a leap-year file.
    w = w[~((w.index.month == 2) & (w.index.day == 29))]
    loc = Location(climate["lat"], climate["lon"], tz=tz)
    return loc, w, climate


@pytest.mark.parametrize("name", sorted(SITES))
@pytest.mark.parametrize("tilt,azimuth", [(20.0, 180.0), (28.4, 90.0)])
def test_annual_yield_on_weather_fixture_against_modelchain(name, tilt, azimuth):
    loc, w, climate = _load(name)
    assert len(w) == 8760
    pdc0 = 6000.0
    mine = ours(loc, w, tilt, azimuth, shading_percent=3.0)
    mc = modelchain(loc, w, tilt, azimuth, pdc0, shading_percent=3.0)
    ref_ac_w = np.clip(mc.results.ac.to_numpy(), 0.0, None)
    my_ac_w = mine.ac_kwh_per_kw * pdc0
    assert np.max(np.abs(my_ac_w - ref_ac_w)) < HOURLY_W
    assert my_ac_w.sum() == pytest.approx(ref_ac_w.sum(), rel=ANNUAL_REL)
    energy = annual_energy(mine.ac_kwh_per_kw, pdc0_kw=pdc0 / 1000, month=w.index.month)
    # Plausibility only (a real year, not the clear sky): kWh per kW DC.
    assert 900 < energy["yield_kwh_per_kw"] < 2200
