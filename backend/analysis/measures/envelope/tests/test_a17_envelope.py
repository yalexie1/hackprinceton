"""A17 acceptance (specs/workplan.md 4.2, row A17): ENV_ATTIC, ENV_AIRSEAL, ROOF_COOL.

Each measure changes only the fields it names; an attic already at the target returns the
already-done reason; the input model is not mutated; each card validates as MeasureResult and
matches the fixture card's params, anchors and formula_ids where the fixture shows one. The
engine is imported here only to prove the plug-ins register and evaluate (test-only import).
No network, fixtures only.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.schema import (BaselineResult, BuildingModel, EnergyUse, MeasureResult,
                            PropertyBundle, Ranged)
from backend.analysis.measures import envelope
from backend.analysis.measures.envelope import MEASURES, airseal, attic, roof_cool
from backend.analysis.measures.engine import Registry, SKIP_PARAM, apply_measure, evaluate

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
FIXTURES = ("house", "office", "office_houston")
IDS = ("ENV_ATTIC", "ENV_AIRSEAL", "ROOF_COOL")


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


def fixture_card(name: str, mid: str):
    cards = json.loads((EX / name / "measures.json").read_text())
    return next((MeasureResult.model_validate(c) for c in cards if c["measure_id"] == mid), None)


def card(name: str, mid: str, role: str = "landlord") -> MeasureResult:
    b, m = bundle(name), model(name)
    p = MEASURES[mid]
    return p.describe(b, m, p.change(b, m), fake_simulate(b, m), {"role": role, "desks_requested": None})


# ---------------------------------------------------------------- fake simulate

def R(x: float, unit: str) -> Ranged:
    return Ranged(low=min(0.9 * x, 1.2 * x), expected=x, high=max(0.9 * x, 1.2 * x), unit=unit)


def fake_simulate(b: PropertyBundle, m: BuildingModel) -> BaselineResult:
    """Heating and cooling from UA, leakage and roof absorptance; enough to move with each measure."""
    ua = sum(s.u_value.expected * s.area_m2 for s in m.surfaces if s.boundary == "exterior")
    sysm = m.systems
    leak = (sysm.infiltration_ach50.expected if sysm.infiltration_ach50 else
            sysm.envelope_leakage_l_s_m2_75pa.expected if sysm.envelope_leakage_l_s_m2_75pa else
            sysm.infiltration_ach.expected)
    sol = sum(s.u_value.expected * s.area_m2 * 0.04 * (s.solar_absorptance.expected if s.solar_absorptance else 0.65)
              for s in m.surfaces if s.kind == "roof" and s.boundary == "exterior")
    heat = ua * 40.0 + leak * 30.0 - sol * 100.0
    cool = ua * 10.0 + leak * 5.0 + sol * 1000.0
    elec, gas = cool / 3.0, heat / 0.8
    annual = EnergyUse(electricity_kwh=R(elec, "kWh"), gas_kwh=R(gas, "kWh"),
                       cost_usd=R(0.3 * elec + 0.05 * gas, "USD"), co2_kg=R(0.2 * elec + 0.18 * gas, "kg"))
    return BaselineResult(annual=annual, end_use_kwh={"heating": heat, "cooling": cool},
                          monthly_electricity_kwh=[elec / 12] * 12, monthly_gas_kwh=[gas / 12] * 12,
                          peak_cooling_w=0.0, peak_heating_w=0.0)


SIM_IDS = ("ZON-04",)


# ---------------------------------------------------------------- registration dict

def test_registration_dict_covers_the_three_measures():
    assert set(MEASURES) == set(IDS)
    for mid, p in MEASURES.items():
        check, change, describe, fids = p           # (check, change, describe, formula_ids)
        assert callable(check) and callable(change) and callable(describe)
        assert isinstance(fids, tuple)
    reg = Registry()
    for mid, p in MEASURES.items():
        reg.register(mid, check=p.check, change=p.change, describe=p.describe, formula_ids=p.formula_ids)
    assert reg.registered() == ["ENV_ATTIC", "ENV_AIRSEAL", "ROOF_COOL"]
    assert envelope.attic_check is attic.check and envelope.roof_cool_describe is roof_cool.describe


# ---------------------------------------------------------------- only the named fields change

def _diff(a, b, path="") -> set[str]:
    """Paths whose values differ, list items addressed by their `id` (or index)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = set()
        for k in set(a) | set(b):
            out |= _diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = set()
        for i, (x, y) in enumerate(zip(a, b)):
            key = x.get("id", i) if isinstance(x, dict) else i
            out |= _diff(x, y, f"{path}[{key}]")
        return out
    return set() if a == b else {path}


