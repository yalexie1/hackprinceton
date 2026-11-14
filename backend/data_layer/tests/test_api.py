"""Acceptance tests for package D5 (the Data lane door).

Every test runs offline: the module never opens a socket. Nothing here names a
literal sid, so the tests keep passing when `specs/examples/office/` is repointed
and `office_houston/` is added.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.data_layer import api
from backend.schema import PropertyBundle, PropertySummary, VexcelDetection

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"
FOLDERS = sorted(p.name for p in EX.iterdir() if (p / "property_summary.json").is_file())
SIDS = [json.loads((EX / f / "property_summary.json").read_text())["sid"] for f in FOLDERS]


def test_folders_discovered():
    assert FOLDERS, "no example folders found"
    assert len(SIDS) == len(set(SIDS)), "two example folders share a sid"


@pytest.mark.parametrize("sid", SIDS)
def test_bundle_validates_and_is_deterministic(sid):
    first = api.get_property_bundle(sid)
    PropertyBundle.model_validate(first.model_dump(mode="json"))
    assert first.summary.sid == sid
    # SPEC 14: a second call returns the same thing (the live version serves it from cache)
    assert api.get_property_bundle(sid).model_dump(mode="json") == first.model_dump(mode="json")


@pytest.mark.parametrize("sid", SIDS)
def test_every_layer_is_present_or_explained(sid):
    """SPEC 14: all three layers present, or an explicit FetchRecord saying what is missing."""
    bundle = api.get_property_bundle(sid)
    explained = {r.layer for r in bundle.provenance}
    for layer, value in (("vexcel", bundle.vexcel), ("costar", bundle.costar)):
        assert value is not None or layer in explained, (
            f"{sid}: {layer} is absent with no FetchRecord explaining it"
        )
    assert bundle.matterport is not None
    assert bundle.climate is not None and bundle.tariff is not None


@pytest.mark.parametrize("sid", SIDS)
def test_summary_matches_bundle(sid):
    summary = api.get_property_summary(sid)
    PropertySummary.model_validate(summary.model_dump(mode="json"))
    assert summary.sid == api.get_property_bundle(sid).summary.sid


def test_unknown_sid_raises_lookuperror():
    with pytest.raises(LookupError):
        api.get_property_bundle("NOSUCHMODEL")
    with pytest.raises(LookupError):
        api.get_property_summary("NOSUCHMODEL")


def test_search_finds_every_golden_property():
    """Workplan R4: search works before D7 lands."""
    found = {s.sid for s in api.search_properties(limit=500)}
    assert set(SIDS) <= found


def test_search_by_address_and_filters():
    for sid in SIDS:
        summary = api.get_property_summary(sid)
        if summary.address:
            hits = {s.sid for s in api.search_properties(q=summary.address, limit=500)}
            assert sid in hits, f"{sid} not found by its own address"
        seg = {s.segment for s in api.search_properties(segment=summary.segment, limit=500)}
        assert seg == {summary.segment}


def test_search_by_use_type_office():
    offices = api.search_properties(use_type="office", limit=500)
    assert all(s.use_type == "office" for s in offices)


def test_search_radius_and_limit():
    summary = api.get_property_summary(SIDS[0])
    if summary.lat is not None and summary.lon is not None:
        near = api.search_properties(lat=summary.lat, lon=summary.lon, radius_m=200, limit=500)
        assert summary.sid in {s.sid for s in near}
        far = api.search_properties(lat=summary.lat, lon=summary.lon, radius_m=1.0, limit=500)
        assert all(s.sid != "EXAMPLEhou1" for s in far)
    assert len(api.search_properties(limit=1)) == 1
    assert api.search_properties(limit=0) == []


@pytest.mark.parametrize("sid", SIDS)
def test_detect_roof_elements(sid):
    dets = api.detect_roof_elements(sid)
    for d in dets:
        VexcelDetection.model_validate(d.model_dump(mode="json"))
    if dets:
        label = dets[0].label
        filtered = api.detect_roof_elements(sid, labels=[label])
        assert filtered and all(d.label == label for d in filtered)
        assert api.detect_roof_elements(sid, labels=["no_such_label"]) == []


def test_get_asset_refuses_paths_outside_the_cache():
    for bad in ("specs/SPEC.md", "../../etc/passwd", "/etc/passwd", ".env"):
        with pytest.raises(ValueError):
            api.get_asset(bad)


def test_get_asset_missing_in_cache_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        api.get_asset("data/cache/does/not/exist.jpg")


def test_get_asset_never_returns_a_url(tmp_path, monkeypatch):
    """A cached asset is returned as bytes; no URL is produced or stored."""
    cache = api._cache_dir() / "_d5_selftest"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / "probe.bin"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        got = api.get_asset(str(f.relative_to(api._ROOT)))
        assert got == b"\x89PNG\r\n\x1a\n"
        assert b"http" not in got
    finally:
        f.unlink()
        cache.rmdir()


def test_no_network_imports():
    """The stub must not reach the network: no socket use anywhere in the module."""
    src = (Path(api.__file__)).read_text()
    for forbidden in ("requests.", "httpx.", "urllib.request", "socket."):
        assert forbidden not in src, f"{forbidden} present in the D5 stub"


# ---------- live assembly, D5 live (issue #104) ----------

def test_offline_is_the_default_and_says_so():
    """Six modules import this door and the suite must stay offline, so `live`
    defaults off and the bundle records that it was replayed."""
    bundle = api.get_property_bundle(SIDS[0])
    replayed = [r for r in bundle.provenance
                if r.status == "fallback" and "specs/examples" in (r.detail or "")]
    assert replayed, "a fixture replay must be labelled as one"


def test_a_cached_live_bundle_never_leaks_into_the_offline_path(tmp_path, monkeypatch):
    """Regression guard. The cache is for the live path only: if the offline path
    read it, a machine that had once assembled live data would silently test against
    that instead of the fixtures."""
    monkeypatch.setattr(api, "_CACHE", tmp_path)
    sid = SIDS[0]
    fake = api.get_property_bundle(sid)
    fake.summary.name = "CACHED LIVE VALUE"
    # Seeded through the writer, not by hand: the on-disk shape is D4's business
    # (it strips `costar.raw` so no URL is persisted), and a test that hand-builds
    # it is really testing a copy of the format that drifts from the real one.
    api._write_bundle_cache(api._bundle_cache_path(sid), fake)

    offline = api.get_property_bundle(sid, live=False)
    assert offline.summary.name != "CACHED LIVE VALUE"
    # ...but the live path does serve it, which is SPEC 14's "second call from cache"
    assert api.get_property_bundle(sid, live=True).summary.name == "CACHED LIVE VALUE"


def test_env_var_selects_the_live_path(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_CACHE", tmp_path)
    monkeypatch.setenv("DATA_LAYER_LIVE", "1")
    sid = SIDS[0]
    seeded = api.get_property_bundle(sid, live=False)
    seeded.summary.name = "FROM CACHE"
    api._write_bundle_cache(api._bundle_cache_path(sid), seeded)
    # DATA_LAYER_LIVE=1 means the cache is consulted without passing live=True
    assert api.get_property_bundle(sid).summary.name == "FROM CACHE"


def test_refresh_bypasses_the_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_CACHE", tmp_path)
    sid = SIDS[0]
    seeded = api.get_property_bundle(sid, live=False)
    seeded.summary.name = "STALE"
    api._write_bundle_cache(api._bundle_cache_path(sid), seeded)
    assert api.get_property_bundle(sid, live=True).summary.name == "STALE"
    calls = []
    monkeypatch.setattr(api, "_assemble", lambda s: (calls.append(s), seeded)[1])
    api.get_property_bundle(sid, live=True, refresh=True)
    assert calls == [sid], "refresh must re-assemble rather than read the cache"


def test_incomplete_bundle_carries_its_provenance():
    from backend.schema import FetchRecord
    notes = [FetchRecord(layer="tariff", what="eia/retail-sales", status="missing")]
    err = api.IncompleteBundle("no tariff", notes)
    assert err.provenance == notes
    assert isinstance(err, RuntimeError)


def test_use_type_mapping_covers_the_golden_properties():
    """The mapping moved to `index.use_type_for` in D7 and is keyed by CoStar's enum
    *code*, not its name: `api` had a second table that had to agree with the
    index's, and two tables that must agree eventually do not."""
    from backend.data_layer import index

    assert index.use_type_for("commercial_property", 5) == "office"       # Office
    assert index.use_type_for("residential_listing", 1) == "single_family"  # Detached


