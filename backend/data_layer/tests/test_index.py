"""D7: the property index over the whole CoStar kit.

The kit is 49 MB of licensed sponsor data and is git-ignored, so a teammate's
checkout has no mirror. Tests that need one skip; the rest run everywhere, because
"search still works with no kit" is the behaviour other lanes actually depend on.

Reading a local file is not a network call, so these do **not** need
`RUN_LIVE_NETWORK=1` - same convention as the D1 kit tests.
"""
from __future__ import annotations

import json

import pytest

from backend.data_layer import api, index
from backend.schema import PropertySummary

#: Index facts per property, **keyed by sid and not by role**, so a golden-set swap
#: does not invalidate the table. @yalexie1 moved the LA golden office from
#: `jfiEvosX974` (PropertyId 246899) to `ZSPaQbkGcJJ` (Culver Connect, 27120) in #253;
#: both stay here, and each test uses whichever is golden today. Hard-coding the golden
#: sid is what broke these tests on `main`.
KNOWN = {
    "zvKHR9DHNjJ": ("residential", "single_family", "Los Angeles", "CA", None),
    "ZSPaQbkGcJJ": ("commercial", "office", "Los Angeles", "CA", "27120"),
    "jfiEvosX974": ("commercial", "office", "Los Angeles", "CA", "246899"),
    "L3266YcPPvd": ("commercial", "office", "Houston", "TX", "234088"),
}


def golden_sids() -> list[str]:
    """The sids of the example folders, discovered the way the lane's own code does."""
    return [api._load(folder, "property_summary.json")["sid"] for folder in api._folders()]


def golden_office() -> str:
    """The commercial golden property in California - the LA office, whichever it is."""
    return next(sid for sid in golden_sids()
                if KNOWN.get(sid, (None,))[0] == "commercial" and KNOWN[sid][3] == "CA")


GOLDEN = {sid: KNOWN[sid][:4] for sid in golden_sids() if sid in KNOWN}

needs_kit = pytest.mark.skipif(not index.kit_available(), reason="no CoStar kit mirror")


# ---------- works with or without a mirror ----------

def test_search_finds_every_golden_property():
    """Workplan R4, and it must hold whether or not the kit is mirrored."""
    found = {s.sid for s in api.search_properties(limit=500)}
    assert set(GOLDEN) <= found


def test_golden_properties_keep_their_fixture_summaries():
    """A kit row for the LA tower carries zeros for the scan statistics, because the
    kit has none. The fixture carries the real ones, so the fixture must win."""
    for sid in GOLDEN:
        summary = next(s for s in api.search_properties(limit=5000) if s.sid == sid)
        fixture = api.get_property_summary(sid)
        assert summary.pano_count == fixture.pano_count
        assert summary.room_count == fixture.room_count
        assert summary.pano_count > 0, f"{sid} lost its panorama count"


def test_use_type_table_covers_every_documented_code():
    """An unmapped code silently becomes `unknown`, which looks like missing data
    rather than a gap in this table."""
    if not index.kit_available():
        pytest.skip("enum names come from the kit")
    from backend.data_layer import costar

    for enum_name, table in (
        ("PropertyType", index.PROPERTY_TYPE_USE),
        ("ListingPropertyType", index.LISTING_TYPE_USE),
    ):
        documented = {int(k) for k in costar.enums()[enum_name]}
        assert documented <= set(table), (
            f"{enum_name} codes missing from the table: {sorted(documented - set(table))}"
        )


def test_use_type_for_is_the_only_mapping():
    assert index.use_type_for("commercial_property", 5) == "office"
    assert index.use_type_for("commercial_property", 11) == "multifamily_unit"
    assert index.use_type_for("residential_listing", 1) == "single_family"
    assert index.use_type_for("residential_listing", 4) == "multifamily_unit"
    # A composite `listingPropertyType` would be new data; it is reported, not guessed.
    assert index.use_type_for("residential_listing", 1 | 4) == "unknown"
    assert index.use_type_for("commercial_property", None) == "unknown"


