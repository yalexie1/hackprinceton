"""A6 acceptance (workplan row A6): calibration of the golden models to twelve monthly bills (MV-06).

The simulation is the door's own baseline in fast mode (no low/high re-runs), passed in as a callable,
exactly as `run_baseline` would pass it. Synthetic bills come from the model itself with known
perturbed assumptions, so the truth is known. Uses the golden house (Los Angeles) and the Houston
office; the Los Angeles office is being rebuilt and is not used.
"""
import socket
import time
from pathlib import Path

import numpy as np
import pytest

from backend.analysis import api
from backend.analysis.physics.calibration import CANDIDATES, calibrate_to_bills
from backend.schema import PropertyBundle, Ranged, UtilityBills

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("network access in a unit test")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def fast_simulate(bundle, model):
    token = api._FAST.set(True)
    try:
        return api._simulate_baseline(bundle, model)
    finally:
        api._FAST.reset(token)


class Site:
    def __init__(self, name, overrides=None):
        raw = PropertyBundle.model_validate_json((EX / name / "property_bundle.json").read_text())
        self.bundle = api._resolved(raw)
        observed, flags = api.observe_interior(self.bundle)
        self.model = api.build_building_model(self.bundle, observed, flags, overrides or {})
        hours, _, _ = api._climate(self.bundle)
        self.temps = np.asarray(hours.temp_c, dtype=float)

    def ranged(self, key):
        return next(a.value for a in self.model.assumptions if a.key == key)

    def bills_from(self, truth, elec_extra=0.0, gas=True, model=None):
        m = model or self.model
        for k, v in truth.items():
            m = api.set_assumption(m, k, v, "user")
        r = fast_simulate(self.bundle, m)
        return UtilityBills(electricity_kwh=list(np.asarray(r.monthly_electricity_kwh) + elec_extra),
                            gas_kwh=list(r.monthly_gas_kwh) if gas else None)

    def calibrate(self, bills, model=None, **kw):
        return calibrate_to_bills(self.bundle, model or self.model, bills, fast_simulate, api.set_assumption,
                                  self.temps, **kw)


@pytest.fixture(scope="module")
def house():
    return Site("house", {"occupancy.count": 3})


@pytest.fixture(scope="module")
def office():
    return Site("office_houston")


def _assert_in_ranges(site, result):
    """Every proposed or applied value lies inside the ORIGINAL low-high range of its assumption."""
    for key, value in result.values.items():
        r = site.ranged(key)
        assert r.low - 1e-9 <= value <= r.high + 1e-9, (key, value, r)
    for mv in result.moves:
        assert mv.low - 1e-9 <= mv.after <= mv.high + 1e-9
    original = {a.key: a for a in site.model.assumptions}
    for a in result.model.assumptions:
        if a.key in result.values and isinstance(a.value, Ranged):
            r = original[a.key].value
            assert r.low - 1e-9 <= a.value.expected <= r.high + 1e-9


# ---------------------------------------------------------------- recovery

def test_recovers_identifiable_inputs_on_the_house(house):
    """One input per signature (base electricity, gas heating, cooling): each is recovered."""
    truth = {"plug.ppd": 6.5, "setpoint.heating": 21.0, "hvac.cooling_rating": 11.0}
    res = house.calibrate(house.bills_from(truth), keys=list(truth))
    assert res.calibrated_to_bills and res.baseline.calibrated_to_bills
    for key, value in truth.items():
        r = house.ranged(key)
        assert abs(res.values[key] - value) <= 0.10 * (r.high - r.low), (key, res.values[key], value)
    for f in ("electricity", "gas"):
        assert abs(res.after[f].nmbe) < 0.01 and res.after[f].cv_rmse < 0.02
    _assert_in_ranges(house, res)