# ---------- D17: a complete summary without the CoStar kit ----------

def _matterport(room_labels=()):
    """A minimal `MatterportData` with a georeference and the given room labels."""
    from backend.schema import GeoReference, MatterportData, Quaternion, Room

    return MatterportData(
        georeference=GeoReference(latitude=29.746, longitude=-95.4576,
                                  rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)),
        floors=[], panos=[],
        rooms=[Room(id=f"r{i}", floor_id="f0", label=label)
               for i, label in enumerate(room_labels)],
    )


def test_the_kit_row_still_wins_when_it_has_a_state():
    """The geocoder is a *fallback*. CoStar's own record stays authoritative where it
    exists, so mirroring the kit cannot change an answer this already got right."""
    summary = api._summary_from(
        "sid", _matterport(), None,
        {"state": "TX", "city": "Houston", "address": "2100 West Loop"},
        state="CA", city="Los Angeles")
    assert summary.state == "TX" and summary.city == "Houston"


def test_a_resolved_state_fills_an_empty_row():
    summary = api._summary_from("sid", _matterport(), None, {},
                                state="TX", city="Houston")
    assert summary.state == "TX" and summary.city == "Houston"


def test_the_address_is_left_empty_rather_than_approximated():
    """A street address is not derivable from a coordinate without a reverse-geocode
    this lane does not make, and an invented one would be quoted in a legal document."""
    summary = api._summary_from("sid", _matterport(), None, {},
                                state="TX", city="Houston")
    assert summary.address is None


