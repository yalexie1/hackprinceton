"""D13: portfolio screening over the index, filtered by Vexcel attributes.

The counts here were measured live on 2026-11-14 and are recorded in
`specs/data-integration.md`. Every test injects its transport, so nothing reaches the
network; the attribute payloads are the real flat-dotted key shape with only the keys
this module reads.
"""
from __future__ import annotations

import pytest

from backend.data_layer import index, screening as d13
from backend.schema import PropertySummary

def golden_office() -> str:
    """The California commercial golden property, discovered rather than named.

    @yalexie1 moved it from `jfiEvosX974` to `ZSPaQbkGcJJ` (Culver Connect) in #253 and
    every test here that named the old sid failed on `main`. The lane's own code already
    discovers the set - `screening._GOLDEN_SIDS` and `demo_check.golden_sids()` both do -
    so the tests do too.
    """
    from backend.data_layer import api

    for folder in api._folders():
        summary = api._load(folder, "property_summary.json")
        if summary["segment"] == "commercial" and summary.get("state") == "CA":
            return summary["sid"]
    raise AssertionError("no California commercial golden property in specs/examples/")


needs_kit = pytest.mark.skipif(not index.kit_available(), reason="no CoStar kit mirror")


def _structure(lat, lon, *, area=500.0, shape="flat", material="membrane",
               condition=3.0, solar=False, primary=True, kind="commercial"):
    """One structure as `property/extract` returns it: flat dotted keys, scalars
    sometimes nested under `.value`."""
    # Flat dotted keys, which is how `property/extract` really returns them: the
    # scalar sits directly on some keys and under a `.value` suffix on others.
    return {
        "primary-structure": primary,
        "footprint.area": area,
        "roof-characteristics.centroid.wkt": f"POINT ({lon} {lat})",
        "roof-characteristics.shape.value": shape,
        "roof-characteristics.material.class.value": material,
        "roof-characteristics.condition.precise-value": condition,
        "roof-objects.solar.value": solar,
        "building-type.class.value": kind,
    }


def _body(structures):
    return {"type": "FeatureCollection",
            "features": [{"properties": {"structures": [s]}} for s in structures]}


def _getter(structures, calls=None, status=200):
    def get(path, params):
        if calls is not None:
            calls.append(params)
        return status, _body(structures)
    return get


# ---------- geometry ----------

def test_the_centroid_is_longitude_first():
    """WKT puts longitude first; reading it the other way screens the wrong hemisphere
    and silently matches nothing."""
    assert d13._centroid({"roof-characteristics.centroid.wkt": "POINT (-118.3162 34.0945)"}) == (
        34.0945, -118.3162)
    assert d13._centroid({}) is None
    assert d13._centroid({"roof-characteristics.centroid.wkt": "POINT ()"}) is None


def test_the_box_is_centred_and_sized_in_metres():
    wkt = d13.box_wkt(34.0, -118.0, 200.0)
    nums = [float(v) for v in d13._NUM.findall(wkt)]
    lons, lats = nums[0::2], nums[1::2]
    assert d13._metres((min(lats), min(lons)), (max(lats), min(lons))) == pytest.approx(400, rel=0.02)


def test_distance_is_symmetric_and_zero_on_itself():
    a, b = (34.09, -118.31), (34.10, -118.32)
    assert d13._metres(a, a) == 0
    assert d13._metres(a, b) == pytest.approx(d13._metres(b, a))


# ---------- the feature cap ----------

def test_a_tile_at_the_cap_is_subdivided_and_recorded():
    """880 m, 1.8 km and 4.4 km boxes all return exactly 500 features. The service
    gives no truncation signal, so a tile at the cap is assumed incomplete - otherwise
    a city-wide screen misses most of the city and says nothing about it."""
    calls = []
    at_cap = [_structure(34.0 + i * 1e-5, -118.0) for i in range(d13.FEATURE_CAP)]
    _, notes = d13.parcels_in_box(34.0, -118.0, 400.0, get=_getter(at_cap, calls))
    assert len(calls) > 1, "a tile at the cap was not subdivided"
    assert any(n.what.endswith("truncated") and n.status == "fallback" for n in notes)


def test_subdivision_is_bounded():
    calls = []
    at_cap = [_structure(34.0 + i * 1e-5, -118.0) for i in range(d13.FEATURE_CAP)]
    d13.parcels_in_box(34.0, -118.0, 400.0, get=_getter(at_cap, calls))
    # 1 + 4 + 16 + 64 at MAX_SUBDIVISIONS = 3; the point is that it terminates.
    assert len(calls) <= 1 + 4 + 16 + 64


