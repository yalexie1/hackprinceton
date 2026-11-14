"""DHW-01 to DHW-03, LGT-01 to LGT-03 and the DEF-09 schedules: worked examples."""
import socket

import numpy as np
import pytest

from backend.analysis.physics.systems.dhw import (daily_hot_water_gallons, daily_hot_water_volume, dhw_energy,
                                                  mains_temperature, mains_temperature_f)
from backend.analysis.physics.systems.constants import HOME_SHARES, OFFICE_SCHEDULES
from backend.analysis.physics.systems.loads import (calendar_from_stamps, default_calendar, end_use_profiles,
                                                    equivalent_full_load_hours, home_appliance_energy,
                                                    home_lighting_base, home_lighting_factor,
                                                    home_lighting_hourly_kwh, home_misc_energy,
                                                    home_occupants_default, internal_gains, lighting_power,
                                                    occupant_presence, office_occupants_default,
                                                    plug_density_scale)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("network access in a unit test")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ---------- DHW-01 ----------

@pytest.mark.parametrize("day,f_route,si", [(15, 17.991, 17.990), (105, 22.192, 22.192), (196, 28.647, 28.647),
                                            (288, 24.434, 24.433)])
def test_dhw01_si_against_f_form(day, f_route, si):
    got = mains_temperature(day, 20.0, 17.0)
    via_f = (mains_temperature_f(day, 20.0 * 1.8 + 32, 17.0 * 1.8) - 32) / 1.8
    assert got == pytest.approx(si, abs=1e-3)
    assert via_f == pytest.approx(f_route, abs=1e-3)
    assert abs(got - via_f) < 0.002


def test_dhw01_annual_mean():
    days = np.arange(1, 366)
    assert mains_temperature(days, 20.0, 17.0).mean() == pytest.approx(23.335, abs=0.01)


# ---------- DHW-02, DHW-03 ----------

def test_dhw02_worked_example():
    g = daily_hot_water_gallons(3, 21.11)
    assert g == pytest.approx(52.83, abs=5e-3)
    assert daily_hot_water_volume(3, 21.11) == pytest.approx(0.2000, abs=5e-5)
    assert (43.33 - 21.11) / (51.67 - 21.11) == pytest.approx(0.7271, abs=1e-4)


def test_dhw03_worked_example():
    e = dhw_energy(0.2000, 21.11, 1.0)
    assert e["delivered_kwh"] == pytest.approx(7.025, abs=1e-3)
    year = e["delivered_kwh"] * 365
    assert year == pytest.approx(2564, abs=1)
    for uef, expected in [(0.5803, 4418), (0.9207, 2785), (2.30, 1115), (3.50, 733)]:
        assert year / uef == pytest.approx(expected, rel=1e-3)
    assert dhw_energy(0.2, 21.11, 0.58)["input_kwh"] == pytest.approx(7.025 / 0.58, rel=1e-3)
    # imperial route: 52.83 gal x 8.2619 lb/gal x 0.9984 Btu/(lb F) x 55 F
    assert 52.83 * 8.2619 * 0.9984 * 55 / 3412.1416 == pytest.approx(7.024, abs=1e-3)


# ---------- DEF-09 schedules ----------

def test_def09_home_shares_sum_to_one():
    for row in HOME_SHARES.values():
        assert sum(row) == pytest.approx(1.0, abs=1e-3)
    for sched in OFFICE_SCHEDULES.values():
        for row in sched.values():
            assert len(row) == 24 and all(0 <= v <= 1 for v in row)


def test_default_calendar_day_counts():
    cal = default_calendar()
    days = np.unique(cal.day_index)
    first = np.unique(cal.day_index, return_index=True)[1]
    counts = np.bincount(cal.day_type[first], minlength=3)
    assert len(days) == 365 and tuple(counts) == (260, 52, 53)


def test_calendar_hour_end_convention():
    stamps = np.array(["2024-01-01T01:00", "2024-01-01T02:00", "2024-01-06T10:00"], dtype="datetime64[h]")
    cal = calendar_from_stamps(stamps, "hour_end")
    assert list(cal.hour) == [0, 1, 9]
    assert list(cal.day_type) == [0, 0, 1]      # Monday, Monday, Saturday


# ---------- LGT-01 ----------

def test_lgt01_office_equivalent_hours_and_examples():
    cal = default_calendar()
    h = equivalent_full_load_hours("lighting", cal)
    assert h == pytest.approx(2939, rel=1e-3)
    for lpd, kwh in [(19.48, 28628), (10.76, 15813), (6.5, 9552)]:
        assert lpd * 500 * h / 1000 == pytest.approx(kwh, rel=1e-3)
    p = lighting_power(10.76, 500, 0.9)
    assert p == pytest.approx(10.76 * 500 * 0.9)


