"""A16 acceptance tests (specs/workplan.md 4.2, row A16), with a fake simulate and fake
measure plug-ins that follow the protocol in engine.py. No network, fixtures only."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.schema import (Anchor, BaselineResult, BuildingModel, EnergyUse, EvidenceRef,
                            MeasureResult, PropertyBundle, Ranged)
from backend.analysis.measures.engine import (CATALOGUE, REGISTRY, SKIP_PARAM, Registry, Skip,
                                              applicability, apply_measure, energy_saved,
                                              evaluate, flow_of, register, skip_reason)

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
FIXTURES = ("house", "office", "office_houston")


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


def load(name: str, file: str):
    return json.loads((EX / name / file).read_text())


# ---------------------------------------------------------------- fakes

def R(x: float, unit: str) -> Ranged:
    return Ranged(low=0.9 * x, expected=x, high=1.2 * x, unit=unit)


class FakeSimulate:
    """Heating from the envelope UA over the heating efficiency, plus lighting. Counts calls."""
    def __init__(self):
        self.calls = 0

    def __call__(self, b: PropertyBundle, m: BuildingModel) -> BaselineResult:
        self.calls += 1
        ua = sum(s.u_value.expected * s.area_m2 for s in m.surfaces if s.boundary == "exterior")
        heat = ua * 50.0 / m.systems.heating_efficiency.expected
        floor = sum(z.floor_area_m2 for z in m.zones)
        light = m.systems.lighting_w_per_m2.expected * floor * 3.0
        gas = heat if m.systems.heating_fuel == "gas" else 0.0
        elec = light + (heat if m.systems.heating_fuel != "gas" else 0.0)
        annual = EnergyUse(electricity_kwh=R(elec, "kWh"), gas_kwh=R(gas, "kWh"),
                           cost_usd=R(0.30 * elec + 0.05 * gas, "USD"),
                           co2_kg=R(0.2 * elec + 0.18 * gas, "kg"))
        return BaselineResult(annual=annual, end_use_kwh={"heating": heat, "lighting": light},
                              monthly_electricity_kwh=[elec / 12] * 12, monthly_gas_kwh=[gas / 12] * 12,
                              peak_cooling_w=0.0, peak_heating_w=0.0)


ATTIC_U = 0.2


def attic_check(b, m):
    roofs = [s for s in m.surfaces if s.kind == "roof"]
    if roofs and all(s.u_value.expected <= ATTIC_U for s in roofs):
        return ("already_done", "the roof is already at the target insulation.")
    return None


def attic_change(b, m):
    out = m.model_copy(deep=True)
    for s in out.surfaces:
        if s.kind == "roof":
            s.u_value = Ranged(low=ATTIC_U, expected=ATTIC_U, high=ATTIC_U, unit="W/m2K")
    return out


def attic_describe(b, m, changed, before, options):
    area = sum(s.area_m2 for s in m.surfaces if s.kind == "roof")
    return MeasureResult(measure_id="ENV_ATTIC", title="Attic insulation", applicable=True,
                         params={"target_u_w_m2k": ATTIC_U, "area_m2": area},
                         anchors=[Anchor(label="attic hatch")],
                         evidence=[EvidenceRef(kind="default_table", ref="DEF-01")],
                         formula_ids=["ENV-01", "ENV-03"])


def hp_change(b, m):
    out = m.model_copy(deep=True)
    out.systems.heating_fuel = "electricity"
    out.systems.heating_efficiency = Ranged(low=2.5, expected=3.0, high=3.2, unit="-")
    return out


def card(mid, ids=("X-01",), **kw):
    def describe(b, m, changed, before, options):
        return MeasureResult(measure_id=mid, title=mid, applicable=True, formula_ids=list(ids), **kw)
    return describe


def identity(b, m):
    return m


def led_change(b, m):
    out = m.model_copy(deep=True)
    out.systems.lighting_w_per_m2 = Ranged(low=2.0, expected=3.0, high=4.0, unit="W/m2")
    return out


def registry() -> Registry:
    reg = Registry()
    reg.register("ENV_ATTIC", check=attic_check, change=attic_change, describe=attic_describe,
                 formula_ids=["ZON-04"])
    reg.register("HVAC_HP", change=hp_change, describe=card("HVAC_HP", ("HVAC-01",)))
    reg.register("LGT_LED", change=led_change, describe=card("LGT_LED", ("LGT-01",)))
    for mid in ("ENV_AIRSEAL", "CTRL_TSTAT", "HVAC_RTU", "DHW_HPWH", "ENV_WALL", "WIN_FILM"):
        reg.register(mid, change=identity, describe=card(mid))
    return reg


# ---------------------------------------------------------------- acceptance

def test_tenant_asking_for_attic_gets_not_applicable_with_a_reason():
    sim = FakeSimulate()
    for name in FIXTURES:
        r = evaluate(bundle(name), model(name), "ENV_ATTIC", "tenant", sim, registry=registry())
        assert r.applicable is False
        assert r.not_applicable_reason == "Owner-only measure (SPEC.md section 6.2); the user is a tenant."
        assert skip_reason(r) == "role"
        assert r.savings is None and r.formula_ids == []
    assert sim.calls == 0          # a skipped measure is never simulated


@pytest.mark.parametrize("name", FIXTURES)
def test_every_result_lists_formula_ids(name):
    reg, sim = registry(), FakeSimulate()
    results = [evaluate(bundle(name), model(name), mid, "owner_occupier", sim, registry=reg,
                        simulate_formula_ids=["ZON-04", "EMI-01"]) for mid in CATALOGUE]
    assert len(results) == len(CATALOGUE)
    for r in results:
        assert isinstance(r.formula_ids, list)
        if r.applicable:
            assert r.formula_ids and r.savings is not None and r.finance is None
            assert "ZON-04" in r.formula_ids and "EMI-01" in r.formula_ids
            assert len(r.formula_ids) == len(set(r.formula_ids))
    attic = next(r for r in results if r.measure_id == "ENV_ATTIC")
    assert attic.formula_ids == ["ZON-04", "ENV-01", "ENV-03", "EMI-01"]   # static, card, simulate


def test_a_plugin_with_no_formula_ids_is_rejected():
    reg = Registry()
    reg.register("LGT_LED", change=led_change, describe=card("LGT_LED", ()))
    with pytest.raises(ValueError, match="formula_ids"):
        evaluate(bundle("house"), model("house"), "LGT_LED", "owner_occupier", FakeSimulate(), registry=reg)


def test_same_measure_on_a_state_with_another_measure_applied_saves_differently():
    reg, sim, b, m = registry(), FakeSimulate(), bundle("house"), model("house")
    alone = evaluate(b, m, "ENV_ATTIC", "owner_occupier", sim, registry=reg)
    after_hp = apply_measure(b, m, "HVAC_HP", reg)
    stacked = evaluate(b, after_hp, "ENV_ATTIC", "owner_occupier", sim, registry=reg)
    assert alone.applicable and stacked.applicable
    assert alone.savings.cost_usd.expected > 0 and stacked.savings.cost_usd.expected > 0
    assert alone.savings.cost_usd.expected != pytest.approx(stacked.savings.cost_usd.expected)
    assert alone.savings.gas_kwh.expected > 0 and stacked.savings.gas_kwh.expected == 0
    assert stacked.savings.electricity_kwh.expected > 0


# ---------------------------------------------------------------- savings

def test_savings_are_before_minus_after_and_ordered():
    reg, sim, b, m = registry(), FakeSimulate(), bundle("house"), model("house")
    r = evaluate(b, m, "ENV_ATTIC", "owner_occupier", sim, registry=reg)
    before, after = sim(b, m).annual, sim(b, attic_change(b, m)).annual
    assert r.savings.gas_kwh.expected == pytest.approx(before.gas_kwh.expected - after.gas_kwh.expected)
    for f in ("electricity_kwh", "gas_kwh", "cost_usd", "co2_kg"):
        x = getattr(r.savings, f)
        assert x.low <= x.expected <= x.high


def test_a_penalty_is_reported_as_a_negative_saving():
    reg = Registry()
    worse = lambda b, m: m.model_copy(update={"systems": m.systems.model_copy(
        update={"lighting_w_per_m2": Ranged(low=20, expected=20, high=20, unit="W/m2")})})
    reg.register("LGT_LED", change=worse, describe=card("LGT_LED"))
    r = evaluate(bundle("house"), model("house"), "LGT_LED", "owner_occupier", FakeSimulate(), registry=reg)
    assert r.applicable and r.savings.electricity_kwh.expected < 0
    assert r.savings.electricity_kwh.low <= r.savings.electricity_kwh.expected <= r.savings.electricity_kwh.high


def test_energy_saved_keeps_nonbaseload_only_when_both_have_it():
    e = EnergyUse(electricity_kwh=R(100, "kWh"), gas_kwh=R(0, "kWh"), cost_usd=R(10, "USD"),
                  co2_kg=R(5, "kg"), co2_nonbaseload_kg=R(8, "kg"))
    assert energy_saved(e, e).co2_nonbaseload_kg.expected == 0
    assert energy_saved(e, e.model_copy(update={"co2_nonbaseload_kg": None})).co2_nonbaseload_kg is None


def test_a_plugin_that_sets_its_own_savings_skips_the_after_simulation():
    direct = EnergyUse(electricity_kwh=R(3000, "kWh"), gas_kwh=R(0, "kWh"), cost_usd=R(900, "USD"),
                       co2_kg=R(600, "kg"))
    seen = {}

    def pv_describe(b, m, changed, before, options):
        seen["before"], seen["options"] = before, options
        return MeasureResult(measure_id="PV_ROOF", title="Rooftop solar", applicable=True,
                             savings=direct, formula_ids=["PV-04"])
    reg, sim = Registry(), FakeSimulate()
    reg.register("PV_ROOF", change=identity, describe=pv_describe)
    r = evaluate(bundle("house"), model("house"), "PV_ROOF", "landlord", sim, registry=reg,
                 simulate_formula_ids=["ZON-04"], desks_requested=3)
    assert r.savings == direct and r.formula_ids == ["PV-04"]
    assert sim.calls == 1 and isinstance(seen["before"], BaselineResult)
    assert seen["options"] == {"role": "landlord", "desks_requested": 3}


# ---------------------------------------------------------------- applicability

def test_flow_skips_match_the_fixture_text():
    reg, sim = registry(), FakeSimulate()
    for name in FIXTURES:
        for fx in load(name, "measures.json"):
            if fx["not_applicable_reason"] and "-flow measure" in fx["not_applicable_reason"]:
                r = evaluate(bundle(name), model(name), fx["measure_id"], "owner_occupier", sim, registry=reg)
                assert not r.applicable and skip_reason(r) == "flow"
                if name == "house":       # the office wording says "office suite"; ours "office property"
                    assert r.not_applicable_reason == fx["not_applicable_reason"]
    assert flow_of(bundle("house").summary) == "home" and flow_of(bundle("office").summary) == "office"


@pytest.mark.parametrize("name", FIXTURES)
def test_tenant_role_skips_match_the_tenant_plan_fixture(name):
    reg, b, m = registry(), bundle(name), model(name)
    want = {s["measure_id"] for s in load(name, "plan_tenant.json")["skipped"] if s["reason"] == "role"}
    for mid in want:
        skip, _ = applicability(b, m, mid, "tenant", reg)
        assert skip.reason == "role" and skip.plan_reason == "role"
    for mid in CATALOGUE:          # only owner-only measures are role-skipped
        skip, _ = applicability(b, m, mid, "tenant", reg)
        if skip is not None and skip.reason == "role":
            assert CATALOGUE[mid].roles == frozenset({"owner_occupier", "landlord"})
            assert not CATALOGUE[mid].consent_roles


def test_landlord_and_owner_occupier_may_do_owner_measures():
    reg = registry()
    for role in ("owner_occupier", "landlord"):
        skip, _ = applicability(bundle("house"), model("house"), "ENV_ATTIC", role, reg)
        assert skip is None


def test_blocking_flag_makes_the_measure_not_applicable():
    r = evaluate(bundle("house"), model("house"), "DHW_HPWH", "owner_occupier", FakeSimulate(), registry=registry())
    assert not r.applicable and skip_reason(r) == "feasibility"
    assert r.not_applicable_reason.startswith("Blocked by feasibility flag dhw.space: ")


def test_tenant_with_consent_measure_follows_the_consent_flag():
    reg, sim = registry(), FakeSimulate()
    blocked = evaluate(bundle("office_houston"), model("office_houston"), "ENV_AIRSEAL", "tenant", sim, registry=reg)
    assert not blocked.applicable and skip_reason(blocked) == "feasibility"
    assert "lease.alteration_consent" in blocked.not_applicable_reason
    ok = evaluate(bundle("office"), model("office"), "ENV_AIRSEAL", "tenant", sim, registry=reg)
    assert ok.applicable and any("consent" in w for w in ok.warnings)
    owner = evaluate(bundle("office_houston"), model("office_houston"), "ENV_AIRSEAL", "landlord", sim, registry=reg)
    assert owner.applicable and not any("consent" in w for w in owner.warnings)


def test_plugin_check_already_done():
    reg, b = registry(), bundle("house")
    done = attic_change(b, model("house"))
    r = evaluate(b, done, "ENV_ATTIC", "owner_occupier", FakeSimulate(), registry=reg)
    assert not r.applicable and skip_reason(r) == "already_done"
    assert r.not_applicable_reason == "Already done: the roof is already at the target insulation."
    assert Skip("already_done", "x").plan_reason == "already_done"
    assert Skip("flow", "x").plan_reason is None and Skip("not_supported", "x").plan_reason is None


def test_plugin_check_with_an_unknown_reason_raises():
    reg = Registry()
    reg.register("LGT_LED", change=led_change, describe=card("LGT_LED"), check=lambda b, m: ("nope", "x"))
    with pytest.raises(ValueError):
        evaluate(bundle("house"), model("house"), "LGT_LED", "owner_occupier", FakeSimulate(), registry=reg)


def test_unregistered_measure_is_not_supported():
    r = evaluate(bundle("house"), model("house"), "WIN_SHADE", "owner_occupier", FakeSimulate(), registry=Registry())
    assert not r.applicable and skip_reason(r) == "not_supported" and r.params == {SKIP_PARAM: "not_supported"}


def test_describe_may_decline_and_is_kept():
    def decline(b, m, changed, before, options):
        return MeasureResult(measure_id="ENV_ATTIC", title="Attic", applicable=False,
                             not_applicable_reason="The suite has no roof in its envelope.")
    reg, sim = Registry(), FakeSimulate()
    reg.register("ENV_ATTIC", change=identity, describe=decline)
    r = evaluate(bundle("office"), model("office"), "ENV_ATTIC", "landlord", sim, registry=reg)
    assert not r.applicable and skip_reason(r) == "feasibility" and r.savings is None
    assert sim.calls == 1


# ---------------------------------------------------------------- purity and registration

def test_input_model_is_not_mutated():
    reg, b, m = registry(), bundle("house"), model("house")
    frozen = m.model_dump_json()
    for mid in CATALOGUE:
        evaluate(b, m, mid, "owner_occupier", FakeSimulate(), registry=reg)
    assert m.model_dump_json() == frozen


def test_a_mutating_plugin_is_caught():
    def bad(b, m):
        m.systems.heating_fuel = "electricity"
        return m
    reg = Registry()
    reg.register("HVAC_HP", change=bad, describe=card("HVAC_HP"))
    with pytest.raises(RuntimeError, match="mutated"):
        evaluate(bundle("house"), model("house"), "HVAC_HP", "owner_occupier", FakeSimulate(), registry=reg)


def test_register_validates_and_the_default_registry_is_used():
    with pytest.raises(ValueError):
        Registry().register("NOT_A_MEASURE", change=identity, describe=card("X"))
    with pytest.raises(TypeError):
        Registry().register("LGT_LED", change=None, describe=card("LGT_LED"))
    saved = dict(REGISTRY.plugins)
    try:
        register("LGT_LED", change=led_change, describe=card("LGT_LED"))
        r = evaluate(bundle("office"), model("office"), "LGT_LED", "tenant", FakeSimulate())
        assert r.applicable and r.savings.electricity_kwh.expected > 0
    finally:
        REGISTRY.plugins.clear()
        REGISTRY.plugins.update(saved)


def test_catalogue_covers_every_measure_id_with_the_spec_roles():
    assert CATALOGUE["ENV_ATTIC"].roles == {"owner_occupier", "landlord"}
    assert CATALOGUE["ENV_AIRSEAL"].consent_roles == {"tenant"}
    assert CATALOGUE["LGT_CTRL"].roles == {"owner_occupier", "landlord", "tenant"}
    assert CATALOGUE["HVAC_RTU"].flows == {"office"} and CATALOGUE["ENV_WALL"].flows == {"home"}
