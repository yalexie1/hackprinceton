"""A18 acceptance (specs/workplan.md 4.2 row A18): HVAC_HP, HVAC_RTU, LGT_LED on the three
golden fixtures, registered in a test Registry and evaluated with a fake simulate. No network."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.schema import BaselineResult, BuildingModel, EnergyUse, Flag, MeasureResult, PropertyBundle, Ranged
from backend.analysis.measures import systems
from backend.analysis.measures.engine import Registry, apply_measure, evaluate, skip_reason
from backend.analysis.measures.systems import heat_pump, lighting, rooftop

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
FIXTURES = ("house", "office", "office_houston")
ROLE = {"house": "owner_occupier", "office": "landlord", "office_houston": "landlord"}


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
    data = json.loads((EX / name / "measures.json").read_text())
    items = data if isinstance(data, list) else data.get("measures", data)
    return next(m for m in items if m["measure_id"] == mid)


def unconfirmed_office():
    """The LA office with nothing confirming a rooftop unit: both golden offices now have
    Vexcel-counted units on the D16 structure, so HVAC-00's other branch needs this variant."""
    b, m = bundle("office"), model("office")
    s0 = b.vexcel.structures[0]
    attrs = {k: v for k, v in s0.attributes.items() if k != "roof-objects.ac-unit.count"}
    vex = b.vexcel.model_copy(update={"structures": [s0.model_copy(update={"attributes": attrs})]
                                      + list(b.vexcel.structures[1:])})
    flag = Flag(key="hvac.system_type", status="unknown", message="No rooftop unit confirmed.")
    planes = [p.model_copy(update={"obstruction_counts": {k: v for k, v in p.obstruction_counts.items()
                                                          if k != "ac-unit"}}) for p in m.roof_planes]
    m = m.model_copy(update={"systems": m.systems.model_copy(update={"hvac_type": "unknown"}),
                             "assumptions": [a for a in m.assumptions if a.key != "hvac.system_type"],
                             "flags": [f for f in m.flags if f.key != "hvac.rtu_service"] + [flag],
                             "roof_planes": planes})
    return b.model_copy(update={"vexcel": vex}), m


def R(x: float, unit: str) -> Ranged:
    return Ranged(low=0.9 * x, expected=x, high=1.2 * x, unit=unit)


class FakeSimulate:
    """Heating over the heating efficiency (gas or electric), cooling over the cooling COP,
    lighting from the power density."""

    def __call__(self, b: PropertyBundle, m: BuildingModel) -> BaselineResult:
        s = m.systems
        floor = sum(z.floor_area_m2 for z in m.zones)
        light = s.lighting_w_per_m2.expected * floor * 3.0
        heat_need, cool_need = 40.0 * floor, 30.0 * floor
        heat = heat_need / s.heating_efficiency.expected
        cool = cool_need / s.cooling_cop.expected
        gas = heat if s.heating_fuel == "gas" else 0.0
        elec = light + cool + (0.0 if s.heating_fuel == "gas" else heat)
        annual = EnergyUse(electricity_kwh=R(elec, "kWh"), gas_kwh=R(gas, "kWh"),
                           cost_usd=R(0.25 * elec + 0.05 * gas, "USD"), co2_kg=R(0.2 * elec + 0.18 * gas, "kg"))
        return BaselineResult(annual=annual, end_use_kwh={"heating": heat, "cooling": cool, "lighting": light},
                              monthly_electricity_kwh=[elec / 12] * 12, monthly_gas_kwh=[gas / 12] * 12,
                              peak_cooling_w=8000.0, peak_heating_w=6000.0)


@pytest.fixture
def reg() -> Registry:
    r = Registry()
    for mid, (check, change, describe, formula_ids) in systems.MEASURES.items():
        r.register(mid, change=change, describe=describe, check=check, formula_ids=formula_ids)
    return r


def run(reg, name, mid, role=None):
    return evaluate(bundle(name), model(name), mid, role or ROLE[name], FakeSimulate(), registry=reg,
                    simulate_formula_ids=("ZON-04",))


# ---------------------------------------------------------------- registration

