"""A23 acceptance (specs/workplan.md 4.2, row A23; SPEC 6.4; physics 03 LCT-02, LCT-03).

Candidates sit on a 0.5 m grid at least 0.6 m from walls and clear of door openings; the number
recommended equals the number requested; recommended desks keep the minimum spacing; the result
validates as LayoutResult and the LAYOUT card as MeasureResult with zero cost and a saving range
starting at 0; the LA office fixture shape is reproduced with a fake scorer. Fixtures only, a
fake scorer and a fake simulate, no network."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Point, Polygon

from backend.schema import Assumption, BaselineResult, BuildingModel, LayoutResult, MeasureResult, PropertyBundle
from backend.analysis.layout import (GRID_M, MEASURES, MIN_SPACING_M, WALL_CLEARANCE_M,
                                     candidate_grid, check, change, desk_score, describe, measures,
                                     place_desks)
from backend.analysis.layout.placement import door_segments, point_segment_distance
from backend.analysis.measures.engine import Registry, evaluate, skip_reason

ROOT = Path(__file__).resolve().parents[4]
EX = ROOT / "specs" / "examples"
FIXTURES = ("office", "house", "office_houston")


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


def fixture_card(name: str, mid: str = "LAYOUT") -> dict:
    return next(m for m in json.loads((EX / name / "measures.json").read_text()) if m["measure_id"] == mid)


def window_segments(b: PropertyBundle, m: BuildingModel) -> dict[str, np.ndarray]:
    out: dict[str, list] = {}
    for f in b.matterport.floors:
        vs = {v.id: (v.x, v.y) for v in f.vertices}
        for s in m.surfaces:
            e = next((e for e in f.edges if e.id == s.source_edge_id), None)
            if s.kind == "window" and e is not None:
                out.setdefault(f.id, []).append((vs[e.vertex_ids[0]], vs[e.vertex_ids[1]]))
    return {k: np.asarray(v, float) for k, v in out.items()}


def fake_scorer(b: PropertyBundle, m: BuildingModel, saved_fraction=None, dt_pr_peak: float = 6.0):
    """Daylight falls with distance from the nearest window wall; glare and discomfort are high
    at the glass. Stands in for A5's score_point."""
    segs = window_segments(b, m)
    calls = []

    def score_point(*, bundle, model, room, x, y, setpoint_lux):
        calls.append((room.id, x, y, setpoint_lux))
        s = segs.get(room.floor_id)
        d = float(point_segment_distance(np.array([[x, y]]), s).min()) if s is not None else 50.0
        return {"daylight": math.exp(-d / 6), "glare_risk": 0.3 * math.exp(-d),
                "comfort_ppd": 5 + 15 * math.exp(-d), "daylight_factor": 6 * math.exp(-d / 3),
                "max_dt_pr_k": dt_pr_peak * math.exp(-d),
                "lighting_saved_fraction": (0.6 * math.exp(-d / 6) if saved_fraction is None
                                            else saved_fraction)}
    score_point.calls = calls
    return score_point


def fake_simulate(b: PropertyBundle, m: BuildingModel) -> BaselineResult:
    """The same baseline whatever the state: LAYOUT changes no model field."""
    return BaselineResult.model_validate_json((EX / "office" / "baseline_result.json").read_text())


# ---------------------------------------------------------------- grid

@pytest.mark.parametrize("name", FIXTURES)
def test_candidates_on_grid_and_clear_of_walls(name):
    b = bundle(name)
    cands = candidate_grid(b.matterport)
    assert cands
    floors = {f.id: f for f in b.matterport.floors}
    rooms = {r.id: r for r in b.matterport.rooms}
    for c in cands:
        assert abs(c.x / GRID_M - round(c.x / GRID_M)) < 1e-9
        assert abs(c.y / GRID_M - round(c.y / GRID_M)) < 1e-9
        poly = Polygon(rooms[c.room_id].polygon)
        assert poly.contains(Point(c.x, c.y))                       # strictly inside
        assert poly.exterior.distance(Point(c.x, c.y)) > 1e-9       # never on the boundary
        f = floors[c.floor_id]
        vs = {v.id: (v.x, v.y) for v in f.vertices}
        for e in f.edges:
            if e.type == "invisible":
                continue
            line = LineString([vs[e.vertex_ids[0]], vs[e.vertex_ids[1]]])
            face = line.distance(Point(c.x, c.y)) - (e.thickness_m or 0.12) / 2
            assert face >= WALL_CLEARANCE_M - 1e-9, (c, e.id)
    assert len({(c.floor_id, c.x, c.y) for c in cands}) == len(cands)


