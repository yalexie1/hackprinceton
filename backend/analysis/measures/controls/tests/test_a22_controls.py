"""A22 acceptance (specs/workplan.md 4.2, row A22): LGT_CTRL and PLUG_MGMT are offered to the
office fixtures only, CTRL_TSTAT to both flows; a tenant may do all three; the input model is
not mutated; cards validate and match the fixture params, anchors and formula ids where shown.
Fixtures only, a fake simulate, no network."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.schema import BaselineResult, BuildingModel, EnergyUse, MeasureResult, PropertyBundle, Ranged
from backend.analysis.measures.controls import MEASURES, plug_saving_share
from backend.analysis.measures.engine import Registry, evaluate, skip_reason

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
FIXTURES = ("house", "office", "office_houston")
OFFICES = ("office", "office_houston")
MIDS = ("LGT_CTRL", "PLUG_MGMT", "CTRL_TSTAT")
ROLES = ("owner_occupier", "landlord", "tenant")
# formula ids that come from the simulation or from finance, not from the measure card
NOT_OURS = {"EMI-01", "ECO-07", "ECO-12b", "ECO-13", "INC-40",
            # the LA office fixture is real output: the simulation's and A24/A25's formula ids
            "ZON-01", "ZON-04", "ENV-03", "INF-01", "HVAC-01", "LGT-03", "TAR-01", "UNC-02",
            "COST-01", "COST-02", "ECO-05", "ECO-06", "ECO-09", "ECO-10", "ECO-11"}


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
    """Lighting and plug from the densities; heating and cooling fall with a deeper setback."""
    s, area = m.systems, sum(z.floor_area_m2 for z in m.zones)
    light = s.lighting_w_per_m2.expected * area * 2.939
    plug = s.plug_w_per_m2.expected * area * 4.487
    heat = 20.0 * area * (1 - 0.05 * (21.0 - (s.heating_setback_c or 21.0)))
    cool = 15.0 * area * (1 - 0.05 * ((s.cooling_setup_c or 24.0) - 24.0))
    elec = light + plug + cool
    annual = EnergyUse(electricity_kwh=R(elec, "kWh"), gas_kwh=R(heat, "kWh"),
                       cost_usd=R(0.2 * elec + 0.05 * heat, "USD"), co2_kg=R(0.3 * elec + 0.18 * heat, "kg"))
    return BaselineResult(annual=annual, end_use_kwh={"lighting": light, "plug": plug},
                          monthly_electricity_kwh=[elec / 12] * 12, monthly_gas_kwh=[heat / 12] * 12,
                          peak_cooling_w=0.0, peak_heating_w=0.0)


@pytest.fixture
def registry() -> Registry:
    reg = Registry()
    for mid, (check, change, describe, fids) in MEASURES.items():
        reg.register(mid, change=change, describe=describe, check=check, formula_ids=fids)
    return reg


def run(name: str, mid: str, role: str, registry: Registry) -> MeasureResult:
    return evaluate(bundle(name), model(name), mid, role, fake_simulate, registry=registry)


# ---------------------------------------------------------------- acceptance

def test_registration_dict_shape():
    assert set(MEASURES) == set(MIDS)
    for check, change, describe, fids in MEASURES.values():
        assert callable(check) and callable(change) and callable(describe) and fids


@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("mid", ("LGT_CTRL", "PLUG_MGMT"))
def test_lighting_and_plug_offered_to_offices_only(name, mid, registry):
    r = run(name, mid, "owner_occupier", registry)
    if name in OFFICES:
        assert r.applicable, r.not_applicable_reason
        assert r.savings.electricity_kwh.expected > 0
    else:
        assert not r.applicable and skip_reason(r) == "flow"


@pytest.mark.parametrize("name", FIXTURES)
def test_thermostat_offered_to_both_flows(name, registry):
    """Offered in both flows; the house already has a smart thermostat (fixture: already_done)."""
    r = run(name, "CTRL_TSTAT", "owner_occupier", registry)
    if name == "house":
        assert skip_reason(r) == "already_done"
        assert r.not_applicable_reason == fixture_card("house", "CTRL_TSTAT")["not_applicable_reason"]
        # without the thermostat reading, the home measure is off by default (LETO_HOME_TSTAT)
        m = model("house")
        m.assumptions = [a for a in m.assumptions if a.key != "hvac.thermostat_type"]
        r2 = evaluate(bundle("house"), m, "CTRL_TSTAT", "owner_occupier", fake_simulate, registry=registry)
        assert not r2.applicable and skip_reason(r2) == "not_supported"
    else:
        assert r.applicable


@pytest.mark.parametrize("name", OFFICES)
@pytest.mark.parametrize("mid", MIDS)
def test_tenant_may_do_all_three(name, mid, registry):
    for role in ROLES:
        assert run(name, mid, role, registry).applicable


@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("mid", MIDS)
def test_input_model_not_mutated(name, mid):
    check, change, describe, _ = MEASURES[mid]
    b, m = bundle(name), model(name)
    frozen = m.model_dump_json()
    check(b, m)
    changed = change(b, m)
    describe(b, m, changed, fake_simulate(b, m), {"role": "tenant", "desks_requested": None})
    assert m.model_dump_json() == frozen
    assert changed is not m


# ---------------------------------------------------------------- what each change touches

def _systems_diff(a: BuildingModel, b: BuildingModel) -> set[str]:
    da, db = a.systems.model_dump(), b.systems.model_dump()
    return {k for k in da if da[k] != db[k]}


@pytest.mark.parametrize("name", OFFICES)
def test_changes_touch_only_named_fields(name):
    b, m = bundle(name), model(name)
    for mid, fields in (("LGT_CTRL", {"lighting_w_per_m2"}), ("PLUG_MGMT", {"plug_w_per_m2"})):
        changed = MEASURES[mid][1](b, m)
        assert _systems_diff(m, changed) == fields
        assert changed.surfaces == m.surfaces and changed.zones == m.zones
    lpd = MEASURES["LGT_CTRL"][1](b, m).systems.lighting_w_per_m2
    assert lpd.expected == pytest.approx(m.systems.lighting_w_per_m2.expected * 0.8)
    assert lpd.low <= lpd.expected <= lpd.high


def test_thermostat_change_sets_setbacks_on_a_home():
    b, m = bundle("house"), model("house")
    changed = MEASURES["CTRL_TSTAT"][1](b, m)
    assert _systems_diff(m, changed) == {"heating_setback_c", "cooling_setup_c"}
    assert changed.systems.heating_setback_c < m.systems.heating_setpoint_c.expected
    assert changed.systems.cooling_setup_c > m.systems.cooling_setpoint_c.expected


def test_change_marks_the_measure_done():
    """The changed model reads as already done, so the measure is not applied twice."""
    for name, mid in (("office", "LGT_CTRL"), ("office", "PLUG_MGMT"), ("office", "CTRL_TSTAT")):
        check, change, _, _ = MEASURES[mid]
        b = bundle(name)
        assert check(b, model(name)) is None
        assert check(b, change(b, model(name)))[0] == "already_done"


def test_plug_saving_share_from_def09():
    # floor 0.25: weekday hours 1-6 (0.15 each), Saturday 13 hours and other days at 0.05
    assert plug_saving_share(0.25) == pytest.approx((260 * 0.9 + 52 * 0.65 + 53 * 1.2) / 4487.0, rel=1e-3)
    assert plug_saving_share(0.15) > plug_saving_share(0.25) > plug_saving_share(0.35) > 0
    assert plug_saving_share(0.25, "office_vacant") == pytest.approx(0.05 / 0.30)


# ---------------------------------------------------------------- cards against the fixtures

@pytest.mark.parametrize("name", OFFICES)
@pytest.mark.parametrize("mid", ("PLUG_MGMT", "CTRL_TSTAT"))
def test_cards_match_fixture(name, mid, registry):
    r = run(name, mid, "tenant", registry)
    MeasureResult.model_validate(r.model_dump())
    fx = fixture_card(name, mid)
    assert r.title == fx["title"]
    for k, v in fx["params"].items():
        assert r.params[k] == v, k
    assert set(fx["formula_ids"]) - NOT_OURS <= set(r.formula_ids)
    got = {(a.room_id, a.pano_id, a.label) for a in r.anchors}
    assert {(a["room_id"], a["pano_id"], a["label"]) for a in fx["anchors"]} <= got
    for w in fx["warnings"]:
        if w.startswith("useful life of"):        # added by pricing (A24), not by the card
            continue
        assert any(x.startswith(w.split(".")[0]) for x in r.warnings), w
    assert any("unsourced" in w for w in r.warnings)


@pytest.mark.parametrize("name,n", (("office", 10), ("office_houston", 4)))
def test_thermostat_count_matches_fixture_cost(name, n, registry):
    """Finance prices `thermostats`; the fixtures' cost_source says x 10 and x 4."""
    r = run(name, "CTRL_TSTAT", "tenant", registry)
    assert r.params["thermostats"] == n
    assert f"x {n}" in fixture_card(name, "CTRL_TSTAT")["finance"]["cost_source"]
    assert r.savings.electricity_kwh.expected == 0   # setback equals DEF-08: fixture no_savings