def _top(paths: set[str]) -> set[str]:
    """Collapse a Ranged's low/expected/high into the field path."""
    return {p.rsplit(".", 1)[0] if p.rsplit(".", 1)[-1] in ("low", "expected", "high", "unit") else p
            for p in paths}


@pytest.mark.parametrize("name", FIXTURES)
def test_each_measure_changes_only_its_fields_and_not_the_input(name):
    b, m = bundle(name), model(name)
    frozen = m.model_dump_json()
    for mid, p in MEASURES.items():
        changed = p.change(b, m)
        assert m.model_dump_json() == frozen, f"{mid} mutated its input"
        assert changed is not m
        assert isinstance(changed, BuildingModel)
        diff = _top(_diff(m.model_dump(), changed.model_dump()))
        if p.check(b, m) is not None:
            assert diff == set(), f"{mid}: not applicable yet changed {diff}"
            continue
        roofs = {s.id for s in m.surfaces if s.kind == "roof"}
        if mid == "ENV_ATTIC":
            allowed = {f"surfaces[{r}].u_value" for r in roofs}
        elif mid == "ROOF_COOL":
            allowed = {f"surfaces[{r}].solar_absorptance" for r in roofs}
        elif name == "house":
            allowed = {"systems.infiltration_ach50", "systems.infiltration_ach"}
        else:
            allowed = {"systems.envelope_leakage_l_s_m2_75pa"}
        assert diff and diff <= allowed, f"{mid} on {name} changed {diff - allowed}"
        p.describe(b, m, changed, fake_simulate(b, m), {"role": "landlord"})
        assert m.model_dump_json() == frozen, f"{mid}: describe mutated its input"


def test_house_values_after_each_measure():
    b, m = bundle("house"), model("house")
    roof = next(s for s in attic.change(b, m).surfaces if s.id == "surf_roof")
    assert roof.u_value.expected == pytest.approx(0.148)
    assert roof.u_value.low <= 0.148 <= roof.u_value.high
    cool = next(s for s in roof_cool.change(b, m).surfaces if s.id == "surf_roof")
    assert (cool.solar_absorptance.low, cool.solar_absorptance.expected, cool.solar_absorptance.high) == (0.25, 0.30, 0.40)
    sealed = airseal.change(b, m).systems
    assert sealed.infiltration_ach50.expected == pytest.approx(15.0 * 0.7)
    assert sealed.infiltration_ach50.low < sealed.infiltration_ach50.expected < sealed.infiltration_ach50.high
    assert sealed.infiltration_ach.expected == pytest.approx(0.75 * 0.7)


def test_office_leakage_after_sealing():
    b, m = bundle("office"), model("office")
    after = airseal.change(b, m).systems.envelope_leakage_l_s_m2_75pa
    assert (after.low, after.expected, after.high) == (2.0, 5.0, 7.5)


# ---------------------------------------------------------------- already done

def test_attic_already_at_target_returns_already_done():
    b, m = bundle("house"), model("house")
    done = attic.change(b, m)
    got = attic.check(b, done)
    assert got is not None and got[0] == "already_done"
    # a roof set by hand to the target, and one better than it
    for u in (0.148, 0.114):
        m2 = m.model_copy(deep=True)
        for s in m2.surfaces:
            if s.kind == "roof":
                s.u_value = Ranged(low=u, expected=u, high=u, unit="W/m2K")
        assert attic.check(b, m2)[0] == "already_done"
        assert attic.change(b, m2).model_dump_json() == m2.model_dump_json()


