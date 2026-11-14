"""D16: which building on the parcel, and which capture of it.

The fixtures here are trimmed from real `property/extract` responses measured on
2026-11-14 and recorded in `specs/data-integration.md` 4.5. The shapes matter: Vexcel
returns **flat dotted keys**, one feature per capture collection, and footprint WKT
that is **longitude first**.

None of this needs the network or the kit.
"""
from __future__ import annotations

import os

import pytest

from backend.data_layer import locate as d16
from backend.data_layer import vexcel as vx
from backend.schema import CostarData

LA = (34.0361802, -118.4428766)       # the Los Angeles office's CoStar address point


def _square(lat: float, lon: float, side_m: float) -> str:
    """A square footprint centred on a point, as longitude-first WKT."""
    dlat = side_m / 2 / 110574.0
    dlon = side_m / 2 / 92000.0       # about right at 34 N; only the ordering matters
    ring = [(lon - dlon, lat - dlat), (lon + dlon, lat - dlat),
            (lon + dlon, lat + dlat), (lon - dlon, lat + dlat), (lon - dlon, lat - dlat)]
    return "POLYGON ((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


def _structure(area, wkt, *, primary=True, solar=False, ac=None):
    out = {
        "footprint.area": area,
        "footprint.wkt": wkt,
        "primary-structure": primary,
        "roof-objects.solar.value": solar,
        "roof-characteristics.centroid.wkt": _centre_of(wkt),
    }
    if ac is not None:
        out["roof-objects.ac-unit.count"] = ac
    return out


def _centre_of(wkt: str) -> str:
    import re

    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", wkt)]
    xs, ys = nums[0::2], nums[1::2]
    return f"POINT({sum(xs) / len(xs)} {sum(ys) / len(ys)})"


def _feature(collection, date, structures, *, ortho=True, geometry=None):
    return {
        "geometry": geometry or {"type": "Polygon", "coordinates": [
            [[-118.4432, 34.0358], [-118.4424, 34.0358],
             [-118.4424, 34.0366], [-118.4432, 34.0366], [-118.4432, 34.0358]]]},
        "properties": {
            "metadata.collection": collection,
            "metadata.ortho-date-estimate": date,
            "metadata.is-ortho-image": ortho,
            "structures": structures,
        },
    }


def _costar(area_m2, stories, **kw) -> CostarData:
    return CostarData(kind="commercial_property", matterport_model_id="m", record_id="r",
                      raw={}, building_area_m2=area_m2, stories=stories, **kw)


# ---------- the floor plate ----------

def test_the_plate_needs_both_an_area_and_a_storey_count():
    assert d16.floor_plate_m2(None) is None
    assert d16.floor_plate_m2(_costar(24147.6, 17)) == pytest.approx(1420.4, abs=0.1)
    assert d16.floor_plate_m2(_costar(24147.6, None)) is None
    assert d16.floor_plate_m2(_costar(None, 17)) is None
    assert d16.floor_plate_m2(_costar(24147.6, 0)) is None, "no division by zero"


def test_rentable_area_is_not_a_fallback_for_gross_area():
    """`rentable_area_m2` excludes cores and common area by a different amount per
    building, so substituting it would bias the plate low unpredictably - and the plate
    is only useful as a *comparison* between candidate footprints."""
    only_rentable = _costar(None, 17, rentable_area_m2=20000.0)
    assert d16.floor_plate_m2(only_rentable) is None


# ---------- the bug this package exists for ----------

def test_the_first_feature_is_not_trusted():
    """**The regression test.** One response holds a feature per capture collection and
    `features[0]` is whatever the service ordered first. At the Los Angeles office that
    was `us-ca-losangeles-2023`, a 2022 capture of a building the address point is not
    inside, while a 2025 capture of the right building sat in the same response unread.
    """
    wrong = _square(34.03574, -118.44245, 47.0)       # the building next door
    right = _square(*LA, 40.0)                        # the one at the address
    features = [
        _feature("us-ca-losangeles-2023", "2022-12-20T00:00:00",
                 [_structure(2207.4, wrong, primary=True)]),
        _feature("us-ca-losangeles-2025", "2025-12-06T00:00:00",
                 [_structure(1566.2, right, primary=False)]),
    ]
    pick, notes = d16.choose(features, at=LA, plate_m2=1420.4)
    assert pick.feature == 1, "chose the capture whose structure is at the address"
    assert pick.area_m2 == 1566.2
    assert any("1,566" in (n.detail or "") for n in notes)


