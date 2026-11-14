"""A5 geometry: azimuth convention, opening placement, window rectangles (T-GEO-1, T-GEO-2)."""
import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.schema import BuildingModel, Floor, Opening, PropertyBundle, Room, Surface, Vertex, WallEdge, Ranged
from backend.analysis.physics.daylight.geometry import (azimuth_in_model, azimuth_true, opening_centre,
                                                        outward_normal, room_windows, wrap180)

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A5 tests must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def load(folder):
    b = PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())
    m = BuildingModel.model_validate_json((EXAMPLES / folder / "building_model.json").read_text())
    return b, m


# ---- T-GEO-1
def test_azimuth_convention():
    assert azimuth_true(0, -1, 30) == pytest.approx(210)
    assert azimuth_true(1, 0, 30) == pytest.approx(120)
    assert wrap180(230 - 210) == pytest.approx(20)


def test_azimuth_against_scipy_rotation():
    Rotation = pytest.importorskip("scipy.spatial.transform").Rotation
    rng = np.random.default_rng(0)
    for _ in range(1000):
        v = rng.normal(size=2)
        off = rng.uniform(0, 360)
        # model +y points at compass azimuth `off`: rotating a model vector clockwise by `off`
        # about +z (negative mathematical angle) gives its (east, north) components
        e, n, _ = Rotation.from_euler("z", -off, degrees=True).apply([v[0], v[1], 0.0])
        want = math.degrees(math.atan2(e, n)) % 360
        got = azimuth_true(v[0], v[1], off)
        assert abs(wrap180(got - want)) < 1e-9


# ---- T-GEO-2
def test_opening_centre_readings():
    a, b = (2.0, 1.0), (6.0, 1.0)
    assert opening_centre(a, b, 0.3) == pytest.approx((3.2, 1.0), abs=1e-9)
    assert opening_centre(a, b, 0.3, "second") == pytest.approx((4.8, 1.0), abs=1e-9)
    assert opening_centre(a, b, 0.5) == pytest.approx(opening_centre(a, b, 0.5, "second"))
    for bad in (-0.1, 1.2, float("nan")):
        with pytest.raises(ValueError):
            opening_centre(a, b, bad)
    with pytest.raises(ValueError):
        opening_centre(a, b, 0.3, "middle")


def test_outward_normal_uses_polygon():
    room = Room(id="r", floor_id="f", polygon=[(0, 0), (4, 0), (4, 6), (0, 6)])
    assert outward_normal((0, 0), (4, 0), room) == pytest.approx((0, -1))
    assert outward_normal((4, 0), (0, 0), room) == pytest.approx((0, -1))
    assert outward_normal((4, 0), (4, 6), room) == pytest.approx((1, 0))


def test_house_measured_windows():
    b, m = load("house")
    fl = b.matterport.floors[0]
    living = next(r for r in b.matterport.rooms if r.id == "room_living")
    wins, src, north, warn = room_windows(living, fl, m.surfaces)
    assert src == "measured"
    assert north == pytest.approx(m.north_offset_deg.expected, abs=1e-6)
    w = next(x for x in wins if x.id == "op_e01_1")
    assert w.centre == pytest.approx((0.2 * 5.04, 0.0))
    assert w.normal == pytest.approx((0.0, -1.0))
    assert (w.width_m, w.z1, w.z2) == pytest.approx((1.2, 0.9, 2.1))
    assert w.azimuth_deg == pytest.approx(86.4, abs=1e-6)        # = Surface.azimuth_deg built by A9
    assert w.tau == (0.4, 0.68, 0.8) and w.surface_id == "surf_win_e01_1"
    assert {x.id for x in wins} == {"op_e01_1", "op_e13_1", "op_e13_2"}   # doorways are not glazing
    w2, *_ = room_windows(living, fl, m.surfaces, relative_center_from="second")
    assert next(x for x in w2 if x.id == "op_e01_1").centre == pytest.approx((0.8 * 5.04, 0.0))
    # the bedroom has only a vision window, centred on its edge with a 0.9 m sill
    bed = next(r for r in b.matterport.rooms if r.id == "room_bedroom")
    wb, src_b, _, warn_b = room_windows(bed, fl, m.surfaces)
    assert src_b == "vision" and len(wb) == 1
    assert wb[0].source == "vision" and wb[0].z1 == 0.9
    assert wb[0].area_m2 == pytest.approx(1.5)
    assert any("no ceiling height" in x for x in warn_b)


def test_office_vision_windows_fit_their_edges():
    b, m = load("office")
    fl = b.matterport.floors[0]
    xy = {v.id: (v.x, v.y) for v in fl.vertices}
    for room in b.matterport.rooms:
        wins, src, north, _ = room_windows(room, fl, m.surfaces)
        if wins:
            assert north == pytest.approx(m.north_offset_deg.expected, abs=0.05)
        for w in wins:
            assert w.source == "vision"
            s = next(x for x in m.surfaces if x.id == w.id)
            assert w.width_m <= w.edge_length_m + 1e-9
            assert w.z1 == 0.9 and w.z2 <= (room.height_m or 2.7) + 1e-9
            assert w.area_m2 == pytest.approx(s.area_m2, rel=1e-6)
            assert abs(wrap180(w.azimuth_deg - s.azimuth_deg)) < 0.05


def test_window_on_edge_wider_than_area_allows_is_clipped():
    fl = Floor(id="f", label="1", vertices=[Vertex(id="a", x=0, y=0), Vertex(id="b", x=2, y=0),
                                            Vertex(id="c", x=2, y=2), Vertex(id="d", x=0, y=2)],
               edges=[WallEdge(id="e1", type="wall", vertex_ids=("a", "b"))])
    room = Room(id="r", floor_id="f", height_m=2.5, polygon=[(0, 0), (2, 0), (2, 2), (0, 2)],
                boundary_edge_ids=["e1"])
    s = Surface(id="w", zone_id="z", kind="window", boundary="exterior", area_m2=10.0,
                azimuth_deg=180.0, tilt_deg=90, u_value=Ranged(low=2, expected=3, high=4, unit="W/m2K"),
                source_edge_id="e1")
    wins, src, north, warn = room_windows(room, fl, [s])
    assert wins[0].width_m == 2.0 and wins[0].z2 == pytest.approx(2.5)
    assert any("does not fit" in x for x in warn)
