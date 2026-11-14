"""The aerial imagery reaches the bundle (issue #319 follow-up, @Sri-SriPod's finding).

`imagery.fetch_ortho` existed and nothing called it, so a live bundle carried no `ortho_path`
and `GET /api/runs/{id}/roof` reported `image_available` false for every property.

Obliques are not fetched, on the lead's call: nothing reads `oblique_paths`, and the four
directions cost about 2.9 s on a cold bundle at the endpoint most prone to 429. The tests below
pin that as a decision with a record behind it rather than an omission.

Nothing here touches the network: each test replaces the fetcher.
"""
from __future__ import annotations

import pytest

from backend.data_layer import api, imagery, vexcel
from backend.schema import FetchRecord, VexcelData

WKT = "POLYGON ((-118.3172 34.0932, -118.3170 34.0932, -118.3170 34.0937, -118.3172 34.0932))"


def _bundle_with(vex: VexcelData):
    """A bundle carrying this VexcelData, read from the house example so the rest is real."""
    import json
    from pathlib import Path
    from backend.schema import PropertyBundle
    root = Path(__file__).resolve().parents[3] / "specs" / "examples" / "house"
    raw = json.loads((root / "property_bundle.json").read_text())
    return PropertyBundle.model_validate(raw).model_copy(update={"vexcel": vex})


def parcel(parcel_wkt_override: str | None = None, **kw) -> VexcelData:
    return VexcelData(collection="us-ca-losangeles-2025",
                      parcel_wkt=parcel_wkt_override or WKT, **kw)


@pytest.fixture
def fake_imagery(monkeypatch):
    """The ortho fetcher under the test's control. `fetch_oblique` and the coverage lookup are
    replaced with refusals: if the assembly ever starts calling them again, these fail loudly
    rather than quietly costing a demo three seconds."""
    state = {"ortho": ("data/cache/vexcel-image/sid-ortho/abc.jpg", [])}

    def fetch_ortho(wkt, *, sid="", post=None, refresh=False):
        path, notes = state["ortho"]
        return path, list(notes)

    def refuse(*a, **k):
        raise AssertionError("the assembly must not fetch obliques: nothing reads them")

    monkeypatch.setattr(imagery, "fetch_ortho", fetch_ortho)
    monkeypatch.setattr(imagery, "fetch_oblique", refuse)
    monkeypatch.setattr(vexcel, "oblique_directions", refuse)
    return state


def test_the_ortho_path_is_filled_from_the_cache(fake_imagery):
    filled, _ = api._with_imagery("sid", parcel())
    assert filled.ortho_path == "data/cache/vexcel-image/sid-ortho/abc.jpg"


def test_assembly_does_not_fetch_obliques_and_points_at_the_door_that_does(fake_imagery):
    """Four directions cost about 2.9 s on a cold bundle at the endpoint most prone to 429, and
    no *run* needs them, so assembly leaves them alone. There is a screen that shows them now
    (#374), so the record points at `get_obliques` rather than saying nothing reads them - an
    empty mapping with no record would read as a failed fetch."""
    filled, notes = api._with_imagery("sid", parcel())
    assert filled.oblique_paths == {}
    said = [n for n in notes if n.what == "oriented/extract"]
    assert len(said) == 1 and said[0].status == "missing"
    assert "get_obliques" in (said[0].detail or ""), "the record names the on-demand door"


def test_no_ortho_is_a_record_and_never_an_exception(fake_imagery):
    """Missing data is a record, never a raise (SPEC 14). The roof view degrades to no image."""
    fake_imagery["ortho"] = (None, [])
    filled, notes = api._with_imagery("sid", parcel())
    assert filled.ortho_path is None
    missing = [n for n in notes if n.what == "ortho/extract" and n.status == "missing"]
    assert len(missing) == 1 and "aerial image" in (missing[0].detail or "")


def test_the_fetchers_own_records_reach_the_provenance(fake_imagery):
    fake_imagery["ortho"] = ("data/cache/vexcel-image/sid-ortho/abc.jpg",
                             [FetchRecord(layer="vexcel", what="ortho/extract", status="ok",
                                          detail="fetched live and cached")])
    _, notes = api._with_imagery("sid", parcel())
    ok = [n for n in notes if n.what == "ortho/extract" and n.status == "ok"]
    assert len(ok) == 1 and ok[0].detail == "fetched live and cached"


