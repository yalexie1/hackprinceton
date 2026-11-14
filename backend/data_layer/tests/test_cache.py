"""D4: the payload cache and the normal-missing-outcome table.

Every test here points `DATA_LAYER_CACHE_DIR` at a `tmp_path`, so nothing touches the
real cache and no test can be influenced by whether someone has run a live assembly
on this machine - which is precisely the failure D5 shipped once.
"""
from __future__ import annotations

import json
import os

import pytest

from backend.data_layer import cache, matterport, vexcel
from backend.schema import FetchRecord


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path / "cache"


# ---------- keys ----------

def test_two_queries_differing_only_in_include_do_not_share_a_key():
    """Finding 4.3: `precomputed` alone leaves every roof height null, so serving a
    caller who asked for `precomputed,calculated` the narrower payload would answer
    "no roof height" when the answer exists."""
    a = cache.key("vexcel", "POINT(0 0)", {"include": "precomputed"})
    b = cache.key("vexcel", "POINT(0 0)", {"include": "precomputed,calculated"})
    assert a != b


def test_key_is_stable_across_dict_ordering():
    a = cache.key("vexcel", "p", {"include": "x", "layer": "urban"})
    b = cache.key("vexcel", "p", {"layer": "urban", "include": "x"})
    assert a == b


def test_key_separates_source_identifier_and_version():
    assert cache.key("vexcel", "p") != cache.key("matterport", "p")
    assert cache.key("vexcel", "p") != cache.key("vexcel", "q")
    assert cache.key("vexcel", "p") != cache.key("vexcel", "p", {"a": 1})


def test_an_identifier_cannot_escape_the_cache_directory(isolated_cache):
    """A WKT point is a legal identifier and carries spaces and brackets; `..` is a
    legal-looking identifier and must not walk upwards."""
    for identifier in ("../../etc/passwd", "POINT(-118.3 34.0)", "/absolute", ".."):
        path = cache.path_for("vexcel", identifier)
        assert isolated_cache.resolve() in path.resolve().parents


def test_an_empty_identifier_still_yields_a_path():
    assert cache.path_for("vexcel", "///").name.endswith(".json")


# ---------- URLs ----------

def test_no_url_survives_a_cache_write(isolated_cache):
    """Matterport's response carries signed pano and floorplan URLs. They expire, so
    a cached one is a trap, not a shortcut."""
    payload = {
        "data": {"model": {
            "panoLocations": [{"id": "p1", "skybox": "https://cdn.matterport.com/x?sig=abc"}],
            "assets": {"floorplans": [{"url": "HTTPS://example.com/fp.png"}]},
            "name": "Executive Tower",
        }},
    }
    path, urls = cache.write_json("matterport", "SID", payload)
    assert len(urls) == 2
    raw = path.read_text()
    assert "https://" not in raw.lower() and "cdn.matterport.com" not in raw
    assert cache.URL_REDACTED in raw
    # The non-URL data is untouched.
    assert json.loads(raw)["data"]["model"]["name"] == "Executive Tower"


def test_strict_mode_raises_instead_of_scrubbing():
    with pytest.raises(cache.SignedUrlInCache):
        cache.write_json("matterport", "SID", {"u": "https://x/y"}, strict=True)


def test_scrubber_leaves_non_urls_alone():
    payload = {"a": "not a url", "b": "ftp://x", "c": "example.com", "d": 5, "e": True}
    scrubbed, urls = cache.scrub_urls(payload)
    assert urls == []
    assert scrubbed == payload


def test_the_redaction_marker_is_distinguishable_from_a_blank():
    scrubbed, _ = cache.scrub_urls({"a": "https://x", "b": "", "c": None})
    assert scrubbed == {"a": cache.URL_REDACTED, "b": "", "c": None}


# ---------- absent vs null ----------

def test_absent_and_null_stay_distinguishable(isolated_cache):
    """`{"ac-unit": {"count": null}}` means Vexcel flew the lot and found none;
    `{}` means it was never flown. Collapsing them loses the difference between "no
    air conditioning" and "we do not know", which changes the HVAC measure."""
    flown = {"roof-objects": {"ac-unit": {"count": None}}}
    never = {"roof-objects": {}}
    cache.write_json("vexcel", "flown", flown)
    cache.write_json("vexcel", "never", never)
    back_flown = cache.read_json("vexcel", "flown")
    back_never = cache.read_json("vexcel", "never")
    assert back_flown == flown and back_never == never
    assert "ac-unit" in back_flown["roof-objects"]
    assert "ac-unit" not in back_never["roof-objects"]


