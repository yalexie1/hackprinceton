"""A2 hourly zone model on the golden fixtures, driven by the real 2024 weather sample.

Acceptance (workplan 4.2, A2): doubling every `u_value` raises the annual heating need; a zone
with `conditioned=false` has zero load. Also the ZON-04 year energy balance and the ZON-06
monthly cross-check (section 9). Irradiance on each plane is built here from the CSV with a
simple sun position and an isotropic sky, so these tests do not depend on A1's code.
"""
import csv
import math
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.analysis.physics.zone import (HOURLY_KEYS, ZoneOptions, distribute_gains, hourly_columns,
                                           monthly_heating_need, office_hvac_on, zone_loads)
from backend.schema import BuildingModel

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
SITES = {"house": ("typical_year_hourly.csv", 34.09, -118.32, -8),
         "office": ("typical_year_hourly.csv", 34.09, -118.32, -8),
         "office_houston": ("typical_year_hourly_houston.csv", 29.75, -95.46, -6)}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A2 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ---------- test helper: weather CSV to hourly arrays ----------

_WEATHER: dict = {}


def weather(folder):
    """8760 hours (29 February dropped) of the sample CSV with plane irradiance by (tilt, azimuth)."""
    if folder in _WEATHER:
        return _WEATHER[folder]
    name, lat, lon, utc = SITES[folder]
    rows = [r for r in csv.DictReader((EXAMPLES / "weather" / name).open())
            if not r["time_local"].startswith("2024-02-29")]
    stamps = np.array([r["time_local"] for r in rows], dtype="datetime64[m]")
    col = {k: np.array([float(r[k]) for r in rows]) for k in
           ("temp_c", "rh_pct", "ghi_w_m2", "dni_w_m2", "dhi_w_m2", "wind_m_s")}
    # sun at the middle of the hour ending at the stamp (hour_end), local standard time
    mid = stamps - np.timedelta64(30, "m")
    doy = (mid.astype("datetime64[D]") - mid.astype("datetime64[Y]")).astype(int) + 1
    hour = (mid - mid.astype("datetime64[D]")).astype(int) / 60.0
    g = 2 * np.pi / 365 * (doy - 1 + (hour - 12) / 24)
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
            + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    eot = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g) - 0.014615 * np.cos(2 * g)
                    - 0.040849 * np.sin(2 * g))
    solar_time = hour + (eot + 4 * (lon - 15 * utc)) / 60.0
    ha = np.radians(15 * (solar_time - 12))
    phi = np.radians(lat)
    cz = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(ha)
    zen = np.arccos(np.clip(cz, -1, 1))
    saz = np.arctan2(np.sin(ha), np.cos(ha) * np.sin(phi) - np.tan(decl) * np.cos(phi)) + np.pi  # from N
    sun = np.array([np.sin(zen) * np.sin(saz), np.sin(zen) * np.cos(saz), np.cos(zen)])

    def plane(tilt, az):
        t, a = np.radians(tilt), np.radians(180.0 if az is None else az)
        n = np.array([np.sin(t) * np.sin(a), np.sin(t) * np.cos(a), np.cos(t)])
        cos_aoi = np.clip(n @ sun, 0, None) * (cz > 0)
        return (col["dni_w_m2"] * cos_aoi + col["dhi_w_m2"] * (1 + np.cos(t)) / 2
                + 0.2 * col["ghi_w_m2"] * (1 - np.cos(t)) / 2)

    # humidity ratio from RH (Magnus saturation pressure; test input only)
    ps = 610.94 * np.exp(17.625 * col["temp_c"] / (col["temp_c"] + 243.04))
    pw = col["rh_pct"] / 100 * ps
    w = 0.622 * pw / (101325 - pw)
    out = dict(stamps=stamps, plane=plane, w=w, **col)
    _WEATHER[folder] = out
    return out


def model(folder) -> BuildingModel:
    return BuildingModel.model_validate_json((EXAMPLES / folder / "building_model.json").read_text())


def gains(m: BuildingModel, n=8760):
    """Constant sensible internal gain, W (lighting and plug at half power, people at 64.5 W)."""
    s = m.systems
    area = sum(z.floor_area_m2 for z in m.zones if z.conditioned)
    occ = s.occupants.expected if s.occupants else 2.0
    return np.full(n, 0.5 * (s.lighting_w_per_m2.expected + s.plug_w_per_m2.expected) * area + 64.5 * occ)


def run(folder, m=None, **kw):
    m = m or model(folder)
    w = weather(folder)
    kw.setdefault("internal_gains_w", gains(m))
    return zone_loads(m, w["temp_c"], w["plane"], wind_m_s=w["wind_m_s"], stamps=w["stamps"], **kw)


