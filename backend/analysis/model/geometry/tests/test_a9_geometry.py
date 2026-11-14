"""A9 zones and surfaces from the wall graph (workplan 4.2, adapted to the fixtures).

The A9 row was written before the fixtures settled: it puts measured windows on the office and
vision windows on the house. The fixtures (and SPEC 5.1) have it the other way round: the house
has measured window openings, the two offices have none and take windows from vision. The tests
below follow the fixtures.
"""
import math
import socket
from pathlib import Path

import pytest

from backend.schema import (Assumption, BuildingModel, EvidenceRef, PropertyBundle, Ranged)
from backend.analysis.model.geometry import build_geometry, opening_center

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
FOLDERS = ["house", "office", "office_houston"]
OPTIONS = {
    "house": dict(use="living", part_of_larger_building=False),
    "office": dict(use="office", part_of_larger_building=True),
    "office_houston": dict(use="office", part_of_larger_building=True),
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A9 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def bundle(folder):
    return PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())


def fixture_model(folder):
    return BuildingModel.model_validate_json((EXAMPLES / folder / "building_model.json").read_text())


def vision(folder):
    """The fixture's vision assumptions stand in for A7's output."""
    return [a for a in fixture_model(folder).assumptions if a.source == "vision"]


def build(folder, assumptions=None, **kw):
    b = bundle(folder)
    opts = dict(OPTIONS[folder], building_stories=b.costar.stories if b.costar else None)
    opts.update(kw)
    return b, build_geometry(b.matterport, b.vexcel,
                             vision(folder) if assumptions is None else assumptions, **opts)


def windows(g):
    return [s for s in g.surfaces if s.kind == "window"]


# ---------------------------------------------------------------- zones

def test_house_zone_areas_sum_to_room_areas():
    b, g = build("house")
    rooms = sum(r.area_m2 for r in b.matterport.rooms)
    assert sum(z.floor_area_m2 for z in g.zones) == pytest.approx(rooms, rel=0.01)
    assert {rid for z in g.zones for rid in z.room_ids} == {r.id for r in b.matterport.rooms}


@pytest.mark.parametrize("folder", FOLDERS)
def test_zones_match_fixture_and_every_surface_names_a_zone(folder):
    b, g = build(folder)
    zone_ids = {z.id for z in g.zones}
    assert all(s.zone_id in zone_ids for s in g.surfaces)
    fx = fixture_model(folder)
    assert sum(z.floor_area_m2 for z in g.zones) == pytest.approx(
        sum(z.floor_area_m2 for z in fx.zones), rel=0.01)
    assert sum(z.volume_m3 for z in g.zones) == pytest.approx(
        sum(z.volume_m3 for z in fx.zones), rel=0.01)
    ids = [s.id for s in g.surfaces]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- measured windows (house)

def test_house_each_window_opening_is_one_window_surface():
    b, g = build("house")
    walls = {s.id: s for s in g.surfaces if s.kind == "wall"}
    openings = {o.id: (e, o) for fl in b.matterport.floors for e in fl.edges for o in e.openings
                if o.type == "window"}
    measured = [s for s in windows(g) if s.source_opening_id]
    assert len(measured) == len(openings) == 7
    assert {s.source_opening_id for s in measured} == set(openings)
    for s in measured:
        edge, o = openings[s.source_opening_id]
        assert s.area_m2 == pytest.approx(o.width_m * o.height_m, abs=1e-6)
        assert s.parent_surface_id in walls
        assert walls[s.parent_surface_id].source_edge_id == edge.id == s.source_edge_id
        assert s.azimuth_deg == walls[s.parent_surface_id].azimuth_deg
        assert s.shgc is not None and s.visible_transmittance is not None
    assert g.window_source == "measured"
    measured_total = next(a for a in g.assumptions if a.key == "window.area_m2")
    assert measured_total.source == "measured"