def test_export_dict_registers_all_three(reg):
    assert set(systems.MEASURES) == {"HVAC_HP", "HVAC_RTU", "LGT_LED"}
    for mid, entry in systems.MEASURES.items():
        assert len(entry) == 4 and all(callable(f) for f in entry[:3]) and entry[3]
    assert set(reg.registered()) == {"HVAC_HP", "HVAC_RTU", "LGT_LED"}


# ---------------------------------------------------------------- applicability (acceptance)

def test_hvac_hp_applies_to_house_not_office(reg):
    house = run(reg, "house", "HVAC_HP")
    assert house.applicable and house.savings is not None
    assert house.savings.gas_kwh.expected > 0 and house.savings.electricity_kwh.expected < 0
    for name in ("office", "office_houston"):
        r = run(reg, name, "HVAC_HP")
        assert not r.applicable and skip_reason(r) == "flow"
        # the engine words the place ("an office property"); the fixture says "an office suite"
        assert r.not_applicable_reason.startswith("Home-flow measure (SPEC.md section 6.2)")


def test_hvac_rtu_reverse_and_hvac00(reg):
    house = run(reg, "house", "HVAC_RTU")
    assert not house.applicable and skip_reason(house) == "flow"
    assert house.not_applicable_reason      # #330: the house fixture evaluates only the home flow, so it has no RTU card
    b, m = unconfirmed_office()                             # no rooftop unit confirmed: HVAC-00
    la = evaluate(b, m, "HVAC_RTU", "landlord", FakeSimulate(), registry=reg, simulate_formula_ids=("ZON-04",))
    assert not la.applicable and skip_reason(la) == "feasibility"
    assert rooftop.NOT_CONFIRMED in la.not_applicable_reason.lower()
    la = run(reg, "office", "HVAC_RTU")                     # Culver Connect: Vexcel counts three
    assert la.applicable and la.params["units"] == 3
    hou = run(reg, "office_houston", "HVAC_RTU")
    assert hou.applicable and hou.savings.electricity_kwh.expected > 0
    assert hou.savings.gas_kwh.expected == 0


def test_hvac_rtu_describe_guard_when_unconfirmed():
    b, m = unconfirmed_office()
    card = rooftop.describe(b, m, rooftop.change(b, m), FakeSimulate()(b, m), {})
    assert not card.applicable and card.not_applicable_reason == rooftop.NOT_CONFIRMED
    assert [f.key for f in card.flags] == ["hvac.system_type"]


@pytest.mark.parametrize("name", ("house", "office_houston"))   # the LA office is already LED
def test_lgt_led_lowers_lighting_power(reg, name):
    b, m = bundle(name), model(name)
    changed = apply_measure(b, m, "LGT_LED", reg)
    old, new = m.systems.lighting_w_per_m2, changed.systems.lighting_w_per_m2
    assert new.expected < old.expected and new.low <= old.low and new.high <= old.high
    r = run(reg, name, "LGT_LED")
    assert r.applicable and r.savings.electricity_kwh.expected > 0


def test_lgt_led_office_target_and_home_factor():
    b, m = bundle("office"), model("office")
    assert lighting.change(b, m).systems.lighting_w_per_m2.expected == 6.5
    assert lighting.home_led_factor(0.30) == pytest.approx(0.6051, abs=1e-4)     # LGT-01 worked example
    assert lighting.home_led_factor() == pytest.approx(0.4851, abs=1e-4)
    hb, hm = bundle("house"), model("house")
    new = lighting.change(hb, hm).systems.lighting_w_per_m2
    assert new.expected == pytest.approx(hm.systems.lighting_w_per_m2.expected * 0.4851, rel=1e-3)


# ---------------------------------------------------------------- no mutation

@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("mid", ["HVAC_HP", "HVAC_RTU", "LGT_LED"])
def test_input_model_not_mutated(name, mid):
    check, change, describe, _ = systems.MEASURES[mid]
    b, m = bundle(name), model(name)
    frozen = m.model_dump_json()
    check(b, m)
    changed = change(b, m)
    assert changed is not m and isinstance(changed, BuildingModel)
    describe(b, m, changed, FakeSimulate()(b, m), {"role": ROLE[name], "desks_requested": None})
    assert m.model_dump_json() == frozen


