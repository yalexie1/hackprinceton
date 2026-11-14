"""Tests for package D2 (the Matterport Model API client).

The offline set injects a fake `post`, so no transport and no keys are needed and
the shapes come from responses actually observed on 2026-11-14. The live set runs
only when a working key set is in the environment.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.data_layer import matterport as mp
from backend.schema import MatterportData

# Shaped exactly like the real response for the golden house, trimmed.
HOUSE = {
    "model": {
        "id": "zvKHR9DHNjJ",
        "name": "5836 La Mirada Ave",
        "geocoordinates": {
            "latitude": 34.093491666999995, "longitude": -118.3171, "altitude": 120.2,
            "source": "processing",
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.7289895896353398, "w": 0.6845247827531877},
        },
        "floors": [{
            "id": "f1", "label": "Floor 1",
            "vertices": [{"id": "v1", "position": {"x": 0.0, "y": 0.0}},
                         {"id": "v2", "position": {"x": 5.023, "y": 0.0}},
                         {"id": "v3", "position": {"x": 5.023, "y": 3.0}}],
            "edges": [
                {"id": "e1", "type": "wall", "thickness": 0.16,
                 "vertices": [{"id": "v1"}, {"id": "v2"}],
                 "openings": [{"id": "o1", "type": "doorway", "width": 2.495,
                               "height": 2.102, "lowerElevation": 0.001,
                               "relativeCenter": 0.5069}]},
                {"id": "e2", "type": "wall", "thickness": 0.28,
                 "vertices": [{"id": "v2"}, {"id": "v3"}],
                 "openings": [{"id": "o2", "type": "window", "width": 1.053,
                               "height": 1.22, "lowerElevation": 0.86,
                               "relativeCenter": 0.7702}]},
                {"id": "e3", "type": "invisible", "vertices": [{"id": "v1"}]},  # dropped
            ],
        }],
        "rooms": [{
            "id": "r1", "floor": {"id": "f1"},
            "classifications": [{"label": "Kitchen", "confidence": 0.4},
                                {"label": "Living Room", "confidence": 0.91}],
            "boundary": {"edges": [{"id": "e1"}, {"id": "e2"}]},
            "dimensions": {"areaFloor": 28.87, "width": 5.0, "depth": 5.8, "height": 2.6},
        }],
        "panoLocations": [{"id": "p1", "label": "Entry",
                           "position": {"x": 1.0, "y": 2.0, "z": 1.5}}],
        "assets": {"floorplans": [{"format": "PNG", "flags": ["labels"],
                                   "resolution": 100.0, "origin": {"x": -1.0, "y": -2.0}}]},
        "bundle": {"availability": "unlocked"},
        "view": {"id": "defurn-1"},
    }
}

# An office: no openings, empty classifications, altitude 0.0, negative rotation z,
# no defurnished view - all measured on the real golden offices.
OFFICE = {
    "model": {
        "id": "jfiEvosX974", "name": "Executive Tower - Suite 140",
        "geocoordinates": {
            "latitude": 34.036533907520074, "longitude": -118.44311817454468,
            "altitude": 0.0, "source": "processing",
            "rotation": {"x": 0.0, "y": 0.0, "z": -0.3548537414, "w": 0.9349218268},
        },
        "floors": [{"id": "f1", "label": "Floor 1",
                    "vertices": [{"id": "v1", "position": {"x": 0.0, "y": 0.0}},
                                 {"id": "v2", "position": {"x": 10.0, "y": 0.0}}],
                    "edges": [{"id": "e1", "type": "wall", "thickness": 0.2,
                               "vertices": [{"id": "v1"}, {"id": "v2"}]}]}],
        "rooms": [{"id": "r1", "floor": {"id": "f1"}, "classifications": [],
                   "dimensions": {"areaFloor": 157.82, "width": 1.46, "depth": 1.34,
                                  "height": 3.18}}],
        "panoLocations": [{"id": "p1", "position": {"x": 0.0, "y": 0.0, "z": 1.6}}],
        "assets": {},
        "bundle": {"availability": "locked"},
    }
}


def _poster(payload, errors=None):
    """Posters return the whole GraphQL body, as the real transport does."""
    body = {"data": payload}
    if errors:
        body["errors"] = errors
    return lambda query, variables: body


# ---------- offline ----------

def test_house_maps_fully():
    d = mp.get_matterport_data("zvKHR9DHNjJ", post=_poster(HOUSE))
    MatterportData.model_validate(d.model_dump(mode="json"))
    g = d.georeference
    assert g and g.source == "processing"
    assert g.rotation.z == pytest.approx(0.7289895896353398)
    assert g.altitude_m == 120.2
    assert d.defurnished_view_id == "defurn-1" and d.matterpak_available is True


def test_openings_are_mapped_with_sill_and_fraction():
    d = mp.get_matterport_data("zvKHR9DHNjJ", post=_poster(HOUSE))
    ops = {o.type: o for e in d.floors[0].edges for o in e.openings}
    assert set(ops) == {"doorway", "window"}
    win = ops["window"]
    assert win.width_m == 1.053 and win.height_m == 1.22
    assert win.lower_elevation_m == 0.86          # sill height, metres
    assert 0.0 <= win.relative_center <= 1.0      # a fraction, never metres


def test_edge_without_both_ends_is_dropped():
    d = mp.get_matterport_data("zvKHR9DHNjJ", post=_poster(HOUSE))
    assert {e.id for e in d.floors[0].edges} == {"e1", "e2"}   # e3 had one vertex


def test_room_label_takes_the_most_confident_classification():
    d = mp.get_matterport_data("zvKHR9DHNjJ", post=_poster(HOUSE))
    assert d.rooms[0].label == "Living Room" and d.rooms[0].label_confidence == 0.91
    assert d.rooms[0].boundary_edge_ids == ["e1", "e2"]


def test_office_shape_commercial_gaps():
    d = mp.get_matterport_data("jfiEvosX974", post=_poster(OFFICE))
    MatterportData.model_validate(d.model_dump(mode="json"))
    assert all(not e.openings for e in d.floors[0].edges)      # no openings at all
    assert d.rooms[0].label is None                            # classifications empty
    assert d.georeference.altitude_m == 0.0                    # unusable, carried anyway
    assert d.georeference.rotation.z < 0                       # z may be either sign
    assert d.defurnished_view_id is None
    assert d.matterpak_available is False                      # "locked"
    assert d.panos[0].defurnished_face_paths == []


def test_area_is_trusted_over_width_times_depth():
    """areaFloor 157.82 contradicts 1.46 x 1.34; both are carried, area is the truth."""
    d = mp.get_matterport_data("jfiEvosX974", post=_poster(OFFICE))
    r = d.rooms[0]
    assert r.area_m2 == 157.82
    assert r.width_m * r.depth_m < r.area_m2 / 10


def test_asset_fields_are_cache_paths_never_urls():
    d = mp.get_matterport_data("zvKHR9DHNjJ", post=_poster(HOUSE))
    paths = [*d.panos[0].face_paths, *d.panos[0].defurnished_face_paths,
             *(f.path for f in d.floorplans)]
    assert paths
    for p in paths:
        assert p.startswith("data/cache/zvKHR9DHNjJ/")
        assert "http" not in p and "X-Amz" not in p
    assert len(d.panos[0].face_paths) == 6          # up, four sides, down
    assert d.mesh_path is None and d.point_cloud_path is None


def test_unknown_model_raises_lookuperror():
    with pytest.raises(LookupError):
        mp.get_matterport_data("NOPE", post=_poster({"model": None}))


def test_field_scoped_error_with_usable_data_is_a_note_not_a_failure():
    """Verified live: asking for a defurnished view a model lacks returns BOTH a
    not.found error on path ["model","view"] AND a fully populated model."""
    errors = [{"message": "Error fetching data (path: /model/view, code: not.found)",
               "path": ["model", "view"],
               "extensions": {"code": "not.found", "httpCode": 404}}]
    data, notes = mp.get_matterport_data_with_notes(
        "jfiEvosX974", post=_poster(OFFICE, errors))
    assert data.rooms and data.defurnished_view_id is None     # the data survived
    assert len(notes) == 1
    assert notes[0].layer == "matterport" and notes[0].what == "model.view"
    assert notes[0].status == "missing"                        # normal, not an error


def test_non_not_found_errors_are_recorded_as_errors():
    errors = [{"message": "boom", "path": ["model", "rooms"],
               "extensions": {"code": "internal"}}]
    _, notes = mp.get_matterport_data_with_notes("x", post=_poster(OFFICE, errors))
    assert notes[0].status == "error" and notes[0].what == "model.rooms"


def test_missing_model_with_errors_still_raises():
    errors = [{"message": "nope", "path": ["model"], "extensions": {"code": "not.found"}}]
    with pytest.raises(LookupError):
        mp.get_matterport_data("NOPE", post=_poster({"model": None}, errors))


def test_absent_fields_are_tolerated():
    """The API omits null fields rather than sending null."""
    d = mp.get_matterport_data("x", post=_poster({"model": {"id": "x", "floors": [], "rooms": []}}))
    assert d.georeference is None and d.panos == [] and d.floorplans == []
    assert d.matterpak_available is False


def test_georeference_needs_a_full_quaternion():
    bad = {"model": {"id": "x", "floors": [], "rooms": [],
                     "geocoordinates": {"latitude": 1.0, "longitude": 2.0,
                                        "rotation": {"x": 0.0, "y": 0.0}}}}
    assert mp.get_matterport_data("x", post=_poster(bad)).georeference is None


def test_the_query_document_is_a_query_and_names_no_mutation():
    """The schema exposes writes against live shared sponsor data. Queries only.

    Asserted against the GraphQL document rather than the whole file, so the module
    is still free to name the forbidden mutations in prose that warns about them.
    """
    doc = mp.MODEL_QUERY
    assert doc.strip().startswith("query ")
    assert "mutation" not in doc
    for forbidden in ("patchModelGeoCoordinates", "resetModelGeoCoordinates",
                      "updateModelAddress", "addEdgeOpenings", "patchEdgeOpening",
                      "removeEdgeOpenings"):
        assert forbidden not in doc, f"{forbidden} present in the D2 query"
    # And no string literal anywhere in the module is a mutation document. Checked
    # with the AST rather than by scanning text, so the warnings in the prose above
    # the code cannot trip it.
    import ast
    tree = ast.parse(Path(mp.__file__).read_text())
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    for lit in literals:
        stripped = lit.strip()
        assert not stripped.startswith("mutation"), "a mutation document is defined"
        assert "mutation {" not in stripped and "mutation(" not in stripped


def test_rate_limit_is_well_under_the_documented_ceiling():
    assert mp.MIN_INTERVAL_S >= 0.1          # <= 10 req/s is the documented ceiling
    assert 1.0 / mp.MIN_INTERVAL_S <= 5.0    # and this client stays well under it


def test_credentials_never_default_to_the_broken_key_set(monkeypatch):
    monkeypatch.delenv("MATTERPORT_API_KEY", raising=False)
    monkeypatch.delenv("MATTERPORT_API_TOKEN", raising=False)
    with pytest.raises(mp.MatterportAuthMissing):
        mp.credentials()
    monkeypatch.setenv("MATTERPORT_API_KEY", "k")
    monkeypatch.setenv("MATTERPORT_API_TOKEN", "t")
    assert mp.credentials() == ("k", "t")
    monkeypatch.setenv("MATTERPORT_API_KEY_B", "kb")
    monkeypatch.setenv("MATTERPORT_API_TOKEN_B", "tb")
    assert mp.credentials("B") == ("kb", "tb")


# ---------- live ----------

def _can_run_live() -> bool:
    """Network tests are **opt-in**: `pytest backend -q` must stay offline, because
    the server lane's checkpoint asserts the whole suite makes no network call."""
    return (os.environ.get("RUN_LIVE_NETWORK") == "1"
            and bool(os.environ.get("MATTERPORT_API_KEY"))
            and bool(os.environ.get("MATTERPORT_API_TOKEN")))