def test_already_done_for_cool_roof_and_sealed_envelope():
    b, m = bundle("house"), model("house")
    assert roof_cool.check(b, roof_cool.change(b, m))[0] == "already_done"
    tight = m.model_copy(deep=True)
    tight.systems.infiltration_ach50 = Ranged(low=4.0, expected=6.0, high=8.0, unit="1/h at 50 Pa")
    assert airseal.check(b, tight)[0] == "already_done"
    bo, mo = bundle("office"), model("office")
    assert airseal.check(bo, airseal.change(bo, mo))[0] == "already_done"


def test_already_done_through_the_engine():
    b, m = bundle("house"), model("house")
    reg = Registry()
    for mid, p in MEASURES.items():
        reg.register(mid, check=p.check, change=p.change, describe=p.describe, formula_ids=p.formula_ids)
    done = apply_measure(b, m, "ENV_ATTIC", reg)
    r = evaluate(b, done, "ENV_ATTIC", "owner_occupier", fake_simulate, registry=reg)
    assert r.applicable is False and r.params[SKIP_PARAM] == "already_done"
    assert r.not_applicable_reason.startswith("Already done:")


# ---------------------------------------------------------------- cards against the fixtures

CARDS = [("house", "ENV_ATTIC"), ("house", "ROOF_COOL"), ("office", "ENV_AIRSEAL"),
         ("office_houston", "ENV_AIRSEAL"), ("office", "ROOF_COOL"), ("office_houston", "ROOF_COOL")]


@pytest.mark.parametrize("name,mid", CARDS)
def test_card_matches_fixture(name, mid):
    got = card(name, mid)
    MeasureResult.model_validate(got.model_dump())           # validates as the contract type
    want = fixture_card(name, mid)
    assert got.measure_id == mid and got.applicable == want.applicable
    assert got.savings is None and got.finance is None
    assert SKIP_PARAM not in got.params
    # params: every fixture key with its value (the card may add the pricing quantity)
    for k, v in want.params.items():
        assert got.params[k] == pytest.approx(v), (k, got.params)
    # formula ids: the card's own entries, in the fixture's order; the rest of the fixture list is
    # the simulation (ZON, HVAC), finance (ECO) and emissions (EMI) the engine and S7 add
    assert [f for f in want.formula_ids if f in got.formula_ids] == got.formula_ids
    assert all(f.split("-")[0] in ("ZON", "HVAC", "ECO", "EMI")
               for f in want.formula_ids if f not in got.formula_ids)
    assert [e.model_dump() for e in got.evidence] == [e.model_dump() for e in want.evidence]
    # anchors: positions exactly; labels exactly except the Houston one (spec note in the PR)
    assert len(got.anchors) == len(want.anchors)
    for a, w in zip(got.anchors, want.anchors):
        assert (a.room_id, a.pano_id, a.x, a.y, a.z) == (w.room_id, w.pano_id, w.x, w.y, w.z)
        if name != "office_houston":
            assert a.label == w.label
    if not want.applicable:
        assert got.not_applicable_reason.startswith(want.not_applicable_reason.rstrip("."))
    assert [f.key for f in got.flags] == [f.key for f in want.flags]


def test_card_warnings_against_fixture():
    # ROOF_COOL on the house: the vented-attic upper bound (the fixture adds a sentence about the
    # sign of the result, which only the simulated saving can tell)
    w = fixture_card("house", "ROOF_COOL").warnings[0]
    assert card("house", "ROOF_COOL").warnings == [w.split(". ")[0] + "."]
    for name in ("office", "office_houston"):
        assert card(name, "ENV_AIRSEAL").warnings == fixture_card(name, "ENV_AIRSEAL").warnings
    assert card("house", "ENV_ATTIC").warnings == []


