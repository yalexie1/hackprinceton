"""A20 acceptance tests (specs/workplan.md 4.2, row A20): ENV_WALL is offered to the house
fixture only; the window measures change `u_value` or `shgc` of window surfaces only; the
input model is not mutated. Cards validate and match the fixtures where they show a field.
Fixtures only, no network."""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.schema import (Assumption, BaselineResult, BuildingModel, EnergyUse, MeasureResult,
                            PropertyBundle, Ranged)
from backend.analysis.measures import walls_windows as ww
from backend.analysis.measures.walls_windows import MEASURES, shade_factor
from backend.analysis.measures.walls_windows import walls as W
from backend.analysis.measures.walls_windows import windows as WIN

ROOT = Path(__file__).resolve().parents[5]
EX = ROOT / "specs" / "examples"
FIXTURES = ("house", "office", "office_houston")
WINDOW_MEASURES = ("WIN_REPLACE", "WIN_FILM", "WIN_SHADE")


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


def bare(name: str) -> BuildingModel:
    """The fixture model without the shading vision saw: the LA office (Culver Connect) has
    interior blinds, which make WIN_SHADE already done; these tests need the windows bare."""
    m = model(name)
    return m.model_copy(update={"assumptions": [a for a in m.assumptions if a.key != "window.shading"]})


def card(name: str, mid: str) -> MeasureResult:
    check, change, describe, _ = MEASURES[mid]
    b, m = bundle(name), bare(name)
    assert check(b, m) is None
    return describe(b, m, change(b, m), None, {"role": "owner_occupier", "desks_requested": None})


def with_assumption(m: BuildingModel, key: str, value, label: str = "x") -> BuildingModel:
    out = m.model_copy(deep=True)
    out.assumptions.append(Assumption(key=key, label=label, value=value, source="vision", confidence=0.6))
    return out


def surface_diff(a: BuildingModel, b: BuildingModel) -> dict[str, set[str]]:
    """surface id -> names of the fields that differ; also asserts nothing but surfaces moved."""
    da, db = a.model_dump(), b.model_dump()
    assert {k: v for k, v in da.items() if k != "surfaces"} == {k: v for k, v in db.items() if k != "surfaces"}
    assert [s["id"] for s in da["surfaces"]] == [s["id"] for s in db["surfaces"]]
    out = {}
    for sa, sb in zip(da["surfaces"], db["surfaces"]):
        fields = {k for k in sa if sa[k] != sb[k]}
        if fields:
            out[sa["id"]] = fields
    return out


# ---------------------------------------------------------------- ENV_WALL

def test_env_wall_offered_to_house_only():
    assert W.wall_check(bundle("house"), model("house")) is None
    for name in ("office", "office_houston"):
        reason, detail = W.wall_check(bundle(name), model(name))
        assert reason == "not_supported" and "home measure" in detail


def test_env_wall_changes_only_wall_u_values_and_does_not_mutate():
    b, m = bundle("house"), model("house")
    frozen = m.model_dump_json()
    new = W.wall_change(b, m)
    assert m.model_dump_json() == frozen
    diff = surface_diff(m, new)
    kinds = {s.id: s.kind for s in m.surfaces}
    assert diff and all(kinds[i] == "wall" and f == {"u_value"} for i, f in diff.items())
    for s_old, s_new in zip(m.surfaces, new.surfaces):
        if s_old.id in diff:
            assert s_new.u_value.expected == W.TARGET_U.expected
            assert s_new.u_value.low <= s_old.u_value.low and s_new.u_value.high <= s_old.u_value.high


def test_env_wall_already_done_after_fill_and_feasibility():
    b, m = bundle("house"), model("house")
    assert W.wall_check(b, W.wall_change(b, m))[0] == "already_done"
    brick = with_assumption(m, "wall.material", "brick")
    assert W.wall_check(b, brick)[0] == "feasibility"