def test_heat_pump_change_fields():
    b, m = bundle("house"), model("house")
    s = heat_pump.change(b, m).systems
    assert s.hvac_type == "heat_pump" and s.heating_fuel == "electricity"
    assert s.cooling_rating_metric == "SEER2" and s.heating_rating_metric == "HSPF2"
    assert s.heating_cop_47f == 3.6 and s.compressor_type == "two_stage"
    assert s.cooling_cop.expected == pytest.approx(16.5 / 0.95 * 0.293071, rel=1e-4)        # HVAC-01
    assert s.heating_efficiency.expected == pytest.approx(8.2 / 0.85 * 0.293071, rel=1e-4)  # HVAC-01
    assert s.lighting_w_per_m2 == m.systems.lighting_w_per_m2       # touches only what it names


# ---------------------------------------------------------------- already done

def test_already_done():
    b, m = bundle("house"), model("house")
    hp = m.model_copy(deep=True)
    hp.systems.hvac_type = "heat_pump"
    assert heat_pump.check(b, hp)[0] == "already_done"
    hb, hm = bundle("office_houston"), model("office_houston")
    new = rooftop.change(hb, hm)
    assert rooftop.check(hb, new)[0] == "already_done"
    assert lighting.check(hb, lighting.change(hb, hm))[0] == "already_done"


# ---------------------------------------------------------------- cards against the fixtures

CARDS = [("house", "HVAC_HP"), ("house", "LGT_LED"),
         ("office_houston", "LGT_LED"), ("office_houston", "HVAC_RTU")]


def test_lgt_led_already_done_on_the_la_office(reg):
    """Culver Connect: the 2024 renovation fitted LED (the request's override), as the fixture says."""
    r = run(reg, "office", "LGT_LED")
    assert not r.applicable and skip_reason(r) == "already_done"
    assert r.not_applicable_reason == fixture_card("office", "LGT_LED")["not_applicable_reason"]


@pytest.mark.parametrize("name,mid", CARDS)
def test_card_matches_fixture(reg, name, mid):
    r = run(reg, name, mid)
    fx = fixture_card(name, mid)
    assert MeasureResult.model_validate(r.model_dump()) == r
    assert r.applicable == fx["applicable"]
    # pricing keys included; the heat pump's capacity is sized from the simulated peak, which the
    # fixture has from the real simulation and this test from FakeSimulate (#330)
    skip = {"capacity_tons"} if mid == "HVAC_HP" else set()
    assert {k: v for k, v in r.params.items() if k not in skip} == {k: v for k, v in fx["params"].items() if k not in skip}
    assert r.title == fx["title"]
    ids = set(r.formula_ids) - {"HVAC-04"}      # HVAC-04: physics 02 HVAC_HP evaluation, not in the fixture
    assert ids <= set(fx["formula_ids"]), ids - set(fx["formula_ids"])
    a, fa = r.anchors[0], fx["anchors"][0]
    assert a.room_id == fa["room_id"] or name == "house" and mid == "LGT_LED"
    if (name, mid) in {("office", "LGT_LED"), ("office_houston", "HVAC_RTU")}:
        assert a.model_dump() == fa
        assert r.description == fx["description"]
    if (name, mid) == ("office_houston", "HVAC_RTU"):
        assert [e.model_dump() for e in r.evidence] == fx["evidence"]
        assert [f.key for f in r.flags] == [f["key"] for f in fx["flags"]]
    if fx["warnings"]:
        assert fx["warnings"][0] in r.warnings


def test_pricing_quantities_present(reg):
    assert run(reg, "house", "HVAC_HP").params["capacity_tons"] == 2.5   # FakeSimulate's 8 kW peak x 1.2, in half tons
    assert run(reg, "house", "LGT_LED").params["lamps"] == 30
    assert run(reg, "office", "HVAC_RTU").params["units"] == 3
    assert run(reg, "office_houston", "HVAC_RTU").params["capacity_tons"] == 30
