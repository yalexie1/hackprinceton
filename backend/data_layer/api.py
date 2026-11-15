"""Public door of the Data lane (workplan 3.1). The only module other lanes import.

`get_property_bundle` can now assemble a real bundle from D1 (CoStar), D2
(Matterport), D3 (Vexcel) and D9 (weather and tariff), or replay the fixtures in
`specs/examples/`.

**Live assembly is opt-in and the default path is offline.** Six modules import this
door, including `backend/server.py` and the agent tools, and the server lane's
checkpoint asserts `pytest backend -q` makes no network call. A door that reached the
network on an ordinary call would break every other lane's offline tests, so live
assembly happens only when asked for - `live=True`, or `DATA_LAYER_LIVE=1`.

Whichever path runs, the bundle's `provenance` says which it was, so no caller can
mistake a fixture for live data.

Two deliberate choices, both from `specs/data-integration.md`:

- **No sid is hard-coded.** Example folders are discovered by scanning
  `specs/examples/` for any directory holding `property_summary.json`, and
  sid -> folder comes from reading those files. `specs/examples/office/` is being
  repointed at the Los Angeles office and an `office_houston/` folder follows, so
  anything keyed on a literal sid would break (noted by @yalexie1 on the board).
- **`search_properties` unions `search_results.json` with every folder's own
  summary**, deduped by sid. That keeps the golden properties findable while that
  file is mid-switch, and answered workplan R4 before `D7` landed.

`D7` now backs search with the whole CoStar kit - 14,932 scanned models over 5,098
properties - through `index.py`. The fixtures still come first and the kit is added
behind them, so:

- a checkout with **no kit mirror** behaves exactly as it did before `D7` (the kit is
  49 MB of licensed sponsor data and is not committed);
- the golden properties stay findable and keep their fixture summaries, which carry
  real room and panorama counts that the kit cannot supply.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Optional

from backend.schema import (
    ClimateSite,
    FetchRecord,
    PropertyBundle,
    PropertySummary,
    Segment,
    UseType,
    VexcelData,
    VexcelDetection,
)

from . import cache, index

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "specs" / "examples"
#: Overridden by tests via `monkeypatch.setattr(api, "_CACHE", tmp_path)`. `None`
#: means "ask D4", which honours `DATA_LAYER_CACHE_DIR` - without that, a runbook or
#: a test asking for a temporary cache still wrote bundles and weather files into the
#: real one, which is how a test asserting a cache file's *absence* came to fail.
_CACHE: Optional[Path] = None


def _cache_dir() -> Path:
    return _CACHE if _CACHE is not None else cache.cache_root()

#: The calendar year of the Open-Meteo **fallback** weather file. The primary source is
#: a TMYx typical year (#295); this year is used only when no station qualifies or the
#: TMYx file fails to verify. Pinned so a bundle is reproducible.
WEATHER_YEAR = 2024


class IncompleteBundle(RuntimeError):
    """A required contract field could not be sourced.

    `climate` and `tariff` are required by `PropertyBundle`. Rather than quietly
    substituting the fixture's numbers for live ones - which would fabricate data
    while looking successful - the call fails and carries the provenance.
    """

    def __init__(self, message: str, provenance: list[FetchRecord]):
        super().__init__(message)
        self.provenance = provenance


# ---------- fixture discovery ----------

def _folders() -> list[Path]:
    """Every example folder that carries a property summary, sorted for determinism."""
    return sorted(p for p in _EXAMPLES.iterdir() if (p / "property_summary.json").is_file())


def _load(folder: Path, name: str):
    return json.loads((folder / name).read_text())


def _fixture_summaries() -> list[PropertySummary]:
    """Every example folder's own summary, in folder order, then the rest of
    `search_results.json`, deduped by sid. Folder order first keeps the golden
    properties at the head of a search and ahead of the invented examples."""
    rows: list[dict] = []
    seen: set[str] = set()
    for folder in _folders():
        row = _load(folder, "property_summary.json")
        rows.append(row)
        seen.add(row["sid"])
    extra_path = _EXAMPLES / "search_results.json"
    if extra_path.is_file():
        for row in json.loads(extra_path.read_text()):
            if row["sid"] not in seen:
                rows.append(row)
                seen.add(row["sid"])
    return [PropertySummary.model_validate(r) for r in rows]


def _folder_for_sid(sid: str) -> Path:
    for folder in _folders():
        if _load(folder, "property_summary.json")["sid"] == sid:
            return folder
    raise LookupError(f"unknown sid: {sid}")


# ---------- door ----------

def search_properties(
    q: Optional[str] = None,
    segment: Optional[Segment] = None,
    use_type: Optional[UseType] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_m: Optional[float] = None,
    limit: int = 20,
    *,
    all_scans: bool = False,
) -> list[PropertySummary]:
    """Stage S1. Matches on name, address and city; `use_type="office"` is CoStar
    property type 5, read from the property record and never from which starter CSV
    the row sat in - 2,765 of the kit's 3,339 commercial properties are Multifamily.

    Ordering is deterministic: the fixture properties first, in folder order, then
    the rest of `search_results.json` as written, then the kit index. With a `lat`
    and `lon` the whole result is ranked nearest-first instead.

    **The kit contributes one row per property, not per scan.** A property averages
    three Matterport models and one apartment complex in the kit has 32, so without
    collapsing, a search for Houston offices returns "333 Northbelt" five times - the
    same building, once per scan. `all_scans=True` returns every model instead, and
    `scans_for_property` lists the siblings of one result.

    The fixture rows are **not** collapsed, because the sibling scans there are the
    point: `specs/examples/search_results.json` deliberately carries three suites of
    the Los Angeles tower, one of which (`BkjvwqdchVY`, 2 rooms and 93 panoramas) is
    the open-plan scan the desk-placement demo needs. Collapsing a curated set of
    nine would throw that away to tidy up a list that is already short.
    """
    out = index.filter_summaries(
        _fixture_summaries(), q, segment, use_type, lat, lon, radius_m
    )
    golden = {s.sid for s in out}

    # The kit goes behind the fixtures, and a kit row for a property a fixture
    # already represents is dropped - otherwise the Los Angeles office would appear
    # twice, once as `jfiEvosX974` with its real room counts and once as a sibling
    # scan of the same tower with zeros.
    kit = index.filter_summaries(index.summaries(), q, segment, use_type, lat, lon, radius_m)
    if kit:
        combined = index.collapse(out + kit, prefer=golden) if not all_scans else out + kit
        taken = {s.sid for s in out}
        out = out + [s for s in combined if s.sid not in taken]

    out = index.rank(out, lat=lat, lon=lon)
    return out[: max(0, limit)]


def get_property_summary(sid: str) -> PropertySummary:
    """Stage S1, workplan R3. Answers `GET /api/properties/{sid}`.

    The fixtures first, then the kit index, so any of the 14,932 scanned models has a
    summary and not only the golden five.
    """
    for folder in _folders():
        row = _load(folder, "property_summary.json")
        if row["sid"] == sid:
            return PropertySummary.model_validate(row)
    for summary in index.summaries():
        if summary.sid == sid:
            return summary
    raise LookupError(f"unknown sid: {sid}")


def scans_for_property(sid: str) -> list[PropertySummary]:
    """Every Matterport scan of the property `sid` belongs to, that one first.

    This is what `search_properties` collapses away, and it is the D5 criterion that
    an office with several models reports the alternatives. The LA tower has nine
    scans and they are not interchangeable: one has 36 panoramas over 8 rooms and
    another has 93 over 2, which is a different answer to "where do the desks go".
    """
    here = get_property_summary(sid)
    key = index.property_key(here)
    siblings = [
        s for s in _fixture_summaries() + list(index.summaries())
        if s.sid != sid and index.property_key(s) == key
    ]
    seen: set[str] = set()
    out = [here]
    for s in siblings:
        if s.sid not in seen:
            seen.add(s.sid)
            out.append(s)
    return out


def _bundle_cache_path(sid: str) -> Path:
    return _cache_dir() / sid / "bundle.json"


def _fixture_bundle(sid: str) -> PropertyBundle:
    bundle = PropertyBundle.model_validate(_load(_folder_for_sid(sid), "property_bundle.json"))
    bundle.provenance = list(bundle.provenance) + [FetchRecord(
        layer="matterport", what="bundle",
        status="fallback", detail="replayed from specs/examples/, not live data",
    )]
    return bundle


def get_property_bundle(
    sid: str, *, live: Optional[bool] = None, refresh: bool = False
) -> PropertyBundle:
    """Stage S2. All three layers present, or an explicit `FetchRecord` in `provenance`
    saying what is missing and why (SPEC 14). A second call is served from cache.

    `live` defaults to `DATA_LAYER_LIVE == "1"`, so the ordinary call path is offline
    and no other lane's tests reach the network.
    """
    if live is None:
        live = os.environ.get("DATA_LAYER_LIVE") == "1"

    # The cache belongs to the live path only. If the offline path consulted it, a
    # machine where someone had once run a live assembly would quietly test against
    # live data instead of the fixtures, and the suite would behave differently from
    # one checkout to the next.
    if not live:
        return _fixture_bundle(sid)

    cached = _bundle_cache_path(sid)
    if cached.is_file() and not refresh:
        replayed = _read_bundle_cache(sid, cached)
        if replayed is not None:
            return replayed

    bundle = _assemble(sid)
    try:
        _write_bundle_cache(cached, bundle)
    except cache.SignedUrlInCache as exc:
        # The bundle is fine; it simply cannot be cached without persisting a URL.
        # Returning it uncached is right - refusing to answer would be worse, and
        # scrubbing it would make a cache hit disagree with a fresh assembly.
        bundle.provenance = list(bundle.provenance) + [FetchRecord(
            layer="matterport", what="bundle:cache", status="error",
            detail=f"not cached: a URL-valued field would be persisted ({exc})"[:200],
        )]
    return bundle


#: What `_write_bundle_cache` removes before writing, and `_read_bundle_cache` puts
#: back. `CostarData.raw` is "the record as found in the kit" per the contract, and
#: those records carry CDN image URLs and agent websites - 54 of them on the golden
#: house. A cached URL is a trap: nothing says when it stopped working.
#:
#: Stripping it is safe precisely because it is *local* data. The kit mirror is on
#: disk, so `raw` is rebuilt on a cache hit in about 0.04 s, and the field stays
#: truthful on both paths. Scrubbing it in place instead would make a cache hit
#: disagree with a fresh assembly, which is the worse failure: silent and invisible.
#: Used only when neither the CoStar kit nor the Census geocoder can say which state
#: a property is in, and `get_tariff` requires one. Two of the three golden properties
#: are in California, and Vexcel's coverage is Los Angeles and Houston - so this is
#: the less-wrong guess, not a correct one, and `_assemble` records it as a fallback.
_TARIFF_DEFAULT_STATE = "CA"

_STRIPPED = "costar.raw"

#: Bumped whenever a change to assembly makes an existing cached bundle **wrong**
#: rather than merely old. An entry stamped with a different number is a miss.
#:
#: The bundle cache is keyed on the sid alone, which is right - one property, one
#: bundle - but it means a rule change does not change the key, so a warm cache keeps
#: serving the old answer. D16 is exactly that case: every bundle written before it
#: names whichever structure `features[0]` happened to hold, and at the Los Angeles
#: office that is a building 100 m from the address. A demo laptop with a warm cache
#: would have shown the old roof with nothing in the output to say so.
#:
#: 1 - pre-D16: Vexcel's `primary-structure` flag from an arbitrary capture.
#: 2 - D16: the structure enclosing the CoStar address point, floor plate deciding.
#: 3 - #295: the weather is a TMYx station typical year, Open-Meteo only the fallback.
#:     A bundle written before names the Open-Meteo 2024 file and its time zone.
#: 4 - #333: the aerial ortho is fetched and `ortho_path` points at the cached file.
#:     A bundle written before carries no path, so the roof view has no image.
#: 5 - #360: `climate_zone` is measured from the site's own weather year. A bundle
#:     written before carries `None`, and the A31 benchmark then reports
#:     `not_checked: no climate zone` - the one sanity check on the model, off.
#:     **#360 changed assembly and did not bump this, which is the bug this entry
#:     fixes.** @Sri-SriPod found it: his first three re-recordings all carried
#:     `climate_zone: None` because his cached bundles were still rule 4 and were
#:     replayed as valid. Changing what `_assemble` produces means bumping this in
#:     the same commit; nothing else makes a warm cache serve the new answer.
BUNDLE_RULE_VERSION = 5


def _write_bundle_cache(path: Path, bundle: PropertyBundle) -> Path:
    """Write the bundle atomically, with `costar.raw` left out.

    Raises `SignedUrlInCache` if any URL survives the strip, rather than persisting
    it or quietly mangling it. That is a loud failure on an unexpected payload shape,
    which is what a cache with a documented invariant should do when the invariant is
    about to break.
    """
    payload = bundle.model_dump(mode="json")
    stripped: list[str] = []
    if payload.get("costar") and payload["costar"].get("raw"):
        payload["costar"]["raw"] = {}
        stripped.append(_STRIPPED)
    _, urls = cache.scrub_urls(payload)
    if urls:
        raise cache.SignedUrlInCache(f"URL-valued fields remain: {urls[:5]}")
    return cache.atomic_write_path(
        path,
        json.dumps({"rule": BUNDLE_RULE_VERSION, "stripped": stripped, "bundle": payload},
                   separators=(",", ":")).encode(),
    )


def _read_bundle_cache(sid: str, path: Path) -> Optional[PropertyBundle]:
    """The cached bundle with `costar.raw` restored from the kit, or `None` on a miss.

    A miss covers a truncated entry and an entry written before this format, both of
    which cost a reassembly rather than the run.
    """
    try:
        entry = json.loads(path.read_text())
        payload = entry["bundle"]
        stripped = entry.get("stripped") or []
        if entry.get("rule") != BUNDLE_RULE_VERSION:
            # Written under an older assembly rule, so it is wrong rather than stale.
            # `KeyError` is how the handler below is already told to bin an entry.
            raise KeyError(f"rule {entry.get('rule')!r}, want {BUNDLE_RULE_VERSION}")
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        # An entry this code can never read again is garbage, a pre-D4 entry is
        # garbage that keeps leaking the URLs D4 exists to keep out of the cache, and
        # an entry from an older assembly rule is garbage that looks exactly like a
        # good answer. All of it is git-ignored and regenerable, so it goes.
        path.unlink(missing_ok=True)
        return None

    if _STRIPPED in stripped and payload.get("costar"):
        from backend.data_layer import costar as d1

        try:
            payload["costar"]["raw"] = d1.get_costar_data(sid).raw
        except Exception:
            # No kit mirror on this machine. The bundle is still usable; `raw` being
            # empty is visible, where a wrong `raw` would not be.
            pass
    try:
        return PropertyBundle.model_validate(payload)
    except Exception:
        return None


def _parcel_at(point, locator: str, costar, plate):
    """One parcel extract at `point`, with D16 choosing the capture and structure."""
    from backend.data_layer import vexcel as d3

    return d3.get_vexcel_data_with_notes(
        d3.point_wkt(*point), stories=(costar.stories if costar else None),
        at=point, floor_plate_m2=plate, locator=locator)


#: What a cold `ortho/extract` costs, measured live on the golden house parcel on 2026-11-14.
#: The four obliques cost 2.88 s more plus a 0.13 s coverage call, which is why they are not
#: fetched: see `_with_imagery`.
ORTHO_FETCH_SECONDS = 0.52


def _with_imagery(sid: str, vexcel: VexcelData) -> tuple[VexcelData, list[FetchRecord]]:
    """Fill `ortho_path` with the cached aerial crop of the parcel.

    `imagery.fetch_ortho` existed and **nothing called it**, so a live bundle carried no path
    and `/api/assets/{path}` had nothing to serve: the roof view (`GET /api/runs/{id}/roof`)
    reported `image_available` false for every property. Found by @Sri-SriPod on a live run.

    One `extract` POST, 0.52 s cold, and only on a live assembly - the bundle cache replays the
    path afterwards, and `BUNDLE_RULE_VERSION` is bumped so bundles cached before this are
    re-assembled rather than replayed without it.

    **Obliques are deliberately not fetched** (the lead's call, board 2026-11-14): nothing reads
    `oblique_paths`, the four directions cost 2.88 s plus a 0.13 s coverage call on a cold
    bundle, and `oriented/extract` is the endpoint most prone to 429 - so it is the likeliest
    thing to stall a demo for data no screen shows. The record says so rather than leaving a
    reader to wonder whether the fetch failed.
    """
    from backend.data_layer import imagery as d8

    notes: list[FetchRecord] = []
    update: dict = {}

    ortho, onotes = d8.fetch_ortho(vexcel.parcel_wkt, sid=sid)
    notes += onotes
    if ortho:
        update["ortho_path"] = ortho
    else:
        notes.append(FetchRecord(
            layer="vexcel", what="ortho/extract", status="missing",
            detail="no ortho crop for this parcel, so the roof view has no aerial image"))

    notes.append(FetchRecord(
        layer="vexcel", what="oriented/extract", status="missing",
        detail=("not fetched during assembly: four directions cost about 2.9 s on a cold bundle "
                "at the endpoint most prone to 429, and no run needs them. `get_obliques(sid)` "
                "fetches them on demand for a screen that does")))

    return (vexcel.model_copy(update=update) if update else vexcel), notes


def _with_climate_zone(climate: ClimateSite, state: Optional[str]) -> tuple[ClimateSite, FetchRecord]:
    """`climate.climate_zone` derived from the weather year this lane just cached.

    Reads the hourly file back rather than threading the arrays out of `get_climate_site`: the
    file is the thing every later stage reads anyway, so deriving the zone from it means the zone
    and the simulation can never disagree about which year they describe.
    """
    from backend.data_layer import external as d9

    if climate.climate_zone:
        return climate, FetchRecord(layer="weather", what="ashrae169/climate-zone", status="ok",
                                    detail=f"zone {climate.climate_zone} was already supplied")
    path = Path(climate.weather_path)
    path = path if path.is_absolute() else _ROOT / path
    try:
        with path.open(newline="") as handle:
            temps = [row["temp_c"] for row in csv.DictReader(handle)]
    except (OSError, KeyError) as exc:
        return climate, FetchRecord(layer="weather", what="ashrae169/climate-zone",
                                    status="missing",
                                    detail=f"the cached weather file could not be read: {exc}"[:200])
    zone, record = d9.climate_zone_from_temperatures(temps, state)
    if zone is None:
        return climate, record
    return climate.model_copy(update={"climate_zone": zone}), record


def _assemble(sid: str) -> PropertyBundle:
    """Build a bundle from the live sources.

    Matterport goes first: its `geocoordinates` is the authoritative location, and
    both Vexcel and the weather need it. CoStar follows for the record and the storey
    count, which the Vexcel height check needs to spot a podium.
    """
    from backend.data_layer import costar as d1
    from backend.data_layer import external as d9
    from backend.data_layer import locate as d16
    from backend.data_layer import matterport as d2
    from backend.data_layer import places as d14
    from backend.data_layer import vexcel as d3

    provenance: list[FetchRecord] = []

    matterport, notes = d2.get_matterport_data_with_notes(sid)
    provenance += notes

    costar = None
    try:
        costar = d1.get_costar_data(sid)
        provenance.append(FetchRecord(layer="costar", what="kit", status="ok"))
    except Exception as exc:
        provenance.append(FetchRecord(layer="costar", what="kit", status="missing",
                                      detail=str(exc)[:200]))

    # D10: the five datasets the spec never used. `Plan.value_uplift` (A30) needs a cap
    # rate and at least ten comparables or it returns None, and office plug loads and
    # schedules were being inferred while real tenancy data sat in the kit.
    if costar is not None and costar.property_id:
        from backend.data_layer import costar_extra as d10

        market, mnotes = d10.market_data(costar.property_id)
        occupancy, onotes = d10.occupancy_data(costar.property_id)
        costar = costar.model_copy(update={"market": market, "occupancy": occupancy})
        provenance += mnotes + onotes

    row = {}
    try:
        row = d1.index_by_model().get(sid) or {}
    except Exception:
        pass

    geo = matterport.georeference
    lat = geo.latitude if geo else None
    lon = geo.longitude if geo else None

    # D16, on the lead's rule: **the CoStar address point decides which building this
    # bundle is about**, not the georeference and not Vexcel's own `primary-structure`
    # flag. At the Los Angeles office the georeference sits inside no building in any
    # capture, 45 m from the address point, and the structure the response listed
    # first is a 2022 capture of the building next door.
    #
    # The parcel is **queried at that same point**, not at the georeference. Measured
    # over the six kit properties whose two locators are furthest apart: four returned
    # a different set of captures from the two points, and at `9xZApYqePUx` (Piney
    # Point Offices II, 78 m apart) the structure enclosing the address is **absent
    # from the georeference query altogether**, so querying there cannot find it. A
    # parcel extract costs 0.3 to 1.1 s. `locate.py` has the rest of the measurements.
    at, locator = (lat, lon), "georeference"
    indexed = index.by_sid().get(sid)
    if indexed is not None and indexed.lat is not None and indexed.lon is not None:
        at, locator = (indexed.lat, indexed.lon), "CoStar address"
    else:
        provenance.append(FetchRecord(
            layer="costar", what="address:coordinates", status="fallback",
            detail=("no CoStar address coordinates, so the Matterport georeference "
                    "picks the building; it locates the scan, not the parcel"),
        ))
    # The point everything downstream is built at. Normally the georeference, because
    # the scan was physically taken at the building. But 10 of 96 models in the warm
    # cache (10.4%) come back with no `geocoordinates` at all - Matterport never
    # georeferenced that scan - and every one of those 10 has coordinates in the CoStar
    # index, which `at` has already resolved above. Reading only `geo` here meant those
    # bundles raised `IncompleteBundle` with a usable location two variables away, and
    # @Sri-SriPod's eval run was losing about 12% of its cohort to it.
    #
    # Deliberately a FALLBACK, not a switch to `at`: where the georeference exists it
    # still wins, so no bundle that builds today moves by the 45-80 m between the two
    # locators. This path only runs where the alternative was no bundle at all.
    site_lat, site_lon = lat, lon
    if site_lat is None or site_lon is None:
        site_lat, site_lon = at
        if site_lat is not None and site_lon is not None:
            provenance.append(FetchRecord(
                layer="weather", what="location", status="fallback",
                detail=("the scan has no georeference, so the weather, the climate zone "
                        "and the parcel all come from the CoStar address point - that "
                        "locates the property, not the scan"),
            ))

    plate = d16.floor_plate_m2(costar)

    vexcel = None
    if site_lat is not None and site_lon is not None:
        vexcel, vnotes = _parcel_at(at, locator, costar, plate)
        provenance += vnotes
        if vexcel is None and locator != "georeference":
            # A geocode can land off the parcel, and then there is no parcel at all to
            # work from. The georeference is physically at the building because the
            # scan was taken there, so it is the right second try - and saying so
            # matters, since the building is then whatever is under the scan.
            vexcel, gnotes = _parcel_at((site_lat, site_lon), "georeference", costar, plate)
            provenance.append(FetchRecord(
                layer="vexcel", what="property/extract:locator", status="fallback",
                detail=(f"no parcel at the CoStar address point, so the georeference was "
                        f"used instead"),
            ))
            provenance += gnotes
    else:
        provenance.append(FetchRecord(layer="vexcel", what="property/extract",
                                      status="missing",
                                      detail="no georeference, so no point to query"))

    if vexcel is not None and vexcel.parcel_wkt:
        vexcel, inotes = _with_imagery(sid, vexcel)
        provenance += inotes

    if site_lat is None or site_lon is None:
        # Neither the scan nor the kit knows where this building is. There is genuinely
        # nothing to build climate from, so this still refuses.
        raise IncompleteBundle(
            f"{sid}: no georeference and no CoStar address coordinates, so climate "
            f"cannot be built", provenance)

    climate, cnotes = d9.get_climate_site(sid, site_lat, site_lon, WEATHER_YEAR)
    provenance += cnotes

    # D17: without a kit mirror the starter-CSV row is `{}`, so `state` was `None` and
    # `get_tariff` fell back to a hard-coded "CA". In Houston that is not a near miss -
    # it swaps 0.0896 for 0.3002 USD/kWh, moves the eGRID subregion from ERCT to CAMX,
    # and selects California contract clauses for a Texas building. @Sri-SriPod hit it
    # on a live run. The Census call D14 already makes carries the state FIPS, so this
    # is free on the bundle path and needs no new source.
    state = row.get("state")
    city = row.get("city")
    if not state:
        state, srecord = d14.state_for(lat, lon)
        provenance.append(srecord)
    if not city:
        city, crecord = d14.city_for(lat, lon)
        provenance.append(crecord)
    sector = "RES" if (costar and costar.kind == "residential_listing") else "COM"

    # D14: who serves the meter, from the Census incorporated-place layer rather than
    # the CoStar `City` field, which is a *mailing* city - right 14/14 for Los Angeles
    # and only 9 of 16 for Houston. `None` means "do not guess", and `get_tariff` then
    # keeps its own honest label rather than being handed a wrong utility name.
    utility, ploc = d14.utility_for(lat, lon, state or _TARIFF_DEFAULT_STATE)
    provenance.append(ploc)

    if not state:
        # Everything above failed: no kit row and no geocoder. The tariff state is a
        # required argument, so there is a default - but it is recorded as a guess
        # rather than passed silently, because a wrong state is invisible downstream.
        provenance.append(FetchRecord(
            layer="tariff", what="state", status="fallback",
            detail=(f"neither the CoStar kit nor the Census geocoder gave a state, so "
                    f"the tariff, the emissions factor and the legal templates all use "
                    f"{_TARIFF_DEFAULT_STATE} - check this before quoting any number"),
        ))
    tariff, tnotes = d9.get_tariff(state or _TARIFF_DEFAULT_STATE, sector, utility=utility)
    provenance += tnotes
    if tariff is None:
        raise IncompleteBundle(
            f"{sid}: tariff is a required field and could not be sourced", provenance)

    # D18: the ASHRAE zone, after the state, because the moisture letter comes from it.
    # Nothing was passing `climate_zone`, so every live bundle carried None while the
    # committed examples carried 3B, 3B and 2A, and the A31 benchmark reported
    # `not_checked: no climate zone` on every live run.
    climate, znote = _with_climate_zone(climate, state)
    provenance.append(znote)

    # Built before the bundle, not inside the constructor: it appends to `provenance`,
    # and relying on left-to-right argument evaluation to get that record into the
    # bundle is the kind of thing that silently stops being true.
    summary = _summary_from(sid, matterport, costar, row, state=state, city=city,
                            provenance=provenance)
    return PropertyBundle(
        summary=summary,
        matterport=matterport,
        vexcel=vexcel,
        costar=costar,
        climate=climate,
        tariff=tariff,
        provenance=provenance,
    )


#: Room labels that only a dwelling has. Measured on the golden set: the house returns
#: Bedroom, Bathroom, Closet, Dining Room and Hallway, while **all three commercial
#: scans return no room labels at all** - which is the same finding as the empty
#: `classifications` in the spec's section 3.4.
#:
#: Deliberately narrow. Bathroom, Kitchen, Closet and Hallway all occur in offices, so
#: they are not here; these are the ones that cannot. The test is positive-only:
#: finding one proves residential, finding none proves nothing.
_DWELLING_ROOMS = frozenset({
    "bedroom", "primary bedroom", "master bedroom", "living room", "dining room",
    "nursery", "guest bedroom", "family room", "den",
})


def _segment_evidence(matterport) -> Optional[str]:
    """`"residential"` when the scan's own room labels prove a dwelling, else `None`.

    The only second source for segment when there is no CoStar kit. **Vexcel's
    `building-type.class` cannot be used**: measured under D16 it reads
    `'single_family'` on the house but `'condo_apartment'` on *both* golden offices and
    `None` on the third, so it would not merely fail to help - it would argue for
    residential on a 16-storey office tower.
    """
    for room in matterport.rooms:
        if room.label and room.label.strip().casefold() in _DWELLING_ROOMS:
            return "residential"
    return None


def _summary_from(sid, matterport, costar, row, *, state=None, city=None,
                  provenance=None) -> PropertySummary:
    geo = matterport.georeference
    known = bool(row.get("property_id")) or (
        costar is not None and costar.kind in ("commercial_property", "residential_listing"))
    commercial = bool(row.get("property_id")) or (
        costar is not None and costar.kind == "commercial_property")

    if not known:
        # No kit, so nothing authoritative says which this is - and `segment` is not a
        # cosmetic field: it picks the measure catalogue (`catalogue.py:79`), the cost
        # and useful-life tables, the incentive filter, **C-PACE eligibility**
        # (`cpace.py:63` requires commercial) and which legal templates are listed.
        # The scan's room labels can prove a dwelling; nothing available can prove an
        # office, so an office without the kit is still recorded as a guess.
        evidence = _segment_evidence(matterport)
        if evidence == "residential":
            commercial = False
        if provenance is not None:
            provenance.append(FetchRecord(
                layer="costar", what="summary:segment",
                status="ok" if evidence else "fallback",
                detail=(
                    f"no CoStar record, so segment is inferred: the scan's room labels "
                    f"prove a dwelling" if evidence else
                    f"no CoStar record and no dwelling room label, so segment falls back to "
                    f"'{'commercial' if commercial else 'residential'}' - it decides the "
                    f"measure catalogue, the cost tables, the incentive filter, C-PACE "
                    f"eligibility and the legal templates, so mirror the kit before "
                    f"trusting a plan built on it"),
            ))
    # One use-type table for the lane, in `index.py`. A second one here, keyed by
    # enum *name* instead of code, is how the two quietly stop agreeing.
    use_type: UseType = (
        index.use_type_for(costar.kind, costar.property_type_code) if costar else "unknown"
    )
    # The index knows the building's name ("Executive Tower"); the starter CSV row
    # only knows its street address.
    indexed = index.by_sid().get(sid)
    return PropertySummary(
        sid=sid,
        name=(indexed.name if indexed else None) or row.get("address") or sid,
        segment="commercial" if commercial else "residential",
        use_type=use_type,
        # The address itself has no second source: a street address is not derivable
        # from a coordinate without a reverse-geocode this lane does not make, so it
        # stays empty without the kit rather than being approximated.
        address=row.get("address"),
        city=row.get("city") or city,
        state=row.get("state") or state,
        lat=geo.latitude if geo else None,
        lon=geo.longitude if geo else None,
        costar_property_id=row.get("property_id"),
        costar_listing_id=row.get("listing_id"),
        costar_residential_listing_id=row.get("residential_listing_id"),
        # The track site is the only source for a splat, and it is D12; until then
        # this says "not known to have one" rather than guessing.
        has_splat=False,
        has_defurnished=bool(matterport.defurnished_view_id),
        pano_count=len(matterport.panos),
        room_count=len(matterport.rooms),
        floor_count=len(matterport.floors),
    )


def detect_roof_elements(
    sid: str, labels: Optional[list[str]] = None, *, live: Optional[bool] = None
) -> list[VexcelDetection]:
    """Vexcel `elements/detect` with SAM 3 (`D8`). Lives in this lane because it is a
    network call and SPEC 14 requires analysis to run without one.

    `specs/data-integration.md` 4.4 measured the label quality: use `"roof"`, not
    `"roof plane"`, which returns nothing, and a detection threshold near 0.3 rather
    than the quickstart's 0.5. **Roof obstruction counts must come from the Vexcel
    precomputed `roof-objects` attributes, not from these masks** - SAM 3 missed a
    chimney the attributes report and invented two skylights they say do not exist.

    Live detection is opt-in on the same flag as the bundle, and needs the parcel
    polygon: a bare `POINT` makes `elements/detect` return 404.
    """
    if live is None:
        live = os.environ.get("DATA_LAYER_LIVE") == "1"

    if live:
        from backend.data_layer import imagery as d8

        bundle = get_property_bundle(sid, live=True)
        parcel = bundle.vexcel.parcel_wkt if bundle.vexcel else None
        if parcel:
            found, _ = d8.detect(
                parcel, sid=sid,
                labels=tuple(labels) if labels else d8.DEFAULT_LABELS,
            )
            return found
        return []

    bundle = get_property_bundle(sid)
    found = list(bundle.vexcel.detections) if bundle.vexcel else []
    if labels is not None:
        wanted = {l.casefold() for l in labels}
        found = [d for d in found if d.label.casefold() in wanted]
    return found


def roof_area_m2(sid: str, *, live: Optional[bool] = None) -> Optional[float]:
    """Usable roof area for the primary structure from the SAM 3 masks, or `None`.

    The **largest single mask**, never the sum and never the most confident: the
    detections are nested, so summing over-states by 2.6x, and on the golden house the
    most confident detection was the secondary structure. Measured 180.9 m2 against a
    precomputed footprint of 190.4 m2 - within 5 %. See `imagery.roof_area_m2`.
    """
    if live is None:
        live = os.environ.get("DATA_LAYER_LIVE") == "1"
    if not live:
        return None

    from backend.data_layer import imagery as d8

    bundle = get_property_bundle(sid, live=True)
    parcel = bundle.vexcel.parcel_wkt if bundle.vexcel else None
    if not parcel:
        return None
    area, _ = d8.roof_area_m2(parcel, sid=sid)
    return area


def in_pace_region(sid: str, *, live: Optional[bool] = None) -> Optional[bool]:
    """Whether the property sits in a PACE region, for `cpace_scenario` (A28).

    **Three answers, and the third is not the second.** `True` positively inside,
    `False` positively elsewhere, `None` could not be checked. A28 treats anything
    other than `True` as not eligible, which is right - but the caller must not report
    "not eligible" to a user when the real answer is that a geocoder was unreachable.

    `None` offline, because the check is a network call and SPEC 14 requires the
    analysis lane to run without one. The Houston golden office returns `True` live.
    """
    if live is None:
        live = os.environ.get("DATA_LAYER_LIVE") == "1"
    if not live:
        return None

    from backend.data_layer import places as d14

    summary = get_property_summary(sid)
    if summary.lat is None or summary.lon is None or not summary.state:
        return None
    return d14.in_pace_region(summary.lat, summary.lon, summary.state)[0]


def get_obliques(sid: str, *, directions: Optional[list[str]] = None,
                 live: Optional[bool] = None) -> tuple[dict[str, str], list[FetchRecord]]:
    """Cached oblique crops of a property's parcel, `{direction: path}`, fetched on demand.

    Deliberately **not** part of bundle assembly. @vinayak-sinha now has a screen that shows
    them, which is the condition the assembly comment named; but the reason the lead kept them
    out of `_assemble` has not changed - four directions cost about 2.9 s on a cold bundle at
    the endpoint most prone to 429, and no *run* needs them. A property preview asks for them
    once, the cache answers afterwards, and a demo run never pays for them at all.

    **`live=False` is cached-only**: it looks on disk and makes no request, so a discovery page
    can show what is already there without fetching imagery per card.

    When live, `directions` defaults to whatever the coverage service says exists here: obliques
    live only in the `urban` layer and not every direction exists everywhere, so asking beats
    guessing. A direction that 403s, 404s or 429s is left out of the mapping and recorded - a
    path that points at nothing would make `/api/assets` 404 for something the response
    promised, and one rate-limited direction must not cost the caller the three that worked.

    The bundle is not modified and `BUNDLE_RULE_VERSION` does not move: this adds no field to a
    cached bundle, so a warm cache stays valid.
    """
    if live is None:
        live = os.environ.get("DATA_LAYER_LIVE") == "1"

    from backend.data_layer import imagery as d8
    from backend.data_layer import vexcel as d3

    # The cache key is built from the parcel polygon, so a lookup only finds crops cut for the
    # *same* parcel. Offline `get_property_bundle` returns the fixture by design, and the office
    # fixtures carry approximated parcels - so looking there found nothing even with all four
    # directions on disk. Cached-only therefore reads the cached live bundle first, and says
    # which parcel it used.
    parcel, source = None, "fixture"
    if not live:
        cached = _bundle_cache_path(sid)
        if cached.is_file():
            replayed = _read_bundle_cache(sid, cached)
            if replayed is not None and replayed.vexcel and replayed.vexcel.parcel_wkt:
                parcel, source = replayed.vexcel.parcel_wkt, "cached live bundle"
    if parcel is None:
        bundle = get_property_bundle(sid, live=live)
        parcel = bundle.vexcel.parcel_wkt if bundle.vexcel else None
    if not parcel:
        return {}, [FetchRecord(layer="vexcel", what="oriented/extract", status="missing",
                                detail="no parcel polygon for this property, so no crop can be cut")]

    notes: list[FetchRecord] = []

    # `live=False` means cached-only, the same as everywhere else in this lane: look on disk and
    # make no request at all. @vinayak-sinha caught the first version asking the coverage service
    # and POSTing regardless, which would have made a discovery page fetch imagery per card.
    if not live:
        paths = {d: p for d in (directions or d8.OBLIQUE_DIRECTIONS)
                 if (p := d8.cached_oblique(parcel, d, sid=sid))}
        notes.append(FetchRecord(
            layer="vexcel", what="oriented/extract",
            status="ok" if paths else "missing",
            detail=(f"{len(paths)} cached oblique(s) for the parcel from the {source}, no "
                    f"request made: {', '.join(sorted(paths))}" if paths else
                    f"no oblique is cached for the parcel from the {source}, and live is off so "
                    f"none was fetched")))
        return paths, notes

    wanted = directions
    if wanted is None:
        try:
            wanted = d3.oblique_directions(parcel)
        except Exception as exc:                    # a preview must not fail on a coverage call
            return {}, [FetchRecord(layer="vexcel", what="oriented/collections", status="error",
                                    detail=str(exc)[:200])]
        notes.append(FetchRecord(
            layer="vexcel", what="oriented/collections", status="ok" if wanted else "missing",
            detail=(f"{len(wanted)} oblique direction(s) over this parcel: {', '.join(wanted)}"
                    if wanted else "no oblique coverage over this parcel")))

    paths: dict[str, str] = {}
    for direction in wanted:
        # `_default_post_bytes` returns None for 403 and 404 but **raises** for 429, which the
        # first version's docstring promised to degrade from and did not. One slow direction
        # must not cost the caller the three that worked.
        try:
            path, records = d8.fetch_oblique(parcel, direction, sid=sid)
        except Exception as exc:
            notes.append(FetchRecord(layer="vexcel", what=f"oriented/extract:{direction}",
                                     status="error", detail=str(exc)[:200]))
            continue
        notes += records
        if path:
            paths[direction] = path
    return paths, notes


def get_asset(path: str) -> bytes:
    """Return cached bytes for a path as stored in a bundle (`face_paths`,
    `ortho_path`, `weather_path`, ...).

    Never returns or stores a URL: signed Matterport and CoStar links expire, so the
    live version re-queries for a fresh link and returns the bytes. Any path outside
    the cache directory is refused.

    The stub has no fetch-on-miss, so a path inside the cache that is not present
    raises `FileNotFoundError` - the server should answer that with 404.
    """
    target = (_ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    cache_root = _cache_dir().resolve()
    if not target.is_relative_to(cache_root):
        raise ValueError(f"path outside the cache directory: {path}")
    if not target.is_file():
        raise FileNotFoundError(f"not cached: {path}")
    return target.read_bytes()


def get_pano_faces(sid: str, pano_id: str, defurnished: bool = False, *,
                   post=None, download=None) -> list[bytes]:
    """The six cube faces of one panorama, in the API's order (up, four sides, down). Cache first
    (`matterport.pano_face_paths`); on a miss, ask Matterport for fresh signed URLs, download the six
    faces, write them to those cache paths and return them. Nothing but bytes is stored: the URLs
    expire and are never kept. Raises `LookupError` when the model has no such panorama (or no
    defurnished set: only the furnished faces can be fetched), and `FileNotFoundError` never.
    """
    from . import matterport
    if defurnished:
        raise LookupError("defurnished panorama faces are not fetched, only the furnished ones")
    paths = [_ROOT / p for p in matterport.pano_face_paths(sid, pano_id)]
    root = _cache_dir().resolve()
    if not all(p.resolve().is_relative_to(root) for p in paths):
        raise ValueError(f"panorama paths outside the cache directory: {sid}/{pano_id}")
    if all(p.is_file() for p in paths):
        return [p.read_bytes() for p in paths]
    urls = matterport.pano_face_urls(sid, post=post).get(pano_id)
    if not urls:
        raise LookupError(f"no 2k panorama {pano_id} in model {sid}")
    get = download or matterport.download_face
    faces = [get(u) for u in urls]
    if not all(faces):
        raise LookupError(f"empty face downloaded for panorama {pano_id}")
    for path, data in zip(paths, faces):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return faces
