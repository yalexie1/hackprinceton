"""A14: LAY-03 order and stop conditions, ROOF-04 capacity, ROOF-06 share re-check, fixtures."""
from __future__ import annotations

import math
import socket
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon

from backend.analysis.solar.layout import (Candidate, greedy_fill, layout_pv, layout_pv_detailed,
                                           plane_excluded)
from backend.schema import BuildingModel, Flag, Ranged, RoofPlane, SolarDesign, VexcelDetection

EX = Path(__file__).resolve().parents[5] / "specs" / "examples"

# #330: the golden house's roof is now A11's parametric Vexcel roof, which carries no positioned
# obstructions. The splat-fitted case these tests cover is rebuilt here from the same planes with the
# two detections the hand-made example used to carry (a roof vent and a tree on the south plane).
HOUSE_SPLAT_OBSTRUCTIONS = [
    {"label": "roof vent", "confidence": 0.33, "image_id": "ortho-1",
     "bbox_wkt": "POLYGON((-118.3172263 34.0935203, -118.3172263 34.0935242, -118.3172217 34.0935242, "
                 "-118.3172217 34.0935203, -118.3172263 34.0935203))",
     "pixel_bbox": [502, 724, 7, 7], "mask_png_path": None, "mask_wkt": None, "mask_area_m2": 0.1},
    {"label": "tree", "confidence": 0.47, "image_id": "ortho-1",
     "bbox_wkt": "POLYGON((-118.3172563 34.0934385, -118.3172563 34.0934770, -118.3172049 34.0934770, "
                 "-118.3172049 34.0934385, -118.3172563 34.0934385))",
     "pixel_bbox": [457, 809, 77, 69], "mask_png_path": None, "mask_wkt": None, "mask_area_m2": 11.8},
]


def house_splat_planes(model):
    """The house planes as if fitted from the splat, with the vent and the tree on the south plane."""
    out = []
    for p in model.roof_planes:
        obs = [VexcelDetection.model_validate(o) for o in HOUSE_SPLAT_OBSTRUCTIONS] if p.id == "plane_south" else []
        out.append(p.model_copy(update={"geometry_source": "splat", "obstructions": obs}))
    return out
FLAVORS = ["house", "office", "office_houston"]
OK = Flag(key="electrical.service", status="likely_ok", message="")
ROOF_OK = Flag(key="roof.structure", status="likely_ok", message="")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def const(y):
    return lambda plane, wkt: y


def tilt(e, lo=None, hi=None):
    return Ranged(low=e if lo is None else lo, expected=e, high=e if hi is None else hi, unit="deg")


def area_plane(pid, az, le=17.0, s=6.3662, usable=91.50, t=28.4):
    """Area-method plane (no map polygon), the ROOF-04 golden-house example by default."""
    return RoofPlane(id=pid, polygon_wkt="POLYGON EMPTY", area_m2=round(le * s, 2),
                     tilt_deg=tilt(t, min(t, 15.8), max(t, 41.1)), azimuth_deg=az, usable_area_m2=usable,
                     eave_length_m=le, slope_length_m=s, geometry_source="vexcel_parametric")


def map_plane(pid="plane_s", w=12.0, d=5.0, t=20.0, az=180.0, lon0=-118.3171, lat0=34.0935):
    """A south-facing plane, w m along the eave and d m deep in plan, drawn in lon/lat."""
    kx = math.radians(1) * 6371008.8 * math.cos(math.radians(lat0))
    ky = math.radians(1) * 6371008.8
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    poly = Polygon([(lon0 + x / kx, lat0 + y / ky) for x, y in pts])
    slope = d / math.cos(math.radians(t))
    return RoofPlane(id=pid, polygon_wkt=poly.wkt, area_m2=w * slope, tilt_deg=tilt(t),
                     azimuth_deg=az, usable_area_m2=w * slope, eave_length_m=w,
                     slope_length_m=slope, geometry_source="splat")


def assert_inside(res):
    design = res.design
    assert design.panel_count == len(design.panels)
    by_plane = {}
    for p in design.panels:
        if p.polygon_wkt is None:
            continue
        region = res.regions[p.plane_id].usable_lonlat()
        assert region is not None
        assert region.buffer(1e-9).contains(shapely_wkt.loads(p.polygon_wkt)), p
        by_plane.setdefault(p.plane_id, []).append(shapely_wkt.loads(p.polygon_wkt))
    for polys in by_plane.values():
        for i, a in enumerate(polys):
            for b in polys[i + 1:]:
                assert a.intersection(b).area < 1e-14     # deg^2: panels do not overlap


# ---------- LAY-03 worked example ----------

