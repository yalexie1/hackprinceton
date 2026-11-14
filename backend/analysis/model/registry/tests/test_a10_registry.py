"""A10 acceptance tests (specs/workplan.md section 4.2, row A10). No network, fixtures only."""
from __future__ import annotations

import socket
from pathlib import Path

import pytest

from backend.schema import Assumption, BuildingModel, EvidenceRef, Flag, PropertyBundle, Ranged
from backend.analysis.model.registry import (
    build_assumptions,
    build_registry,
    costar_assumptions,
    feasibility_flags,
    merge_assumptions,
    set_assumption,
    set_model_assumption,
    systems_from_assumptions,
)

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


def by_key(assumptions):
    return {a.key: a for a in assumptions}


def width(r: Ranged) -> float:
    return r.high - r.low


def fixture_inputs(name: str):
    """The vision assumptions, flags and user overrides recorded in the model fixture."""
    m = model(name)
    observed = [a for a in m.assumptions if a.source == "vision"]
    overrides = {a.key: (a.value.expected if isinstance(a.value, Ranged) else a.value)
                 for a in m.assumptions if a.source == "user"}
    return observed, m.flags, overrides


def a(key, value, source, conf=0.5):
    return Assumption(key=key, label=key, value=value, source=source, confidence=conf)


# ---------------------------------------------------------------- merge by source strength

def test_user_replaces_vision_replaces_vintage_default():
    vd = a("wall.u_value", Ranged(low=0.6, expected=2.0, high=2.0, unit="W/m2K"), "vintage_default")
    vi = a("wall.u_value", Ranged(low=0.5, expected=0.8, high=1.1, unit="W/m2K"), "vision")
    us = a("wall.u_value", Ranged(low=0.4, expected=0.4, high=0.4, unit="W/m2K"), "user", 1.0)
    assert by_key(merge_assumptions([vd]))["wall.u_value"].source == "vintage_default"
    assert by_key(merge_assumptions([vd, vi]))["wall.u_value"] == vi
    assert by_key(merge_assumptions([vi, vd]))["wall.u_value"] == vi      # order does not matter
    assert by_key(merge_assumptions([us, vd, vi]))["wall.u_value"] == us
    assert len(merge_assumptions([us, vd, vi])) == 1


def test_merge_order_follows_source_strength():
    out = merge_assumptions([a("x", "1", "vintage_default"), a("y", "2", "vision"), a("z", "3", "user")])
    assert [x.source for x in out] == ["user", "vision", "vintage_default"]


def test_registry_merges_user_over_vision_over_vintage_for_one_key():
    b = bundle("house")
    plain = by_key(build_assumptions(b))
    assert plain["wall.u_value"].source == "vintage_default"
    seen = a("wall.u_value", Ranged(low=0.5, expected=0.8, high=1.1, unit="W/m2K"), "vision")
    with_vision = by_key(build_assumptions(b, observed=[seen]))
    assert with_vision["wall.u_value"].source == "vision"
    assert with_vision["wall.u_value"].value.expected == 0.8
    with_user = by_key(build_assumptions(b, observed=[seen], overrides={"wall.u_value": 0.4}))
    assert with_user["wall.u_value"].source == "user"
    assert with_user["wall.u_value"].value.expected == 0.4


# ---------------------------------------------------------------- vintage defaults

@pytest.mark.parametrize("name", FIXTURES)
def test_vintage_defaults_match_the_model_fixture(name):
    observed, flags, overrides = fixture_inputs(name)
    mine = by_key(build_registry(bundle(name), observed, flags, overrides).assumptions)
    # Keys owned by other packages (physics 03 daylight) are not built here.
    others = {"lighting.manual_switch_fraction", "lighting.control_type"}
    checked = 0
    for fx in model(name).assumptions:
        if fx.source != "vintage_default" or fx.key in others:
            continue
        got = mine[fx.key]
        assert got.source == "vintage_default", fx.key
        for f in ("low", "expected", "high"):
            assert getattr(got.value, f) == pytest.approx(getattr(fx.value, f), abs=1e-3), (fx.key, f)
        assert got.value.unit == fx.value.unit, fx.key
        checked += 1
    assert checked >= 6