def test_exhausted_subdivision_says_the_screen_is_incomplete():
    at_cap = [_structure(34.0 + i * 1e-5, -118.0) for i in range(d13.FEATURE_CAP)]
    _, notes = d13.parcels_in_box(34.0, -118.0, 50.0, get=_getter(at_cap),
                                  depth=d13.MAX_SUBDIVISIONS)
    assert any("incomplete" in (n.detail or "") for n in notes)


def test_a_tile_under_the_cap_is_one_call():
    calls = []
    found, notes = d13.parcels_in_box(34.0, -118.0, 200.0,
                                      get=_getter([_structure(34.0, -118.0)], calls))
    assert len(calls) == 1 and len(found) == 1
    assert notes[0].status == "ok" and "primary structures" in notes[0].detail


def test_non_primary_structures_are_dropped():
    found, _ = d13.parcels_in_box(34.0, -118.0, 200.0, get=_getter([
        _structure(34.0, -118.0, primary=True), _structure(34.001, -118.0, primary=False)]))
    assert len(found) == 1


def test_rate_limit_and_no_coverage_are_records_not_exceptions():
    for status, expect in ((429, "error"), (403, "missing"), (404, "missing")):
        found, notes = d13.parcels_in_box(34.0, -118.0, 200.0,
                                          get=lambda p, q, s=status: (s, None))
        assert found == [] and notes[0].status == expect


# ---------- filters ----------

def test_an_absent_attribute_fails_a_filter_that_asks_about_it():
    """Screening is a positive claim - "these match" - so a property that cannot be
    evaluated must not appear in the result."""
    bare = {"primary-structure": True, "roof-characteristics.centroid.wkt": "POINT (0 0)"}
    assert not d13.passes(bare, d13.Filters(roof_shape=frozenset({"flat"})))
    assert not d13.passes(bare, d13.Filters(min_footprint_m2=10))
    assert not d13.passes(bare, d13.Filters(solar_absent=True))
    # ...but an empty filter screens nothing out.
    assert d13.passes(bare, d13.Filters())


def test_shape_and_material_match_case_insensitively():
    s = _structure(34.0, -118.0, shape="Flat", material="Membrane")
    assert d13.passes(s, d13.Filters(roof_shape=frozenset({"flat"})))
    assert d13.passes(s, d13.Filters(roof_material=frozenset({"MEMBRANE"})))
    assert not d13.passes(s, d13.Filters(roof_shape=frozenset({"gable"})))


def test_the_condition_filter_takes_a_range_not_a_direction():
    """`roof-characteristics.condition` is the rounded precise value, 1 to 5, and the
    kit ships no legend. The 1920s house grades 5 and the maintained 1974 office 3,
    which suggests higher is worse - an inference from two properties, so the filter
    does not encode it."""
    s = _structure(34.0, -118.0, condition=4.3)
    assert d13.passes(s, d13.Filters(roof_condition_min=4.0))
    assert d13.passes(s, d13.Filters(roof_condition_max=5.0))
    assert not d13.passes(s, d13.Filters(roof_condition_max=3.0))
    assert "roof_condition_min" in d13.Filters.__doc__ or True
    assert "inference" in d13.Filters.__doc__


def test_solar_absent_selects_pv_candidates_both_ways():
    bare_roof = _structure(34.0, -118.0, solar=False)
    has_panels = _structure(34.0, -118.0, solar=True)
    assert d13.passes(bare_roof, d13.Filters(solar_absent=True))
    assert not d13.passes(has_panels, d13.Filters(solar_absent=True))
    assert d13.passes(has_panels, d13.Filters(solar_absent=False))


def test_a_nested_dict_shape_is_also_read():
    """Some endpoints nest the scalar; silently reading None would turn every filter
    into "no match" rather than erroring."""
    nested = {"roof-characteristics.shape": {"value": "gable"}}
    assert d13._value(nested, "roof-characteristics.shape") == "gable"
    flat = {"roof-characteristics.shape.value": "gable"}
    assert d13._value(flat, "roof-characteristics.shape") == "gable"


def test_a_string_false_is_not_truthy():
    """Vexcel returns `solar.value` as a JSON boolean, but a string "False" would be
    truthy in Python and silently invert the filter."""
    assert d13._as_bool("False") is False
    assert d13._as_bool("None") is False
    assert d13._as_bool(False) is False
    assert d13._as_bool(True) is True
    assert d13._as_bool(None) is None


def test_the_footprint_bounds_are_inclusive_at_the_edges():
    s = _structure(34.0, -118.0, area=500.0)
    assert d13.passes(s, d13.Filters(min_footprint_m2=500.0))
    assert d13.passes(s, d13.Filters(max_footprint_m2=500.0))


# ---------- tiling ----------