def test_vexcels_own_primary_flag_does_not_decide():
    """It is right on the golden house and wrong on both golden offices: at the Los
    Angeles office the flagged structure is one the address point is not inside."""
    flagged_but_wrong = _square(34.03574, -118.44245, 47.0)
    unflagged_but_right = _square(*LA, 40.0)
    features = [_feature("c", "2025-01-01", [
        _structure(2207.4, flagged_but_wrong, primary=True),
        _structure(1566.2, unflagged_but_right, primary=False),
    ])]
    pick, _ = d16.choose(features, at=LA, plate_m2=1420.4)
    assert pick.structure == 1 and pick.primary is False


# ---------- the plate as a discriminator ----------

def test_the_plate_separates_two_buildings_that_differ_by_twice():
    """1,566 m2 against 2,938 m2 for a 1,420 m2 plate: 10 % against 107 %."""
    small, large = _square(*LA, 40.0), _square(*LA, 54.0)
    features = [_feature("newer", "2025-12-06", [_structure(1566.2, small)]),
                _feature("older", "2024-04-16", [_structure(2937.7, large)])]
    pick, _ = d16.choose(features, at=LA, plate_m2=1420.4)
    assert pick.area_m2 == 1566.2


def test_captures_of_one_building_are_not_separated_on_noise():
    """The golden house is 190.4, 190.0, 191.7, 190.5 and 191.3 m2 across five
    captures. Choosing the closest to the plate would pick on a 0.9 % difference, so
    everything within `PLATE_BAND` of the best ties and the **newest** wins - which is
    what decides whether the demo quotes 2 rooftop AC units from 2022 or 0 from 2025.
    """
    wkt = _square(34.093471, -118.317082, 14.0)
    features = [
        _feature("us-ca-losangeles-2023", "2022-12-14", [_structure(190.4, wkt, ac=2)]),
        _feature("us-ca-glendale-2024", "2024-03-25", [_structure(190.0, wkt, ac=1)]),
        _feature("us-ca-losangeles-2025", "2025-11-29", [_structure(191.7, wkt, ac=1)]),
        _feature("us-ca-glendale-2025", "2025-12-09", [_structure(191.3, wkt, ac=0)]),
    ]
    pick, notes = d16.choose(features, at=(34.093471, -118.317082), plate_m2=151.2)
    assert pick.collection == "us-ca-glendale-2025", "the newest capture of the house"
    assert pick.area_m2 == 191.3
    assert "lost on date" in (notes[0].detail or "")
    # And the closest-to-plate structure (190.0) was *not* chosen.
    assert pick.area_m2 != 190.0


def test_the_right_building_beats_a_newer_capture_of_the_wrong_one():
    """Houston: the newest capture (`us-tx-houston-2026`, imagery 2025-12-31) reports
    4,164 m2 over the address against a 944 m2 plate, while a 2023 capture reports
    1,104 m2 - and D8's mask, from imagery, measured 1,064 m2. Every roof number
    downstream scales with the footprint; a two-year-old capture only ages the roof
    condition."""
    hou = (29.7460487, -95.4576844)
    big, small = _square(*hou, 65.0), _square(*hou, 33.0)
    features = [_feature("us-tx-houston-2026", "2025-12-31", [_structure(4164.0, big)]),
                _feature("us-tx-houston-2023", "2023-01-14", [_structure(1104.5, small)])]
    pick, _ = d16.choose(features, at=hou, plate_m2=943.8)
    assert pick.area_m2 == 1104.5 and pick.collection == "us-tx-houston-2023"


# ---------- containment ----------

def test_a_structure_that_encloses_the_point_beats_a_better_plate_match():
    """Containment is the lead's rule and comes first: the plate is a tie-break between
    candidates at the address, not a search over the whole parcel."""
    at_address = _square(*LA, 40.0)                       # 1,566 m2, 10 % off
    elsewhere = _square(34.03574, -118.44245, 39.0)       # a perfect plate match
    features = [_feature("c", "2025-01-01", [
        _structure(1566.2, at_address, primary=False),
        _structure(1420.0, elsewhere, primary=True),
    ])]
    pick, _ = d16.choose(features, at=LA, plate_m2=1420.0)
    assert pick.area_m2 == 1566.2, "the plate must not reach outside the address point"


