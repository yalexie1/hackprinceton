"""Weather reader and the hourly climate output of A1 (workplan 4.2, A1 acceptance)."""
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.analysis.physics.climate.hourly import hourly_climate, load_climate
from backend.analysis.physics.climate.weather import read_site_weather, read_weather, standard_offset
from backend.schema import ClimateSite

ROOT = Path(__file__).resolve().parents[5]
SAMPLE = ROOT / "specs" / "examples" / "weather" / "typical_year_hourly.csv"
SAMPLE_HOU = ROOT / "specs" / "examples" / "weather" / "typical_year_hourly_houston.csv"
LA = dict(lat=34.0934917, lon=-118.3171, timezone="America/Los_Angeles")


def _site(path, **kw):
    base = dict(LA, weather_path=str(path), weather_source="test", weather_time_convention="hour_end")
    base.update(kw)
    return ClimateSite(**base)


def _write(tmp_path, frame, name="w.csv"):
    p = tmp_path / name
    frame.to_csv(p, index=False)
    return p


def _frame(times, **cols):
    n = len(times)
    data = {"time_local": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
            "temp_c": np.full(n, 15.0), "ghi_w_m2": np.zeros(n)}
    data.update(cols)
    return pd.DataFrame(data)


# ---------- reader ----------

def test_sample_reads_8760_hours_in_local_standard_time():
    w = read_weather(SAMPLE, "America/Los_Angeles")
    assert len(w) == 8760
    assert w.has_direct_diffuse
    assert w.stamps.tz.utcoffset(None) == dt.timedelta(hours=-8)
    assert bool(np.all(np.diff(w.stamps.asi8) > 0))
    assert not ((w.stamps.month == 2) & (w.stamps.day == 29)).any()
    assert any("29 February" in m for m in w.warnings)
    for arr in (w.temp_c, w.ghi_w_m2, w.dni_w_m2, w.dhi_w_m2, w.rh_pct, w.wind_m_s):
        assert arr.shape == (8760,) and np.isfinite(arr).all()
    assert w.albedo is None


def test_houston_sample_reads_8760_hours():
    w = read_weather(SAMPLE_HOU, "America/Chicago")
    assert len(w) == 8760 and w.stamps.tz.utcoffset(None) == dt.timedelta(hours=-6)


def test_read_site_weather_resolves_repo_relative_path():
    site = _site("specs/examples/weather/typical_year_hourly.csv")
    w = read_site_weather(site)
    assert len(w) == 8760 and w.convention == "hour_end" and w.source == "test"


def test_standard_offset_ignores_daylight_saving():
    assert standard_offset("America/Los_Angeles", 2024).utcoffset(None) == dt.timedelta(hours=-8)
    assert standard_offset("Australia/Sydney", 2024).utcoffset(None) == dt.timedelta(hours=10)


def test_explicit_offsets_are_kept(tmp_path):
    times = pd.date_range("2025-01-01 00:00", periods=48, freq="h")
    f = _frame(times)
    f["time_local"] = [s + "-08:00" for s in f["time_local"]]
    w = read_weather(_write(tmp_path, f), "America/Los_Angeles")
    assert w.stamps[0] == pd.Timestamp("2025-01-01 08:00", tz="UTC")


def test_wall_clock_file_is_detected_and_flagged(tmp_path):
    wall = pd.date_range("2025-03-08 00:00", "2025-03-10 00:00", freq="h", tz="America/Los_Angeles")
    f = _frame(wall.tz_localize(None))
    w = read_weather(_write(tmp_path, f), "America/Los_Angeles")
    assert any("wall clock" in m for m in w.warnings)
    utc = w.stamps.tz_convert("UTC")
    assert bool(np.all((utc[1:] - utc[:-1]) == pd.Timedelta(hours=1)))


def test_gappy_time_axis_is_rejected(tmp_path):
    times = pd.DatetimeIndex(["2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 05:00"])
    with pytest.raises(ValueError):
        read_weather(_write(tmp_path, _frame(times)), "America/Los_Angeles")


def test_missing_values_are_interpolated_and_flagged(tmp_path):
    times = pd.date_range("2025-01-01", periods=5, freq="h")
    f = _frame(times, temp_c=[10.0, np.nan, 14.0, 15.0, np.nan])
    w = read_weather(_write(tmp_path, f), "America/Los_Angeles")
    assert w.temp_c.tolist() == [10.0, 12.0, 14.0, 15.0, 15.0]
    assert any("2 missing values in temp_c" in m for m in w.warnings)
    assert any("not 8760" in m for m in w.warnings)