def test_no_candidate_on_an_invisible_room_edge():
    # LA office room_01 has an invisible edge at y = 9.5 (to room_02). No wall clearance
    # removes points there, and the daylight scorer may put a boundary point outside the
    # room, so the grid must not offer them (15 such points before the fix).
    b = bundle("office")
    rooms = {r.id: r for r in b.matterport.rooms}
    on_edge = [c for c in candidate_grid(b.matterport)
               if Polygon(rooms[c.room_id].polygon).exterior.distance(Point(c.x, c.y)) < 1e-9]
    assert on_edge == []
    assert not [c for c in candidate_grid(b.matterport) if c.room_id == "room_01" and abs(c.y - 9.5) < 1e-9]


def test_candidates_avoid_door_openings():
    b = bundle("house")
    f = b.matterport.floors[0]
    doors, widths = door_segments(f)
    assert len(doors) >= 2              # op_e01_2 doorway, both readings of relative_center
    cands = candidate_grid(b.matterport)
    pts = np.array([[c.x, c.y] for c in cands])
    d = point_segment_distance(pts, doors)
    assert (d > widths[None, :] + WALL_CLEARANCE_M).all()
    # the door actually removes positions: drop the openings and the grid grows
    bare = b.model_copy(deep=True)
    for fl in bare.matterport.floors:
        for e in fl.edges:
            e.openings = [o for o in e.openings if o.type == "window"]
    assert len(candidate_grid(bare.matterport)) > len(cands)


def test_non_work_rooms_are_skipped():
    b = bundle("house")
    rooms = {c.room_id for c in candidate_grid(b.matterport)}
    assert "room_kitchen" not in rooms and "room_living" in rooms


# ---------------------------------------------------------------- score and selection

def test_desk_score_worked_example():
    # physics 03 LCT-03 worked example
    assert desk_score(0.50, 0.03, 8.0)["score"] == pytest.approx(0.710, abs=1e-4)
    assert desk_score(0.05, 0.0, 6.0)["score"] == pytest.approx(0.605, abs=1e-4)
    assert desk_score(0.90, 0.25, 18.0)["score"] == pytest.approx(0.465, abs=1e-4)


@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("n", [1, 2, 4, 6])
def test_recommended_count_and_spacing(name, n):
    b, m = bundle(name), model(name)
    lay = place_desks(b, m, n, fake_scorer(b, m))
    LayoutResult.model_validate(lay.result.model_dump())
    rec = [d for d in lay.result.candidates if d.recommended]
    assert len(rec) == n == lay.result.desks_requested
    for i, a in enumerate(rec):
        for c in rec[i + 1:]:
            assert math.hypot(a.x - c.x, a.y - c.y) >= MIN_SPACING_M - 1e-9
    grid = {(c.room_id, c.x, c.y) for c in candidate_grid(b.matterport)}
    assert all((d.room_id, d.x, d.y) in grid for d in lay.result.candidates)


def test_hot_glass_is_never_recommended():
    b, m = bundle("office"), model("office")
    lay = place_desks(b, m, 4, fake_scorer(b, m, dt_pr_peak=40.0))
    for d in lay.result.candidates:
        if d.recommended:
            assert d.max_dt_pr_k < 10.0
    assert len([d for d in lay.result.candidates if d.recommended]) == 4


def test_desk_count_defaults_from_occupants():
    b, m = bundle("office"), model("office")
    lay = place_desks(b, m, None, fake_scorer(b, m))
    assert lay.result.desks_requested == round(m.systems.occupants.expected)


# ---------------------------------------------------------------- the LAYOUT card

