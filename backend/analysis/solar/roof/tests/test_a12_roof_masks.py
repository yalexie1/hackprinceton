"""A12 acceptance tests (workplan 4.2, adapted to the Data lane's D8 findings).

Masks are synthetic numpy arrays; no PNG is read from disk.
"""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely import wkt as shapely_wkt

from backend.schema import PropertyBundle, VexcelData, VexcelDetection, VexcelStructure
from backend.analysis.solar.roof import (build_parametric_roof, mask_to_map, refine_with_masks,
                                         vectorise_detections)
from backend.analysis.solar.roof.masks import ROOF_AREA_TOLERANCE

ROOT = Path(__file__).resolve().parents[5]
EXAMPLES = ROOT / "specs" / "examples"
FIXTURES = ["house", "office", "office_houston"]
R = 6371008.8
LAT0, LON0 = 34.0935, -118.3171


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


# ---------------------------------------------------------------- helpers

def _ll(x: float, y: float) -> tuple[float, float]:
    """Local metres (x east, y north) around (LON0, LAT0) to lon/lat."""
    return (LON0 + math.degrees(x / (R * math.cos(math.radians(LAT0)))), LAT0 + math.degrees(y / R))


def _poly_wkt(pts_m) -> str:
    pts = [_ll(x, y) for x, y in pts_m] + [_ll(*pts_m[0])]
    return "POLYGON((" + ", ".join(f"{a:.10f} {b:.10f}" for a, b in pts) + "))"