def test_nothing_enclosing_the_point_widens_the_search_and_says_so():
    """A geocode can land on open ground. Widening is better than refusing, but it is a
    weaker claim than "the building at this address" and has to be recorded as one."""
    away = _square(34.0300, -118.4500, 40.0)
    features = [_feature("c", "2025-01-01", [_structure(1500.0, away)])]
    pick, notes = d16.choose(features, at=LA, plate_m2=1420.0)
    assert pick is not None, "a parcel with a building is still an answer"
    widened = [n for n in notes if n.what == "property/extract:containment"]
    assert widened and widened[0].status == "fallback"
    assert "encloses" in widened[0].detail


def test_no_locator_point_at_all_still_beats_the_first_feature():
    features = [_feature("old", "2022-01-01", [_structure(2207.4, _square(*LA, 47.0))]),
                _feature("new", "2025-01-01", [_structure(2300.0, _square(*LA, 48.0))])]
    pick, notes = d16.choose(features, at=None, plate_m2=None)
    assert pick.collection == "new"
    assert notes[0].status == "fallback" and "no locator point" in notes[0].detail


# ---------- capture quality ----------

def test_an_oblique_capture_loses_a_tie():
    """`metadata.is-ortho-image` false means the attributes came from an oblique. The
    two in the golden set gave 9,162 m2 for a 1,420 m2 plate and 3,802 m2 for a 944 m2
    one, both with no AC count and no roof condition at all."""
    wkt = _square(*LA, 40.0)
    features = [
        _feature("oblique-2026", "2026-01-01", [_structure(1566.0, wkt)], ortho=False),
        _feature("ortho-2025", "2025-01-01", [_structure(1566.0, wkt)], ortho=True),
    ]
    pick, _ = d16.choose(features, at=LA, plate_m2=1420.0)
    assert pick.collection == "ortho-2025", "newer, but derived from an oblique"


def test_a_structure_with_no_area_is_never_chosen_over_one_with_an_area():
    wkt = _square(*LA, 40.0)
    features = [_feature("c", "2025-01-01", [
        _structure(None, wkt), _structure(1566.2, wkt)])]
    pick, _ = d16.choose(features, at=LA, plate_m2=1420.0)
    assert pick.area_m2 == 1566.2


def test_no_plate_falls_back_to_the_flag_then_the_date():
    wkt = _square(*LA, 40.0)
    features = [_feature("old", "2022-01-01", [_structure(2000.0, wkt, primary=True)]),
                _feature("new", "2025-01-01", [_structure(2100.0, wkt, primary=False)])]
    pick, notes = d16.choose(features, at=LA, plate_m2=None)
    assert pick.primary is True and pick.collection == "old"
    assert "no CoStar floor plate" in (notes[0].detail or "")


# ---------- the extent record ----------

def test_one_building_outlined_twice_is_recorded_once_with_the_solar_split():
    """The podium case. Two captures outline the same building 1.9x apart and disagree
    about rooftop solar, which decides whether `PV_ROOF` runs or skips as
    `already_done`. Houston produced four near-identical records before they were
    collapsed, and four sentences saying one thing is how a warning gets skimmed."""
    tower, podium = _square(*LA, 40.0), _square(34.03634, -118.44283, 54.0)
    features = [
        _feature("us-ca-losangeles-2025", "2025-12-06", [_structure(1566.2, tower)]),
        _feature("us-ca-losangeles-2024", "2024-04-16",
                 [_structure(2937.7, podium, solar=True)]),
    ]
    pick, notes = d16.choose(features, at=LA, plate_m2=1420.4)
    extent = [n for n in notes if n.what == "property/extract:extent"]
    assert len(extent) == 1, "one record, however many captures disagree"
    assert "1.9x" in extent[0].detail
    assert "rooftop solar" in extent[0].detail and "PV_ROOF" in extent[0].detail
    assert extent[0].layer == "vexcel" and extent[0].status == "fallback"


def test_two_captures_of_the_same_outline_are_not_reported_as_a_disagreement():
    """190.4 against 191.3 m2 is capture noise, not an extent disagreement."""
    wkt = _square(34.093471, -118.317082, 14.0)
    features = [_feature("a", "2025-12-09", [_structure(191.3, wkt)]),
                _feature("b", "2022-12-14", [_structure(190.4, wkt)])]
    _, notes = d16.choose(features, at=(34.093471, -118.317082), plate_m2=151.2)
    assert not [n for n in notes if n.what == "property/extract:extent"]