def scaled_u(m: BuildingModel, factor: float) -> BuildingModel:
    surfaces = [s.model_copy(update={"u_value": s.u_value.model_copy(update={
        "low": s.u_value.low * factor, "expected": s.u_value.expected * factor,
        "high": s.u_value.high * factor})}) for s in m.surfaces]
    return m.model_copy(update={"surfaces": surfaces})


FOLDERS = list(SITES)


# ---------- acceptance ----------

@pytest.mark.parametrize("folder", FOLDERS)
def test_year_run_shapes_and_sanity(folder):
    r = run(folder)
    assert len(r.phi_hc_w) == 8760
    z = r.zones[0]
    for k in HOURLY_KEYS:
        assert len(z.hourly[k]) == 8760
    assert r.heating_need_kwh > 0 and r.cooling_need_kwh > 0
    assert r.peak_heating_w > 0 and r.peak_cooling_w > 0
    assert sum(r.monthly_heating_kwh) == pytest.approx(r.heating_need_kwh)
    assert sum(r.monthly_cooling_kwh) == pytest.approx(r.cooling_need_kwh)
    assert set(z.hourly["mode"]) <= {"heating", "cooling", "off"}
    on = z.hourly["mode"] != "off"
    # where heating or cooling runs, the air sits at a setpoint (capacity permitting)
    at_set = np.isclose(z.hourly["theta_air_c"], z.hourly["setpoint_heat_c"], atol=1e-6) | \
        np.isclose(z.hourly["theta_air_c"], z.hourly["setpoint_cool_c"], atol=1e-6)
    assert at_set[on].mean() > 0.95
    assert 0.0 < r.infiltration_ach < 3.0
    assert {"ENV-03", "ZON-04", "WIN-01"} <= set(r.formula_ids)
    cols = hourly_columns(z)
    assert set(cols) == set(HOURLY_KEYS) and len(cols["theta_op_c"]) == 8760


@pytest.mark.parametrize("folder", FOLDERS)
def test_doubling_every_u_value_raises_annual_heating(folder):
    base = run(folder)
    doubled = run(folder, scaled_u(model(folder), 2.0))
    assert doubled.heating_need_kwh > base.heating_need_kwh
    assert doubled.zones[0].h_tr_w_w_k == pytest.approx(2 * base.zones[0].h_tr_w_w_k)


@pytest.mark.parametrize("folder", FOLDERS)
def test_unconditioned_zone_has_zero_load(folder):
    m = model(folder)
    m = m.model_copy(update={"zones": [z.model_copy(update={"conditioned": False}) for z in m.zones]})
    r = run(folder, m, internal_gains_w={z.id: gains(model(folder)) for z in m.zones})
    assert r.heating_need_kwh == 0.0 and r.cooling_need_kwh == 0.0
    assert r.peak_heating_w == 0.0 and r.peak_cooling_w == 0.0
    z = r.zones[0]
    assert not z.hourly["phi_hc_w"].any() and set(z.hourly["mode"]) == {"off"}
    assert np.isfinite(z.hourly["theta_air_c"]).all()     # free-floating temperature still reported


def test_mixed_zones_only_the_unconditioned_one_is_zero():
    m = model("house")
    z0 = m.zones[0]
    extra = z0.model_copy(update={"id": "zone_garage", "conditioned": False, "floor_area_m2": 20.0,
                                  "volume_m3": 50.0})
    wall = next(s for s in m.surfaces if s.kind == "wall").model_copy(update={"id": "g_wall",
                                                                                "zone_id": "zone_garage"})
    m = m.model_copy(update={"zones": [z0, extra], "surfaces": list(m.surfaces) + [wall]})
    r = run("house", m)
    assert r.zone("zone_garage").heating_need_kwh == 0 and r.zone("zone_garage").cooling_need_kwh == 0
    assert r.zone(z0.id).heating_need_kwh > 0


# ---------- ZON-04 energy balance, ZON-06 cross-check ----------