def test_env_wall_card():
    c = card("house", "ENV_WALL")
    MeasureResult.model_validate(c.model_dump())
    walls = [s for s in model("house").surfaces if s.kind == "wall" and s.boundary == "exterior"]
    assert c.params["area_m2"] == pytest.approx(sum(s.area_m2 for s in walls), abs=0.01)
    assert c.params["target_u_w_m2k"] == 0.579
    assert c.savings is None and c.finance is None
    assert c.formula_ids == ["DEF-01", "ENV-03", "ZON-04", "EMI-01"]
    assert c.anchors and all(a.room_id and a.pano_id for a in c.anchors)
    assert any(e.ref == "DEF-01" for e in c.evidence)


# ---------------------------------------------------------------- windows: what changes

@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("mid", WINDOW_MEASURES)
def test_window_measures_change_window_u_or_shgc_only(name, mid):
    check, change, _, _ = MEASURES[mid]
    b, m = bundle(name), bare(name)
    assert check(b, m) is None
    frozen = m.model_dump_json()
    new = change(b, m)
    assert m.model_dump_json() == frozen, "input model mutated"
    diff = surface_diff(m, new)
    kinds = {s.id: s.kind for s in m.surfaces}
    allowed = {"u_value", "shgc"} if mid == "WIN_REPLACE" else {"shgc"}
    assert diff
    assert all(kinds[i] == "window" and f <= allowed for i, f in diff.items())
    after = {s.id: s for s in new.surfaces}
    for s in m.surfaces:
        if s.id in diff:
            assert after[s.id].shgc.expected <= max(s.shgc.expected, WIN.REPLACE_SHGC)
            assert after[s.id].u_value.expected <= s.u_value.expected


def test_win_replace_targets_def03_and_is_then_done():
    b, m = bundle("house"), model("house")
    new = WIN.replace_change(b, m)
    for s in new.surfaces:
        if s.kind == "window":
            assert (s.u_value.expected, s.shgc.expected) == (2.16, 0.44)
    assert WIN.replace_check(b, new)[0] == "already_done"


def test_film_and_screen_reproduce_win02_worked_example():
    """WIN-01 window: A 2.0 m2, SHGC 0.60, I 500 W/m2, F_w 0.90, baseline F_int 0.70 = 378.0 W.
    Film and screen multiply SHGC; the zone model keeps F_int: 264.6 W and 113.4 W."""
    def solar(shgc):
        return 2.0 * 0.90 * shgc * WIN.F_INT_BASELINE * 500.0
    assert solar(0.60) == pytest.approx(378.0)
    assert solar(0.60 * WIN.FILM_FACTOR) == pytest.approx(264.6)
    assert solar(0.60 * shade_factor("solar_screen", 0.60)) == pytest.approx(113.4)
    # interior devices replace the baseline F_int: light blinds closed at SHGC 0.60 = 0.498
    assert shade_factor("light_blinds_closed", 0.60) * WIN.F_INT_BASELINE == pytest.approx(0.498)
    assert shade_factor("medium_shades", 0.60) * WIN.F_INT_BASELINE == pytest.approx(0.836)
    assert shade_factor("light_curtains", 0.60) * WIN.F_INT_BASELINE == pytest.approx(0.794)


def test_film_scales_every_glazed_window():
    b, m = bundle("office"), model("office")
    new = WIN.film_change(b, m)
    old = {s.id: s for s in m.surfaces}
    for s in new.surfaces:
        if s.kind == "window":
            for end in ("low", "expected", "high"):
                assert getattr(s.shgc, end) == pytest.approx(0.70 * getattr(old[s.id].shgc, end))


def test_shade_treats_sun_side_windows_only():
    b, m = bundle("house"), model("house")
    diff = surface_diff(m, WIN.shade_change(b, m))
    az = {s.id: s.azimuth_deg for s in m.surfaces}
    assert diff and all(90.0 <= az[i] <= 270.0 for i in diff)
    assert {"surf_win_e13_1", "surf_win_e13_2"} <= set(diff)


# ---------------------------------------------------------------- windows: checks

def test_window_already_done_from_recorded_fittings():
    b, m = bundle("office"), bare("office")
    reason, detail = WIN.shade_check(b, with_assumption(m, "window.interior_shading", "roller_shades"))
    assert reason == "already_done" and "roller shades" in detail
    assert WIN.shade_check(b, with_assumption(m, "window.exterior_shading", "none")) is None
    assert WIN.film_check(b, with_assumption(m, "window.film", True, "Solar film"))[0] == "already_done"
    assert WIN.film_check(b, with_assumption(m, "window.film", False)) is None