def test_recovers_with_every_candidate_on_the_house(house):
    """All candidates free: the bills are matched, and every perturbed input moves towards its truth
    (inputs with the same signature share the correction, so exact recovery is not expected)."""
    truth = {"plug.ppd": 6.5, "setpoint.heating": 20.9, "infiltration.ach50": 22.0, "hvac.cooling_rating": 11.0}
    t0 = time.perf_counter()
    res = house.calibrate(house.bills_from(truth))
    elapsed = time.perf_counter() - t0
    assert elapsed < 60.0, f"calibration took {elapsed:.1f} s"
    assert res.calibrated_to_bills
    assert set(res.fuels) == {"electricity", "gas"}
    for f in res.fuels:
        assert res.before[f].cv_rmse > 0.05 and res.after[f].cv_rmse < 0.03
    for key, value in truth.items():
        before = house.ranged(key).expected
        assert abs(res.values[key] - value) < abs(before - value), (key, res.values[key], value)
    _assert_in_ranges(house, res)


def test_office_gas_and_electric(office):
    truth = {"plug.ppd": 9.5, "occupancy.count": 44.0, "setpoint.cooling": 23.5, "hvac.cooling_rating": 9.0}
    res = office.calibrate(office.bills_from(truth))
    assert res.calibrated_to_bills
    assert set(res.after) == {"electricity", "gas"}
    assert res.before["gas"].cv_rmse > 0.15 and res.after["gas"].cv_rmse < 0.05
    for key, value in truth.items():
        before = office.ranged(key).expected
        assert abs(res.values[key] - value) < abs(before - value), key
    # zero summer gas is what this office's model does too: no vacancy warning
    assert not any("far below the model's seasonal pattern" in w for w in res.warnings)
    _assert_in_ranges(office, res)


# ---------------------------------------------------------------- impossible bills

def test_impossible_bills_stay_uncalibrated_with_a_clear_warning(house):
    """350 kWh a month that no in-range input can explain (an electric vehicle, a pool pump)."""
    res = house.calibrate(house.bills_from({}, elec_extra=350.0))
    assert not res.calibrated_to_bills and not res.baseline.calibrated_to_bills
    assert res.model is house.model                                  # nothing is applied
    assert res.after["electricity"].nmbe > 0.05                       # still below the bills
    text = " ".join(res.warnings)
    assert "cannot be brought within" in text and "outside its range" in text
    assert "electric vehicle" in text and "base part" in text
    assert "left as it was" in text
    assert any(m.at_bound for m in res.moves)
    _assert_in_ranges(house, res)


@pytest.mark.parametrize("scale", [0.3, 3.0])
def test_never_outside_the_ranges(house, scale):
    r = fast_simulate(house.bundle, house.model)
    bills = UtilityBills(electricity_kwh=[x * scale for x in r.monthly_electricity_kwh],
                         gas_kwh=[x * scale for x in r.monthly_gas_kwh])
    res = house.calibrate(bills)
    assert not res.calibrated_to_bills
    _assert_in_ranges(house, res)
    # even when asked to apply the proposal, the applied values stay inside the ranges
    forced = house.calibrate(bills, apply_when_uncalibrated=True)
    assert not forced.calibrated_to_bills and forced.model is not house.model
    _assert_in_ranges(house, forced)
    assert any("MV-04 NOT met" in (e.note or "") for a in forced.model.assumptions for e in a.evidence)


def test_gas_bills_against_a_model_without_gas(office):
    electric = api.set_assumption(office.model, "hvac.heating_fuel", "electricity", "user")
    assert sum(fast_simulate(office.bundle, electric).monthly_gas_kwh) == 0
    gas = [3000, 1500, 500, 100, 0, 0, 0, 0, 0, 100, 800, 2000]
    r = fast_simulate(office.bundle, electric)
    res = office.calibrate(UtilityBills(electricity_kwh=r.monthly_electricity_kwh, gas_kwh=gas), model=electric)
    assert not res.calibrated_to_bills
    assert any("model burns no gas" in w for w in res.warnings)