def test_pricing_quantities_in_params():
    """The finance cost table multiplies these keys (finance/costs quantity_of)."""
    assert card("house", "ENV_ATTIC").params["area_m2"] == pytest.approx(82.04)
    assert card("house", "ROOF_COOL").params["roof_area_m2"] == pytest.approx(202.6)   # the two roof planes
    assert card("office", "ENV_AIRSEAL").params["floor_area_m2"] == pytest.approx(383.42)
    assert card("house", "ENV_AIRSEAL").params["floor_area_m2"] == pytest.approx(82.04)


def test_house_airseal_card():
    c = card("house", "ENV_AIRSEAL")
    assert c.applicable and c.formula_ids == ["INF-02", "INF-03"]
    assert c.params["ach50_after"] == pytest.approx(10.5)
    assert c.warnings == [airseal.ASSUMPTION_WARNING]
    assert c.anchors and c.anchors[0].room_id == "room_bedroom"


def test_no_roof_check_is_not_supported():
    for name in ("office", "office_houston"):
        b, m = bundle(name), model(name)
        for mod in (attic, roof_cool):
            reason, detail = mod.check(b, m)
            assert reason == "not_supported" and "roof is not part of its envelope" in detail
    assert roof_cool.check(bundle("office"), model("office"))[1] == fixture_card("office", "ROOF_COOL").not_applicable_reason


# ---------------------------------------------------------------- through the engine

@pytest.fixture
def reg():
    r = Registry()
    for mid, p in MEASURES.items():
        r.register(mid, check=p.check, change=p.change, describe=p.describe, formula_ids=p.formula_ids)
    return r


def test_engine_evaluates_the_house(reg):
    b, m = bundle("house"), model("house")
    frozen = m.model_dump_json()
    attic_r = evaluate(b, m, "ENV_ATTIC", "owner_occupier", fake_simulate, registry=reg, simulate_formula_ids=SIM_IDS)
    assert attic_r.applicable and attic_r.savings.gas_kwh.expected > 0
    assert attic_r.formula_ids == ["ENV-01", "ENV-03", "ZON-04"]
    seal = evaluate(b, m, "ENV_AIRSEAL", "owner_occupier", fake_simulate, registry=reg, simulate_formula_ids=SIM_IDS)
    assert seal.applicable and seal.savings.gas_kwh.expected > 0 and seal.formula_ids[:2] == ["INF-02", "INF-03"]
    cool = evaluate(b, m, "ROOF_COOL", "owner_occupier", fake_simulate, registry=reg, simulate_formula_ids=SIM_IDS)
    assert cool.applicable and cool.savings.electricity_kwh.expected > 0 and cool.savings.gas_kwh.expected < 0
    assert m.model_dump_json() == frozen
    # a tenant is turned away by the engine before any of our code runs
    t = evaluate(b, m, "ENV_ATTIC", "tenant", fake_simulate, registry=reg)
    assert not t.applicable and t.params[SKIP_PARAM] == "role"


def test_engine_on_the_offices(reg):
    for name in ("office", "office_houston"):
        b, m = bundle(name), model(name)
        r = evaluate(b, m, "ROOF_COOL", "landlord", fake_simulate, registry=reg)
        assert not r.applicable and r.params[SKIP_PARAM] == "not_supported"
        s = evaluate(b, m, "ENV_AIRSEAL", "landlord", fake_simulate, registry=reg, simulate_formula_ids=SIM_IDS)
        assert s.applicable and s.savings.gas_kwh.expected > 0 and s.formula_ids == ["INF-05", "ZON-04"]
    # Houston tenant: the consent flag is blocked, so the engine skips it for feasibility
    t = evaluate(bundle("office_houston"), model("office_houston"), "ENV_AIRSEAL", "tenant",
                 fake_simulate, registry=reg)
    assert not t.applicable and t.params[SKIP_PARAM] == "feasibility"