def test_scrubber_never_invents_a_key():
    scrubbed, _ = cache.scrub_urls({"a": {}})
    assert scrubbed == {"a": {}}
    assert list(scrubbed["a"]) == []


# ---------- atomic writes ----------

def test_an_interrupted_write_never_reads_as_a_hit(isolated_cache, monkeypatch):
    real_replace = os.replace

    def die(src, dst):
        raise KeyboardInterrupt("killed between the write and the rename")

    monkeypatch.setattr(os, "replace", die)
    with pytest.raises(KeyboardInterrupt):
        cache.write_json("vexcel", "POINT(0 0)", {"features": [1, 2, 3]})
    monkeypatch.setattr(os, "replace", real_replace)

    assert cache.read_json("vexcel", "POINT(0 0)") is None
    # And no temporary file is left lying around to be mistaken for an entry.
    leftovers = list(isolated_cache.rglob("*.tmp"))
    assert leftovers == [], leftovers


def test_a_truncated_entry_is_a_miss_not_a_crash(isolated_cache):
    path = cache.path_for("vexcel", "p")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"features": [1, 2')
    assert cache.read_json("vexcel", "p") is None


def test_a_rewrite_replaces_the_entry_rather_than_appending(isolated_cache):
    cache.write_json("vexcel", "p", {"v": 1})
    cache.write_json("vexcel", "p", {"v": 2})
    assert cache.read_json("vexcel", "p") == {"v": 2}


def test_bytes_and_text_round_trip(isolated_cache):
    path = cache.write_bytes("vexcel", "ortho", b"\x89PNG\r\n", suffix=".png")
    assert path.read_bytes() == b"\x89PNG\r\n"
    csv_path = cache.write_text("open-meteo", "34,-118", "time,temp\n1,2\n")
    assert csv_path.read_text().startswith("time,temp")


def test_atomic_write_path_creates_parents(tmp_path):
    target = tmp_path / "a" / "b" / "c.csv"
    cache.atomic_write_path(target, b"x")
    assert target.read_bytes() == b"x"


# ---------- cached_json ----------

def test_a_second_identical_call_is_served_from_the_cache():
    calls = []

    def fetch():
        calls.append(1)
        return {"features": [{"id": 1}]}

    first, hit1 = cache.cached_json("vexcel", "POINT(0 0)", fetch, {"include": "x"})
    second, hit2 = cache.cached_json("vexcel", "POINT(0 0)", fetch, {"include": "x"})
    assert (hit1, hit2) == (False, True)
    assert first == second
    assert len(calls) == 1, "the second call fetched again"


def test_refresh_refetches_and_overwrites():
    values = iter([{"v": 1}, {"v": 2}])
    nxt = lambda: next(values)
    cache.cached_json("vexcel", "p", nxt)
    again, hit = cache.cached_json("vexcel", "p", nxt, refresh=True)
    assert (again, hit) == ({"v": 2}, False)
    assert cache.read_json("vexcel", "p") == {"v": 2}


def test_use_cache_false_neither_reads_nor_writes(isolated_cache):
    """The D5 lesson. A caller that injects a transport is in control of what comes
    back, and a stubbed response must not be left on disk for the next caller."""
    cache.cached_json("vexcel", "p", lambda: {"real": True})
    stub, hit = cache.cached_json("vexcel", "p", lambda: {"stub": True}, use_cache=False)
    assert (stub, hit) == ({"stub": True}, False)
    assert cache.read_json("vexcel", "p") == {"real": True}, "the stub overwrote the cache"


# ---------- the missing-outcome table ----------

def test_every_normal_outcome_has_a_distinct_what():
    """`FetchRecord.status` has five values and the table has twelve outcomes, so
    `what` is the only thing that tells a reader which one happened."""
    whats = [v[1] for v in cache.MISSING_OUTCOMES.values()]
    assert len(whats) == len(set(whats)), "two outcomes share a `what`"


def test_every_normal_outcome_builds_a_valid_record():
    for name in cache.MISSING_OUTCOMES:
        rec = cache.record(name)
        FetchRecord.model_validate(rec.model_dump(mode="json"))
        assert rec.detail and len(rec.detail) > 20, f"{name} has no readable detail"


def test_the_six_four_outcomes_are_all_present():
    """Section 6.4 of the lane spec lists these as normal. A missing entry means a
    module invents its own string and two of them eventually collide."""
    for name in (
        "vexcel.no_parcel", "vexcel.rate_limited", "vexcel.no_building_type",
        "matterport.matterpak_locked", "matterport.no_splat",
        "matterport.no_defurnished", "matterport.rooms_without_dimensions",
        "costar.no_model_id", "costar.hidden_address", "costar.non_public_listing",
    ):
        assert name in cache.MISSING_OUTCOMES


def test_an_unknown_outcome_fails_loudly():
    with pytest.raises(KeyError):
        cache.record("vexcel.probably_fine")


def test_a_detail_suffix_is_appended_not_replaced():
    rec = cache.record("vexcel.no_parcel", "POINT(0 0)")
    assert "no parcel" in rec.detail and "POINT(0 0)" in rec.detail


def test_cache_note_says_which_way_the_payload_came():
    assert "cache" in cache.cache_note("vexcel", "x", hit=True).detail
    fresh = cache.cache_note("vexcel", "x", hit=False, urls_dropped=3)
    assert "3 URL" in fresh.detail
    assert fresh.status == "ok", "a replayed payload is real data, just not new"


# ---------- the source modules ----------

def test_vexcel_caches_the_default_transport_and_not_an_injected_one():
    calls = []

    def live(path, params):
        calls.append(params)
        return 200, {"features": [{"properties": {"parcel-source": "urban"}}]}

    # Injected: no cache read, no cache write.
    vexcel.get_vexcel_data_with_notes("POINT(0 0)", get=live)
    vexcel.get_vexcel_data_with_notes("POINT(0 0)", get=live)
    assert len(calls) == 2, "an injected transport was cached"
    assert cache.read_json("vexcel", "POINT(0 0)", vexcel._query_shape("urban")) is None


def test_vexcel_cache_hit_is_recorded_in_provenance(monkeypatch):
    body = {"features": [{"properties": {"parcel-source": "urban"}}]}
    monkeypatch.setattr(vexcel, "_default_get", lambda path, params: (200, body))

    _, first = vexcel.get_vexcel_data_with_notes("POINT(1 1)")
    _, second = vexcel.get_vexcel_data_with_notes("POINT(1 1)")
    assert any("fetched live" in (n.detail or "") for n in first)
    assert any("from the cache" in (n.detail or "") for n in second)


def test_a_rate_limit_is_never_left_in_the_cache(monkeypatch):
    """A 429 describes the service's last few seconds, not the parcel. Caching it
    would poison that point for every later run."""
    monkeypatch.setattr(vexcel, "_default_get", lambda path, params: (429, None))
    data, notes = vexcel.get_vexcel_data_with_notes("POINT(2 2)")
    assert data is None and notes[0].status == "error"
    assert cache.read_json("vexcel", "POINT(2 2)", vexcel._query_shape("urban")) is None


def test_a_404_is_cached_because_coverage_is_stable(monkeypatch):
    calls = []

    def absent(path, params):
        calls.append(1)
        return 404, None

    monkeypatch.setattr(vexcel, "_default_get", absent)
    vexcel.get_vexcel_data_with_notes("POINT(3 3)")
    vexcel.get_vexcel_data_with_notes("POINT(3 3)")
    assert len(calls) == 1, "a stable 'no parcel here' was re-asked"


def test_matterport_cache_key_includes_the_query_document():
    """Adding a field to `MODEL_QUERY` must not serve the older, narrower response -
    the Vexcel `include=` trap in a different costume."""
    before = matterport._query_shape()
    original = matterport.MODEL_QUERY
    try:
        matterport.MODEL_QUERY = original + "\n# one more field\n"
        assert matterport._query_shape() != before
    finally:
        matterport.MODEL_QUERY = original


def test_matterport_caches_the_default_transport_only(monkeypatch):
    body = {"data": {"model": {"id": "SID", "name": "x"}}}
    calls = []

    def post(query, variables):
        calls.append(variables)
        return body

    # Injected twice: two calls, nothing cached.
    matterport.get_matterport_data_with_notes("SID", post=post)
    matterport.get_matterport_data_with_notes("SID", post=post)
    assert len(calls) == 2
    assert cache.read_json("matterport", "SID", matterport._query_shape()) is None

    # Default transport twice: one call, and the second is a recorded hit.
    monkeypatch.setattr(matterport, "_default_post", lambda q, v: (calls.append(v) or body))
    _, first = matterport.get_matterport_data_with_notes("SID")
    _, second = matterport.get_matterport_data_with_notes("SID")
    assert len(calls) == 3, "the default transport was not cached"
    assert any("from the cache" in (n.detail or "") for n in second)
    assert any("fetched live" in (n.detail or "") for n in first)


# ---------- the bundle entry ----------

def test_the_bundle_entry_carries_no_url_and_rebuilds_raw(monkeypatch, tmp_path):
    """`CostarData.raw` is "the record as found in the kit" per the contract, and the
    golden house's record carries 54 URL-valued fields - CDN images and agent
    websites. A cached URL is a trap: nothing says when it stopped working. It is
    stripped on write and rebuilt from the local kit on read, so `raw` stays truthful
    on both paths instead of a cache hit disagreeing with a fresh assembly.
    """
    from backend.data_layer import api, index

    monkeypatch.setattr(api, "_CACHE", tmp_path)
    sid = "zvKHR9DHNjJ"
    bundle = api.get_property_bundle(sid, live=False)
    bundle.costar = _costar_with_urls(sid)

    path = api._write_bundle_cache(api._bundle_cache_path(sid), bundle)
    text = path.read_text()
    assert "https://" not in text and "http://" not in text
    assert json.loads(text)["stripped"] == ["costar.raw"]

    back = api._read_bundle_cache(sid, path)
    assert back is not None
    if index.kit_available():
        assert back.costar.raw, "raw was not rebuilt from the kit"
        assert back.costar.raw.get("id") is not None


def _costar_with_urls(sid):
    from backend.schema import CostarData

    return CostarData(
        kind="residential_listing", matterport_model_id=sid, record_id="1",
        raw={"id": 1, "media": [{"uri": "https://imagescdn.example.com/x.jpg?sig=a"}]},
    )


def test_a_url_outside_costar_raw_refuses_the_write_rather_than_persisting_it(
    monkeypatch, tmp_path
):
    """If a future field starts carrying a URL, the cache must not quietly persist it
    nor quietly mangle it. It refuses the write, the caller still gets the bundle, and
    `provenance` says why it was not cached."""
    from backend.data_layer import api

    monkeypatch.setattr(api, "_CACHE", tmp_path)
    sid = "zvKHR9DHNjJ"
    bundle = api.get_property_bundle(sid, live=False)
    bundle.climate.weather_source = "https://example.com/tmy.csv"

    with pytest.raises(cache.SignedUrlInCache):
        api._write_bundle_cache(api._bundle_cache_path(sid), bundle)


def test_a_bundle_entry_in_the_old_bare_format_is_a_miss(monkeypatch, tmp_path):
    """Entries written before the wrapper exist on real machines. They must cost a
    reassembly, not an exception."""
    from backend.data_layer import api

    monkeypatch.setattr(api, "_CACHE", tmp_path)
    sid = "zvKHR9DHNjJ"
    bundle = api.get_property_bundle(sid, live=False)
    path = api._bundle_cache_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(bundle.model_dump_json())      # the pre-D4 shape
    assert api._read_bundle_cache(sid, path) is None
    # ...and it is removed. An entry this code can never read again is garbage, and a
    # pre-D4 entry is garbage that keeps leaking the URLs D4 exists to keep out.
    assert not path.exists()


def test_no_url_in_any_entry_in_the_real_cache():
    """The D4 criterion, checked against whatever is actually on this machine. Skips
    on a checkout that has never fetched anything."""
    import re

    root = cache.cache_root()
    # The env var is pointed at a tmp_path by the autouse fixture; check the real one.
    from backend.data_layer.cache import _ROOT

    real = _ROOT / "data" / "cache"
    if not real.is_dir():
        pytest.skip("nothing cached on this machine")
    url = re.compile(r"https?://")
    offenders = []
    for path in real.rglob("*.json"):
        if "/kit/" in str(path):
            continue        # the CoStar kit mirror is the sponsor's file, not our entry
        if url.search(path.read_text(errors="ignore")):
            offenders.append(str(path.relative_to(real)))
    assert offenders == [], f"URLs persisted in: {offenders[:5]}"
