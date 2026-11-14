"""A9 true north: ROOF-02, georeference cross-checked by the footprint, and the fallbacks."""
import math
import socket
from pathlib import Path

import numpy as np
import pytest

from backend.schema import BuildingModel, PropertyBundle, Quaternion
from backend.analysis.model.geometry import (build_geometry, inverse_north_offset,
                                             quaternion_north_offset, resolve_north)
from backend.analysis.model.geometry.north import rotation_matrix

EXAMPLES = Path(__file__).resolve().parents[5] / "specs" / "examples"
FOLDERS = ["house", "office", "office_houston"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("A9 must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def bundle(folder: str) -> PropertyBundle:
    return PropertyBundle.model_validate_json((EXAMPLES / folder / "property_bundle.json").read_text())


def fixture_model(folder: str) -> BuildingModel:
    return BuildingModel.model_validate_json((EXAMPLES / folder / "building_model.json").read_text())


def yaw(q: Quaternion, deg: float) -> Quaternion:
    """q followed by an extra turn about z (a level model turned by deg)."""
    h = math.radians(deg) / 2.0
    w2, z2 = math.cos(h), math.sin(h)
    return Quaternion(w=w2 * q.w - z2 * q.z, x=w2 * q.x - z2 * q.y,
                      y=w2 * q.y + z2 * q.x, z=w2 * q.z + z2 * q.w)


# ---------------------------------------------------------------- ROOF-02

def test_roof02_worked_example():
    h = math.radians(-12.5)
    q = Quaternion(w=math.cos(h), x=0, y=0, z=math.sin(h))
    psi = quaternion_north_offset(q)
    assert psi == pytest.approx(25.0, abs=1e-9)
    assert (180.0 + psi) % 360 == pytest.approx(205.0, abs=1e-9)   # "model south" plane


def test_roof02_matrix_matches_scipy():
    from scipy.spatial.transform import Rotation
    rng = np.random.default_rng(7)
    for _ in range(5):
        x, y, z, w = rng.normal(size=4)
        ours = np.array(rotation_matrix(Quaternion(x=x, y=y, z=z, w=w)))
        ref = Rotation.from_quat([x, y, z, w]).as_matrix()
        assert np.allclose(ours, ref, atol=1e-12)


def test_inverse_reading_is_the_mirror_for_a_level_model():
    q = bundle("house").matterport.georeference.rotation
    assert inverse_north_offset(q) == pytest.approx(360 - quaternion_north_offset(q), abs=1e-9)


# ---------------------------------------------------------------- source selection

@pytest.mark.parametrize("folder", FOLDERS)
def test_with_georeference_source_is_georeference(folder):
    b = bundle(folder)
    r = resolve_north(b.matterport, b.vexcel)
    assert r.source == "georeference"
    q = b.matterport.georeference.rotation
    r01, r11 = 2 * (q.x * q.y - q.w * q.z), 1 - 2 * (q.x ** 2 + q.z ** 2)
    assert r.offset.expected == pytest.approx(math.degrees(math.atan2(r01, r11)) % 360, abs=0.01)
    fx = fixture_model(folder)
    assert fx.north_source == "georeference"
    assert r.offset.expected == pytest.approx(fx.north_offset_deg.expected, abs=0.05)
    assert r.offset.low < r.offset.expected < r.offset.high
    assert r.delta_deg is not None and r.delta_deg < 1.0          # footprint agrees
    assert r.assumption.key == "geometry.north_offset_deg" and r.assumption.source == "measured"
    g = build_geometry(b.matterport, b.vexcel)
    assert g.north_source == "georeference"


@pytest.mark.parametrize("folder", FOLDERS)
def test_disagreeing_georeference_falls_back_to_footprint_with_wider_range(folder):
    b = bundle(folder)
    good = resolve_north(b.matterport, b.vexcel)
    geo = b.matterport.georeference
    bad = geo.model_copy(update={"rotation": yaw(geo.rotation, 30.0)})
    mp = b.matterport.model_copy(update={"georeference": bad})
    r = resolve_north(mp, b.vexcel)
    assert r.source == "footprint_registration"
    assert (r.offset.high - r.offset.low) > (good.offset.high - good.offset.low)
    # the footprint keeps the true orientation (mod 90), the wrong quaternion does not move it
    assert abs(((r.offset.expected - good.offset.expected) + 45) % 90 - 45) < 0.5
    assert r.warnings
    assert build_geometry(mp, b.vexcel).north_source == "footprint_registration"


@pytest.mark.parametrize("folder", FOLDERS)
def test_absent_georeference_registers_to_footprint(folder):
    b = bundle(folder)
    good = resolve_north(b.matterport, b.vexcel)
    mp = b.matterport.model_copy(update={"georeference": None})
    r = resolve_north(mp, b.vexcel)
    assert r.source == "footprint_registration"
    assert (r.offset.high - r.offset.low) > (good.offset.high - good.offset.low)
    assert abs(((r.offset.expected - good.offset.expected) + 45) % 90 - 45) < 0.5
    assert r.assumption.source == "vexcel" and r.assumption.confidence < good.assumption.confidence
    g = build_geometry(mp, b.vexcel)
    assert g.north_source == "footprint_registration"
    assert g.north_offset_deg == r.offset


@pytest.mark.parametrize("folder", FOLDERS)
def test_no_georeference_and_no_footprint_is_assumed(folder):
    b = bundle(folder)
    mp = b.matterport.model_copy(update={"georeference": None})
    for vex in (None, b.vexcel.model_copy(update={"structures": []})):
        r = resolve_north(mp, vex)
        assert r.source == "assumed"
        assert r.offset.high - r.offset.low == pytest.approx(360.0)
        assert build_geometry(mp, vex).north_source == "assumed"


def test_georeference_without_footprint_is_kept_but_widened():
    b = bundle("house")
    checked = resolve_north(b.matterport, b.vexcel)
    r = resolve_north(b.matterport, None)
    assert r.source == "georeference"
    assert r.offset.expected == pytest.approx(checked.offset.expected)
    assert (r.offset.high - r.offset.low) > (checked.offset.high - checked.offset.low)
    assert "unconfirmed" in r.assumption.evidence[0].note


def test_inverse_quaternion_reading_is_detected():
    """If Matterport's quaternion turned out to rotate ENU -> model, the cross-check says so."""
    b = bundle("office_houston")
    geo = b.matterport.georeference
    q = geo.rotation
    flipped = geo.model_copy(update={"rotation": Quaternion(x=-q.x, y=-q.y, z=-q.z, w=q.w)})
    mp = b.matterport.model_copy(update={"georeference": flipped})
    r = resolve_north(mp, b.vexcel)
    assert r.source == "footprint_registration"
    assert r.offset.expected == pytest.approx(330.0, abs=0.5)
    assert "inverse" in r.assumption.evidence[0].note