def test_no_costar_record_gives_a_wider_vintage_range():
    for name, keys in (("house", ("wall.u_value", "roof.u_value", "infiltration.ach50")),
                       ("office", ("wall.u_value", "roof.u_value", "lighting.lpd"))):
        b = bundle(name)
        with_costar = by_key(build_assumptions(b))
        without = by_key(build_assumptions(b.model_copy(update={"costar": None})))
        assert "building.year_built" not in without
        for k in keys:
            assert without[k].source == "vintage_default"
            assert width(without[k].value) > width(with_costar[k].value), (name, k)
            assert without[k].confidence < with_costar[k].confidence, (name, k)
        assert any(width(without[k].value) > width(with_costar[k].value) for k in keys)


def test_year_from_a_non_completion_event_widens_to_adjacent_rows():
    b = bundle("house")   # 1924, house wall: before 1970 row
    c = b.costar.model_copy(update={"year_built": 1975, "year_built_event": "ConstructionComplete"})
    complete = by_key(build_assumptions(b.model_copy(update={"costar": c})))
    c2 = c.model_copy(update={"year_built_event": "Renovation"})
    renov = by_key(build_assumptions(b.model_copy(update={"costar": c2})))
    for k in ("wall.u_value", "roof.u_value"):
        assert width(renov[k].value) >= width(complete[k].value)
    assert width(renov["wall.u_value"].value) > width(complete["wall.u_value"].value)
    assert renov["wall.u_value"].value.expected == complete["wall.u_value"].value.expected


def test_year_built_from_costar_with_the_event_as_evidence():
    yb = by_key(costar_assumptions(bundle("office")))["building.year_built"]
    assert yb.source == "costar"
    assert (yb.value.low, yb.value.expected, yb.value.high) == (1989, 1989, 1989)
    refs = {e.ref: e for e in yb.evidence}
    assert refs["CostarData.year_built"].kind == "costar_field"
    assert "ConstructionComplete" in refs["CostarData.year_built"].note
    assert refs["CostarData.year_built_event"].note == "ConstructionComplete"


def test_envelope_area_uses_gross_building_area_never_rentable():
    b = bundle("office")
    c = b.costar.model_copy(update={"rentable_area_m2": 12345.6})
    out = build_assumptions(b.model_copy(update={"costar": c}))
    m = by_key(out)
    assert m["building.gross_area_m2"].value.expected == pytest.approx(24147.6)
    assert m["building.gross_area_m2"].source == "costar"
    assert m["building.floor_plate_m2"].value.expected == pytest.approx(24147.6 / 17, rel=1e-4)
    for x in out:
        if isinstance(x.value, Ranged):
            assert 12345.6 not in (x.value.low, x.value.expected, x.value.high), x.key
    # changing only the rentable area changes nothing
    assert out == build_assumptions(b)


# ---------------------------------------------------------------- office occupancy

@pytest.mark.parametrize("name,expected", [("office", 20.0), ("office_houston", 48.0)])
def test_office_tenancies_give_occupants_and_a_costar_assumption(name, expected):
    r = build_registry(bundle(name))
    occ = by_key(r.assumptions)["occupancy.count"]
    assert occ.source == "costar"
    assert occ.value.expected == expected
    assert occ.evidence[0].kind == "costar_field"
    assert r.systems.occupants is not None
    assert r.systems.occupants.expected == expected
    oa = by_key(r.assumptions)["ventilation.outdoor_air_m3_s"]
    assert oa.source == "costar"
    assert r.systems.outdoor_air_m3_s.expected == pytest.approx(expected * 0.00944, rel=1e-3)


def test_office_occupancy_matches_the_fixture_range():
    r = build_registry(bundle("office"))
    fx = model("office").systems.occupants
    assert (r.systems.occupants.low, r.systems.occupants.expected, r.systems.occupants.high) == \
        (fx.low, fx.expected, fx.high)