def test_la_office_fixture_shape():
    """The LA office fixture (Culver Connect, #253) is the real A23 card with the A5 scorer; with a
    fake scorer the card keeps its shape, and its saving follows LCT-02 from its own parameters."""
    b, m = bundle("office"), model("office")
    fx = fixture_card("office")
    card = describe(b, m, change(b, m), fake_simulate(b, m), {"role": "tenant", "desks_requested": 12},
                    score_point=fake_scorer(b, m, saved_fraction=0.42))
    card = MeasureResult.model_validate(card.model_dump())
    lay = card.layout
    assert card.applicable and card.title == fx["title"]
    assert len(lay.candidates) == len(fx["layout"]["candidates"]) == 24
    assert sum(d.recommended for d in lay.candidates) == fx["layout"]["desks_requested"] == 12
    assert lay.window_source == fx["layout"]["window_source"] == "vision"     # no openings in the scan (#301)
    assert lay.control_type == fx["layout"]["control_type"] == "none"
    assert lay.target_lux == 300 and lay.setpoint_lux == 500 and lay.occupied_hours_per_year == 2600
    assert lay.score_weights == fx["layout"]["score_weights"]
    assert any("read from panoramas" in w for w in card.warnings)   # vision windows: the card says so
    # LCT-02 with the saved fraction: zero cost, range from 0, k_m = 0.5 in the middle
    s = card.savings
    assert s.electricity_kwh.low == 0 and s.cost_usd.low == 0 and s.co2_kg.low == 0
    full = card.params["controlled_power_w"] / 1000 * 2600 * 0.42
    assert s.electricity_kwh.expected == pytest.approx(0.5 * full, rel=1e-3)
    assert s.electricity_kwh.high == pytest.approx(full, rel=1e-3)
    assert s.gas_kwh.high == 0
    assert set(fx["params"]) <= set(card.params)
    assert card.params["auto_on_off_saved_fraction"] == pytest.approx(0.42)
    fs = fx["savings"]["electricity_kwh"]      # the fixture follows the same rule with its own fraction
    f_fx = fx["params"]["controlled_power_w"] / 1000 * 2600 * fx["params"]["auto_on_off_saved_fraction"]
    assert fs["expected"] == pytest.approx(0.5 * f_fx, rel=2e-3) and fs["high"] == pytest.approx(f_fx, rel=2e-3)
    assert set(card.formula_ids) <= set(fx["formula_ids"])
    for w in fx["warnings"]:
        assert w in card.warnings or w.startswith("useful life of")
    assert [a.label for a in card.anchors] == [a["label"] for a in fx["anchors"]]
    assert card.finance is None


def test_automatic_control_claims_full_saving():
    b, m = bundle("office"), model("office")
    m2 = m.model_copy(deep=True)
    m2.assumptions = [a for a in m2.assumptions if a.key != "lighting.control_type"] + [
        Assumption(key="lighting.control_type", label="Lighting control", value="continuous",
                   source="user", confidence=1.0)]
    lay = place_desks(b, m2, 4, fake_scorer(b, m2, saved_fraction=0.42))
    kwh = lay.result.lighting_kwh_saved
    assert kwh.low > 0
    assert kwh.expected == pytest.approx(lay.params["controlled_power_w"] / 1000 * 2600 * 0.42, rel=1e-4)
    assert "depends on occupants switching lights off" not in lay.result.warnings


def test_check_and_change():
    b, m = bundle("office"), model("office")
    assert check(b, m) is None
    assert change(b, m) is m
    no_win = m.model_copy(update={"surfaces": [s for s in m.surfaces if s.kind != "window"]})
    reason, detail = check(b, no_win)
    assert reason == "feasibility" and detail


# ---------------------------------------------------------------- engine registration

def _registry(score_point=None) -> Registry:
    reg = Registry()
    table = MEASURES if score_point is None else measures(score_point)
    assert set(table) == {"LAYOUT"}
    for mid, (chk, chg, dsc, fids) in table.items():
        reg.register(mid, change=chg, describe=dsc, check=chk, formula_ids=fids)
    return reg


@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("role", ["owner_occupier", "landlord", "tenant"])
def test_engine_evaluates_layout(name, role):
    b, m = bundle(name), model(name)
    frozen = m.model_dump_json()
    r = evaluate(b, m, "LAYOUT", role, fake_simulate, registry=_registry(fake_scorer(b, m)),
                 desks_requested=3)
    assert m.model_dump_json() == frozen
    MeasureResult.model_validate(r.model_dump())
    assert r.applicable and r.finance is None
    assert sum(d.recommended for d in r.layout.candidates) == 3
    assert r.savings.electricity_kwh.low == 0 and r.savings.cost_usd.low == 0
    assert r.savings.electricity_kwh.expected > 0
    # the saving is LAYOUT's own, not a simulation difference (which would be zero here)
    assert r.savings.electricity_kwh == r.layout.lighting_kwh_saved.model_copy(
        update={k: round(getattr(r.layout.lighting_kwh_saved, k), 2) for k in ("low", "expected", "high")})


def test_unbound_describe_is_not_supported():
    b, m = bundle("office"), model("office")
    r = evaluate(b, m, "LAYOUT", "tenant", fake_simulate, registry=_registry(), desks_requested=2)
    assert not r.applicable and skip_reason(r) == "not_supported"


def test_scorer_gets_setpoint_and_rooms():
    b, m = bundle("house"), model("house")
    sp = fake_scorer(b, m)
    place_desks(b, m, 2, sp, flow="home")
    assert sp.calls and {c[3] for c in sp.calls} == {300.0}
