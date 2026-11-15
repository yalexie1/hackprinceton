"""A scan with no Matterport georeference must still build, from the CoStar address.

Measured on the warm cache: 10 of 96 Matterport models (10.4%) come back with no
`geocoordinates.latitude` - the scan was simply never georeferenced. Every one of
those 10 has coordinates in the CoStar index, and `_assemble` already loads them and
already *prefers* them for the parcel query, on the lead's D16 rule that the address
point decides which building the bundle is about.

The fatal guard and `get_climate_site` read the georeference anyway, so all 10 died
with `IncompleteBundle: no georeference, so climate cannot be built` while a usable
location sat two variables away. @Sri-SriPod's EBEWE eval run was losing ~12% of its
cohort to this.

Nothing here touches the network: every source is replaced.
"""
from __future__ import annotations

import pytest

from backend.data_layer import api
from backend.schema import (ClimateSite, FetchRecord, MatterportData, PropertySummary,
                            Tariff)

SID = "SCANNOGEO01"
ADDR_LAT, ADDR_LON = 29.7635, -95.4602       # a real failing case: Houston


@pytest.fixture
def sources(monkeypatch):
    """Every live source replaced. Matterport returns a scan with NO georeference."""
    from backend.data_layer import costar as d1
    from backend.data_layer import external as d9
    from backend.data_layer import locate as d16
    from backend.data_layer import matterport as d2
    from backend.data_layer import places as d14
    from backend.data_layer import index as dix

    scan = MatterportData(floors=[], rooms=[], panos=[], georeference=None)

    monkeypatch.setattr(d2, "get_matterport_data_with_notes", lambda sid: (scan, []))
    monkeypatch.setattr(d1, "get_costar_data",
                        lambda sid: (_ for _ in ()).throw(LookupError("no kit row")))
    monkeypatch.setattr(d1, "index_by_model", lambda: {})
    monkeypatch.setattr(dix, "by_sid", lambda: {
        SID: PropertySummary(sid=SID, name="No-georeference scan", segment="commercial",
                             use_type="office", lat=ADDR_LAT, lon=ADDR_LON,
                             address="1 Test St", city="Houston", state="TX")})
    monkeypatch.setattr(d16, "floor_plate_m2", lambda costar: None)
    monkeypatch.setattr(api, "_parcel_at", lambda *a, **k: (None, []))
    monkeypatch.setattr(d14, "state_for", lambda la, lo: ("TX", FetchRecord(
        layer="costar", what="state", status="ok")))
    monkeypatch.setattr(d14, "city_for", lambda la, lo: ("Houston", FetchRecord(
        layer="costar", what="city", status="ok")))
    monkeypatch.setattr(d14, "utility_for", lambda la, lo, st: (None, FetchRecord(
        layer="tariff", what="utility", status="missing")))

    seen = {}

    def climate(sid, lat, lon, year):
        seen["climate_point"] = (lat, lon)
        return ClimateSite(lat=lat, lon=lon, timezone="America/Chicago",
                           weather_path="data/cache/x.csv", weather_source="test"), []

    monkeypatch.setattr(d9, "get_climate_site", climate)
    monkeypatch.setattr(d9, "get_tariff", lambda st, sector, utility=None: (
        Tariff(utility="Test Co", electricity_usd_per_kwh=0.1, source="test",
               retrieved="2026-11-15"), []))
    return seen


def test_a_scan_with_no_georeference_still_builds(sources):
    """The whole point: this raised IncompleteBundle for 10.4% of real scans."""
    bundle = api._assemble(SID)
    assert bundle.climate is not None


def test_the_climate_is_built_at_the_costar_address_point(sources):
    """Not merely "it did not crash": it must use the address, not some other guess."""
    api._assemble(SID)
    assert sources["climate_point"] == (ADDR_LAT, ADDR_LON)


def test_the_fallback_is_recorded_not_silent(sources):
    """A location that did not come from the scan changes what the bundle means, so a
    reader must be able to see it. A silent fallback here is how a wrong location
    becomes invisible downstream."""
    bundle = api._assemble(SID)
    said = [r for r in bundle.provenance
            if r.status == "fallback" and "georeference" in (r.detail or "").lower()]
    assert said, "no FetchRecord explains that the location did not come from the scan"


def test_a_scan_with_neither_location_still_refuses(sources, monkeypatch):
    """The guard must not be deleted, only moved. With no georeference AND no address
    there is genuinely nothing to build climate from, and that must still refuse."""
    from backend.data_layer import index as dix
    monkeypatch.setattr(dix, "by_sid", lambda: {})
    with pytest.raises(api.IncompleteBundle):
        api._assemble(SID)


# --- the retry that must not happen (@yalexie1's review of #442) -----------------
def test_no_second_parcel_query_at_the_same_point(sources, monkeypatch):
    """With no georeference, the 'retry at the georeference' path has nothing to retry.

    #442 moved the retry's point from the georeference to `site_lat/site_lon`. When the
    georeference is absent those ARE the CoStar address, so the retry re-queries the
    identical point and files a record saying the georeference was used. That is a
    wasted call and, worse, a provenance line that is not true: a reader would believe
    the parcel came from the scan's own location.
    """
    calls = []

    def record(point, locator, costar, plate):
        calls.append((point, locator))
        return None, []                      # no parcel anywhere, to force the retry

    monkeypatch.setattr(api, "_parcel_at", record)
    bundle = api._assemble(SID)

    assert len(calls) == 1, f"queried the same point twice: {calls}"
    assert calls[0][1] == "CoStar address"
    claimed = [r for r in bundle.provenance
               if r.what == "property/extract:locator"]
    assert not claimed, (
        "a record claims the georeference was used, but there is no georeference: "
        f"{[r.detail for r in claimed]}")