def test_house_exterior_doorway_is_a_door_and_interior_walls_get_no_surface():
    b, g = build("house")
    doors = [s for s in g.surfaces if s.kind == "door"]
    assert [d.source_opening_id for d in doors] == ["op_e01_2"]
    edges_with_surface = {s.source_edge_id for s in g.surfaces if s.kind == "wall"}
    assert not edges_with_surface & {"e08", "e09", "e10", "e12"}   # invisible and interior


def test_house_vision_window_only_for_the_room_without_openings():
    """The bedroom has no window opening; its vision reading builds the one vision window."""
    b, g = build("house")
    from_vision = [s for s in windows(g) if s.source_opening_id is None]
    assert len(from_vision) == 1 and from_vision[0].area_m2 == pytest.approx(1.5)
    wall_room = {"e14", "e15", "e16"}                                # the bedroom's exterior
    assert from_vision[0].source_edge_id in wall_room


def test_vision_never_replaces_measured_openings():
    extra = Assumption(key="window.area_m2", label="vision total",
                       value=Ranged(low=7, expected=10, high=13, unit="m2"), source="vision",
                       confidence=0.5)
    b, g = build("house", assumptions=[extra])
    assert all(s.source_opening_id for s in windows(g))
    assert any("cross-check" in w for w in g.warnings)


def test_vision_window_on_an_edge_named_in_evidence():
    a = next(a for a in vision("house") if a.key == "window.room_bedroom.area_m2")
    a = a.model_copy(update={"evidence": a.evidence + [EvidenceRef(kind="matterport_field",
                                                                    ref="e16")]})
    _, g = build("house", assumptions=[a])
    v = [s for s in windows(g) if s.source_opening_id is None]
    assert [s.source_edge_id for s in v] == ["e16"]


# ---------------------------------------------------------------- vision windows (offices)

@pytest.mark.parametrize("folder", ["office", "office_houston"])
def test_office_windows_come_from_vision(folder):
    b, g = build(folder)
    assert not any(o.type == "window" for fl in b.matterport.floors for e in fl.edges
                   for o in e.openings)
    ws = windows(g)
    assert ws and all(s.source_opening_id is None for s in ws)
    assert g.window_source == "vision"
    total = next(a for a in vision(folder) if a.key == "window.area_m2").value.expected
    assert sum(s.area_m2 for s in ws) == pytest.approx(total, rel=1e-6)
    walls = {s.id: s for s in g.surfaces if s.kind == "wall"}
    for s in ws:
        assert walls[s.parent_surface_id].boundary == "exterior"
        assert walls[s.parent_surface_id].source_edge_id == s.source_edge_id
    fx_edges = {s.source_edge_id for s in fixture_model(folder).surfaces if s.kind == "window"}
    assert {s.source_edge_id for s in ws} == fx_edges


@pytest.mark.parametrize("folder", ["office", "office_houston"])
def test_office_without_vision_uses_the_default_ratio(folder):
    _, g = build(folder, assumptions=[])
    ws = windows(g)
    assert ws and all(s.source_opening_id is None for s in ws)
    assert g.window_source == "default"
    a = next(a for a in g.assumptions if a.key == "window.area_m2")
    assert a.source == "vintage_default"
    ext = sum(s.area_m2 for s in g.surfaces if s.kind == "wall" and s.boundary == "exterior")
    assert sum(s.area_m2 for s in ws) / (ext + sum(s.area_m2 for s in ws)) == pytest.approx(0.30)


# ---------------------------------------------------------------- walls, roof, floor

@pytest.mark.parametrize("folder", FOLDERS)
def test_surfaces_match_fixture_boundaries_and_azimuths(folder):
    _, g = build(folder)
    fx = {s.source_edge_id: s for s in fixture_model(folder).surfaces if s.kind == "wall"}
    ours = {s.source_edge_id: s for s in g.surfaces if s.kind == "wall"}
    assert set(ours) == set(fx)
    for e, s in ours.items():
        assert s.boundary == fx[e].boundary
        assert abs((s.azimuth_deg - fx[e].azimuth_deg + 180) % 360 - 180) < 0.1
    assert {s.kind for s in g.surfaces if s.source_edge_id is None} == \
        {s.kind for s in fixture_model(folder).surfaces if s.source_edge_id is None}