def test_lay03_worked_example_greedy():
    cands = ([Candidate(0, j, None, 1650, 1650, 1650, 0.0, 1) for j in range(10)]
             + [Candidate(1, j, None, 1380, 1380, 1380, 0.0, 1) for j in range(8)]
             + [Candidate(2, j, None, 1340, 1340, 1340, 0.0, 1) for j in range(8)])
    placed, reason = greedy_fill(cands, {0: 10, 1: 8, 2: 8}, 0.430, annual_use_kwh=9000)
    assert reason == "consumption"
    assert len(placed) == 14
    assert [sum(c.plane_idx == k for c in placed) for k in range(3)] == [10, 4, 0]
    assert sum(c.yield_exp for c in placed) * 0.430 == pytest.approx(9468.6, abs=0.05)


# ---------- the three stop conditions, one test each ----------

def test_stop_roof_area():
    res = layout_pv_detailed([map_plane()], OK, ROOF_OK, const(1500.0),
                             budget_usd=1e9, annual_consumption_kwh=1e9, installed_cost_usd=1000.0)
    assert res.stop_reason == "roof_area"
    assert res.design.panel_count == res.capacity["plane_s"] > 0
    assert_inside(res)


def test_stop_budget():
    res = layout_pv_detailed([map_plane()], OK, ROOF_OK, const(1500.0),
                             budget_usd=5500.0, annual_consumption_kwh=1e9, installed_cost_usd=1000.0)
    assert res.stop_reason == "budget"
    assert res.design.panel_count == 5          # the 6th would cost 6000 > 5500
    assert res.design.system_kw_dc == pytest.approx(2.15)
    assert_inside(res)


def test_stop_budget_with_cost_function():
    cost = lambda n: 2000.0 + 800.0 * n     # fixed plus per-module cost
    design = layout_pv([map_plane()], OK, ROOF_OK, const(1500.0), budget_usd=6000.0,
                       installed_cost_usd=cost)
    assert design.panel_count == 5          # 2000 + 800 * 5 = 6000 fits, 6 would not


def test_stop_consumption():
    res = layout_pv_detailed([map_plane()], OK, ROOF_OK, const(1500.0),
                             budget_usd=1e9, annual_consumption_kwh=3000.0, installed_cost_usd=1000.0)
    assert res.stop_reason == "consumption"
    # each module 645 kWh: 4 give 2580, the 5th reaches 3225 >= 3000 and is placed
    assert res.design.panel_count == 5
    assert res.design.annual_kwh.expected == pytest.approx(3225.0)
    assert_inside(res)


def test_budget_without_cost_is_an_error():
    with pytest.raises(ValueError):
        layout_pv([map_plane()], OK, ROOF_OK, const(1500.0), budget_usd=1000.0)


# ---------- order, exclusion, shading ----------

def test_fills_best_plane_first():
    east = map_plane("plane_e", az=90.0, lon0=-118.3, lat0=34.1)
    south = map_plane("plane_s")
    y = lambda plane, wkt: 1650.0 if plane.azimuth_deg == 180 else 1340.0
    design = layout_pv([east, south], OK, ROOF_OK, y, annual_consumption_kwh=3000.0)
    assert {p.plane_id for p in design.panels} == {"plane_s"}


def test_north_and_steep_planes_excluded():
    assert plane_excluded(area_plane("n", 0.0))
    assert plane_excluded(area_plane("nw", 300.0))
    assert plane_excluded(area_plane("ne", 60.0))
    assert plane_excluded(area_plane("steep", 180.0, t=65.0))
    assert plane_excluded(area_plane("s", 180.0)) is None
    assert plane_excluded(area_plane("e", 90.0)) is None
    assert plane_excluded(area_plane("n", 0.0), exclude_north=False) is None


def test_heavily_shaded_positions_skipped():
    def y(plane, wkt):
        return (1500.0, 0.25)
    res = layout_pv_detailed([map_plane()], OK, ROOF_OK, y)
    assert res.design.panel_count == 0 and res.stop_reason == "roof_area"


def test_ranged_yield_sums_into_annual_kwh():
    y = lambda plane, wkt: (Ranged(low=1400, expected=1500, high=1550, unit="kWh/kW"), 0.03)
    design = layout_pv([map_plane()], OK, ROOF_OK, y, annual_consumption_kwh=1000.0)
    assert design.panel_count == 2
    assert design.annual_kwh.low == pytest.approx(2 * 1400 * 0.43)
    assert design.annual_kwh.high == pytest.approx(2 * 1550 * 0.43)
    assert all(p.shading_loss_fraction == 0.03 for p in design.panels)


def test_blocked_flag_places_nothing():
    blocked = Flag(key="roof.structure", status="blocked", message="roof failing")
    res = layout_pv_detailed([map_plane()], OK, blocked, const(1500.0))
    assert res.stop_reason == "blocked" and res.design.panel_count == 0
    assert res.design.structural == blocked


