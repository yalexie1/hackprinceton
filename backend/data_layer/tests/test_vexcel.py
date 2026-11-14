"""Tests for package D3 (the Vexcel client).

The offline set injects a fake getter built from responses actually observed on
2026-11-14. The live set runs only when a key is present and asserts the verified
attribute values on all three golden lots.
"""
from __future__ import annotations

import os

import pytest

from backend.data_layer import vexcel as vx
from backend.schema import VexcelData

# Golden house: a two-structure parcel with a MultiPolygon geometry, and a rise that
# is implausible as a building height (0.36 m for a gabled house).
HOUSE = {
    "type": "FeatureCollection",
    "features": [{
        "geometry": {"type": "MultiPolygon", "coordinates": [
            [[[-118.3171, 34.0935], [-118.3170, 34.0935], [-118.3170, 34.0936]]],
            [[[-118.3172, 34.0934], [-118.3171, 34.0934], [-118.3171, 34.0935],
              [-118.3172, 34.0935]]],
        ]},
        "properties": {
            "structure.count": 2, "parcel-source": "Bins",
            "parcel-tree-cover.percent": 30.0, "hardscapes.area": 128.0,
            "structures": [
                {"primary-structure": True, "footprint.area": 190.39486191642033,
                 "footprint.wkt": "POLYGON ((...))",
                 "ground-elevation.value": 100.584,
                 "roof-characteristics.elevation": 100.220123,
                 "roof-characteristics.height": 0.363877,
                 "roof-characteristics.shape.value": "gable",
                 "roof-characteristics.material.class": "shingle",
                 "roof-objects.ac-unit.count": 2, "roof-objects.chimney.count": 1,
                 "building-type.class": None},
                {"primary-structure": False, "footprint.area": 20.0},
            ],
        },
    }],
}

# LA golden office: one flat-roofed tower, negative height, podium footprint.
OFFICE = {
    "type": "FeatureCollection",
    "features": [{
        "geometry": {"type": "Polygon", "coordinates": [
            [[-118.4431, 34.0365], [-118.4430, 34.0365], [-118.4430, 34.0366]]]},
        "properties": {
            "structure.count": 1, "parcel-source": "Bins",
            "structures": [{
                "primary-structure": True, "footprint.area": 2207.433929607084,
                "ground-elevation.value": 54.5592,
                "roof-characteristics.elevation": 70.05658721923828,
                "roof-characteristics.height": -15.497387219238277,
                "roof-characteristics.shape.value": "flat",
                "roof-characteristics.material.class": "membrane",
                "roof-objects.ac-unit.count": 0, "building-type.class": None,
            }],
        },
    }],
}


def _getter(status, body, record=None):
    def get(path, params):
        if record is not None:
            record.append((path, params))
        return status, body
    return get


# ---------- transport rules ----------

def test_wkt_is_longitude_first():
    assert vx.point_wkt(34.093491667, -118.3171) == "POINT(-118.3171 34.093491667)"


def test_403_outside_coverage_is_a_note():
    data, notes = vx.get_vexcel_data_with_notes("POINT(0 0)", get=_getter(403, None))
    assert data is None and notes[0].status == "missing"
    assert "coverage" in notes[0].detail


def test_layer_defaults_to_urban_and_is_recorded():
    """The layer set selects the collection and so changes every attribute, so the
    default is pinned and the collection travels on the result."""
    calls = []
    vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE, calls))
    assert calls[0][1]["layer"] == vx.DEFAULT_LAYERS == "urban"
    assert vx.ALL_LAYERS != vx.DEFAULT_LAYERS


def test_one_combined_include_and_srid_4326():
    calls = []
    vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE, calls))
    assert len(calls) == 1, "must be one call, not precomputed then calculated"
    path, params = calls[0]
    assert path == "property/extract"
    assert params["include"] == "precomputed,calculated"
    assert params["srid"] == 4326


def test_404_is_a_note_not_an_exception():
    data, notes = vx.get_vexcel_data_with_notes("POINT(0 0)", get=_getter(404, None))
    assert data is None
    assert notes[0].layer == "vexcel" and notes[0].status == "missing"
    with pytest.raises(vx.NoParcel):
        vx.get_vexcel_data("POINT(0 0)", get=_getter(404, None))


def test_429_after_retries_is_an_error_note():
    data, notes = vx.get_vexcel_data_with_notes("POINT(0 0)", get=_getter(429, None))
    assert data is None and notes[0].status == "error"


