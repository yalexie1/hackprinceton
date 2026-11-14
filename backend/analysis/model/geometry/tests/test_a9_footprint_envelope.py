"""A9 fallback for a scan with rooms but no wall graph (issue #346, physics 02 DEF-12).

Live office scans return room areas with no polygon, no boundary edges and floors with no
edges. Synthetic bundles only: a committed example bundle with its outlines and edges stripped.
"""
import math
import socket
from pathlib import Path

import pytest

from backend.schema import Assumption, BuildingModel, PropertyBundle, Ranged
from backend.analysis.model.geometry import build, build_geometry
from backend.analysis import layout

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
FOLDERS = ["house", "office", "office_houston"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A9 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def bundle(folder) -> PropertyBundle:
    return PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())


def strip(b: PropertyBundle, keep_edges: bool = False) -> PropertyBundle:
    """As the live office scans: room areas and heights, no outlines, no edge ownership."""
    mp = b.matterport
    floors = mp.floors if keep_edges else [f.model_copy(update={"edges": [], "vertices": []})
                                           for f in mp.floors]
    rooms = [r.model_copy(update={"polygon": [], "boundary_edge_ids": []}) for r in mp.rooms]
    return b.model_copy(update={"matterport": mp.model_copy(update={"floors": floors,
                                                                   "rooms": rooms})})


def geometry(b: PropertyBundle, assumptions=(), **kw):
    opts = dict(use="office", part_of_larger_building=True,
                building_stories=b.costar.stories if b.costar else None)
    opts.update(kw)
    return build_geometry(b.matterport, b.vexcel, list(assumptions), **opts)


def footprint_sides(b: PropertyBundle):
    """(length m, true azimuth) of each edge of the primary footprint, computed independently:
    equirectangular projection, outward normal from the sign of the shoelace area."""
    s = next(s for s in sorted(b.vexcel.structures, key=lambda s: not s.primary) if s.footprint_wkt)
    body = s.footprint_wkt[s.footprint_wkt.index("((") + 2:s.footprint_wkt.index(")")]
    ll = [tuple(map(float, p.split())) for p in body.split(",")]
    lat0 = sum(p[1] for p in ll[:-1]) / (len(ll) - 1)
    k = math.radians(1.0) * 6371008.8
    xy = [(lon * k * math.cos(math.radians(lat0)), lat * k) for lon, lat in ll]
    area2 = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(xy, xy[1:]))
    sides = []
    for (x0, y0), (x1, y1) in zip(xy, xy[1:]):
        dx, dy = x1 - x0, y1 - y0
        nx, ny = (dy, -dx) if area2 > 0 else (-dy, dx)
        sides.append((math.hypot(dx, dy), math.degrees(math.atan2(nx, ny)) % 360.0))
    return sides, abs(area2) / 2.0


def walls(g):
    return [s for s in g.surfaces if s.kind == "wall"]


def gross(g, s):
    return s.area_m2 + sum(c.area_m2 for c in g.surfaces if c.parent_surface_id == s.id)


# ---------------------------------------------------------------- footprint walls

def test_walls_follow_footprint_azimuths_and_scaled_length():
    b = strip(bundle("office_houston"))
    g = geometry(b)
    sides, fp_area = footprint_sides(b)
    scanned = sum(r.area_m2 for r in b.matterport.rooms)
    share = min(1.0, scanned / fp_area)
    assert 0 < share < 1
    height = sum(z.volume_m3 for z in g.zones) / sum(z.floor_area_m2 for z in g.zones)
    ws = walls(g)
    assert len(ws) == len(sides)
    assert all(w.boundary == "exterior" and w.source_edge_id is None for w in ws)
    got = sorted((round(w.azimuth_deg, 3), gross(g, w)) for w in ws)
    want = sorted((round(az, 3), length * share * height) for length, az in sides)
    for (az_g, a_g), (az_w, a_w) in zip(got, want):
        assert az_g == pytest.approx(az_w, abs=0.01)
        assert a_g == pytest.approx(a_w, rel=1e-3)


def test_windows_follow_def03_without_vision():
    b = strip(bundle("office_houston"))
    g = geometry(b)
    ext = [w for w in walls(g) if w.boundary == "exterior"]
    total_gross = sum(gross(g, w) for w in ext)
    wins = [s for s in g.surfaces if s.kind == "window"]
    assert g.window_source == "default"
    assert len(wins) == len(ext)
    assert sum(w.area_m2 for w in wins) == pytest.approx(0.30 * total_gross, rel=1e-3)
    a = next(a for a in g.assumptions if a.key == "window.area_m2")
    assert a.source == "vintage_default" and a.evidence[0].ref == "DEF-03"


def test_vision_window_area_spreads_over_footprint_walls():
    b = strip(bundle("office_houston"))
    vis = Assumption(key="window.area_m2", label="vision", source="vision", confidence=0.4,
                     value=Ranged(low=70, expected=100, high=130, unit="m2"))
    g = geometry(b, [vis])
    assert g.window_source == "vision"
    assert sum(s.area_m2 for s in g.surfaces if s.kind == "window") == pytest.approx(100, rel=1e-3)


