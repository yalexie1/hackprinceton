"""A19 acceptance tests (workplan 4.2): measure PV_ROOF from a SolarDesign."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.schema import BaselineResult, Flag, MeasureResult, PropertyBundle, Ranged, SolarDesign, Tariff
from backend.analysis.measures.pv import (
    evaluate_pv, export_regime, hourly_load_from_monthly, propagate, pv_bill_savings,
    self_consumption_fraction)

ROOT = Path(__file__).resolve().parents[5]
EXAMPLES = ROOT / "specs" / "examples"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", deny)


def _fixture(name: str):
    bundle = PropertyBundle.model_validate_json((EXAMPLES / name / "property_bundle.json").read_text())
    baseline = BaselineResult.model_validate_json((EXAMPLES / name / "baseline_result.json").read_text())
    measures = json.loads((EXAMPLES / name / "measures.json").read_text())
    pv = MeasureResult.model_validate(next(m for m in measures if m["measure_id"] == "PV_ROOF"))
    return bundle, baseline, pv


def _flag(key="roof.structure", status="likely_ok", msg="ok") -> Flag:
    return Flag(key=key, status=status, message=msg)


def _design(e_pv=(8000.0, 8000.0, 8000.0), f_sc=None, structural=None, electrical=None,
            panels=10) -> SolarDesign:
    return SolarDesign(system_kw_dc=4.3, panel_count=panels, panels=[],
                       annual_kwh=Ranged(low=e_pv[0], expected=e_pv[1], high=e_pv[2], unit="kWh"),
                       self_consumption_fraction=f_sc,
                       electrical=electrical or _flag("electrical.service"),
                       structural=structural or _flag())


def _baseline(e_load=10000.0, monthly=None) -> BaselineResult:
    r = lambda v, u: Ranged(low=v, expected=v, high=v, unit=u)
    return BaselineResult.model_validate({
        "annual": {"electricity_kwh": r(e_load, "kWh"), "gas_kwh": r(0, "kWh"),
                   "cost_usd": r(0, "USD"), "co2_kg": r(0, "kg")},
        "end_use_kwh": {}, "monthly_electricity_kwh": monthly or [e_load / 12] * 12,
        "monthly_gas_kwh": [0.0] * 12, "peak_cooling_w": 0, "peak_heating_w": 0})


def _tariff(utility="Southern California Edison", price=0.30, export=None, regime=None) -> Tariff:
    return Tariff(utility=utility, electricity_usd_per_kwh=price, export_usd_per_kwh=export,
                  export_regime=regime, source="test", retrieved="2026-11-14")


# ---------------------------------------------------------------- TAR-03 formulas

def test_tar03_example_a_net_billing():
    assert pv_bill_savings("net_billing", 8000, 10000, 0.45, 0.30, 0.06) == pytest.approx(1344.0)
    m = evaluate_pv(_design(f_sc=0.45), _baseline(), _tariff(export=0.06, regime="net_billing"),
                    state="CA")
    assert m.applicable and m.savings.cost_usd.expected == pytest.approx(1344.0)
    assert m.params["export_value_usd"]["expected"] == pytest.approx(264.0)


def test_tar03_example_b_net_metering_with_surplus():
    t = _tariff(utility="LADWP", price=0.30, regime="net_metering")
    assert evaluate_pv(_design(), _baseline(), t).savings.cost_usd.expected == pytest.approx(2400.0)
    m = evaluate_pv(_design(e_pv=(12000.0,) * 3), _baseline(), t, state="CA")
    assert m.savings.cost_usd.expected == pytest.approx(3000.0)
    assert m.params["surplus_kwh"] == pytest.approx(2000.0)
    assert any("surplus credit is valued at zero" in w for w in m.warnings)
    assert any("steady-state annual netting" in w for w in m.warnings)


def test_production_above_consumption_is_valued_at_export_price_hourly():
    # 24-hour pattern repeated: load 1 kWh every hour, PV 3 kWh in hours 10..13.
    load = np.ones(8760)
    pv = np.zeros(8760)
    for d in range(365):
        pv[d * 24 + 10:d * 24 + 14] = 3.0
    assert self_consumption_fraction(load, pv) == pytest.approx(1 / 3)
    e_pv, e_load = float(pv.sum()), float(load.sum())
    m = evaluate_pv(_design(e_pv=(e_pv,) * 3), _baseline(e_load), _tariff(export=0.05,
                    regime="net_billing"), hourly_pv_kwh=pv, hourly_load_kwh=load, state="CA")
    self_kwh, exp_kwh = e_pv / 3, e_pv * 2 / 3
    assert m.savings.cost_usd.expected == pytest.approx(self_kwh * 0.30 + exp_kwh * 0.05, abs=0.01)
    assert m.params["exported_kwh"] == pytest.approx(exp_kwh, abs=0.1)
    assert m.solar.self_consumption_fraction == pytest.approx(1 / 3, abs=1e-4)


def test_hourly_pv_without_load_uses_monthly_flat_load():
    load = hourly_load_from_monthly([31.0 * 24] * 12)
    assert load.shape == (8760,) and load.sum() == pytest.approx(31 * 24 * 12)
    assert load[0] == pytest.approx(1.0) and load[24 * 40] == pytest.approx(31 / 28)
    pv = np.tile(np.r_[np.zeros(10), np.full(4, 3.0), np.zeros(10)], 365)
    m = evaluate_pv(_design(e_pv=(float(pv.sum()),) * 3), _baseline(8760.0), _tariff(
        export=0.05, regime="net_billing"), hourly_pv_kwh=pv, state="CA")
    assert m.params["self_consumption_source"] == "hourly_pv_monthly_load"
    assert 0 < m.params["self_consumption_fraction"] < 1


# ---------------------------------------------------------------- Texas: no export price

def test_texas_no_export_price_low_end_zero_and_all_from_self_consumption():
    t = _tariff(utility="Retail electric provider not known (CenterPoint)", price=0.09,
                regime="none")
    m = evaluate_pv(_design(f_sc=0.6), _baseline(), t, state="TX")
    ev = m.params["export_value_usd"]
    assert ev["low"] == 0.0 and ev["expected"] == 0.0 and ev["high"] == 0.0
    assert m.savings.cost_usd.expected == pytest.approx(0.6 * 8000 * 0.09)
    assert any("all savings come from self-consumption" in w for w in m.warnings)


def test_texas_with_buyback_rate_export_value_is_range_from_zero():
    t = _tariff(utility="CenterPoint Energy Houston Electric", price=0.09, regime="none")
    m = evaluate_pv(_design(f_sc=0.6), _baseline(), t, state="TX",
                    export_price=Ranged(low=0.04, expected=0.04, high=0.04, unit="USD/kWh"))
    ev = m.params["export_value_usd"]
    assert ev["low"] == 0.0 and ev["expected"] == pytest.approx(0.4 * 8000 * 0.04) == ev["high"]
    assert m.params["export_usd_per_kwh"]["low"] == 0.0
    assert m.savings.cost_usd.low == pytest.approx(0.6 * 8000 * 0.09)
    # a tariff export price in Texas is also treated as an assumption with low 0
    m2 = evaluate_pv(_design(f_sc=0.6), _baseline(), t.model_copy(update={"export_usd_per_kwh": 0.04}))
    assert m2.params["export_value_usd"]["low"] == 0.0
    assert m2.params["export_value_usd"]["expected"] > 0


# ---------------------------------------------------------------- skips

def test_structural_blocked_flag_gives_not_applicable_with_reason():
    blocked = _flag("roof.structure", "blocked", "Roof deck is rotten; it cannot carry an array.")
    m = evaluate_pv(_design(structural=blocked), _baseline(), _tariff(regime="net_billing"))
    assert m.applicable is False and m.savings is None
    assert "roof.structure" in m.not_applicable_reason
    assert "Roof deck is rotten" in m.not_applicable_reason
    assert m.flags == [blocked]


def test_other_blocked_flags_also_skip():
    m = evaluate_pv(_design(electrical=_flag("electrical.service", "blocked", "No room for a breaker.")),
                    _baseline(), _tariff(regime="net_billing"))
    assert not m.applicable and "electrical.service" in m.not_applicable_reason
    m = evaluate_pv(_design(), _baseline(), _tariff(regime="net_billing"),
                    flags=[_flag("roof.age", "blocked", "Roof must be replaced first.")])
    assert not m.applicable and "Roof must be replaced first." in m.not_applicable_reason


def test_existing_solar_is_already_done():
    m = evaluate_pv(_design(), _baseline(), _tariff(regime="net_billing"), existing_solar=True)
    assert not m.applicable and m.not_applicable_reason.startswith("Already done")


def test_empty_design_is_not_applicable():
    m = evaluate_pv(_design(e_pv=(0.0, 0.0, 0.0), panels=0), _baseline(), _tariff(regime="net_billing"))
    assert not m.applicable


# ---------------------------------------------------------------- utility and regime

def test_unconfirmed_utility_is_valued_by_export_regime_with_warning():
    t = _tariff(utility="CA state average (RES)", price=0.3258, regime="net_metering")
    regime, warns = export_regime(t)
    assert regime == "net_metering" and any("unconfirmed" in w for w in warns)
    m = evaluate_pv(_design(), _baseline(), t, state="CA")
    assert m.savings.cost_usd.expected == pytest.approx(8000 * 0.3258)
    assert any("unconfirmed" in w for w in m.warnings)


def test_named_utilities_are_confirmed():
    for u, r in [("LADWP (electricity), SoCalGas (gas)", "net_metering"),
                 ("Southern California Edison", "net_billing"),
                 ("Retail electric provider not known (CenterPoint Energy Houston Electric delivery area)", "none")]:
        regime, warns = export_regime(_tariff(utility=u))
        assert regime == r and not any("unconfirmed" in w for w in warns)


def test_missing_export_price_in_net_billing_is_zero_never_retail():
    m = evaluate_pv(_design(f_sc=0.5), _baseline(), _tariff(regime="net_billing"))
    assert m.params["export_usd_per_kwh"]["expected"] == 0.0
    assert m.savings.cost_usd.expected == pytest.approx(0.5 * 8000 * 0.30)
    assert any("never substituted" in w for w in m.warnings)


def test_no_regime_and_no_named_utility_falls_back_to_net_billing():
    regime, warns = export_regime(_tariff(utility="unknown"))
    assert regime == "net_billing" and len(warns) == 2


def test_unknown_self_consumption_is_an_assumed_range():
    m = evaluate_pv(_design(e_pv=(7000.0, 8000.0, 9000.0)), _baseline(), _tariff(export=0.05,
                    regime="net_billing"))
    assert m.params["self_consumption_source"] == "assumed_range"
    c = m.savings.cost_usd
    assert c.low < c.expected < c.high


# ---------------------------------------------------------------- UNC-02 and ranges

def test_propagate_unc02_worked_example():
    f = lambda x: x["a"] * x["b"]
    lo, ex, hi = propagate(f, {"a": (8000, 10000, 13000), "b": (0.118, 0.133, 0.160)})
    assert (lo, ex, hi) == pytest.approx((1024.6, 1330.0, 1811.8), abs=0.1)
    lo, _, hi = propagate(f, {"a": (8000, 10000, 13000), "b": (0.118, 0.133, 0.160)},
                          {"a": "g", "b": "g"})
    assert (lo, hi) == pytest.approx((914.0, 1999.0), abs=0.5)


def test_price_range_widens_cost_and_ranges_are_ordered():
    m = evaluate_pv(_design(e_pv=(7500.0, 8000.0, 8400.0), f_sc=0.5), _baseline(),
                    _tariff(export=0.05, regime="net_billing"), state="CA",
                    electricity_price=Ranged(low=0.25, expected=0.30, high=0.35, unit="USD/kWh"))
    s = m.savings
    for r in (s.electricity_kwh, s.cost_usd, s.co2_kg, s.co2_nonbaseload_kg):
        assert r.low <= r.expected <= r.high
    assert s.cost_usd.low < 0.5 * 7500 * 0.30 + 0.5 * 7500 * 0.05
    MeasureResult.model_validate(m.model_dump())


# ---------------------------------------------------------------- fixtures

@pytest.mark.parametrize("name", ["house", "office", "office_houston"])
def test_fixture_expected_values_reproduced(name):
    bundle, baseline, fx = _fixture(name)
    design = fx.solar
    m = evaluate_pv(design, baseline, bundle.tariff, state=bundle.summary.state)
    assert m.applicable and m.measure_id == "PV_ROOF"
    s, f = m.savings, fx.savings
    assert s.electricity_kwh.expected == pytest.approx(f.electricity_kwh.expected, abs=0.01)
    assert s.cost_usd.expected == pytest.approx(f.cost_usd.expected, abs=0.02)
    assert s.co2_kg.expected == pytest.approx(f.co2_kg.expected, abs=0.05)
    assert s.co2_nonbaseload_kg.expected == pytest.approx(f.co2_nonbaseload_kg.expected, abs=0.05)
    assert m.title == fx.title
    assert {fl.key for fl in m.flags} == {fl.key for fl in fx.flags}
    assert not any("unconfirmed" in w for w in m.warnings)


def test_house_fixture_low_and_high_from_production_and_price_range():
    # the house is priced at the EIA California average with a registry range (data-integration
    # 5.1c), so the fixture's band combines the production range and the price range
    bundle, baseline, fx = _fixture("house")
    model = json.loads((EXAMPLES / "house" / "building_model.json").read_text())
    price = Ranged(**next(a["value"] for a in model["assumptions"]
                          if a["key"] == "tariff.electricity_usd_per_kwh"))
    m = evaluate_pv(fx.solar, baseline, bundle.tariff, state="CA", electricity_price=price)
    assert m.savings.cost_usd.low == pytest.approx(fx.savings.cost_usd.low, abs=0.02)
    assert m.savings.cost_usd.high == pytest.approx(fx.savings.cost_usd.high, abs=0.02)
    assert any("service upgrade" in w or "not in the installed cost" in w for w in m.warnings)


def test_houston_fixture_export_value_is_zero_range():
    bundle, baseline, fx = _fixture("office_houston")
    m = evaluate_pv(fx.solar, baseline, bundle.tariff, state="TX")
    assert m.params["export_regime"] == "none"
    assert m.params["export_value_usd"]["low"] == 0.0
    assert m.params["egrid_subregion"] == "ERCT"