def test_nothing_else_about_the_parcel_is_touched(fake_imagery):
    """The imagery step adds paths. It must not disturb the D16 structure choice or the
    attributes the rest of the lane reads."""
    before = parcel(attributes={"metadata.collection": "us-ca-losangeles-2025"})
    filled, _ = api._with_imagery("sid", before)
    assert filled.model_dump(exclude={"ortho_path", "oblique_paths"}) == \
        before.model_dump(exclude={"ortho_path", "oblique_paths"})


def test_the_stored_path_is_the_shape_get_asset_can_serve(fake_imagery):
    """`get_asset` resolves a bundle path against the repo root and refuses anything outside the
    cache, so the path has to be the repo-relative one `cache.relative` returns - not absolute,
    and not the `data/cache/<sid>/vexcel/ortho.png` the old hand-written fixtures carried."""
    filled, _ = api._with_imagery("sid", parcel())
    assert not filled.ortho_path.startswith("/")
    assert filled.ortho_path.startswith("data/cache/")


#: What `_assemble` currently produces. **Pinned, not a floor.** The previous version of this
#: test asserted `>= 4`, which passed happily when #360 changed assembly without bumping the
#: version - so a warm cache kept serving bundles with no climate zone and @Sri-SriPod's first
#: three re-recordings were all wrong. A floor can never catch a missing bump; an equality
#: forces whoever changes assembly to come here and decide.
EXPECTED_BUNDLE_RULE = 5


def test_the_bundle_rule_version_matches_what_assembly_produces():
    """The bundle cache is keyed on this, so a bundle written by older code is replayed as valid
    unless the number changes. If you changed what `_assemble` returns, bump both."""
    assert api.BUNDLE_RULE_VERSION == EXPECTED_BUNDLE_RULE, (
        "assembly changed without bumping BUNDLE_RULE_VERSION, or the version was bumped "
        "without updating this test - a warm cache will serve the old answer either way"
    )


def test_every_rule_version_is_documented():
    """The comment above the constant is how the next person knows what a cached bundle at
    version N is missing. A bump with no entry leaves that unanswerable."""
    import inspect
    source = inspect.getsource(api)
    head = source[: source.index("BUNDLE_RULE_VERSION =")]
    for version in range(1, EXPECTED_BUNDLE_RULE + 1):
        assert f"#: {version} - " in head, f"rule version {version} is not documented"


def test_the_assembly_actually_calls_the_imagery_step(monkeypatch, fake_imagery):
    """The tests above all exercise `_with_imagery` directly, so they pass whether or not
    `_assemble` calls it - which is exactly how a wiring gap survives a green suite. This one
    drives the assembly far enough to reach the step and no further: the climate fetch after it
    is allowed to fail, because what is under test is that the imagery step was reached at all.
    """
    from backend.data_layer import costar as d1
    from backend.data_layer import external as d9
    from backend.data_layer import index as d_index
    from backend.data_layer import matterport as d2
    from backend.schema import GeoReference, MatterportData, Quaternion

    scan = MatterportData(floors=[], rooms=[], panos=[], georeference=GeoReference(
        latitude=34.0934, longitude=-118.3171, rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0)))
    monkeypatch.setattr(d2, "get_matterport_data_with_notes", lambda sid: (scan, []))
    monkeypatch.setattr(d1, "get_costar_data", lambda sid: None)
    monkeypatch.setattr(d1, "index_by_model", lambda: {})
    monkeypatch.setattr(d_index, "by_sid", lambda: {})
    monkeypatch.setattr(api, "_parcel_at", lambda *a, **k: (parcel(), []))

    seen: list = []
    real = api._with_imagery

    def recorder(sid, vexcel):
        seen.append(sid)
        return real(sid, vexcel)

    monkeypatch.setattr(api, "_with_imagery", recorder)

    def no_climate(*a, **k):
        raise api.IncompleteBundle("climate is not under test here", [])
    monkeypatch.setattr(d9, "get_climate_site", no_climate)

    with pytest.raises(api.IncompleteBundle):
        api._assemble("sid")
    assert seen == ["sid"], "_assemble never reached the imagery step"