def _rect(x0, y0, x1, y1) -> str:
    return _poly_wkt([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _area_m2(wkt: str) -> float:
    g = shapely_wkt.loads(wkt)
    kx = math.radians(1) * R * math.cos(math.radians(LAT0))
    ky = math.radians(1) * R
    return shapely.transform(g, lambda xy: (xy - (LON0, LAT0)) * (kx, ky)).area


def _to_m(wkt: str):
    g = shapely_wkt.loads(wkt)
    kx = math.radians(1) * R * math.cos(math.radians(LAT0))
    ky = math.radians(1) * R
    return shapely.transform(g, lambda xy: (xy - (LON0, LAT0)) * (kx, ky))


def _house(shape="gable", extra_structures=(), detections=()) -> VexcelData:
    """17 m (east-west) x 11.2 m footprint centred on the origin: gable faces north and south."""
    fp = _rect(-8.5, -5.6, 8.5, 5.6)
    return VexcelData(structures=[VexcelStructure(
        primary=True, footprint_wkt=fp, footprint_area_m2=17 * 11.2,
        attributes={"roof-characteristics.shape.value": shape})] + list(extra_structures),
        detections=list(detections))


def _det(label, x0, y0, x1, y1, *, conf=0.5, mask_area=None, mask_wkt=None, image="ortho-1",
         px=(0, 0, 100, 100), path=None) -> VexcelDetection:
    return VexcelDetection(label=label, confidence=conf, image_id=image, bbox_wkt=_rect(x0, y0, x1, y1),
                           pixel_bbox=px, mask_png_path=path, mask_wkt=mask_wkt, mask_area_m2=mask_area)


def _bundle(name: str) -> PropertyBundle:
    return PropertyBundle(**json.loads((EXAMPLES / name / "property_bundle.json").read_text()))


# ---------------------------------------------------------------- pixel mask -> map

def test_synthetic_disk_mask_becomes_polygon_and_area_within_5pct():
    # 100 x 80 pixel box over a 20 m (east) x 16 m (north) ground box: 0.2 m pixels
    rows, cols = 80, 100
    yy, xx = np.mgrid[0:rows, 0:cols]
    mask = (xx + 0.5 - 50) ** 2 + (yy + 0.5 - 40) ** 2 <= 30 ** 2
    expected = math.pi * (30 * 0.2) ** 2                     # 113.1 m2
    mp = mask_to_map(mask, _rect(0, 0, 20, 16), (400, 300, cols, rows))
    assert mp.pixel_area_m2 == pytest.approx(0.04, rel=1e-3)
    assert mp.area_m2 == pytest.approx(expected, rel=0.05)
    assert _area_m2(mp.polygon_wkt) == pytest.approx(expected, rel=0.05)
    c = _to_m(mp.polygon_wkt).centroid
    assert c.x == pytest.approx(10, abs=0.2) and c.y == pytest.approx(8, abs=0.2)
    assert mp.fill == pytest.approx(expected / 320, rel=0.05)


def test_pixel_row_zero_is_north_and_column_zero_is_west():
    mask = np.zeros((80, 100), dtype=bool)
    mask[:20, :25] = True                                     # top-left quarter-by-quarter
    mp = mask_to_map(mask, _rect(0, 0, 20, 16))
    g = _to_m(mp.polygon_wkt)
    x0, y0, x1, y1 = g.bounds
    assert (x0, x1) == (pytest.approx(0, abs=0.01), pytest.approx(5, abs=0.01))
    assert (y0, y1) == (pytest.approx(12, abs=0.01), pytest.approx(16, abs=0.01))
    assert mp.area_m2 == pytest.approx(20.0, rel=1e-3)


def test_rotated_box_keeps_its_rotation_and_scale():
    # 20 m x 10 m box rotated 30 degrees; a full mask must give the box itself
    a = math.radians(30)
    ux, uy = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
    nw = (-10 * ux[0] + 5 * uy[0], -10 * ux[1] + 5 * uy[1])
    corners = [nw, (nw[0] + 20 * ux[0], nw[1] + 20 * ux[1]),
               (nw[0] + 20 * ux[0] - 10 * uy[0], nw[1] + 20 * ux[1] - 10 * uy[1]),
               (nw[0] - 10 * uy[0], nw[1] - 10 * uy[1])]
    mp = mask_to_map(np.ones((50, 100), dtype=np.uint8), _poly_wkt(corners))
    assert mp.area_m2 == pytest.approx(200.0, rel=1e-3)
    assert _to_m(mp.polygon_wkt).symmetric_difference(shapely.Polygon(corners)).area < 1.0


def test_vectorise_fills_mask_wkt_and_area_without_touching_others():
    mask = np.zeros((50, 50), dtype=bool)
    mask[10:40, 10:40] = True                                 # 900 px of 0.04 m2 = 36 m2
    d1 = _det("roof", 0, 0, 10, 10, px=(0, 0, 50, 50), path="m/a.png")
    d2 = _det("roof", 0, 0, 10, 10, path="m/b.png", mask_area=12.0)
    out = vectorise_detections([d1, d2], {"m/a.png": mask})
    assert out[0].mask_area_m2 == pytest.approx(36.0, rel=1e-3)
    assert _area_m2(out[0].mask_wkt) == pytest.approx(36.0, rel=0.05)
    assert out[1] == d2 and d1.mask_wkt is None               # no array: unchanged; input not mutated


# ---------------------------------------------------------------- planes

def test_no_detections_returns_planes_unchanged():
    vex = _house()
    planes = build_parametric_roof(vex).planes
    res = refine_with_masks(planes, vex)
    assert res.planes == planes
    assert res.tree_area_m2 == {} and res.roof_check.mask_area_m2 is None


def test_tree_box_over_plane_lowers_usable_by_at_least_the_overlap():
    # south plane covers y in [-5.6, 0]. Tree box 4 x 4 m, 3 x 3 m of it over the
    # south plane; canopy fills 60 % of its box (mask_wkt is None, as on live data).
    tree = _det("tree", 6.5, -8.0, 10.5, -4.0, mask_area=0.6 * 16)
    vex = _house(detections=[tree])
    base = build_parametric_roof(vex).planes
    res = refine_with_masks(base, vex)
    south = next(p for p in base if p.id == "plane_south")
    got = next(p for p in res.planes if p.id == "plane_south")
    plan_overlap = 0.6 * (8.5 - 6.5) * (-4.0 - -5.6)          # fill x (box n plane)
    assert south.usable_area_m2 - got.usable_area_m2 >= plan_overlap - 0.01
    cosb = math.cos(math.radians(south.tilt_deg.expected))
    assert res.tree_area_m2["plane_south"] == pytest.approx(plan_overlap / cosb, abs=0.02)
    north = next(p for p in res.planes if p.id == "plane_north")
    assert north == next(p for p in base if p.id == "plane_north")
    assert got.area_m2 == south.area_m2 and got.polygon_wkt == south.polygon_wkt
    assert any(a.key == "roof.tree_overhang_m2" for a in res.assumptions)


def test_tree_with_mask_polygon_uses_the_polygon():
    tree_poly = _rect(-2.0, -3.0, 2.0, -1.0)                  # 8 m2, entirely over the south plane
    tree = _det("tree", -3, -4, 3, 0, mask_wkt=tree_poly)     # box would be 24 m2
    vex = _house(detections=[tree])
    base = build_parametric_roof(vex).planes
    res = refine_with_masks(base, vex)
    south_b = next(p for p in base if p.id == "plane_south")
    south = next(p for p in res.planes if p.id == "plane_south")
    assert south_b.usable_area_m2 - south.usable_area_m2 >= 8.0 - 0.02
    assert res.tree_area_m2["plane_south"] < 24.0


def test_nested_trees_are_not_double_counted():
    a = _det("tree", -2, -4, 2, 0, mask_area=16.0)            # full box
    b = _det("tree", -1, -3, 1, -1, mask_area=4.0)            # inside a
    vex = _house(detections=[a, b])
    base = build_parametric_roof(vex).planes
    res = refine_with_masks(base, vex)
    cosb = math.cos(math.radians(base[0].tilt_deg.expected))
    assert res.tree_area_m2["plane_south"] == pytest.approx(16.0 / cosb, abs=0.02)


def test_fragments_never_raise_usable_area():
    # Nested roof fragments whose summed area is 2.5 x the footprint, plus a large box
    frags = [_det("roof", -8.5, -5.6, 8.5, 5.6, mask_area=180.0, conf=0.4)]
    frags += [_det("roof", -8 + i, -5, -2 + i, 5, mask_area=50.0, conf=0.6) for i in range(6)]
    frags += [_det("roof", -9, -6, 9, 6, image="oriented-1", conf=0.3)]
    vex = _house(detections=frags)
    for shape in ("gable", "hip", "flat", None):
        vex_s = vex.model_copy(update={"structures": _house(shape).structures})
        base = build_parametric_roof(vex_s).planes
        res = refine_with_masks(base, vex_s)
        for b, p in zip(base, res.planes):
            assert p.usable_area_m2 <= b.usable_area_m2
        assert res.roof_check.mask_area_m2 == pytest.approx(180.0)   # largest, never the sum


@pytest.mark.parametrize("name", FIXTURES)
def test_fixtures_never_raise_usable_area(name):
    vex = _bundle(name).vexcel
    base = build_parametric_roof(vex).planes
    res = refine_with_masks(base, vex)
    assert len(res.planes) == len(base)
    for b, p in zip(base, res.planes):
        assert p.usable_area_m2 <= b.usable_area_m2
        assert (p.id, p.area_m2, p.polygon_wkt, p.tilt_deg, p.azimuth_deg, p.obstruction_counts) == \
            (b.id, b.area_m2, b.polygon_wkt, b.tilt_deg, b.azimuth_deg, b.obstruction_counts)
    assert res.roof_check.mask_area_m2 is not None


# ---------------------------------------------------------------- roof cross-check

def test_roof_check_takes_largest_mask_on_the_building_not_the_most_confident():
    # D8 on the golden house: footprint 190.4 m2, largest roof mask 180.9 m2; the
    # highest-confidence detection is the garage, off the house footprint.
    garage_fp = _rect(12, -3, 18, 3)
    garage = VexcelStructure(primary=False, footprint_wkt=garage_fp, footprint_area_m2=36.0)
    dets = [
        _det("roof", 11.5, -3.5, 18.5, 3.5, conf=0.70, mask_area=40.0),         # garage
        _det("roof", -9.0, -6.0, 9.0, 6.0, conf=0.36, mask_area=180.9),         # whole house
        _det("roof", -8.0, -5.0, 0.0, 5.0, conf=0.52, mask_area=60.0),          # nested fragment
        _det("roof", 0.0, -5.0, 8.0, 5.0, conf=0.58, mask_area=55.0),           # nested fragment
    ]
    vex = _house(extra_structures=[garage], detections=dets)
    vex.structures[0].footprint_area_m2 = 190.4
    res = refine_with_masks(build_parametric_roof(vex).planes, vex)
    chk = res.roof_check
    assert chk.detection_index == 1
    assert chk.mask_area_m2 == pytest.approx(180.9)
    assert chk.ratio_to_footprint == pytest.approx(180.9 / 190.4, rel=1e-3)
    assert chk.agrees is True and chk.tolerance == ROOF_AREA_TOLERANCE
    assert not res.warnings


def test_roof_check_warns_beyond_tolerance():
    dets = [_det("roof", -9.0, -6.0, 9.0, 6.0, mask_area=100.0)]
    vex = _house(detections=dets)
    res = refine_with_masks(build_parametric_roof(vex).planes, vex)
    assert res.roof_check.agrees is False
    assert any("tolerance" in w for w in res.warnings)
    # the roof check never changes the planes
    assert res.planes == build_parametric_roof(vex).planes


def test_roof_check_keeps_the_whole_roof_mask_on_a_rotated_footprint():
    # A 30 m square turned 45 degrees: its axis-aligned box is twice its area, so the
    # whole-roof box overlaps the footprint by under half of the box. Vexcel boxes are
    # always axis-aligned (the LA golden office is turned about 42 degrees).
    h = 30 / math.sqrt(2)
    fp = _poly_wkt([(0, -h), (h, 0), (0, h), (-h, 0)])
    dets = [
        _det("roof", -h - 0.8, -h - 0.8, h + 0.8, h + 0.8, mask_area=860.0),   # whole roof
        _det("roof", -5.0, -5.0, 5.0, 5.0, mask_area=60.0),                    # nested fragment
        _det("roof", h - 1.0, -10.0, h + 19.0, 10.0, mask_area=300.0),         # neighbour touching a corner
    ]
    vex = VexcelData(structures=[VexcelStructure(primary=True, footprint_wkt=fp, footprint_area_m2=900.0,
                                                 attributes={"roof-characteristics.shape.value": "flat"})],
                     detections=dets)
    g0 = _to_m(dets[0].bbox_wkt)
    assert g0.intersection(_to_m(fp)).area / g0.area < 0.5        # the old test would drop it
    res = refine_with_masks(build_parametric_roof(vex).planes, vex)
    chk = res.roof_check
    assert chk.detection_index == 0
    assert chk.mask_area_m2 == pytest.approx(860.0)
    assert chk.agrees is True
    assert not any("tolerance" in w for w in res.warnings)
    assert "2 roof detections on the building" in " ".join(res.notes)


def test_inputs_are_not_mutated():
    tree = _det("tree", 6.5, -8.0, 10.5, -4.0, mask_area=9.6)
    vex = _house(detections=[tree])
    planes = build_parametric_roof(vex).planes
    before = [p.model_dump() for p in planes]
    vex_before = vex.model_dump()
    refine_with_masks(planes, vex)
    assert [p.model_dump() for p in planes] == before and vex.model_dump() == vex_before