@pytest.mark.parametrize("name,fixtures", (("office", 289), ("office_houston", 112)))
def test_lighting_control_card(name, fixtures, registry):
    r = run(name, "LGT_CTRL", "tenant", registry)
    assert r.params["fixtures"] == fixtures      # finance's quantity key; luminaire counts of LGT_LED
    assert r.anchors and r.formula_ids[:2] == ["LGT-01", "LGT-03"]
    assert any("unsourced" in w for w in r.warnings)


def test_home_thermostat_is_off_by_default_and_switches_back_on(monkeypatch, registry):
    """CTRL_TSTAT on homes is off unless LETO_HOME_TSTAT is truthy; offices are unaffected."""
    m = model("house")
    m.assumptions = [a for a in m.assumptions if a.key != "hvac.thermostat_type"]
    monkeypatch.delenv("LETO_HOME_TSTAT", raising=False)
    off = evaluate(bundle("house"), m, "CTRL_TSTAT", "owner_occupier", fake_simulate, registry=registry)
    assert not off.applicable and skip_reason(off) == "not_supported"
    assert "never turned down" in off.not_applicable_reason
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv("LETO_HOME_TSTAT", value)
        on = evaluate(bundle("house"), m, "CTRL_TSTAT", "owner_occupier", fake_simulate, registry=registry)
        assert on.applicable and on.params["thermostats"] == 1
    monkeypatch.setenv("LETO_HOME_TSTAT", "0")
    assert not evaluate(bundle("house"), m, "CTRL_TSTAT", "owner_occupier", fake_simulate,
                        registry=registry).applicable
    monkeypatch.delenv("LETO_HOME_TSTAT", raising=False)
    for name in OFFICES:
        assert run(name, "CTRL_TSTAT", "owner_occupier", registry).applicable