def test_two_distinct_buildings_are_not_called_the_same_building():
    """The two buildings on the Los Angeles parcel are 70 m apart at the centroid,
    against 9 m between two captures of one of them."""
    here, there = _square(*LA, 40.0), _square(34.03574, -118.44245, 54.0)
    features = [_feature("a", "2025-01-01", [_structure(1566.2, here)]),
                _feature("b", "2024-01-01", [_structure(2937.7, there, solar=True)])]
    pick, notes = d16.choose(features, at=LA, plate_m2=1420.4)
    assert pick.area_m2 == 1566.2
    assert not [n for n in notes if n.what == "property/extract:extent"], \
        "a different building is a rejected candidate, not an extent disagreement"


# ---------- empty and broken responses ----------

def test_no_features_is_a_record_not_a_crash():
    pick, notes = d16.choose([], at=LA, plate_m2=1420.0)
    assert pick is None and notes[0].status == "missing"


def test_a_parcel_with_no_structure_is_still_a_parcel():
    """It has a polygon, which `elements/detect` needs, and attributes. Returning
    nothing turned "a parcel with no building" into "no parcel" and broke the cache's
    own provenance note."""
    features = [_feature("c", "2025-01-01", [])]
    pick, notes = d16.choose(features, at=LA, plate_m2=1420.0)
    assert pick is None and notes[0].status == "missing"
    assert d16.newest_feature(features) == 0

    data, vnotes = vx.get_vexcel_data_with_notes(
        "POINT(0 0)", at=LA, floor_plate_m2=1420.0,
        get=lambda path, params: (200, {"features": features}))
    assert data is not None and data.structures == []
    assert data.collection == "c"


def test_the_newest_feature_is_picked_when_there_is_nothing_to_choose_by():
    features = [_feature("old", "2022-01-01", []), _feature("new", "2025-01-01", [])]
    assert d16.newest_feature(features) == 1
    assert d16.newest_feature([]) == 0


def test_an_undated_capture_sorts_oldest_rather_than_newest():
    """A missing date must not win by comparing as an empty string or a zero year."""
    assert d16._date_rank(None) == 0.0
    assert d16._date_rank("2025-12-06T00:00:00") > d16._date_rank("2024-04-16")


# ---------- reaching the analysis lane ----------

def test_the_chosen_structure_is_first_and_the_only_primary_one():
    """Every consumer picks the building either as the first `primary` structure
    (`registry.py:391`) or by sorting on `not primary` (`north.py:150`,
    `hvac_dhw.py:75`), so satisfying both is what makes the choice reach A2, A11, A12,
    A14 and A19 without a contract change."""
    wrong, right = _square(34.03574, -118.44245, 47.0), _square(*LA, 40.0)
    body = {"features": [_feature("c", "2025-01-01", [
        _structure(2207.4, wrong, primary=True),
        _structure(1566.2, right, primary=False),
    ])]}
    data, _ = vx.get_vexcel_data_with_notes(
        "POINT(0 0)", at=LA, floor_plate_m2=1420.4,
        get=lambda path, params: (200, body))

    assert data.structures[0].footprint_area_m2 == 1566.2
    assert data.structures[0].primary is True
    assert [s.primary for s in data.structures] == [True, False], "exactly one primary"
    assert vx.primary_structure(data).footprint_area_m2 == 1566.2
    # Both consumer idioms agree.
    assert next(s for s in data.structures if s.primary).footprint_area_m2 == 1566.2
    assert sorted(data.structures, key=lambda s: not s.primary)[0].footprint_area_m2 == 1566.2


def test_vexcels_own_flag_survives_in_the_attributes():
    """`VexcelStructure.primary` now means "the building this bundle is about". What the
    service actually said stays readable, so the override is visible rather than lost."""
    wrong, right = _square(34.03574, -118.44245, 47.0), _square(*LA, 40.0)
    body = {"features": [_feature("c", "2025-01-01", [
        _structure(2207.4, wrong, primary=True),
        _structure(1566.2, right, primary=False),
    ])]}
    data, _ = vx.get_vexcel_data_with_notes(
        "POINT(0 0)", at=LA, floor_plate_m2=1420.4,
        get=lambda path, params: (200, body))
    chosen = data.structures[0]
    assert chosen.primary is True
    assert chosen.attributes["primary-structure"] is False, "Vexcel said otherwise"
    assert data.structures[1].attributes["primary-structure"] is True