@pytest.mark.parametrize("folder", ["house", "office_houston"])
def test_zon04_year_energy_balance(folder):
    r = run(folder)
    z = r.zones[0]
    p, h = z.params, z.hourly
    g = distribute_gains(h["phi_int_w"], h["phi_sol_w"], p.a_m_m2, p.a_tot_m2, p.h_tr_w_w_k)
    te = weather(folder)["temp_c"]
    flows = (1200 * h["q_ve_m3_s"] * (te - h["theta_air_c"]) + p.h_tr_w_w_k * (te - h["theta_s_c"])
             + p.h_tr_em_w_k * (te - h["theta_m_c"]) + g["phi_ia_w"] + g["phi_st_w"] + g["phi_m_w"]
             + h["phi_hc_w"])
    m_prev = np.concatenate([[2 * h["theta_m_c"][0] - h["theta_m_end_c"][0]], h["theta_m_end_c"][:-1]])
    stored = p.c_m_j_k / 3600 * (h["theta_m_end_c"] - m_prev)
    annual_gains = np.abs(h["phi_int_w"]).sum() + np.abs(h["phi_sol_w"]).sum()
    assert abs((flows - stored).sum()) < 1e-3 * annual_gains
    assert np.abs(flows - stored).max() < 1e-6 * annual_gains


def _monthly_vs_hourly(folder, m, internal, irradiance, options=None):
    w = weather(folder)
    sp = 20.0
    r = zone_loads(m, w["temp_c"], irradiance, internal, wind_m_s=w["wind_m_s"], stamps=w["stamps"],
                   setpoint_heat_c=sp, setpoint_cool_c=80.0, hvac_on=np.ones(8760, bool),
                   options=options)
    z = r.zones[0]
    p, h = z.params, z.hourly
    month = (w["stamps"] - np.timedelta64(60, "m")).astype("datetime64[M]").astype(int) % 12
    total = 0.0
    for k in range(12):
        sel = month == k
        h_tot = z.h_tr_op_w_k + p.h_tr_w_w_k + 1200 * h["q_ve_m3_s"][sel].mean()
        total += monthly_heating_need(h_tot, sp, w["temp_c"][sel].mean(), sel.sum(),
                                      h["phi_int_w"][sel].mean(), h["phi_sol_w"][sel].mean(),
                                      p.c_m_j_k)["q_h_nd_kwh"]
    return total, z


def test_zon06_monthly_cross_check_house():
    """Section 9, ZON-06: constant setpoint, the house's gains and sun; within 15 % on the year."""
    m = model("house")
    monthly, z = _monthly_vs_hourly("house", m, gains(m), weather("house")["plane"])
    assert abs(monthly - z.heating_need_kwh) / z.heating_need_kwh < 0.15


@pytest.mark.parametrize("folder", FOLDERS)
def test_wiring_against_hand_sums_and_steady_state(folder):
    """The wiring check ZON-06 is meant for, made exact. Envelope coefficients summed here by hand
    from the fixture (ENV-03, ENV-04) must equal the model's; at a constant 5 degC outdoors with no
    gain, no sun, no sky radiation and no wind, the year run must settle at the ZON-05 identity
    `H_eff (20 - 5)`, which is below the plain sum the monthly method uses.

    The 15 % test of section 9 with real gains is applied to the house only: the offices are
    gain-dominated (gain-to-loss ratio near 1), where the monthly utilisation factor departs from
    the hourly model by far more than 15 % (reported on the PR)."""
    import math as _m
    from backend.analysis.physics.zone import steady_state_h_eff
    m = model(folder)
    h_w = h_op = 0.0
    for s in m.surfaces:
        u = s.u_value.expected
        if s.boundary == "ground":
            b = 2 * s.area_m2 / s.exposed_perimeter_m
            d_t = 0.15 + 1.5 * 0.21
            ug = (3.0 / (_m.pi * b + d_t) * _m.log(_m.pi * b / d_t + 1)) if d_t < b else 1.5 / (0.457 * b + d_t)
            h_op += s.area_m2 * ug
        elif s.boundary == "exterior":
            if s.kind in ("window", "door"):
                h_w += s.area_m2 * u
            else:
                h_op += s.area_m2 * u
    n = 24 * 60
    r = zone_loads(m, np.full(n, 5.0), lambda tilt, az: 0.0, 0.0, wind_m_s=np.zeros(n),
                   setpoint_heat_c=20.0, setpoint_cool_c=80.0, hvac_on=np.ones(n, bool),
                   options=ZoneOptions(dt_sky_k=0.0, warmup_hours=0))
    z = r.zones[0]
    assert z.h_tr_w_w_k == pytest.approx(h_w, rel=1e-9)
    assert z.h_tr_op_w_k == pytest.approx(h_op, rel=1e-9)
    h_ve = 1200 * z.hourly["q_ve_m3_s"][-1]
    h_eff = steady_state_h_eff(h_ve, z.params)
    assert z.hourly["phi_hc_w"][-1] == pytest.approx(h_eff * 15.0, rel=1e-4)
    assert h_eff < h_op + h_w + h_ve


# ---------- inputs and options ----------

