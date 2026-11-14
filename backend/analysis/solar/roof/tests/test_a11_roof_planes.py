"""A11 acceptance tests (workplan 4.2): parametric roof planes from VexcelData."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import pytest
from shapely import wkt as shapely_wkt

from backend.schema import BuildingModel, PropertyBundle, RoofPlane, VexcelData, VexcelStructure
from backend.analysis.solar.roof import build_parametric_roof

ROOT = Path(__file__).resolve().parents[5]
EXAMPLES = ROOT / "specs" / "examples"
FIXTURES = ["house", "office", "office_houston"]
R = 6371008.8


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def deny(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def _bundle(name: str) -> PropertyBundle:
    return PropertyBundle(**json.loads((EXAMPLES / name / "property_bundle.json").read_text()))


def _vexcel(name: str) -> VexcelData:
    return _bundle(name).vexcel


def _rect_wkt(length: float, width: float, bearing_deg: float = 90.0,
              lat0: float = 34.0935, lon0: float = -118.3171) -> str:
    """Rectangle footprint in lon/lat, long side `length` along compass bearing `bearing_deg`."""
    a = math.radians(bearing_deg)
    eu = (math.sin(a), math.cos(a))
    ev = (math.sin(a + math.pi / 2), math.cos(a + math.pi / 2))
    pts = []
    for su, sv in [(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)]:
        x = su * length / 2 * eu[0] + sv * width / 2 * ev[0]
        y = su * length / 2 * eu[1] + sv * width / 2 * ev[1]
        lon = lon0 + math.degrees(x / (R * math.cos(math.radians(lat0))))
        lat = lat0 + math.degrees(y / R)
        pts.append(f"{lon:.9f} {lat:.9f}")
    return f"POLYGON(({', '.join(pts)}))"


def _synthetic(shape=None, length=17.0, width=11.2, area=None, **attrs) -> VexcelData:
    a = dict(attrs)
    if shape is not None:
        a["roof-characteristics.shape.value"] = shape
    return VexcelData(structures=[VexcelStructure(
        primary=True, footprint_wkt=_rect_wkt(length, width),
        footprint_area_m2=area if area is not None else length * width, attributes=a)])


# ---------- the fixtures ----------

@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_planes_validate_and_area_matches_footprint_over_cos_tilt(name):
    vex = _vexcel(name)
    roof = build_parametric_roof(vex, 0.0)
    assert roof.planes
    fp = next(s for s in vex.structures if s.primary).footprint_area_m2
    total = sum(p.area_m2 for p in roof.planes)
    expected = fp / math.cos(math.radians(roof.planes[0].tilt_deg.expected))
    assert total == pytest.approx(expected, rel=0.02)
    for p in roof.planes:
        RoofPlane.model_validate(p.model_dump())
        assert p.geometry_source == "vexcel_parametric"
        assert 0 <= p.usable_area_m2 <= p.area_m2
        assert p.ridge_confirmed is False


def test_house_gable_matches_fixture_orientation_and_counts():
    roof = build_parametric_roof(_vexcel("house"), 266.4)
    model = BuildingModel(**json.loads((EXAMPLES / "house" / "building_model.json").read_text()))
    assert sorted(p.azimuth_deg for p in roof.planes) == pytest.approx(
        sorted(p.azimuth_deg for p in model.roof_planes), abs=0.5)
    assert {p.id for p in roof.planes} == {"plane_south", "plane_north"}
    assert roof.planes[0].tilt_deg.model_dump() == {"low": 15.8, "expected": 28.4, "high": 41.1, "unit": "deg"}
    for p in roof.planes:
        assert p.obstruction_counts == {"chimney": 1, "roof-vent": 5, "skylight": 0, "ac-unit": 2}
    # the plane polygons tile the footprint
    fp = shapely_wkt.loads(_vexcel("house").structures[0].footprint_wkt)
    union = shapely_wkt.loads(roof.planes[0].polygon_wkt).union(shapely_wkt.loads(roof.planes[1].polygon_wkt))
    assert union.area == pytest.approx(fp.area, rel=1e-3)


def test_office_flat_roof_row_and_rack_azimuth():
    roof = build_parametric_roof(_vexcel("office"), 41.57)
    (p,) = roof.planes
    assert p.tilt_deg.model_dump() == {"low": 0.0, "expected": 1.2, "high": 9.5, "unit": "deg"}
    assert p.azimuth_deg == 180.0
    assert roof.building_group == "commercial"
    assert roof.setbacks.perimeter_m == pytest.approx(1.2192)


# ---------- acceptance: assumed geometry ----------

@pytest.mark.parametrize("shape", [None, "", "gambrel", "complex"])
def test_missing_or_unknown_shape_gives_assumed_with_widest_range(shape):
    roof = build_parametric_roof(_synthetic(shape), 0.0)
    (p,) = roof.planes
    assert p.geometry_source == "assumed"
    t = p.tilt_deg
    assert (t.low, t.expected, t.high) == (0.0, 28.4, 47.4)
    for s in ("flat", "gable", "hip"):
        other = build_parametric_roof(_synthetic(s), 0.0).planes[0].tilt_deg
        assert t.low <= other.low and t.high >= other.high
    assert p.area_m2 == pytest.approx(17.0 * 11.2 / math.cos(math.radians(28.4)), rel=0.02)
    assert 0 <= p.usable_area_m2 <= p.area_m2
    assert any("assumed" in n for n in roof.notes)


def test_no_footprint_polygon_gives_assumed_plane_from_area():
    vex = VexcelData(structures=[VexcelStructure(
        primary=True, footprint_area_m2=150.0,
        attributes={"roof-characteristics.shape.value": "gable"})])
    (p,) = build_parametric_roof(vex, 0.0).planes
    assert p.geometry_source == "assumed"
    assert p.area_m2 == pytest.approx(150.0 / math.cos(math.radians(28.4)), rel=0.02)


def test_no_structure_gives_no_planes():
    assert build_parametric_roof(VexcelData(), 0.0).planes == []


# ---------- acceptance: areas ----------

@pytest.mark.parametrize("shape", ["flat", "gable", "hip", None])
@pytest.mark.parametrize("dims", [(17.0, 11.2), (40.0, 12.0), (30.0, 30.0)])
def test_plane_areas_match_footprint_over_cos_tilt(shape, dims):
    roof = build_parametric_roof(_synthetic(shape, *dims), 0.0)
    fp = dims[0] * dims[1]
    tilt = roof.planes[0].tilt_deg.expected
    assert sum(p.area_m2 for p in roof.planes) == pytest.approx(fp / math.cos(math.radians(tilt)), rel=0.02)
    for p in roof.planes:
        assert 0 <= p.usable_area_m2 <= p.area_m2


def test_hip_planes_rof05_worked_example():
    roof = build_parametric_roof(_synthetic("hip"), 0.0)
    cos_b = math.cos(math.radians(28.4))
    plan = sorted(round(p.area_m2 * cos_b, 2) for p in roof.planes)
    assert plan == pytest.approx([31.36, 31.36, 63.84, 63.84], abs=0.05)
    assert sorted(p.azimuth_deg for p in roof.planes) == pytest.approx([0.0, 90.0, 180.0, 270.0], abs=0.1)


def test_gable_long_side_east_west_faces_south_and_north():
    roof = build_parametric_roof(_synthetic("gable"), 0.0)
    assert sorted(p.azimuth_deg for p in roof.planes) == pytest.approx([0.0, 180.0], abs=0.1)
    for p in roof.planes:
        assert p.area_m2 == pytest.approx(108.23, abs=0.05)               # ROOF-05 worked example
        assert p.slope_length_m == pytest.approx(6.3662, abs=1e-3)
        assert p.eave_length_m == pytest.approx(17.0, abs=1e-3)


def test_tower_floor_plate_override_caps_area():
    vex = _vexcel("office_houston")
    full = build_parametric_roof(vex, 330.0)
    tower = build_parametric_roof(vex, 330.0, roof_plan_area_m2=943.8)
    assert tower.planes[0].area_m2 == pytest.approx(943.8 / math.cos(math.radians(1.2)), rel=1e-3)
    assert tower.planes[0].usable_area_m2 < full.planes[0].usable_area_m2
    # never larger than the footprint
    bigger = build_parametric_roof(vex, 330.0, roof_plan_area_m2=1e6)
    assert bigger.planes[0].area_m2 == full.planes[0].area_m2


# ---------- acceptance: obstructions ----------

@pytest.mark.parametrize("kind", ["chimney", "roof-vent", "skylight", "ac-unit", "satellite-dish"])
@pytest.mark.parametrize("shape", ["gable", "hip", "flat"])
def test_higher_obstruction_count_lowers_usable_area(shape, kind):
    key = f"roof-objects.{kind}.count"
    few = build_parametric_roof(_synthetic(shape, **{key: 1.0}), 0.0)
    many = build_parametric_roof(_synthetic(shape, **{key: 4.0}), 0.0)
    assert sum(p.usable_area_m2 for p in many.planes) < sum(p.usable_area_m2 for p in few.planes)
    for p in many.planes:
        assert p.usable_area_m2 < next(q for q in few.planes if q.id == p.id).usable_area_m2
        assert p.obstruction_counts[kind] == 4


def test_house_obstruction_counts_lower_usable_area_against_no_counts():
    vex = _vexcel("house")
    stripped = vex.model_copy(deep=True)
    s = stripped.structures[0]
    s.attributes = {k: v for k, v in s.attributes.items() if not k.startswith("roof-objects.")}
    with_counts = build_parametric_roof(vex, 0.0)
    without = build_parametric_roof(stripped, 0.0)
    for a, b in zip(with_counts.planes, without.planes):
        assert a.usable_area_m2 < b.usable_area_m2
        assert b.obstruction_counts == {}


# ---------- acceptance: existing solar ----------

def test_solar_attribute_true_is_reported():
    roof = build_parametric_roof(_synthetic("gable", **{"roof-objects.solar.value": True}), 0.0)
    assert roof.existing_solar is True
    assert "solar" not in roof.planes[0].obstruction_counts


def test_solar_attribute_false_and_absent():
    assert build_parametric_roof(_vexcel("house"), 0.0).existing_solar is False
    assert build_parametric_roof(_vexcel("office_houston"), 0.0).existing_solar is False   # D16 structure
    assert build_parametric_roof(_synthetic("flat"), 0.0).existing_solar is None


def test_solar_panel_count_or_area_implies_existing_solar():
    roof = build_parametric_roof(_synthetic("gable", **{
        "roof-objects.solar.value": None,
        "roof-objects.solar-panel-photovoltaic.count": 12.0,
        "roof-objects.solar-panel-photovoltaic.area": 24.5}), 0.0)
    assert roof.existing_solar is True
    assert roof.existing_solar_area_m2 == 24.5


# ---------- acceptance: roof height is never used for pitch ----------

@pytest.mark.parametrize("name", FIXTURES)
@pytest.mark.parametrize("height", [-15.5, 0.36, 3.0, 47.0, None])
def test_roof_height_changes_no_tilt(name, height):
    vex = _vexcel(name)
    base = build_parametric_roof(vex, 0.0)
    changed = vex.model_copy(deep=True)
    for s in changed.structures:
        s.attributes["roof-characteristics.height"] = height
        s.attributes["roof-characteristics.elevation"] = None if height is None else 100.0 + height
        s.attributes["maximum-roof-height"] = height
        s.attributes["eave-height"] = height
    other = build_parametric_roof(changed, 0.0)
    assert [p.model_dump() for p in base.planes] == [p.model_dump() for p in other.planes]


# ---------- north offset and assumptions ----------

def test_north_offset_does_not_turn_map_coordinate_planes():
    vex = _vexcel("house")
    a = build_parametric_roof(vex, 0.0)
    b = build_parametric_roof(vex, 266.4)
    assert [p.azimuth_deg for p in a.planes] == [p.azimuth_deg for p in b.planes]


def test_unverified_inputs_are_carried_as_assumptions_with_ranges():
    roof = build_parametric_roof(_vexcel("house"), 0.0)
    keys = {a.key: a for a in roof.assumptions}
    assert {"roof.tilt_deg", "roof.ridge_direction", "roof.obstruction_allowance_m2",
            "roof.fire_setbacks", "roof.usable_area_m2"} <= set(keys)
    assert "[U]" in keys["roof.tilt_deg"].label
    assert "[U]" in keys["roof.obstruction_allowance_m2"].label
    allow = keys["roof.obstruction_allowance_m2"].value
    assert allow.low < allow.expected < allow.high
    usable = keys["roof.usable_area_m2"].value
    assert usable.expected == pytest.approx(sum(p.usable_area_m2 for p in roof.planes), abs=0.02)
    assert usable.low <= usable.expected <= usable.high