def test_room_labels_prove_a_dwelling_when_there_is_no_costar_record():
    """`segment` is not cosmetic: it selects the measure catalogue, the cost and
    useful-life tables, the incentive filter, **C-PACE eligibility** (which requires
    commercial) and which legal templates are offered."""
    provenance = []
    summary = api._summary_from(
        "sid", _matterport(["Bedroom", "Dining Room"]), None, {}, provenance=provenance)
    assert summary.segment == "residential"
    note = next(n for n in provenance if n.what == "summary:segment")
    assert note.status == "ok" and "room labels" in note.detail


def test_an_office_without_the_kit_is_recorded_as_a_guess():
    """All three commercial golden scans return **no room labels at all**, so nothing
    available proves an office. The honest outcome is a loud record, not a confident
    answer - and the fix is to mirror the kit."""
    provenance = []
    summary = api._summary_from("sid", _matterport(), None, {}, provenance=provenance)
    note = next(n for n in provenance if n.what == "summary:segment")
    assert note.status == "fallback"
    assert "C-PACE" in note.detail and "mirror the kit" in note.detail
    assert summary.segment in ("residential", "commercial")


def test_a_costar_record_means_no_segment_guess_is_recorded():
    from backend.schema import CostarData

    provenance = []
    costar = CostarData(kind="commercial_property", matterport_model_id="m",
                        record_id="r", raw={}, property_id="234088")
    summary = api._summary_from("sid", _matterport(), costar, {}, provenance=provenance)
    assert summary.segment == "commercial"
    assert not [n for n in provenance if n.what == "summary:segment"]


def test_vexcel_building_type_is_not_used_for_segment():
    """Measured under D16: `building-type.class` reads `'single_family'` on the house
    but **`'condo_apartment'` on both golden offices** and None on the third. Using it
    would argue for residential on a 16-storey office tower, so it is not consulted -
    this asserts the source does not quietly come back."""
    import inspect

    source = inspect.getsource(api._segment_evidence)
    assert "building-type" not in source or "cannot be used" in source
    assert "rooms" in source


def test_bathrooms_and_hallways_are_not_dwelling_evidence():
    """They occur in offices too. The test is positive-only: finding a dwelling room
    proves residential; finding none proves nothing."""
    assert api._segment_evidence(_matterport(["Bathroom", "Hallway", "Closet"])) is None
    assert api._segment_evidence(_matterport(["Bedroom"])) == "residential"
    assert api._segment_evidence(_matterport()) is None