# ---------- obliques on demand, for a screen that shows them (#374) ----------

def test_obliques_are_keyed_by_direction_and_only_when_fetched(monkeypatch):
    """@vinayak-sinha now has a screen that shows them, which is the condition the assembly
    comment named. They stay out of `_assemble`: a run never needs them, and four directions
    cost about 2.9 s at the endpoint most prone to 429."""
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel()))
    monkeypatch.setattr(vexcel, "oblique_directions", lambda wkt, **k: ["north", "south"])
    monkeypatch.setattr(imagery, "fetch_oblique", lambda wkt, d, **k: (
        (f"data/cache/vexcel-image/sid-{d}/x.jpg", []) if d == "north" else (None, [])))

    paths, notes = api.get_obliques("sid", live=True)
    assert paths == {"north": "data/cache/vexcel-image/sid-north/x.jpg"}
    assert "south" not in paths, "a direction that could not be fetched is left out"
    assert any(n.what == "oriented/collections" for n in notes)


def test_a_property_with_no_parcel_asks_for_nothing(monkeypatch):
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel().model_copy(
                            update={"parcel_wkt": None})))

    def refuse(*a, **k):
        raise AssertionError("no parcel means no crop can be cut, so nothing may be fetched")
    monkeypatch.setattr(vexcel, "oblique_directions", refuse)
    monkeypatch.setattr(imagery, "fetch_oblique", refuse)

    paths, notes = api.get_obliques("sid", live=True)
    assert paths == {} and notes[0].status == "missing"


def test_a_failing_coverage_call_is_recorded_rather_than_raised(monkeypatch):
    """A property preview must degrade to no imagery, never 500."""
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel()))
    monkeypatch.setattr(vexcel, "oblique_directions",
                        lambda wkt, **k: (_ for _ in ()).throw(RuntimeError("HTTP 429")))

    paths, notes = api.get_obliques("sid", live=True)
    assert paths == {} and notes[0].status == "error" and "429" in (notes[0].detail or "")


def test_asking_for_named_directions_skips_the_coverage_call(monkeypatch):
    """A caller that already knows which direction it wants should not pay for a lookup."""
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel()))

    def refuse(*a, **k):
        raise AssertionError("the coverage service must not be asked when directions are given")
    monkeypatch.setattr(vexcel, "oblique_directions", refuse)
    monkeypatch.setattr(imagery, "fetch_oblique",
                        lambda wkt, d, **k: (f"data/cache/vexcel-image/sid-{d}/x.jpg", []))

    paths, _ = api.get_obliques("sid", directions=["north"], live=True)
    assert paths == {"north": "data/cache/vexcel-image/sid-north/x.jpg"}


def test_the_bundle_rule_version_does_not_move_for_an_on_demand_fetch():
    """This adds no field to a cached bundle, so a warm cache stays valid."""
    assert api.BUNDLE_RULE_VERSION == EXPECTED_BUNDLE_RULE


def test_cached_only_makes_no_request_at_all(monkeypatch):
    """@vinayak-sinha caught this: the first version asked the coverage service and POSTed even
    with live=False, so a discovery page would have fetched imagery per card. `live=False` means
    cached-only everywhere else in this lane and must mean it here."""
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel()))

    def refuse(*a, **k):
        raise AssertionError("cached-only must not touch the network")
    monkeypatch.setattr(vexcel, "oblique_directions", refuse)
    monkeypatch.setattr(imagery, "fetch_oblique", refuse)
    monkeypatch.setattr(imagery, "cached_oblique",
                        lambda wkt, d, sid="": f"data/cache/vexcel-image/sid-{d}/x.jpg"
                        if d == "oblique-north" else None)

    paths, notes = api.get_obliques("sid", live=False)
    assert paths == {"oblique-north": "data/cache/vexcel-image/sid-oblique-north/x.jpg"}
    assert notes[0].status == "ok" and "no request made" in (notes[0].detail or "")


