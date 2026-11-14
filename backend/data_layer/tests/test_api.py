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
    cache = api._CACHE / "_d5_selftest"
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
