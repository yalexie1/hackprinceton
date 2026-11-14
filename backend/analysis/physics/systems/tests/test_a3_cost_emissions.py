"""TAR-01, TAR-04, TAR-05, EMI-01 to EMI-03 and UNC-02: worked examples of physics 04."""
import socket

import pytest

from backend.analysis.physics.systems.cost import (annual_bill_flat, annual_co2_kg, bill_savings, egrid_subregion,
                                                   gas_emission_factor, grid_emission_factor, kwh_to_mj,
                                                   kwh_to_therms, mmbtu_to_kwh, therms_to_kwh,
                                                   usd_per_therm_to_usd_per_kwh)
from backend.analysis.physics.systems.uncertainty import propagate, quadrature


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("network access in a unit test")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_tar01_flat_bill_and_savings():
    monthly = [900, 800, 750, 700, 800, 1100, 1400, 1500, 1200, 900, 800, 850]
    assert sum(monthly) == 11700
    assert annual_bill_flat(monthly, 0.25, 10) == pytest.approx(3045.00)
    assert bill_savings(11700, 11700 * 0.9, 0.25) == pytest.approx(292.50)


def test_tar04_gas_bill_and_tar05_conversions():
    kwh = therms_to_kwh(500)
    assert kwh == pytest.approx(14653.55, abs=0.005)
    assert kwh_to_mj(kwh) / 500 == pytest.approx(105.505585, rel=1e-8)
    assert kwh_to_therms(kwh) == pytest.approx(500)
    p = usd_per_therm_to_usd_per_kwh(1.50)
    assert p == pytest.approx(0.051182, abs=1e-6)
    assert annual_bill_flat([kwh / 12] * 12, p, 5) == pytest.approx(810.00)
    assert mmbtu_to_kwh(1) == pytest.approx(293.07107)


def test_emi01_factors_and_examples():
    assert grid_emission_factor("CAMX") == pytest.approx(0.19504, abs=1e-5)
    assert grid_emission_factor("ERCT") == pytest.approx(0.33413, abs=1e-5)
    assert grid_emission_factor("CAMX", "nonbaseload") == pytest.approx(0.43599, abs=1e-5)
    assert grid_emission_factor("ERCT", "nonbaseload") == pytest.approx(0.56586, abs=1e-5)
    assert grid_emission_factor("US") == pytest.approx(0.3497, abs=1e-4)
    assert 10000 * grid_emission_factor("ERCT") == pytest.approx(3341, abs=1)
    assert 10000 * grid_emission_factor("ERCT", "nonbaseload") == pytest.approx(5659, abs=1)
    assert 10000 * grid_emission_factor("CAMX") == pytest.approx(1950, abs=1)
    assert 10000 * grid_emission_factor("CAMX", "nonbaseload") == pytest.approx(4360, abs=1)


def test_emi01_subregion_lookup():
    assert egrid_subregion(zip_code="90038") == "CAMX"
    assert egrid_subregion(zip_code="77027") == "ERCT"
    assert egrid_subregion(state="CA") == "CAMX"
    assert egrid_subregion(state="TX") == "ERCT"
    assert egrid_subregion(state="NY") == "US"


def test_emi02_gas_and_emi03_fuel_switch():
    assert gas_emission_factor() == pytest.approx(0.18123, abs=1e-5)
    gas = therms_to_kwh(500)
    assert gas * gas_emission_factor() == pytest.approx(2655.7, abs=0.1)
    assert annual_co2_kg(0, gas, "ERCT") - annual_co2_kg(4500, 0, "ERCT") == pytest.approx(1152.1, abs=0.1)


def test_unc02_worked_example_independent_and_correlated():
    a = (8000, 10000, 13000)
    b = (0.118, 0.133, 0.160)
    f = lambda p: {"y": p["a"] * p["b"]}  # noqa: E731
    res, rows = propagate(f, {"a": a[1], "b": b[1]}, {"a": (a[0], a[2]), "b": (b[0], b[2])})
    lo, y0, hi = res["y"]
    assert y0 == pytest.approx(1330.0)
    assert lo == pytest.approx(1024.6, abs=0.1)
    assert hi == pytest.approx(1811.8, abs=0.1)
    swing = {r.key: r.swing for r in rows}
    assert swing["a"] == pytest.approx(665) and swing["b"] == pytest.approx(420)
    lo_c, _, hi_c = propagate(f, {"a": a[1], "b": b[1]}, {"a": (a[0], a[2]), "b": (b[0], b[2])},
                              {"a": "g", "b": "g"})[0]["y"]
    assert lo_c == pytest.approx(914, abs=0.5) and hi_c == pytest.approx(1999, abs=0.5)


def test_unc02_non_monotonic_input_goes_to_its_side():
    lo, hi = quadrature(10.0, {"x": (12.0, 13.0)})
    assert lo == 10.0 and hi == 13.0