def test_collapse_keeps_one_row_per_property_and_respects_prefer():
    rows = [
        PropertySummary(sid="a", name="Tower", segment="commercial", use_type="office",
                        costar_property_id="1"),
        PropertySummary(sid="b", name="Tower", segment="commercial", use_type="office",
                        costar_property_id="1"),
        PropertySummary(sid="c", name="Other", segment="commercial", use_type="office",
                        costar_property_id="2"),
    ]
    assert [s.sid for s in index.collapse(rows)] == ["a", "c"]
    assert [s.sid for s in index.collapse(rows, prefer={"b"})] == ["b", "c"]
    # Order is the input's, not the preferred row's position.
    assert [s.sid for s in index.collapse(list(reversed(rows)))] == ["c", "b"]


def test_property_key_falls_back_to_the_sid():
    orphan = PropertySummary(sid="lonely", name="x", segment="commercial", use_type="other")
    assert index.property_key(orphan) == "lonely"


def test_ranking_is_total_and_nearest_first():
    rows = [
        PropertySummary(sid="far", name="far", segment="commercial", use_type="office",
                        lat=34.1, lon=-118.3),
        PropertySummary(sid="none", name="none", segment="commercial", use_type="office"),
        PropertySummary(sid="near", name="near", segment="commercial", use_type="office",
                        lat=34.0, lon=-118.3),
    ]
    assert [s.sid for s in index.rank(rows, lat=34.0, lon=-118.3)] == ["near", "far", "none"]
    # No point given: input order, so a page does not reshuffle between calls.
    assert [s.sid for s in index.rank(rows)] == ["far", "none", "near"]


def test_scans_for_property_lists_the_siblings_with_the_asked_one_first():
    """One building, several scans. The sibling sids differ per property, so this asserts
    the rule rather than the names: the asked-for scan leads, nothing is listed twice,
    there is at least one sibling, and every scan belongs to the same CoStar property."""
    sid = golden_office()
    scans = api.scans_for_property(sid)
    assert scans[0].sid == sid
    assert len(scans) == len({s.sid for s in scans}), "a scan is listed twice"
    assert len(scans) > 1, f"{sid} should have sibling scans of the same building"
    expected_pid = KNOWN[sid][4]
    assert all(s.costar_property_id == expected_pid for s in scans)


# ---------- needs the mirror ----------

@needs_kit
def test_index_holds_every_scanned_model_once():
    from backend.data_layer import costar

    rows = index.summaries()
    assert len(rows) == len(costar.rows_by_model()), "a model was dropped or duplicated"
    assert len({s.sid for s in rows}) == len(rows)


@needs_kit
def test_the_golden_properties_are_in_the_kit_index():
    by = index.by_sid()
    for sid, (segment, use_type, city, state) in GOLDEN.items():
        row = by[sid]
        assert (row.segment, row.use_type, row.city, row.state) == (segment, use_type, city, state)
        assert row.lat is not None and row.lon is not None


@needs_kit
def test_the_la_office_resolves_to_the_property_id_the_team_picked():
    sid = golden_office()
    assert index.by_sid()[sid].costar_property_id == KNOWN[sid][4]


@needs_kit
def test_a_property_that_stopped_being_golden_is_still_in_the_index():
    """Dropping a property from `specs/examples/` must not drop it from the kit index -
    the index is every scanned model, not the demo set. `jfiEvosX974` stopped being the
    LA golden office in #253 and is still a real office in the kit."""
    row = index.by_sid()["jfiEvosX974"]
    assert row.costar_property_id == "246899"
    assert (row.segment, row.use_type) == ("commercial", "office")


@needs_kit
def test_offices_come_from_the_property_type_not_the_segment():
    """2,765 of the kit's 3,339 commercial properties are Multifamily, so
    "commercial" and "office" are different questions."""
    offices = index.search(use_type="office", limit=10_000)
    assert all(s.use_type == "office" for s in offices)
    commercial = index.search(segment="commercial", limit=20_000, all_scans=True)
    assert len(offices) < len(commercial) / 10


@needs_kit
def test_search_collapses_repeated_scans_of_one_building():
    """Before collapsing, "offices in Houston" returned 333 Northbelt five times."""
    collapsed = index.search(use_type="office", q="houston", limit=10_000)
    keys = [index.property_key(s) for s in collapsed]
    assert len(keys) == len(set(keys))
    every = index.search(use_type="office", q="houston", limit=10_000, all_scans=True)
    assert len(every) > len(collapsed), "this kit has repeated scans; nothing was collapsed"