def test_assumption_and_warning_are_recorded():
    b = strip(bundle("office_houston"))
    g = geometry(b)
    a = next(a for a in g.assumptions if a.key == "geometry.envelope_source")
    assert a.source == "vintage_default" and a.confidence <= 0.2
    assert {e.ref for e in a.evidence} >= {"footprint.wkt", "DEF-12"}
    assert any("no wall graph" in w and "footprint" in w for w in g.warnings)


def test_no_roof_and_no_ground_on_a_mid_floor_suite():
    b = strip(bundle("office_houston"))
    level = int(b.matterport.floors[0].label.split()[-1])
    assert 1 < level < b.costar.stories            # the example is a mid-floor suite
    kinds = {s.kind for s in geometry(b).surfaces}
    assert "roof" not in kinds and "floor" not in kinds


def test_ground_floor_gets_floor_with_scaled_perimeter():
    b = strip(bundle("office_houston"))
    g = geometry(b, floor_levels={b.matterport.floors[0].id: 1})
    floor = next(s for s in g.surfaces if s.kind == "floor")
    sides, fp_area = footprint_sides(b)
    share = min(1.0, sum(r.area_m2 for r in b.matterport.rooms) / fp_area)
    assert floor.boundary == "ground"
    assert floor.exposed_perimeter_m == pytest.approx(share * sum(l for l, _ in sides), rel=1e-3)
    assert "roof" not in {s.kind for s in g.surfaces}


def test_rooms_owning_no_edge_also_fall_back():
    """Edges present, but no room has an outline or boundary ids: no room owns an edge."""
    b = strip(bundle("office"), keep_edges=True)
    g = geometry(b)
    assert any(a.key == "geometry.envelope_source" for a in g.assumptions)
    assert walls(g) and all(w.source_edge_id is None for w in walls(g))


def test_no_footprint_uses_a_square_of_the_scanned_area():
    b = strip(bundle("office_houston"))
    b = b.model_copy(update={"vexcel": None})
    g = geometry(b)
    area = sum(r.area_m2 for r in b.matterport.rooms)
    height = sum(z.volume_m3 for z in g.zones) / area
    ws = walls(g)
    assert len(ws) == 4
    for w in ws:
        assert gross(g, w) == pytest.approx(math.sqrt(area) * height, rel=1e-3)
    psi = g.north_offset_deg.expected
    assert sorted(w.azimuth_deg for w in ws) == pytest.approx(
        sorted((a + psi) % 360 for a in (0, 90, 180, 270)), abs=1e-3)
    a = next(a for a in g.assumptions if a.key == "geometry.envelope_source")
    assert a.value == "square_of_scanned_area" and a.confidence < 0.2
    assert any("no Vexcel footprint" in w for w in g.warnings)


def test_a_zone_without_exterior_wall_is_never_silent():
    """One edge shared by both rooms: owned, so no fallback, but no envelope either."""
    b = bundle("house")
    fl = b.matterport.floors[0]
    e = next(e for e in fl.edges if e.type != "invisible")
    rooms = [r.model_copy(update={"polygon": [], "boundary_edge_ids": [e.id]})
             for r in b.matterport.rooms[:2]]
    mp = b.matterport.model_copy(update={"floors": [fl.model_copy(update={"edges": [e]})],
                                         "rooms": rooms})
    g = build_geometry(mp, b.vexcel, [], use="living")
    assert not walls(g)
    assert any("has no exterior wall" in w for w in g.warnings)


# ---------------------------------------------------------------- full wall graph unchanged

@pytest.mark.parametrize("folder", FOLDERS)
def test_full_wall_graph_never_takes_the_fallback(folder, monkeypatch):
    """With a wall graph the fallback is not reached, so the model is exactly as before."""
    def refuse(*a, **k):
        raise AssertionError("fallback reached on a model with a wall graph")
    monkeypatch.setattr(build, "_footprint_envelope", refuse)
    b = bundle(folder)
    fx = BuildingModel.model_validate_json((EXAMPLES / folder / "building_model.json").read_text())
    vis = [a for a in fx.assumptions if a.source == "vision"]
    office = folder != "house"
    g = build_geometry(b.matterport, b.vexcel, vis, use="office" if office else "living",
                       part_of_larger_building=office,
                       building_stories=b.costar.stories if b.costar else None)
    assert not any(a.key == "geometry.envelope_source" for a in g.assumptions)
    assert not any("no wall graph" in w or "no exterior wall" in w for w in g.warnings)
    assert all(s.source_edge_id for s in g.surfaces if s.kind == "wall")


# ---------------------------------------------------------------- LAYOUT

def test_layout_says_the_scan_has_no_room_outlines():
    b = strip(bundle("office_houston"))
    g = geometry(b)
    model = BuildingModel.model_validate_json(
        (EXAMPLES / "office_houston" / "building_model.json").read_text())
    model = model.model_copy(update={"zones": g.zones, "surfaces": g.surfaces})
    reason, text = layout.check(b, model)
    assert reason == "feasibility" and "no room outlines" in text


def test_layout_check_unchanged_with_outlines():
    b = bundle("office_houston")
    model = BuildingModel.model_validate_json(
        (EXAMPLES / "office_houston" / "building_model.json").read_text())
    res = layout.check(b, model)
    assert res is None or "room outlines" not in res[1]