def test_required_columns_and_conventions(tmp_path):
    times = pd.date_range("2025-01-01", periods=5, freq="h")
    p = _write(tmp_path, _frame(times).drop(columns="ghi_w_m2"))
    with pytest.raises(ValueError, match="ghi_w_m2"):
        read_weather(p, "America/Los_Angeles")
    p = _write(tmp_path, _frame(times), "ok.csv")
    with pytest.raises(ValueError):
        read_weather(p, "America/Los_Angeles", convention="instant")
    w = read_weather(p, "America/Los_Angeles", convention=None)
    assert w.convention == "hour_end" and any("assumed hour_end" in m for m in w.warnings)


# ---------- hourly climate ----------

@pytest.fixture(scope="module")
def la_hours():
    return load_climate(_site(SAMPLE), elevation_m=104.0)


def test_hourly_climate_outputs(la_hours):
    out = hourly_climate(_site(SAMPLE), 20.0, 180.0, hours=la_hours)
    for key in ("sun_azimuth_deg", "sun_elevation_deg", "poa_global", "poa_beam", "poa_sky_diffuse",
                "poa_ground", "temp_c"):
        assert out[key].shape == (8760,) and np.isfinite(out[key]).all(), key
    assert len(out["stamps"]) == 8760
    assert {"SOL-01", "SOL-07", "IRR-08", "IRR-10"} <= set(out["formula_ids"])
    assert "IRR-02" not in out["formula_ids"]
    night = out["sun_elevation_deg"] <= 0
    assert night.sum() > 3500 and np.all(out["poa_global"][night] == 0)
    # a south plane at 20 degrees in Los Angeles collects more than the horizontal over the year
    assert out["poa_global"].sum() > la_hours.ghi_w_m2.sum()
    # the 2024 sample is a real year: annual GHI in a plausible band for Los Angeles (kWh/m2)
    assert 1700 < la_hours.ghi_w_m2.sum() / 1000 < 2200


def test_closure_reported(la_hours):
    c = la_hours.closure
    assert c["hours"] > 4000
    assert c["mean_abs_w_m2"] < 5.0       # Open-Meteo components close to within a few W/m2


def test_sunrise_row_matches_data_lane_check(la_hours):
    """Data spec 5.1a: on 21 June the 05:00 stamp (hour 04:00-05:00) holds the first light."""
    k = int(np.flatnonzero(la_hours.stamps == pd.Timestamp("2024-06-21 05:00", tz="Etc/GMT+8"))[0])
    assert la_hours.ghi_w_m2[k] > 0 and la_hours.ghi_w_m2[k - 1] == 0
    assert la_hours.stamps[k] - pd.Timedelta(hours=1) < la_hours.eval_times[k] < la_hours.stamps[k]
    assert la_hours.eval_times[k] > la_hours.stamps[k] - pd.Timedelta(minutes=30)   # sun-up half
    assert la_hours.sun_elevation_deg[k] > 0


def test_ghi_only_file_falls_back_to_erbs(tmp_path, la_hours):
    w = la_hours.weather
    f = pd.DataFrame({"time_local": [t.strftime("%Y-%m-%dT%H:%M") for t in w.stamps.tz_localize(None)],
                      "temp_c": w.temp_c, "ghi_w_m2": w.ghi_w_m2})
    h = load_climate(_site(_write(tmp_path, f)), elevation_m=104.0)
    assert h.decomposed and "IRR-02" in h.formula_ids
    assert any("Erbs" in m for m in h.warnings)
    np.testing.assert_allclose(h.dni_w_m2 * np.cos(np.radians(h.apparent_zenith_deg)) + h.dhi_w_m2,
                               h.ghi_w_m2, atol=1e-6)
    poa = hourly_climate(_site(SAMPLE), 20.0, 180.0, hours=h)["poa_global"].sum()
    ref = hourly_climate(_site(SAMPLE), 20.0, 180.0, hours=la_hours)["poa_global"].sum()
    assert abs(poa / ref - 1) < 0.10


def test_albedo_column_is_used(tmp_path, la_hours):
    w = la_hours.weather
    f = pd.DataFrame({"time_local": [t.strftime("%Y-%m-%dT%H:%M") for t in w.stamps.tz_localize(None)],
                      "temp_c": w.temp_c, "ghi_w_m2": w.ghi_w_m2, "dni_w_m2": w.dni_w_m2,
                      "dhi_w_m2": w.dhi_w_m2, "albedo": np.full(len(w), 0.5)})
    h = load_climate(_site(_write(tmp_path, f)), elevation_m=104.0)
    g = hourly_climate(_site(SAMPLE), 90.0, 180.0, hours=h)["poa_ground"]
    g_ref = hourly_climate(_site(SAMPLE), 90.0, 180.0, hours=la_hours)["poa_ground"]
    assert g.sum() == pytest.approx(2.5 * g_ref.sum(), rel=1e-9)