live = pytest.mark.skipif(not _can_run_live(),
                          reason="set RUN_LIVE_NETWORK=1 and a Matterport key set to run")


@live
def test_live_golden_house():
    d = mp.get_matterport_data("zvKHR9DHNjJ")
    MatterportData.model_validate(d.model_dump(mode="json"))
    g = d.georeference
    assert g.source == "processing"
    assert g.rotation.z == pytest.approx(0.7289895896353398, rel=1e-9)
    assert g.rotation.w == pytest.approx(0.6845247827531877, rel=1e-9)
    windows = [o for f in d.floors for e in f.edges for o in e.openings if o.type == "window"]
    assert windows, "the golden house has window openings"
    assert all(0.0 <= o.relative_center <= 1.0 for f in d.floors for e in f.edges
               for o in e.openings if o.relative_center is not None)
    assert any(r.label for r in d.rooms), "residential rooms carry classifications"


@live
@pytest.mark.parametrize("sid", ["jfiEvosX974", "L3266YcPPvd"])
def test_live_golden_offices_have_no_windows_or_room_labels(sid):
    d = mp.get_matterport_data(sid)
    MatterportData.model_validate(d.model_dump(mode="json"))
    assert not [o for f in d.floors for e in f.edges for o in e.openings if o.type == "window"]
    assert all(r.label is None for r in d.rooms)
    assert d.georeference is not None