@pytest.mark.parametrize("name", ["office", "office_houston"])
def test_office_without_occupancy_gives_no_occupants_and_the_vintage_default(name):
    b = bundle(name)
    b = b.model_copy(update={"costar": b.costar.model_copy(update={"occupancy": None})})
    r = build_registry(b)
    occ = by_key(r.assumptions)["occupancy.count"]
    assert occ.source == "vintage_default"
    area = sum(x.area_m2 for x in b.matterport.rooms if x.area_m2)
    assert occ.value.expected == pytest.approx(area / 18.59, rel=1e-3)
    assert r.systems.occupants is None
    assert by_key(r.assumptions)["ventilation.outdoor_air_m3_s"].source == "vintage_default"
    assert not any(x.source == "costar" and x.key.startswith("occupancy") for x in r.assumptions)


def test_office_with_only_ended_tenancies_falls_back_to_the_vintage_default():
    b = bundle("office")
    occ = b.costar.occupancy
    ended = [t.model_copy(update={"move_out": "2020-01-01"}) for t in occ.tenancies]
    c = b.costar.model_copy(update={"occupancy": occ.model_copy(update={"tenancies": ended})})
    r = build_registry(b.model_copy(update={"costar": c}))
    assert by_key(r.assumptions)["occupancy.count"].source == "vintage_default"
    assert r.systems.occupants is None


# ---------------------------------------------------------------- feasibility flags

@pytest.mark.parametrize("name", FIXTURES)
def test_with_no_cue_the_electrical_and_structural_flags_are_unknown(name):
    r = build_registry(bundle(name))
    flags = {f.key: f for f in r.flags}
    assert flags["electrical.service"].status == "unknown"
    assert flags["roof.structure"].status == "unknown"


def test_a_cue_sets_the_flag_and_is_kept():
    cue = Flag(key="electrical.service", status="likely_upgrade", message="60 A panel seen",
               evidence=[EvidenceRef(kind="pano", ref="pano_03")])
    flags = {f.key: f for f in feasibility_flags("home", [], [cue])}
    assert flags["electrical.service"] == cue
    assert flags["roof.structure"].status == "unknown"


def test_office_without_a_confirmed_unit_raises_the_hvac_flag():
    r = build_registry(bundle("office"))
    assert r.systems.hvac_type == "unknown"
    assert {f.key: f.status for f in r.flags}["hvac.system_type"] == "unknown"
    h = build_registry(bundle("office_houston"))   # Vexcel counts two rooftop units
    assert h.systems.hvac_type == "rooftop_unit"
    assert "hvac.system_type" not in {f.key for f in h.flags}


# ---------------------------------------------------------------- Systems

@pytest.mark.parametrize("name", FIXTURES)
def test_systems_match_the_model_fixture(name):
    observed, flags, overrides = fixture_inputs(name)
    s = build_registry(bundle(name), observed, flags, overrides).systems
    fx = model(name).systems
    for f in ("hvac_type", "heating_fuel", "dhw_type", "dhw_fuel", "occupancy_schedule", "cooling_rating_metric"):
        assert getattr(s, f) == getattr(fx, f), f
    for f in ("cooling_cop", "heating_efficiency", "dhw_efficiency", "lighting_w_per_m2", "plug_w_per_m2",
              "cooling_rating", "heating_setpoint_c", "cooling_setpoint_c"):
        got, want = getattr(s, f), getattr(fx, f)
        if want is None:
            continue
        assert got.expected == pytest.approx(want.expected, abs=2e-3), f
        assert got.low == pytest.approx(want.low, abs=2e-3), f
        assert got.high == pytest.approx(want.high, abs=2e-3), f
    if fx.occupants is not None:
        assert s.occupants.expected == fx.occupants.expected


def test_house_occupants_only_from_a_building_specific_source():
    r = build_registry(bundle("house"))
    assert by_key(r.assumptions)["occupancy.count"].source == "vintage_default"
    assert r.systems.occupants is None
    r2 = build_registry(bundle("house"), overrides={"occupancy.count": 3})
    assert r2.systems.occupants == Ranged(low=3, expected=3, high=3, unit="people")


def test_systems_from_assumptions_reports_missing_fields():
    with pytest.raises(ValueError):
        systems_from_assumptions([], "home")


# ---------------------------------------------------------------- overrides and set_assumption

def test_number_override_collapses_the_range_and_sets_source_user():
    b = bundle("house")
    before = by_key(build_assumptions(b))["infiltration.ach50"]
    assert width(before.value) > 0
    after = by_key(build_assumptions(b, overrides={"infiltration.ach50": 9}))["infiltration.ach50"]
    assert after.source == "user"
    assert after.confidence == 1.0
    assert (after.value.low, after.value.expected, after.value.high) == (9, 9, 9)
    assert after.value.unit == before.value.unit
    assert after.evidence[0].kind == "user"


