"""HVAC-01 to HVAC-08: worked examples and the checks of physics 02 section 9."""
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.analysis.physics.systems.hvac import (apply_distribution_efficiency, cooling_eir_modifier,
                                                   cooling_power_single_stage, cop47_from_hspf, eer_a_from_seer,
                                                   fuel_heating_energy, heat_pump_heating_power,
                                                   heating_eir_modifier, ieer_from_points, rating_to_cop,
                                                   seasonal_cooling_energy)

ROOT = Path(__file__).resolve().parents[5]
WEATHER = ROOT / "specs" / "examples" / "weather"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("network access in a unit test")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _temps(name):
    return np.genfromtxt(WEATHER / name, delimiter=",", skip_header=1, usecols=1)


# ---------- HVAC-01 ----------

@pytest.mark.parametrize("value,metric,expected", [
    (10, "SEER", 2.931), (13, "SEER", 3.810), (14, "SEER", 4.103), (16, "SEER", 4.689),
    (8.2, "HSPF", 2.403), (11, "EER", 3.224),
    (12.35, "SEER2", 3.810), (13.30, "SEER2", 4.103), (15.20, "SEER2", 4.689), (6.97, "HSPF2", 2.403),
])
def test_hvac01_rating_to_cop(value, metric, expected):
    assert rating_to_cop(value, metric) == pytest.approx(expected, abs=6e-4)


def test_hvac01_divide_route_and_passthrough():
    assert rating_to_cop(13, "SEER") == pytest.approx(13 / 3.412142, rel=1e-5)
    assert rating_to_cop(0.8, "AFUE") == 0.8
    assert rating_to_cop(13, "SEER2", ducted=False) == pytest.approx(rating_to_cop(13, "SEER"))
    with pytest.raises(ValueError):
        rating_to_cop(1, "XYZ")


# ---------- HVAC-02 ----------

@pytest.mark.parametrize("t,f", [(20, 0.6592), (25, 0.7384), (27.78, 0.7973), (30, 0.8520), (35, 1.0),
                                 (40, 1.1825), (45, 1.3993)])
def test_hvac02_curve_values(t, f):
    assert float(cooling_eir_modifier(t)) == pytest.approx(f, abs=1e-4)


@pytest.mark.parametrize("seer,eer_a,s14,s13", [(13, 10.91, 11.1, 11.04), (14, 11.75, 12.0, 11.77),
                                                (15, 12.59, 13.0, 12.50), (16, 13.43, 14.0, 13.23)])
def test_hvac02_eer_a_table_and_second_sources(seer, eer_a, s14, s13):
    got = eer_a_from_seer(seer)
    assert got == pytest.approx(eer_a, abs=0.005)
    assert abs(got / s14 - 1) < 0.05 and abs(got / s13 - 1) < 0.05


# ---------- HVAC-03 ----------

def test_hvac03_worked_example_both_routes():
    eer_a = eer_a_from_seer(10)
    cop_a = eer_a * 0.293071
    assert eer_a == pytest.approx(8.392, abs=5e-4)
    assert cop_a == pytest.approx(2.4596, abs=5e-4)
    assert float(cooling_eir_modifier(38)) == pytest.approx(1.1053, abs=1e-4)
    p = cooling_power_single_stage(5000, 38, cop_a, 8000, 0.10)
    assert p == pytest.approx(2334.6, rel=1e-3)
    plf = 1 - 0.10 * (1 - 5000 / 8000)
    assert plf == pytest.approx(0.9625)
    assert 5000 * (1 / cop_a) * float(cooling_eir_modifier(38)) / plf == pytest.approx(p, rel=1e-12)


@pytest.mark.parametrize("seer", [10, 13, 16])
def test_hvac03_self_consistency_returns_seer(seer):
    cop_a = eer_a_from_seer(seer) * 0.293071
    p = cooling_power_single_stage(4000, 27.78, cop_a, 8000, 0.10)
    assert 4000 / p / 0.293071 == pytest.approx(seer, abs=1e-6)