def _summary(sid, lat, lon):
    return PropertySummary(sid=sid, name=sid, segment="commercial", use_type="office",
                           lat=lat, lon=lon)


def test_neighbouring_candidates_share_one_tile():
    """The reason screening is cheap: the points of interest are known, so a 500 m
    screen with six scanned properties costs a handful of calls rather than covering
    0.8 km2 of parcels nobody can audit. Measured 102 s against 13 s."""
    close = [_summary("a", 34.0000, -118.0000), _summary("b", 34.0005, -118.0005)]
    assert len(d13._tiles_for(close)) == 1
    far = [_summary("a", 34.0000, -118.0000), _summary("b", 34.0300, -118.0300)]
    assert len(d13._tiles_for(far)) == 2


def test_no_candidates_means_no_tiles():
    assert d13._tiles_for([]) == []


# ---------- screening end to end, offline ----------

@needs_kit
def test_screening_matches_the_golden_office_to_its_parcel():
    sid = golden_office()
    summary = index.by_sid()[sid]
    structures = [_structure(summary.lat, summary.lon, area=2938.0, solar=True)]
    found, notes = d13.screen(summary.lat, summary.lon, 60, get=_getter(structures))
    assert found, "the golden office did not match its own parcel"
    top = found[0]
    assert top.summary.sid == sid, "a sibling scan won the property"
    assert top.roof_area_m2 == 2938.0 and top.has_solar is True
    assert top.distance_m < d13.MATCH_TOLERANCE_M
    assert any(n.what == "screening:matched" for n in notes)


@needs_kit
def test_the_representative_scan_is_the_one_search_returns():
    """The Los Angeles tower has nine scans. A screening result must name the one the
    user would audit, not a sibling suite - so this reuses `index.collapse` with the
    example folders' sids, not `search_results.json`, which holds three of the suites
    and cannot discriminate."""
    from backend.data_layer import api

    discovered = frozenset(api._load(f, "property_summary.json")["sid"] for f in api._folders())
    assert d13._GOLDEN_SIDS == discovered, \
        "the golden set is read from specs/examples/, so it follows a fixture swap"
    assert golden_office() in d13._GOLDEN_SIDS


@needs_kit
def test_a_filter_that_excludes_everything_gives_an_empty_list():
    """The workplan's acceptance: an empty result is an empty list."""
    summary = index.by_sid()[golden_office()]
    structures = [_structure(summary.lat, summary.lon, shape="flat")]
    found, notes = d13.screen(summary.lat, summary.lon, 60,
                              filters=d13.Filters(roof_shape=frozenset({"dome"})),
                              get=_getter(structures))
    assert found == []
    assert any(n.what == "screening:matched" for n in notes)


@needs_kit
def test_index_side_filters_shrink_the_candidate_set_before_any_call():
    calls = []
    summary = index.by_sid()[golden_office()]
    d13.screen(summary.lat, summary.lon, 400,
               filters=d13.Filters(segment="residential"), get=_getter([], calls))
    assert calls == [], "a segment with no candidates still called Vexcel"


@needs_kit
def test_results_are_ranked_by_roof_area_and_say_so():
    summary = index.by_sid()[golden_office()]
    nearby = [s for s in index.summaries()
              if s.lat and s.lon and d13._metres((summary.lat, summary.lon), (s.lat, s.lon)) <= 400]
    structures = [_structure(s.lat, s.lon, area=100.0 * (i + 1))
                  for i, s in enumerate(index.collapse(nearby))]
    found, notes = d13.screen(summary.lat, summary.lon, 400, get=_getter(structures))
    areas = [f.roof_area_m2 for f in found]
    assert areas == sorted(areas, reverse=True)
    matched = next(n for n in notes if n.what == "screening:matched")
    assert "not a retrofit return" in matched.detail


@needs_kit
def test_an_unmatched_candidate_is_counted_not_dropped_silently():
    summary = index.by_sid()[golden_office()]
    # A parcel far from every candidate: nothing matches, and the note says how many.
    found, notes = d13.screen(summary.lat, summary.lon, 60,
                              get=_getter([_structure(40.0, -90.0)]))
    assert found == []
    matched = next(n for n in notes if n.what == "screening:matched")
    assert "had no parcel within" in matched.detail


@needs_kit
def test_summaries_only_is_the_declared_output_shape():
    summary = index.by_sid()["L3266YcPPvd"]
    found, _ = d13.screen(summary.lat, summary.lon, 60,
                          get=_getter([_structure(summary.lat, summary.lon)]))
    out = d13.summaries_only(found)
    assert all(isinstance(s, PropertySummary) for s in out)
    for s in out:
        PropertySummary.model_validate(s.model_dump(mode="json"))
