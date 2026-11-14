"""A21 acceptance (specs/workplan.md 4.2 row A21): HVAC_ECON is offered to the office fixtures
only, HVAC_DUCT and DHW_HPWH to the house only; the input model is never mutated; cards validate
and match the fixtures. Fixtures only, a fake simulate, no network."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.schema import BaselineResult, BuildingModel, EnergyUse, MeasureResult, PropertyBundle, Ranged
from backend.analysis.measures.engine import CATALOGUE, Registry, applicability, evaluate
from backend.analysis.measures.hvac_dhw import (DUCT_REASON, ECONOMIZER_LIMIT_C, HPWH_UEF, MEASURES,
                                                duct_change, econ_change, econ_check, hpwh_change,
                                                hpwh_check, rooftop_units)

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
FIXTURES = ("house", "office", "office_houston")
OWNER = {"house": "owner_occupier", "office": "landlord", "office_houston": "landlord"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


def bundle(name: str) -> PropertyBundle:
    return PropertyBundle.model_validate_json((EX / name / "property_bundle.json").read_text())


def model(name: str) -> BuildingModel:
    return BuildingModel.model_validate_json((EX / name / "building_model.json").read_text())


def fixture_card(name: str, mid: str) -> dict:
    return next(m for m in json.loads((EX / name / "measures.json").read_text()) if m["measure_id"] == mid)


def R(x: float, unit: str) -> Ranged:
    return Ranged(low=0.9 * x, expected=x, high=1.1 * x, unit=unit)


def fake_simulate(b: PropertyBundle, m: BuildingModel) -> BaselineResult:
    """Cooling falls by a fifth with an economizer; hot water = 2564 kWh / UEF in its fuel."""
    s = m.systems
    cooling = 10000.0 * (0.8 if s.has_economizer else 1.0)
    dhw = 2564.0 / s.dhw_efficiency.expected
    elec = cooling + (dhw if s.dhw_fuel == "electricity" else 0.0)
    gas = dhw if s.dhw_fuel == "gas" else 0.0
    annual = EnergyUse(electricity_kwh=R(elec, "kWh"), gas_kwh=R(gas, "kWh"),
                       cost_usd=R(0.3 * elec + 0.05 * gas, "USD"), co2_kg=R(0.3 * elec + 0.18 * gas, "kg"))
    return BaselineResult(annual=annual, end_use_kwh={"cooling": cooling, "water_heating": dhw},
                          monthly_electricity_kwh=[elec / 12] * 12, monthly_gas_kwh=[gas / 12] * 12,
                          peak_cooling_w=0.0, peak_heating_w=0.0)


@pytest.fixture
def registry() -> Registry:
    reg = Registry()
    for mid, (check, change, describe, formula_ids) in MEASURES.items():
        reg.register(mid, check=check, change=change, describe=describe, formula_ids=formula_ids)
    return reg


def run(reg, name, mid, b=None, m=None, role=None):
    b = b or bundle(name)
    m = m or model(name)
    frozen = m.model_dump_json()
    out = evaluate(b, m, mid, role or OWNER[name], fake_simulate, registry=reg,
                   simulate_formula_ids=("ZON-04",))
    assert m.model_dump_json() == frozen, "input model mutated"
    MeasureResult.model_validate(out.model_dump())
    return out


# ---------------------------------------------------------------- export and registration

def test_export_dict_shape():
    assert set(MEASURES) == {"HVAC_ECON", "HVAC_DUCT", "DHW_HPWH"}
    for mid, (check, change, describe, formula_ids) in MEASURES.items():
        assert mid in CATALOGUE
        assert callable(check) and callable(change) and callable(describe)
        assert formula_ids and all(isinstance(f, str) for f in formula_ids)


# ---------------------------------------------------------------- offered by property type

@pytest.mark.parametrize("name", FIXTURES)
def test_offered_by_property_type(registry, name):
    b, m = bundle(name), model(name)
    for mid in MEASURES:
        skip, _ = applicability(b, m, mid, OWNER[name], registry)
        offered = skip is None or skip.reason != "flow"
        want = (name != "house") if mid == "HVAC_ECON" else (name == "house")
        assert offered == want, (name, mid, skip)


# ---------------------------------------------------------------- HVAC_ECON

def test_econ_office_not_confirmed(registry):
    out = run(registry, "office", "HVAC_ECON")
    assert not out.applicable and out.params["skip_reason"] == "feasibility"
    assert out.not_applicable_reason == ("No packaged rooftop unit confirmed: flag hvac.system_type is "
                                         "unknown (physics 02 HVAC-00).")
    assert "no packaged rooftop unit confirmed" in out.not_applicable_reason.lower()


def test_econ_houston_matches_fixture(registry):
    out = run(registry, "office_houston", "HVAC_ECON")
    fx = fixture_card("office_houston", "HVAC_ECON")
    assert out.applicable and out.savings is not None
    assert out.savings.electricity_kwh.expected == pytest.approx(2000.0)
    assert out.title == fx["title"]
    assert out.params == fx["params"]
    assert out.description.startswith(fx["description"])
    assert [a.model_dump() for a in out.anchors] == fx["anchors"]
    assert [e.model_dump() for e in out.evidence] == fx["evidence"]
    assert out.flags == MeasureResult.model_validate(fx).flags
    analysis_ids = [f for f in fx["formula_ids"] if not f.startswith(("ECO", "EMI"))]
    assert out.formula_ids == analysis_ids
    for w in fx["warnings"]:
        assert w in out.warnings


def test_econ_tenant_rejected_by_role(registry):
    out = run(registry, "office_houston", "HVAC_ECON", role="tenant")
    assert not out.applicable and out.params["skip_reason"] == "role"


def test_econ_already_done_and_change():
    m = model("office_houston")
    frozen = m.model_dump_json()
    changed = econ_change(bundle("office_houston"), m)
    assert m.model_dump_json() == frozen and changed is not m
    assert changed.systems.has_economizer is True
    assert changed.systems.economizer_limit_c == ECONOMIZER_LIMIT_C
    reason, _ = econ_check(bundle("office_houston"), changed)
    assert reason == "already_done"


def test_econ_units_fallbacks():
    b, m = bundle("office_houston"), model("office_houston")
    assert rooftop_units(b, m)[0] == 2
    b2 = b.model_copy(update={"vexcel": None})
    assert rooftop_units(b2, m)[0] == 2            # from roof_planes obstruction_counts
    assert rooftop_units(bundle("office"), model("office")) == (None, None)


# ---------------------------------------------------------------- HVAC_DUCT

def test_duct_house_not_supported(registry):
    out = run(registry, "house", "HVAC_DUCT")
    fx = fixture_card("house", "HVAC_DUCT")
    assert not out.applicable and out.params["skip_reason"] == "not_supported"
    assert out.not_applicable_reason == fx["not_applicable_reason"] == DUCT_REASON
    assert out.title == fx["title"]


def test_duct_change_does_not_mutate():
    m = model("house")
    frozen = m.model_dump_json()
    changed = duct_change(bundle("house"), m)
    assert changed is not m and m.model_dump_json() == frozen


# ---------------------------------------------------------------- DHW_HPWH

def test_hpwh_house_blocked(registry):
    out = run(registry, "house", "DHW_HPWH")
    fx = fixture_card("house", "DHW_HPWH")
    assert not out.applicable and out.params["skip_reason"] == "feasibility"
    assert out.not_applicable_reason.startswith("Blocked by feasibility flag dhw.space")
    assert fx["not_applicable_reason"].startswith("Blocked by feasibility flag dhw.space")
    assert out.title == fx["title"]


def _house_garage_heater() -> BuildingModel:
    m = model("house")
    m.flags = [f for f in m.flags if f.key != "dhw.space"]
    m.systems.dhw_location = "garage"
    return m


def test_hpwh_applicable_when_heater_outside(registry):
    m = _house_garage_heater()
    out = run(registry, "house", "DHW_HPWH", m=m)
    assert out.applicable
    assert out.params["units"] == 1 and out.params["uef_new"] == HPWH_UEF.expected
    assert out.params["uef_old"] == pytest.approx(0.58) and out.params["fuel_old"] == "gas"
    assert {"DHW-03", "DEF-07"} <= set(out.formula_ids)
    # gas saving 2564/0.58, electricity penalty 2564/2.30
    assert out.savings.gas_kwh.expected == pytest.approx(2564 / 0.58)
    assert out.savings.electricity_kwh.expected == pytest.approx(-2564 / 2.30)
    assert any("Fuel switch" in w for w in out.warnings)
    assert any("outside the conditioned space" in w for w in out.warnings)


def test_hpwh_change_and_checks():
    b, m = bundle("house"), _house_garage_heater()
    frozen = m.model_dump_json()
    changed = hpwh_change(b, m)
    assert m.model_dump_json() == frozen
    s = changed.systems
    assert (s.dhw_type, s.dhw_fuel, s.dhw_efficiency.expected) == ("heat_pump", "electricity", 2.30)
    assert hpwh_check(b, changed)[0] == "already_done"
    inside = _house_garage_heater()
    inside.systems.dhw_location = "conditioned"
    assert hpwh_check(b, inside)[0] == "feasibility"