def test_hvac03_zero_load_and_arrays():
    out = cooling_power_single_stage(np.array([0.0, 1000.0]), np.array([30.0, 30.0]), 3.0, 2000.0)
    assert out[0] == 0.0 and out[1] > 0


# ---------- HVAC-04 ----------

def test_hvac04_worked_example():
    assert seasonal_cooling_energy(3000, 10) == pytest.approx(1023.6, abs=0.05)
    assert seasonal_cooling_energy(3000, 16) == pytest.approx(639.8, abs=0.05)


@pytest.mark.parametrize("name", ["typical_year_hourly.csv", "typical_year_hourly_houston.csv"])
def test_hvac03_against_hvac04_within_20_percent(name):
    t = _temps(name)
    load = np.maximum(t - 18.0, 0.0) * 600.0                      # synthetic cooling load, W
    seer = 13.0
    cop_a = eer_a_from_seer(seer) * 0.293071
    hourly = cooling_power_single_stage(load, np.clip(t, 18, 46), cop_a, 1.2 * load.max()).sum() / 1000
    seasonal = seasonal_cooling_energy(load.sum() / 1000, seer)
    assert abs(hourly / seasonal - 1) < 0.20


# ---------- HVAC-05 ----------

@pytest.mark.parametrize("t,f,cop", [(-5, 1.3902, 2.410), (0, 1.2120, 2.764), (5, 1.0720, 3.125),
                                     (8.33, 1.0, 3.350), (12, 0.9403, 3.563), (15, 0.9069, 3.694)])
def test_hvac05_curve_and_cop(t, f, cop):
    assert float(heating_eir_modifier(t)) == pytest.approx(f, abs=1e-4)
    assert 3.35 / float(heating_eir_modifier(t)) == pytest.approx(cop, abs=1e-3)


def test_hvac05_worked_example_and_fallback():
    assert cop47_from_hspf(8.2) == pytest.approx(3.35)
    assert cop47_from_hspf(7.95) == pytest.approx(3.20)
    assert cop47_from_hspf(9.0) is None and cop47_from_hspf(7.0) is None
    assert heat_pump_heating_power(4000, 5, cop_47=3.35) == pytest.approx(1280.0, abs=0.1)
    assert heat_pump_heating_power(4000, 5, hspf=8.2) == pytest.approx(1280.0, abs=0.1)
    seasonal = heat_pump_heating_power(4000, 5, hspf=9.5)          # outside 7.7 to 8.5: seasonal line
    assert seasonal == pytest.approx(4000 / (9.5 * 0.293071))
    assert 4000 / (8.2 * 0.293071) == pytest.approx(1664.5, abs=0.1)
    with pytest.raises(ValueError):
        heat_pump_heating_power(4000, 5)


@pytest.mark.parametrize("name", ["typical_year_hourly.csv", "typical_year_hourly_houston.csv"])
def test_hvac05_hourly_below_seasonal(name):
    t = _temps(name)
    load = np.maximum(18.0 - t, 0.0) * 300.0
    hourly = heat_pump_heating_power(load, t, cop_47=3.35).sum()
    seasonal = load.sum() / (8.2 * 0.293071)
    assert hourly < seasonal


# ---------- HVAC-06, 07, 08 ----------

def test_hvac06_worked_example():
    assert fuel_heating_energy(10000, 0.80) == pytest.approx(12500)
    assert fuel_heating_energy(10000, 0.95) == pytest.approx(10526, abs=0.5)


def test_hvac07_worked_example():
    assert ieer_from_points(11.0, 12.5, 13.4, 12.8) == pytest.approx(12.722, abs=1e-3)
    e_old = seasonal_cooling_energy(20000, 11.2)
    e_new = seasonal_cooling_energy(20000, 14.8)
    assert e_old == pytest.approx(6093, abs=0.5)
    assert e_new == pytest.approx(4611, abs=0.5)
    assert e_old - e_new == pytest.approx(1482, abs=1)


def test_hvac08_worked_example():
    dse = 1 - 0.20 * 2 / 3
    assert dse == pytest.approx(0.867, abs=5e-4)
    assert apply_distribution_efficiency(5000, 0.867) == pytest.approx(5767, abs=0.5)