def test_empty_feature_list_is_a_note():
    data, notes = vx.get_vexcel_data_with_notes(
        "POINT(0 0)", get=_getter(200, {"features": []}))
    assert data is None and notes[0].status == "missing"


def test_backoff_settings_are_sane():
    assert vx.MAX_RETRIES >= 2 and vx.BACKOFF_BASE_S > 0


def test_key_is_required_and_supports_key_sets(monkeypatch):
    monkeypatch.delenv("VEXCEL_API_KEY", raising=False)
    with pytest.raises(vx.VexcelAuthMissing):
        vx.api_key()
    monkeypatch.setenv("VEXCEL_API_KEY", "k")
    monkeypatch.setenv("VEXCEL_API_KEY_C", "kc")
    assert vx.api_key() == "k" and vx.api_key("C") == "kc"


# ---------- geometry ----------

def test_multipolygon_takes_the_largest_ring():
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE))
    assert data.parcel_wkt and data.parcel_wkt.startswith("POLYGON ((")
    # the 4-point ring, not the 3-point one
    assert data.parcel_wkt.count(",") == 3


def test_polygon_and_unsupported_geometry():
    assert vx.largest_ring_wkt({"type": "Polygon",
                                "coordinates": [[[0, 0], [1, 0], [1, 1]]]}).startswith("POLYGON")
    assert vx.largest_ring_wkt({"type": "Point", "coordinates": [0, 0]}) is None
    assert vx.largest_ring_wkt(None) is None
    assert vx.largest_ring_wkt({"type": "Polygon", "coordinates": []}) is None


# ---------- structures ----------

def test_primary_structure_is_chosen_on_a_two_structure_parcel():
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE))
    assert len(data.structures) == 2
    primary = vx.primary_structure(data)
    assert primary.primary is True
    assert primary.footprint_area_m2 == pytest.approx(190.39486191642033)


def test_primary_falls_back_to_the_largest_when_no_flag_is_set():
    body = {"features": [{"geometry": None, "properties": {"structures": [
        {"footprint.area": 10.0}, {"footprint.area": 99.0}]}}]}
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, body))
    assert vx.primary_structure(data).footprint_area_m2 == 99.0


def test_parcel_attributes_exclude_structures():
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE))
    assert "structures" not in data.attributes
    assert data.attributes["parcel-tree-cover.percent"] == 30.0


# ---------- the height rule ----------

@pytest.mark.parametrize("body,expected", [(HOUSE, 0.363877), (OFFICE, 15.497387219238277)])
def test_roof_rise_discards_the_sign(body, expected):
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, body))
    attrs = vx.primary_structure(data).attributes
    assert vx.roof_rise_m(attrs) == pytest.approx(expected)
    assert vx.roof_rise_m(attrs) > 0, "sign is unreliable; magnitude is the reading"


def test_rise_magnitude_matches_roof_minus_ground_on_both_lots():
    for body in (HOUSE, OFFICE):
        a = vx.primary_structure(vx.get_vexcel_data("POINT(0 0)", get=_getter(200, body))).attributes
        diff = abs(a["roof-characteristics.elevation"] - a["ground-elevation.value"])
        assert vx.roof_rise_m(a) == pytest.approx(diff)


def test_house_rise_fails_the_absolute_floor():
    """0.36 m for a gabled house is a failed measurement, not a short building."""
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE))
    assert vx.plausible_building_height(vx.primary_structure(data).attributes) is False


def test_tower_needs_the_storey_count_to_be_caught():
    """15.5 m passes an absolute floor but not 17 storeys: Vexcel outlined a podium.

    This is why `stories` has to be passed from CoStar - without it the podium reading
    looks like a perfectly ordinary low building.
    """
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, OFFICE))
    attrs = vx.primary_structure(data).attributes
    assert vx.plausible_building_height(attrs) is True            # absolute floor alone
    assert vx.plausible_building_height(attrs, stories=17) is False
    assert vx.plausible_building_height(attrs, stories=1) is True


def test_a_fallback_note_is_raised_when_the_rise_is_not_believable():
    _, notes = vx.get_vexcel_data_with_notes(
        "POINT(0 0)", stories=17, get=_getter(200, OFFICE))
    # By `what`, not by position: D16 also records which capture and structure it
    # chose, and that record is a `fallback` too whenever there was a choice to make.
    height = [n for n in notes if n.what == "roof-characteristics.height"]
    assert height and height[0].status == "fallback"
    assert "numStoriesAboveGrade" in height[0].detail