def test_the_parcel_polygon_comes_from_the_chosen_capture():
    """`detect_roof_elements` and A11 both work from `parcel_wkt`, so it has to be the
    polygon of the capture the roof numbers came from, not of whichever was first."""
    first = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0],
                                                 [1.0, 0.0], [0.0, 0.0]]]}
    second = {"type": "Polygon", "coordinates": [[[10.0, 10.0], [10.0, 11.0], [11.0, 11.0],
                                                  [11.0, 10.0], [10.0, 10.0]]]}
    wrong, right = _square(34.03574, -118.44245, 47.0), _square(*LA, 40.0)
    body = {"features": [
        _feature("old", "2022-01-01", [_structure(2207.4, wrong)], geometry=first),
        _feature("new", "2025-01-01", [_structure(1566.2, right)], geometry=second),
    ]}
    data, _ = vx.get_vexcel_data_with_notes(
        "POINT(0 0)", at=LA, floor_plate_m2=1420.4,
        get=lambda path, params: (200, body))
    assert data.collection == "new"
    assert "10.0 10.0" in data.parcel_wkt, "the chosen capture's polygon"
    assert "0.0 1.0" not in data.parcel_wkt, "not the first feature's"


# ---------- live ----------

live = pytest.mark.skipif(os.environ.get("RUN_LIVE_NETWORK") != "1",
                          reason="set RUN_LIVE_NETWORK=1")


@live
def test_the_golden_three_resolve_to_the_measured_buildings():
    """Measured 2026-11-14. These are the numbers the demo shows, so a change in them
    is something to find here rather than on stage."""
    from backend.data_layer import api

    os.environ["DATA_LAYER_LIVE"] = "1"
    expected = {
        "zvKHR9DHNjJ": (191.3, "us-ca-glendale-2025"),
        "jfiEvosX974": (1566.2, "us-ca-losangeles-2025"),
        "L3266YcPPvd": (1104.5, "us-tx-houston-2023"),
    }
    for sid, (area, collection) in expected.items():
        bundle = api.get_property_bundle(sid, live=True)
        structure = vx.primary_structure(bundle.vexcel)
        assert structure.footprint_area_m2 == pytest.approx(area, abs=1.0), sid
        assert bundle.vexcel.collection == collection, sid


@live
def test_the_chosen_structure_encloses_the_address_on_all_three():
    from backend.data_layer import api, index, screening

    os.environ["DATA_LAYER_LIVE"] = "1"
    for sid in ("zvKHR9DHNjJ", "jfiEvosX974", "L3266YcPPvd"):
        bundle = api.get_property_bundle(sid, live=True)
        indexed = index.by_sid()[sid]
        structure = vx.primary_structure(bundle.vexcel)
        assert screening.contains(structure.footprint_wkt, indexed.lat, indexed.lon), sid


def test_a_bundle_cached_under_the_old_rule_is_a_miss_not_an_answer(tmp_path, monkeypatch):
    """The bundle cache is keyed on the sid, so a rule change does not change the key.
    Without a stamp, a demo laptop with a warm cache keeps serving the pre-D16
    structure - a building 100 m from the address at the Los Angeles office - with
    nothing in the output to say so."""
    from backend.data_layer import api

    monkeypatch.setattr(api, "_CACHE", tmp_path)
    path = api._bundle_cache_path("sid-1")
    path.parent.mkdir(parents=True, exist_ok=True)

    bundle = api._fixture_bundle(api._load(api._folders()[0], "property_summary.json")["sid"])
    api._write_bundle_cache(path, bundle)
    assert api._read_bundle_cache("sid-1", path) is not None, "the current rule reads"

    import json

    entry = json.loads(path.read_text())
    entry["rule"] = api.BUNDLE_RULE_VERSION - 1
    path.write_text(json.dumps(entry))
    assert api._read_bundle_cache("sid-1", path) is None, "an older rule is a miss"
    assert not path.exists(), "and the entry is removed rather than re-read next time"