# ---------- ROOF-04 capacity and the ROOF-06 share re-check ----------

def test_roof04_golden_house_capacity_and_ridge_setback():
    planes = [area_plane("plane_south", 180.0), area_plane("plane_north", 0.0)]
    res = layout_pv_detailed(planes, OK, ROOF_OK, const(1500.0))
    # 18 in: 43 modules, 38.8 % of 190.4 m2; above 33 %, so 36 in: 40 modules, 36.1 %
    assert res.ridge_setback_m == pytest.approx(0.9144)
    assert res.capacity["plane_south"] == 40
    assert res.design.panel_count == 40
    assert res.array_plan_share == pytest.approx(0.361, abs=5e-4)
    assert "gives 40 modules" in res.notes[0] and "gives 36" in res.notes[0]
    assert all(p.polygon_wkt is None for p in res.design.panels)   # area method: count only


def test_roof06_sprinklered_keeps_18_inch():
    planes = [area_plane("plane_south", 180.0), area_plane("plane_north", 0.0)]
    res = layout_pv_detailed(planes, OK, ROOF_OK, const(1500.0), sprinklered=True)
    assert res.ridge_setback_m == pytest.approx(0.4572)
    assert res.design.panel_count == 43
    assert res.array_plan_share == pytest.approx(0.388, abs=5e-4)


def test_roof06_below_threshold_keeps_18_inch():
    planes = [area_plane("plane_south", 180.0), area_plane("plane_north", 0.0)]
    res = layout_pv_detailed(planes, OK, ROOF_OK, const(1500.0), annual_consumption_kwh=10 * 645.0)
    assert res.design.panel_count == 10 and res.ridge_setback_m == pytest.approx(0.4572)


# ---------- fixtures ----------

@pytest.mark.parametrize("flavor", FLAVORS)
def test_fixture_roof_planes(flavor):
    model = BuildingModel.model_validate_json((EX / flavor / "building_model.json").read_text())
    res = layout_pv_detailed(model.roof_planes, OK, ROOF_OK, const(1500.0))
    design = SolarDesign.model_validate_json(res.design.model_dump_json())
    assert design.panel_count > 0
    assert design.module_w == 430.0
    assert design.system_kw_dc == pytest.approx(design.panel_count * 0.43)
    assert_inside(res)
    if flavor == "house":
        assert "plane_north" in res.excluded
        assert {p.plane_id for p in design.panels} == {"plane_south"}


def test_fixture_house_budget_sized_like_the_plan():
    """The fixture's PV_ROOF design is sized by the budget left over: 5 modules, 2.15 kW."""
    model = BuildingModel.model_validate_json((EX / "house" / "building_model.json").read_text())
    design = layout_pv(model.roof_planes, OK, ROOF_OK, const(1750.0), budget_usd=5 * 2900.0 + 100,
                       annual_consumption_kwh=8000.0, installed_cost_usd=2900.0)
    assert design.panel_count == 5 and design.system_kw_dc == pytest.approx(2.15)


def test_house_obstructions_cut_out():
    model = BuildingModel.model_validate_json((EX / "house" / "building_model.json").read_text())
    planes = house_splat_planes(model)
    res = layout_pv_detailed(planes, OK, ROOF_OK, const(1500.0))
    south = next(p for p in planes if p.id == "plane_south")
    vent = shapely_wkt.loads(next(o for o in south.obstructions if o.label == "roof vent").bbox_wkt)
    assert any(p.plane_id == "plane_south" for p in res.design.panels)
    for p in res.design.panels:
        assert not shapely_wkt.loads(p.polygon_wkt).intersects(vent)


def test_west_face_fills_before_east_on_a_yield_tie():
    """#396: an east/west tie goes to the west face (afternoon value), even when east is listed first."""
    east = [Candidate(0, j, None, 1300, 1300, 1300, 0.0, 1, 90.0) for j in range(6)]
    west = [Candidate(1, j, None, 1300, 1300, 1300, 0.0, 1, 270.0) for j in range(6)]
    placed, reason = greedy_fill(east + west, {0: 6, 1: 6}, 0.430, annual_use_kwh=4 * 1300 * 0.430)
    assert reason == "consumption"
    assert {c.plane_idx for c in placed} == {1}


def test_west_tiebreak_never_beats_a_clearly_better_face():
    """The nudge orders near-ties only: a south face 3 % better still fills first."""
    south = [Candidate(0, j, None, 1340, 1340, 1340, 0.0, 1, 180.0) for j in range(4)]
    west = [Candidate(1, j, None, 1300, 1300, 1300, 0.0, 1, 270.0) for j in range(4)]
    placed, _ = greedy_fill(west + south, {0: 4, 1: 4}, 0.430, annual_use_kwh=4 * 1340 * 0.430)
    assert {c.plane_idx for c in placed} == {0}