def test_lgt01_home_examples():
    assert home_lighting_base(150) == pytest.approx(1209, rel=1e-3)
    led = home_lighting_factor(0, 0, 1, 0, 0.30)
    assert led == pytest.approx(0.6051, abs=1e-4)
    assert home_lighting_base(150) * led == pytest.approx(732, abs=1)
    assert home_lighting_base(150) * (1 - led) == pytest.approx(478, abs=1)
    assert home_lighting_factor(0, 0, 1, 0, 15 / 90) == pytest.approx(0.4851, abs=1e-4)   # ER_led = 15/90


def test_lgt01_home_hourly_spread_keeps_annual_and_winter_peak():
    cal = default_calendar()
    h = home_lighting_hourly_kwh(1209.0, cal)
    assert h.sum() == pytest.approx(1209.0)
    jan = h[cal.month == 1].sum() / 31
    jun = h[cal.month == 6].sum() / 30
    assert jan / jun == pytest.approx(1.19 / 0.80, rel=1e-6)


# ---------- LGT-02 ----------

def test_lgt02_examples():
    cal = default_calendar()
    h = equivalent_full_load_hours("equipment", cal)
    assert h == pytest.approx(4487, rel=1e-3)
    assert 10.76 * 500 * h / 1000 == pytest.approx(24140, rel=1e-3)
    assert home_misc_energy(3, 150) == pytest.approx(2241, abs=1)
    appl = home_appliance_energy(3)
    assert appl["refrigerator"] == 434 and appl["dryer"] == pytest.approx(538.2 + 3 * 179.4)


def test_lgt02_plug_scaling_limits():
    assert plug_density_scale(500 / 18.59, 500) == pytest.approx(1.0)
    assert plug_density_scale(1, 500) == 0.5
    assert plug_density_scale(1000, 500) == 2.0


# ---------- LGT-03 ----------

def test_lgt03_worked_example():
    n = home_occupants_default(3)
    assert n == pytest.approx(2.64, abs=5e-3)
    occ = 0.082 * 16.5
    assert occ == pytest.approx(1.353, abs=1e-3)
    g = internal_gains(0.0, 0.0, n, occ, "home")
    assert g["sensible_w"] == pytest.approx(230, abs=0.5)
    assert g["latent_w"] == pytest.approx(172, abs=0.5)
    assert office_occupants_default(500) == pytest.approx(500 / 18.59)


def test_lgt03_presence_peak_and_office_fractions():
    cal = default_calendar()
    home = occupant_presence("home", cal)
    assert home.max() == pytest.approx(0.082 * 16.5)
    assert home.sum() / 365 == pytest.approx(16.5, rel=1e-3)
    office = occupant_presence("office", cal)
    assert office.max() == 0.95
    vacant = occupant_presence("office", cal, vacant=True)
    assert vacant.sum() == 0


def test_office_gains_at_a_weekday_hour():
    cal = default_calendar()
    eu = end_use_profiles(occupancy_schedule="office", floor_area_m2=500, cal=cal, lpd_w_m2=10.76, ppd_w_m2=10.76,
                          occupants=40)
    i = int(np.flatnonzero((cal.day_type == 0) & (cal.hour == 9))[0])     # schedule hour 10
    scale = plug_density_scale(40, 500)
    expected = 10.76 * 500 * 0.9 + 10.76 * scale * 500 * 0.9 + 40 * 0.95 * 73.3
    assert eu.sensible_gain_w[i] == pytest.approx(expected)
    assert eu.latent_gain_w[i] == pytest.approx(40 * 0.95 * 58.6)
    assert eu.occupants_source == "systems"


def test_office_without_occupants_uses_schedule_default_unscaled():
    cal = default_calendar()
    eu = end_use_profiles(occupancy_schedule="office", floor_area_m2=500, cal=cal, lpd_w_m2=10.76, ppd_w_m2=10.76,
                          occupants=None)
    assert eu.occupants == pytest.approx(500 / 18.59)
    assert eu.occupants_source == "schedule_default"
    assert eu.plug_kwh.sum() == pytest.approx(10.76 * 500 * 4487 / 1000, rel=1e-3)


def test_home_end_uses_and_bedroom_fallbacks():
    cal = default_calendar()
    eu = end_use_profiles(occupancy_schedule="home", floor_area_m2=150, cal=cal, lpd_w_m2=7, ppd_w_m2=5,
                          occupants=None, bedrooms=3)
    assert eu.lighting_kwh.sum() == pytest.approx(home_lighting_base(150))
    assert eu.plug_kwh.sum() == pytest.approx(2241, abs=1)
    assert eu.appliances_kwh.sum() == pytest.approx(sum(home_appliance_energy(3).values()))
    assert eu.occupants == pytest.approx(2.64, abs=5e-3)
    inferred = end_use_profiles(occupancy_schedule="home", floor_area_m2=150, cal=cal, lpd_w_m2=7, ppd_w_m2=5,
                                occupants=2.64, bedrooms=None)
    assert inferred.bedrooms == pytest.approx(3.0, abs=0.01) and inferred.warnings
    neither = end_use_profiles(occupancy_schedule="home", floor_area_m2=150, cal=cal, lpd_w_m2=7, ppd_w_m2=5,
                               occupants=None, bedrooms=None)
    assert neither.bedrooms == 3 and neither.warnings