def test_a_real_height_is_accepted():
    body = {"features": [{"geometry": None, "properties": {"structures": [
        {"primary-structure": True, "roof-characteristics.height": 44.0}]}}]}
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, body))
    assert vx.plausible_building_height(vx.primary_structure(data).attributes) is True


def test_building_type_class_is_never_required():
    data = vx.get_vexcel_data("POINT(0 0)", get=_getter(200, HOUSE))
    VexcelData.model_validate(data.model_dump(mode="json"))
    assert vx.primary_structure(data).attributes["building-type.class"] is None


# ---------- obliques ----------

def test_oblique_directions_uses_only_the_newest_collection():
    body = {"features": [
        {"properties": {"product-type": "oblique-north", "last-capture-date": "2025-12-10"}},
        {"properties": {"product-type": "oblique-south", "last-capture-date": "2025-12-10"}},
        {"properties": {"product-type": "oblique-west", "last-capture-date": "2024-03-17"}},
    ]}
    dirs = vx.oblique_directions("POLYGON ((0 0))", get=_getter(200, body))
    assert dirs == ["oblique-north", "oblique-south"]       # west is from an older flight
    assert vx.oblique_directions("x", get=_getter(404, None)) == []
    assert vx.oblique_directions("x", get=_getter(200, {"features": []})) == []


def test_obliques_are_requested_from_the_urban_layer_only():
    calls = []
    vx.oblique_directions("POLYGON ((0 0))", get=_getter(200, {"features": []}, calls))
    assert calls[0][1]["layer"] == "urban" and calls[0][1]["product-type"] == "oblique"


# ---------- live ----------

#: Opt-in, so `pytest backend -q` stays offline for every lane.
live = pytest.mark.skipif(
    not (os.environ.get("RUN_LIVE_NETWORK") == "1" and os.environ.get("VEXCEL_API_KEY")),
    reason="set RUN_LIVE_NETWORK=1 and VEXCEL_API_KEY to run")

GOLDEN = [
    # lat, lon, roof shape, roof material, storeys
    (34.093491667, -118.3171, "gable", "shingle", 1),                      # house
    (34.036533907520074, -118.44311817454468, "flat", "membrane", 17),     # LA office
    (29.74602759879178, -95.45754572577202, "flat", "membrane", 16),       # Houston office
]


@live
@pytest.mark.parametrize("lat,lon,shape,material,stories", GOLDEN)
def test_live_golden_lots(lat, lon, shape, material, stories):
    """Asserts the stable attributes only.

    Structure count, footprint area and roof elevation all shift with the selected
    collection, and the calculated height is not even reproducible call to call, so
    none of those is asserted by value.
    """
    data = vx.get_vexcel_data(vx.point_wkt(lat, lon), stories=stories)
    VexcelData.model_validate(data.model_dump(mode="json"))
    s = vx.primary_structure(data)
    assert s.attributes["roof-characteristics.shape.value"] == shape
    assert s.attributes["roof-characteristics.material.class"] == material
    assert data.parcel_wkt and data.parcel_wkt.startswith("POLYGON ((")
    assert data.collection, "the collection must travel with the result"
    # the combined call delivers precomputed and calculated together
    assert s.footprint_area_m2 and s.footprint_area_m2 > 0
    assert "roof-characteristics.height" in s.attributes
    # and the rise is never believable as this building's height
    assert vx.plausible_building_height(s.attributes, stories=stories) is False


@live
def test_live_layer_set_changes_the_decomposition():
    """Recorded because it is surprising: the same point under two layer sets gives
    different collections, structure counts and footprints."""
    pt = vx.point_wkt(34.036533907520074, -118.44311817454468)
    urban = vx.get_vexcel_data(pt, layers=vx.DEFAULT_LAYERS)
    allL = vx.get_vexcel_data(pt, layers=vx.ALL_LAYERS)
    assert urban.collection != allL.collection
    assert (len(urban.structures), vx.primary_structure(urban).footprint_area_m2) != \
           (len(allL.structures), vx.primary_structure(allL).footprint_area_m2)


@live
def test_live_no_parcel_in_the_ocean():
    data, notes = vx.get_vexcel_data_with_notes(vx.point_wkt(0.0, 0.0))
    assert data is None and notes[0].status == "missing"