@pytest.mark.parametrize("folder", FOLDERS)
def test_wall_net_area_plus_openings_is_gross(folder):
    b, g = build(folder)
    xy = {v.id: (v.x, v.y) for fl in b.matterport.floors for v in fl.vertices}
    edges = {e.id: e for fl in b.matterport.floors for e in fl.edges}
    psi = g.north_offset_deg.expected
    heights = next(a for a in g.assumptions if a.key == "geometry.ceiling_height_m")
    for wall in (s for s in g.surfaces if s.kind == "wall"):
        e = edges[wall.source_edge_id]
        (x0, y0), (x1, y1) = (xy[v] for v in e.vertex_ids)
        along = math.degrees(math.atan2(x1 - x0, y1 - y0)) + psi
        assert abs((wall.azimuth_deg - along) % 180 - 90) < 1e-3          # perpendicular
        kids = sum(s.area_m2 for s in g.surfaces if s.parent_surface_id == wall.id)
        room = next(r for r in b.matterport.rooms if e.id in r.boundary_edge_ids)
        height = room.height_m or heights.value.expected
        assert wall.area_m2 + kids == pytest.approx(math.dist((x0, y0), (x1, y1)) * height,
                                                    abs=0.01)
        assert wall.tilt_deg == 90.0


def test_roof_and_ground_floor_by_storey():
    _, house = build("house")
    assert {s.kind for s in house.surfaces} >= {"roof", "floor"}
    floor = next(s for s in house.surfaces if s.kind == "floor")
    assert floor.boundary == "ground"
    assert floor.exposed_perimeter_m == pytest.approx(43.32, abs=0.01)
    _, la = build("office")                       # floor 4 of 4: the roof, no slab
    assert [s.kind for s in la.surfaces if s.kind in ("roof", "floor")] == ["roof"]
    assert next(s for s in la.surfaces if s.kind == "roof").area_m2 == pytest.approx(2312.0)
    _, hou = build("office_houston")              # floor 5 of 16: neither
    assert not [s for s in hou.surfaces if s.kind in ("roof", "floor")]


def test_bedroom_without_height_uses_mean_of_measured_rooms():
    _, g = build("house")
    h = next(a for a in g.assumptions if a.key == "geometry.ceiling_height_m")
    assert h.value.expected == pytest.approx(2.69, abs=0.005)
    assert "room_bedroom" in h.evidence[0].note


def test_envelope_properties_come_from_assumptions():
    u = Assumption(key="wall.u_value", label="Wall U", source="vintage_default", confidence=0.4,
                   value=Ranged(low=0.6, expected=2.0, high=2.0, unit="W/m2K"))
    _, g = build("house", assumptions=vision("house") + [u])
    ext_walls = [s for s in g.surfaces if s.kind == "wall" and s.boundary == "exterior"]
    assert all(s.u_value == u.value for s in ext_walls)
    assert not any("wall.u_value" in w for w in g.warnings)


def test_inputs_are_not_changed_and_output_is_repeatable():
    b = bundle("house")
    before = b.model_dump_json()
    one = build_geometry(b.matterport, b.vexcel, vision("house"))
    two = build_geometry(b.matterport, b.vexcel, vision("house"))
    assert b.model_dump_json() == before
    assert [s.model_dump() for s in one.surfaces] == [s.model_dump() for s in two.surfaces]


def test_opening_center_carries_both_readings():
    b = bundle("house")
    fl = b.matterport.floors[0]
    xy = {v.id: (v.x, v.y) for v in fl.vertices}
    e = next(e for e in fl.edges if e.id == "e01")
    o = e.openings[0]                              # relative_center 0.2 on a 5.04 m edge
    first, second = opening_center(xy[e.vertex_ids[0]], xy[e.vertex_ids[1]], o)
    assert first == pytest.approx((1.008, 0.0))
    assert second == pytest.approx((4.032, 0.0))