# ---------------------------------------------------------------- one fuel, provenance, determinism

def test_electricity_only_does_not_rewrite_the_gas_side(house):
    truth = {"plug.ppd": 6.5, "hvac.cooling_rating": 11.0}
    res = house.calibrate(house.bills_from(truth, gas=False))
    assert res.fuels == ["electricity"] and res.calibrated_to_bills
    for key in ("setpoint.heating", "infiltration.ach50"):          # move gas more than electricity
        assert key not in res.values
        assert any(s.startswith(key) and "acts mainly on gas" in s for s in res.screened_out)
    assert "hvac.heating_rating" not in res.values                  # moves gas only
    assert any(s.startswith("hvac.heating_rating") for s in res.screened_out)
    assert any("No gas bills were given" in w for w in res.warnings)


def test_calibrated_values_carry_evidence_and_the_original_range(house):
    truth = {"plug.ppd": 6.5, "setpoint.heating": 21.0, "hvac.cooling_rating": 11.0}
    res = house.calibrate(house.bills_from(truth), keys=list(truth))
    before = {a.key: a for a in house.model.assumptions}
    after = {a.key: a for a in res.model.assumptions}
    for key, value in res.values.items():
        a = after[key]
        assert a.source == "measured" and a.confidence == pytest.approx(0.7)
        assert a.value.expected == pytest.approx(value) and a.value.low == a.value.high
        ev = a.evidence[-1]
        assert ev.kind == "user" and "bills.electricity_kwh" in ev.ref and "bills.gas_kwh" in ev.ref
        r = before[key].value
        assert "Inferred, not measured" in ev.note and f"{r.low:.3g}" in ev.note and "CV(RMSE)" in ev.note
        assert a.evidence[:-1] == before[key].evidence
    for key in set(before) - set(res.values):
        assert after[key] == before[key]
    move = next(m for m in res.moves if m.key == "plug.ppd")
    assert move.before == 5.0 and move.drives == "base load" and "raised" in move.reason
    # the calibrated model, simulated again by the door, gives the baseline the result reports
    again = fast_simulate(house.bundle, res.model)
    assert again.monthly_electricity_kwh == pytest.approx(res.baseline.monthly_electricity_kwh)


def test_deterministic(house):
    bills = house.bills_from({"plug.ppd": 4.0, "setpoint.cooling": 25.0})
    a, b = house.calibrate(bills), house.calibrate(bills)
    assert a.values == b.values and a.warnings == b.warnings and a.simulations == b.simulations
    assert a.after["electricity"] == b.after["electricity"]


def test_savings_uncertainty_on_a_calibrated_model(house):
    res = house.calibrate(house.bills_from({"plug.ppd": 6.5, "hvac.cooling_rating": 11.0}))
    annual = sum(res.simulated_after["gas"])
    u = res.savings_uncertainty("gas", 0.2 * annual)
    assert u.acceptable and 0 < u.fsu_68 < u.fsu_90 < 0.5
    assert u.half_width_90_kwh > u.half_width_68_kwh > 0
    bad = house.calibrate(house.bills_from({}, elec_extra=350.0))
    assert not bad.savings_uncertainty("electricity", 1000.0).acceptable


def test_candidates_reach_the_simulation():
    """Every candidate key is one set_assumption carries into Systems (physics 02 section 12)."""
    from backend.analysis.model.registry.registry import systems_from_assumptions  # noqa: F401
    import inspect
    src = inspect.getsource(systems_from_assumptions)
    for key in CANDIDATES:
        assert f'"{key}"' in src, key


def test_bad_bills_are_rejected(house):
    with pytest.raises(ValueError):
        house.calibrate(UtilityBills(electricity_kwh=[100.0] * 11))
    with pytest.raises(ValueError):
        house.calibrate(UtilityBills(electricity_kwh=[100.0] * 11 + [-5.0]))