@needs_kit
def test_radius_excludes_properties_without_coordinates():
    near = index.search(lat=34.0361802, lon=-118.4428766, radius_m=1500, limit=100)
    assert near, "nothing near the LA office"
    assert all(s.lat is not None and s.lon is not None for s in near)
    from backend.data_layer.index import _haversine_m

    assert all(_haversine_m(34.0361802, -118.4428766, s.lat, s.lon) <= 1500 for s in near)


@needs_kit
def test_every_row_validates_and_coordinates_are_nearly_complete():
    rows = index.summaries()
    for s in rows:
        PropertySummary.model_validate(s.model_dump(mode="json"))
    with_coords = sum(1 for s in rows if s.lat is not None and s.lon is not None)
    # Measured 2026-11-14: 14,929 of 14,932. A drop means the address parse broke.
    assert with_coords / len(rows) > 0.999


@needs_kit
def test_states_are_normalised_to_the_two_the_contract_allows():
    assert {s.state for s in index.summaries()} <= {"CA", "TX", None}


@needs_kit
def test_cache_is_rebuilt_when_a_source_file_changes(tmp_path, monkeypatch):
    """A stale cache would answer searches with fields that no longer mean what the
    caller thinks, and nothing would say so."""
    kit = tmp_path / "kit"
    (kit / "data").mkdir(parents=True)
    (kit / "schemas").mkdir()
    (kit / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n7,MODELA,1 Main St,HOUSTON,Texas\n")
    (kit / "residential-listings.csv").write_text(
        "ListingId,ResidentialListingId,MatterportModelId,Address,City,State\n")
    (kit / "data" / "commercial-property.jsonl").write_text(json.dumps({
        "id": 7, "propertyType": 5, "buildingName": "First Tower",
        "primaryAddress": {"fullStreetAddress": "1 Main St", "city": "Houston",
                           "state": "TX", "latitude": 29.7, "longitude": -95.4},
    }) + "\n")
    (kit / "data" / "residential-listings.jsonl").write_text("")
    monkeypatch.setenv("COSTAR_KIT_DIR", str(kit))

    from backend.data_layer import costar

    for fn in (costar.rows_by_model, index.summaries, index.by_sid, costar.enums):
        fn.cache_clear()

    assert [s.name for s in index.summaries()] == ["First Tower"]

    (kit / "data" / "commercial-property.jsonl").write_text(json.dumps({
        "id": 7, "propertyType": 5, "buildingName": "Renamed Tower",
        "primaryAddress": {"fullStreetAddress": "1 Main St", "city": "Houston",
                           "state": "TX", "latitude": 29.7, "longitude": -95.4},
    }) + "\n")
    index.summaries.cache_clear()
    index.by_sid.cache_clear()
    assert [s.name for s in index.summaries()] == ["Renamed Tower"], "stale cache served"

    for fn in (costar.rows_by_model, index.summaries, index.by_sid, costar.enums):
        fn.cache_clear()


@needs_kit
def test_a_csv_row_pointing_at_a_missing_record_stays_findable(tmp_path, monkeypatch):
    """The kit ships 15,371 CSV rows and records for only some of their parents. A
    row we cannot enrich is still a real address, so it is indexed as `unknown`
    rather than dropped."""
    kit = tmp_path / "kit"
    (kit / "data").mkdir(parents=True)
    (kit / "commercial-properties.csv").write_text(
        "PropertyId,MatterportModelId,Address,City,State\n999,GHOST,5 Elm St,Austin,TX\n")
    (kit / "residential-listings.csv").write_text(
        "ListingId,ResidentialListingId,MatterportModelId,Address,City,State\n")
    (kit / "data" / "commercial-property.jsonl").write_text("")
    (kit / "data" / "residential-listings.jsonl").write_text("")
    monkeypatch.setenv("COSTAR_KIT_DIR", str(kit))

    from backend.data_layer import costar

    for fn in (costar.rows_by_model, index.summaries, index.by_sid):
        fn.cache_clear()

    row = index.by_sid()["GHOST"]
    assert (row.address, row.city, row.state) == ("5 Elm St", "Austin", "TX")
    assert row.use_type == "unknown"
    assert row.lat is None

    for fn in (costar.rows_by_model, index.summaries, index.by_sid):
        fn.cache_clear()