def test_cached_only_with_nothing_cached_says_so(monkeypatch):
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel()))
    monkeypatch.setattr(imagery, "cached_oblique", lambda wkt, d, sid="": None)
    paths, notes = api.get_obliques("sid", live=False)
    assert paths == {} and notes[0].status == "missing"
    assert "live is off" in (notes[0].detail or "")


def test_a_rate_limited_direction_does_not_lose_the_others(monkeypatch):
    """`_default_post_bytes` returns None for 403 and 404 but **raises** for 429, which the first
    version's docstring promised to degrade from and did not. One slow direction must not cost
    the caller the three that worked."""
    monkeypatch.setattr(api, "get_property_bundle",
                        lambda sid, live=None: _bundle_with(parcel()))
    monkeypatch.setattr(vexcel, "oblique_directions",
                        lambda wkt, **k: ["north", "south", "east"])

    def flaky(wkt, direction, **k):
        if direction == "south":
            raise RuntimeError("Client error '429 Too Many Requests'")
        return f"data/cache/vexcel-image/sid-{direction}/x.jpg", []
    monkeypatch.setattr(imagery, "fetch_oblique", flaky)

    paths, notes = api.get_obliques("sid", live=True)
    assert sorted(paths) == ["east", "north"], "the two that worked survive"
    failed = [n for n in notes if n.status == "error"]
    assert len(failed) == 1 and "429" in (failed[0].detail or "")
    assert "south" in failed[0].what


def test_the_cache_lookup_and_the_fetch_cannot_disagree_about_the_key():
    """`cached_oblique` resolves the path a later `fetch_oblique` would write. If the two built
    the request differently, a cached file would never be found and every preview would re-fetch."""
    from backend.data_layer import cache
    wkt = "POLYGON ((0 0, 1 0, 1 1, 0 0))"
    request = imagery._oblique_request(wkt, "oblique-north")
    expected = cache.path_for("vexcel-image", "sid-oblique-north", request, suffix=".jpg")
    assert imagery.cached_oblique(wkt, "oblique-north", sid="sid") is None, "nothing cached yet"
    cache.write_bytes("vexcel-image", "sid-oblique-north", b"\xff\xd8\xff\xe0data", request,
                      suffix=".jpg")
    try:
        assert imagery.cached_oblique(wkt, "oblique-north", sid="sid") == cache.relative(expected)
    finally:
        expected.unlink(missing_ok=True)


def test_cached_only_uses_the_cached_live_parcel_not_the_fixture(monkeypatch, tmp_path):
    """The cache key is built from the parcel polygon, so a lookup only finds crops cut for the
    same parcel. Offline `get_property_bundle` returns the fixture by design, and the office
    fixtures carry approximated parcels - so the first version found nothing for either office
    even with all four directions on disk. Cached-only reads the cached live bundle first.
    """
    import json
    live_parcel = "POLYGON ((-118.4 34.0, -118.3 34.0, -118.3 34.1, -118.4 34.0))"
    folder = tmp_path / "sid"
    folder.mkdir()
    (folder / "bundle.json").write_text(json.dumps({
        "rule": api.BUNDLE_RULE_VERSION, "stripped": [],
        "bundle": _bundle_with(parcel(parcel_wkt_override=live_parcel)).model_dump(mode="json"),
    }))
    monkeypatch.setattr(api, "_cache_dir", lambda: tmp_path)

    def fixture_only(sid, live=None):
        raise AssertionError("the fixture must not be consulted when a live bundle is cached")
    monkeypatch.setattr(api, "get_property_bundle", fixture_only)

    asked: list[str] = []

    def lookup(wkt, direction, sid=""):
        asked.append(wkt)
        return f"data/cache/vexcel-image/sid-{direction}/x.jpg"
    monkeypatch.setattr(imagery, "cached_oblique", lookup)

    paths, notes = api.get_obliques("sid", live=False)
    assert len(paths) == 4
    assert asked and all(wkt == live_parcel for wkt in asked), "the live parcel, not the fixture's"
    assert "cached live bundle" in (notes[0].detail or "")