def test_no_windows_is_a_feasibility_skip():
    b, m = bundle("house"), model("house")
    bare = m.model_copy(update={"surfaces": [s for s in m.surfaces if s.kind != "window"]}, deep=True)
    for mid in WINDOW_MEASURES:
        assert MEASURES[mid][0](b, bare)[0] == "feasibility"
    north = m.model_copy(deep=True)
    for s in north.surfaces:
        if s.kind == "window":
            s.azimuth_deg = 0.0
    assert WIN.shade_check(b, north)[0] == "feasibility"


# ---------------------------------------------------------------- cards against the fixtures

@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("mid", WINDOW_MEASURES)
def test_window_cards_validate(name, mid):
    c = card(name, mid)
    MeasureResult.model_validate(c.model_dump())
    assert c.applicable and c.savings is None and c.finance is None
    assert c.formula_ids and c.anchors and c.evidence
    assert c.params["glazing_area_m2"] > 0
    assert set(c.params["window_surface_ids"]) <= {s.id for s in model(name).surfaces if s.kind == "window"}
    if mid in ("WIN_FILM", "WIN_SHADE"):
        assert WIN.NO_COST_WARNING in c.warnings
    if name in ("office", "office_houston"):  # windows read from panoramas (no office scan has openings)
        assert any("panoramas" in w for w in c.warnings)


@pytest.mark.parametrize("name", ("office", "office_houston"))
def test_film_card_matches_fixture(name):
    fx, c = fixture_card(name, "WIN_FILM"), card(name, "WIN_FILM")
    assert c.params["glazing_area_m2"] == pytest.approx(fx["params"]["glazing_area_m2"])
    # the LA fixture is real output: the simulation adds its own ids after the card's
    assert fx["formula_ids"][:len(c.formula_ids)] == c.formula_ids
    assert c.title == fx["title"]
    assert fx["anchors"][0]["room_id"] in {a.room_id for a in c.anchors}


def test_shade_card_matches_house_fixture():
    fx, c = fixture_card("house", "WIN_SHADE"), card("house", "WIN_SHADE")
    # the fixture is real output (#330): the simulation adds its own ids after the card's
    assert fx["formula_ids"][:len(c.formula_ids)] == c.formula_ids
    assert set(fx["params"]["window_surface_ids"]) <= set(c.params["window_surface_ids"])
    assert fx["anchors"][0]["room_id"] == c.anchors[0].room_id
    assert c.title.startswith("Exterior shading on the south")
    assert any(e.kind == fx["evidence"][0]["kind"] and e.ref == fx["evidence"][0]["ref"] for e in c.evidence)


def test_pricing_keys():
    """finance/costs reads ENV_WALL from area_m2 and WIN_REPLACE from glazing_area_m2."""
    assert W.COST_KEY in card("house", "ENV_WALL").params
    assert "glazing_area_m2" in card("house", "WIN_REPLACE").params


def test_export_dict():
    assert set(ww.MEASURES) == {"ENV_WALL", *WINDOW_MEASURES}
    for mid, (check, change, describe, fids) in ww.MEASURES.items():
        assert callable(check) and callable(change) and callable(describe) and fids


# ---------------------------------------------------------------- registration with the engine

def R(x: float, unit: str) -> Ranged:
    return Ranged(low=0.9 * x, expected=x, high=1.1 * x, unit=unit)


def fake_simulate(b: PropertyBundle, m: BuildingModel) -> BaselineResult:
    """Conduction UA x 40 kKh plus window solar gain x 300 kWh per m2 of SHGC, all electric."""
    ua = sum(s.u_value.expected * s.area_m2 for s in m.surfaces if s.boundary == "exterior")
    sol = sum((s.shgc.expected if s.shgc else 0.0) * s.area_m2 for s in m.surfaces if s.kind == "window")
    e = ua * 40.0 + sol * 300.0
    annual = EnergyUse(electricity_kwh=R(e, "kWh"), gas_kwh=R(0.0, "kWh"), cost_usd=R(0.2 * e, "USD"),
                       co2_kg=R(0.3 * e, "kg"))
    return BaselineResult(annual=annual, end_use_kwh={"heating": e}, monthly_electricity_kwh=[e / 12] * 12,
                          monthly_gas_kwh=[0.0] * 12, peak_cooling_w=0.0, peak_heating_w=0.0)