def test_office_schedule_from_hour_ending_stamps():
    s = np.array(["2024-01-01T09:00", "2024-01-01T07:00", "2024-01-01T06:00", "2024-01-01T22:00",
                  "2024-01-01T23:00", "2024-01-06T18:00", "2024-01-06T19:00", "2024-01-07T12:00",
                  "2024-01-02T00:00"], dtype="datetime64[m]")
    assert office_hvac_on(s).tolist() == [True, True, False, True, False, True, False, False, False]
    assert not office_hvac_on(s, "office_vacant").any()


def test_office_needs_a_schedule():
    m = model("office")
    w = weather("office")
    with pytest.raises(ValueError):
        zone_loads(m, w["temp_c"], w["plane"], gains(m))


def test_office_ventilation_follows_occupants():
    m = model("office")
    base = run("office")
    more = m.model_copy(update={"systems": m.systems.model_copy(update={
        "occupants": m.systems.occupants.model_copy(update={"expected": 2 * m.systems.occupants.expected})})})
    r = run("office", more)
    on = office_hvac_on(weather("office")["stamps"])
    dq = r.zones[0].hourly["q_ve_m3_s"] - base.zones[0].hourly["q_ve_m3_s"]
    assert dq[on] == pytest.approx(m.systems.occupants.expected * 0.00944)
    assert dq[~on] == pytest.approx(0.0)


def test_latent_only_in_cooling_hours():
    w = weather("office_houston")
    r = run("office_houston", humidity_ratio_out=w["w"])
    z = r.zones[0]
    assert r.latent_cooling_kwh > 0 and "INF-07" in r.formula_ids
    assert not z.hourly["latent_w"][z.hourly["phi_hc_w"] >= 0].any()


def test_irradiance_by_surface_id_matches_function():
    m = model("house")
    w = weather("house")
    by_id = {s.id: w["plane"](s.tilt_deg, s.azimuth_deg) for s in m.surfaces}
    a = run("house")
    b = zone_loads(m, w["temp_c"], by_id, gains(m), wind_m_s=w["wind_m_s"], stamps=w["stamps"])
    assert b.heating_need_kwh == pytest.approx(a.heating_need_kwh, rel=1e-12)
    c = zone_loads(m, w["temp_c"], {}, gains(m), wind_m_s=w["wind_m_s"], stamps=w["stamps"])
    assert c.cooling_need_kwh < a.cooling_need_kwh and any("no irradiance" in x for x in c.warnings)


def test_ground_method_and_capacity_options():
    a = run("house")
    b = run("house", options=ZoneOptions(ground_method="u_value"))
    m = model("house")
    floor = next(s for s in m.surfaces if s.boundary == "ground")
    assert b.zones[0].h_g_w_k == pytest.approx(floor.area_m2 * floor.u_value.expected)
    assert a.zones[0].h_g_w_k != pytest.approx(b.zones[0].h_g_w_k)
    capped = run("house", options=ZoneOptions(use_cooling_capacity=True))
    assert capped.peak_cooling_w <= m.systems.cooling_capacity_w + 1e-6


def test_deterministic():
    a, b = run("house"), run("house")
    assert np.array_equal(a.phi_hc_w, b.phi_hc_w)


def test_home_setback_lowers_heating_and_cooling_need():
    # CTRL_TSTAT on a home sets heating_setback_c and cooling_setup_c (A22); without home setback
    # hours the zone model ignored them and the measure saved nothing
    base = run("house")
    m = model("house")
    m = m.model_copy(update={"systems": m.systems.model_copy(
        update={"heating_setback_c": 17.8, "cooling_setup_c": 27.8})})
    sb = run("house", m)
    assert sb.heating_need_kwh < base.heating_need_kwh
    assert sb.cooling_need_kwh < base.cooling_need_kwh
    assert any("setback hours are unsourced" in w for w in sb.warnings)


def test_home_setback_hours():
    from backend.analysis.physics.zone.model import home_setback_on
    # hour-ending stamps on Monday 2024-01-08: hour 1 (00-01) is set back, hour 8 (07-08) is not,
    # hour 10 (09-10) is (weekday away), hour 20 (19-20) is not, hour 23 (22-23) is
    stamps = np.array(["2024-01-08T01:00", "2024-01-08T08:00", "2024-01-08T10:00",
                       "2024-01-08T20:00", "2024-01-08T23:00"], dtype="datetime64[m]")
    assert home_setback_on(stamps).tolist() == [True, False, True, False, True]
    # Saturday 2024-01-13 at 09-10: not set back (weekend daytime)
    assert home_setback_on(np.array(["2024-01-13T10:00"], dtype="datetime64[m]")).tolist() == [False]
