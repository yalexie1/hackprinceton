"""A9 storey of a suite whose floor label says nothing (issue #349, physics 02 DEF-13).

Live office scans name their only floor "Floor 1" even on an upper storey of a 16-storey
building. Synthetic bundles only: the Houston example with its floor relabelled.
"""
import socket
from pathlib import Path

import pytest

from backend.schema import PropertyBundle
from backend.analysis.model.geometry import build, build_geometry

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A9 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def houston(label) -> PropertyBundle:
    b = PropertyBundle.model_validate_json(
        (EXAMPLES / "office_houston" / "property_bundle.json").read_text())
    mp = b.matterport
    floors = [f.model_copy(update={"label": label}) for f in mp.floors]
    return b.model_copy(update={"matterport": mp.model_copy(update={"floors": floors})})


def geometry(b: PropertyBundle, stories, part_of_larger_building=True):
    return build_geometry(b.matterport, b.vexcel, [], use="office",
                          part_of_larger_building=part_of_larger_building, building_stories=stories)


def kinds(g):
    return {(s.kind, s.boundary) for s in g.surfaces if s.kind in ("roof", "floor")}


def storey(g):
    return next((a for a in g.assumptions if a.key == "geometry.storey"), None)


@pytest.mark.parametrize("label", ["Floor 1", "1", None, "", "floor 01"])
def test_generic_label_in_16_storey_building_is_mid_building(label):
    g = geometry(houston(label), 16)
    assert kinds(g) == set()                     # no ground floor, no roof
    a = storey(g)
    assert a is not None and a.value == "unknown_mid_building"
    assert a.confidence <= 0.3 and a.user_editable and a.source == "vintage_default"
    refs = {e.ref for e in a.evidence}
    assert refs >= {"floors.label", "stories", "footprint.wkt", "DEF-13"}
    share = next(e.note for e in a.evidence if e.ref == "footprint.wkt")
    assert "below 0.95" in share
    assert any("DEF-13" in w and "16 storeys" in w for w in g.warnings)


def test_numbered_label_keeps_existing_rule():
    g = geometry(houston("Floor 3"), 3)          # the top of a 3-storey building: roof, no ground
    assert kinds(g) == {("roof", "exterior")}
    assert storey(g) is None
    g = geometry(houston("Floor 3"), 16)         # a middle storey by its label
    assert kinds(g) == set() and storey(g) is None


def test_single_storey_building_keeps_ground_floor():
    g = geometry(houston("Floor 1"), 1)
    assert kinds(g) == {("roof", "exterior"), ("floor", "ground")}
    assert storey(g) is None


def test_detached_building_keeps_ground_floor():
    g = geometry(houston("Floor 1"), 2, part_of_larger_building=False)
    assert ("floor", "ground") in kinds(g) and storey(g) is None


def test_scan_covering_the_footprint_keeps_ground_floor(monkeypatch):
    monkeypatch.setattr(build, "MID_BUILDING_MAX_SHARE", 0.0)
    g = geometry(houston("Floor 1"), 16)
    assert kinds(g) == {("floor", "ground")} and storey(g) is None


def test_no_footprint_keeps_existing_rule():
    b = houston("Floor 1").model_copy(update={"vexcel": None})
    g = geometry(b, 16)
    assert ("floor", "ground") in kinds(g) and storey(g) is None


def test_floor_levels_override_the_rule():
    b = houston("Floor 1")
    fid = b.matterport.floors[0].id
    g = build_geometry(b.matterport, b.vexcel, [], use="office", part_of_larger_building=True,
                       building_stories=16, floor_levels={fid: 1})
    assert ("floor", "ground") in kinds(g) and storey(g) is None