@pytest.fixture
def registry():
    from backend.analysis.measures.engine import Registry
    reg = Registry()
    for mid, (check, change, describe, fids) in MEASURES.items():
        reg.register(mid, change=change, describe=describe, check=check, formula_ids=fids)
    return reg


def test_engine_offers_env_wall_to_house_only(registry):
    from backend.analysis.measures.engine import evaluate, skip_reason
    r = evaluate(bundle("house"), model("house"), "ENV_WALL", "owner_occupier", fake_simulate, registry=registry)
    assert r.applicable and r.savings.electricity_kwh.expected > 0
    for name in ("office", "office_houston"):
        r = evaluate(bundle(name), model(name), "ENV_WALL", "landlord", fake_simulate, registry=registry)
        assert not r.applicable and skip_reason(r) == "flow"


@pytest.mark.parametrize("name", FIXTURES)
def test_engine_evaluates_window_measures(registry, name):
    from backend.analysis.measures.engine import evaluate
    role = "owner_occupier" if name == "house" else "landlord"
    for mid in WINDOW_MEASURES:
        r = evaluate(bundle(name), bare(name), mid, role, fake_simulate, registry=registry)
        assert r.applicable, (mid, r.not_applicable_reason)
        assert r.savings.electricity_kwh.expected > 0
        assert r.formula_ids[: len(MEASURES[mid][3])] == list(MEASURES[mid][3])


def test_engine_role_rules(registry):
    from backend.analysis.measures.engine import evaluate, skip_reason
    b, m = bundle("office_houston"), model("office_houston")
    assert skip_reason(evaluate(b, m, "WIN_REPLACE", "tenant", fake_simulate, registry=registry)) == "role"
    # the fixture's lease flag blocks a tenant's film; shades are open to every role
    assert skip_reason(evaluate(b, m, "WIN_FILM", "tenant", fake_simulate, registry=registry)) == "feasibility"
    assert evaluate(b, m, "WIN_SHADE", "tenant", fake_simulate, registry=registry).applicable


def test_engine_stacks_window_measures(registry):
    """Film on top of replaced windows saves less than film on the old ones."""
    from backend.analysis.measures.engine import apply_measure, evaluate
    b, m = bundle("office_houston"), model("office_houston")
    first = evaluate(b, m, "WIN_FILM", "landlord", fake_simulate, registry=registry)
    replaced = apply_measure(b, m, "WIN_REPLACE", registry)
    second = evaluate(b, replaced, "WIN_FILM", "landlord", fake_simulate, registry=registry)
    assert 0 < second.savings.electricity_kwh.expected < first.savings.electricity_kwh.expected


@pytest.mark.parametrize("name", ["office", "office_houston"])
@pytest.mark.parametrize("seen", ["interior_blinds", "curtains", "exterior_shade", "overhang"])
def test_shading_seen_by_vision_makes_win_shade_already_done(name, seen):
    m = with_assumption(model(name), "window.shading", seen)
    out = WIN.shade_check(bundle(name), m)
    assert out is not None and out[0] == "already_done", out
    assert WIN.film_check(bundle(name), m) is None or WIN.film_check(bundle(name), m)[0] != "already_done"


@pytest.mark.parametrize("seen", ["none", "unknown"])
def test_no_shading_seen_leaves_win_shade_offered(seen):
    m = with_assumption(bare("office"), "window.shading", seen)
    out = WIN.shade_check(bundle("office"), m)
    assert out is None or out[0] != "already_done", out


def test_tinted_film_seen_by_vision_makes_win_film_already_done_only():
    m = with_assumption(bare("office"), "window.shading", "tinted_film")
    assert WIN.film_check(bundle("office"), m)[0] == "already_done"
    shade = WIN.shade_check(bundle("office"), m)
    assert shade is None or shade[0] != "already_done"