def test_string_and_bool_overrides_are_kept_as_values():
    m = by_key(build_assumptions(bundle("house"), overrides={"window.type": "double_lowe_non_metal",
                                                            "roof.existing_solar": True}))
    assert m["window.type"].value == "double_lowe_non_metal" and m["window.type"].source == "user"
    assert m["roof.existing_solar"].value is True and m["roof.existing_solar"].source == "user"
    # the window type sets U and SHGC from its DEF-03 row
    assert m["window.u_value"].value.expected == pytest.approx(2.16)
    assert m["window.shgc"].value.expected == pytest.approx(0.44)


def test_year_override_changes_the_vintage_row():
    m = by_key(build_assumptions(bundle("house"), overrides={"building.year_built": 1995}))
    assert m["building.year_built"].source == "user"
    assert m["wall.u_value"].value.expected == pytest.approx(0.625)
    assert m["infiltration.ach50"].value.expected == 8


def test_set_assumption_collapses_and_does_not_change_its_input():
    src = build_assumptions(bundle("house"))
    snapshot = [x.model_copy(deep=True) for x in src]
    out = set_assumption(src, "wall.u_value", 0.5)
    assert src == snapshot
    got = by_key(out)["wall.u_value"]
    assert got.source == "user"
    assert (got.value.low, got.value.expected, got.value.high) == (0.5, 0.5, 0.5)
    assert got.value.unit == "W/m2K"
    assert len(out) == len(src)


def test_set_model_assumption_rederives_systems():
    m = model("office")
    before = m.model_copy(deep=True)
    new = set_model_assumption(m, "occupancy.count", 30)
    assert m == before
    occ = by_key(new.assumptions)["occupancy.count"]
    assert occ.source == "user" and occ.value.expected == 30 and occ.value.low == 30
    assert new.systems.occupants.expected == 30
    assert new.systems.outdoor_air_m3_s.expected == pytest.approx(30 * 0.00944, rel=1e-3)
    assert by_key(new.assumptions)["ventilation.outdoor_air_m3_s"].source == "user"
    new2 = set_model_assumption(m, "hvac.cooling_rating", 13)
    assert new2.systems.cooling_cop.expected == pytest.approx(13 * 0.293071, rel=1e-3)
    assert new2.systems.cooling_cop.low == new2.systems.cooling_cop.high


# ---------------------------------------------------------------- purity

@pytest.mark.parametrize("name", FIXTURES)
def test_same_input_same_output(name):
    b = bundle(name)
    snapshot = b.model_copy(deep=True)
    r1, r2 = build_registry(b), build_registry(b)
    assert r1.assumptions == r2.assumptions and r1.systems == r2.systems and r1.flags == r2.flags
    assert b == snapshot


@pytest.mark.parametrize("name", FIXTURES)
def test_registry_output_fits_a_building_model(name):
    r = build_registry(bundle(name))
    m = model(name)
    BuildingModel.model_validate({**m.model_dump(), "assumptions": [x.model_dump() for x in r.assumptions],
                                  "systems": r.systems.model_dump(), "flags": [f.model_dump() for f in r.flags]})


def test_a_missing_gas_price_is_unknown_not_no_gas():
    # a live bundle may carry no gas price; that must not turn a home into an all-electric heat pump
    b = bundle("house")
    no_price = b.model_copy(update={"tariff": b.tariff.model_copy(update={"gas_usd_per_kwh": None})})
    with_price = {x.key: x for x in build_registry(b).assumptions}
    without = {x.key: x for x in build_registry(no_price).assumptions}
    assert without["hvac.system_type"].value == with_price["hvac.system_type"].value == "central_ac_furnace"
    assert without["hvac.system_type"].confidence < with_price["hvac.system_type"].confidence
    assert without["hvac.heating_fuel"].value == "gas"
    assert without["dhw.fuel"].value == with_price["dhw.fuel"].value == "gas"
    assert without["dhw.fuel"].confidence < with_price["dhw.fuel"].confidence
