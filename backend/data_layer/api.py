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

import json
import os
from pathlib import Path
from typing import Optional

from backend.schema import (
    FetchRecord,
    PropertyBundle,
    PropertySummary,
    Segment,
    UseType,
    VexcelDetection,
)

from . import cache, index

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "specs" / "examples"
_CACHE = _ROOT / "data" / "cache"

#: The calendar year fetched for the hourly weather file. One real year, not a TMY -
#: see D9. Pinned so a bundle is reproducible.
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
    return _CACHE / sid / "bundle.json"


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
_STRIPPED = "costar.raw"


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
        json.dumps({"stripped": stripped, "bundle": payload}, separators=(",", ":")).encode(),
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
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        # An entry this code can never read again is garbage, and a pre-D4 entry is
        # garbage that keeps leaking the URLs D4 exists to keep out of the cache. It
        # is git-ignored and regenerable from the live sources, so it goes.
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


def _assemble(sid: str) -> PropertyBundle:
    """Build a bundle from the live sources.

    Matterport goes first: its `geocoordinates` is the authoritative location, and
    both Vexcel and the weather need it. CoStar follows for the record and the storey
    count, which the Vexcel height check needs to spot a podium.
    """
    from backend.data_layer import costar as d1
    from backend.data_layer import external as d9
    from backend.data_layer import matterport as d2
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

    row = {}
    try:
        row = d1.index_by_model().get(sid) or {}
    except Exception:
        pass

    geo = matterport.georeference
    lat = geo.latitude if geo else None
    lon = geo.longitude if geo else None

    vexcel = None
    if lat is not None and lon is not None:
        vexcel, vnotes = d3.get_vexcel_data_with_notes(
            d3.point_wkt(lat, lon), stories=(costar.stories if costar else None))
        provenance += vnotes
    else:
        provenance.append(FetchRecord(layer="vexcel", what="property/extract",
                                      status="missing",
                                      detail="no georeference, so no point to query"))

    if lat is None or lon is None:
        raise IncompleteBundle(f"{sid}: no georeference, so climate cannot be built",
                               provenance)

    climate, cnotes = d9.get_climate_site(sid, lat, lon, WEATHER_YEAR)
    provenance += cnotes

    state = row.get("state")
    sector = "RES" if (costar and costar.kind == "residential_listing") else "COM"
    tariff, tnotes = d9.get_tariff(state or "CA", sector)
    provenance += tnotes
    if tariff is None:
        raise IncompleteBundle(
            f"{sid}: tariff is a required field and could not be sourced", provenance)

    return PropertyBundle(
        summary=_summary_from(sid, matterport, costar, row),
        matterport=matterport,
        vexcel=vexcel,
        costar=costar,
        climate=climate,
        tariff=tariff,
        provenance=provenance,
    )


def _summary_from(sid, matterport, costar, row) -> PropertySummary:
    geo = matterport.georeference
    commercial = bool(row.get("property_id")) or (
        costar is not None and costar.kind == "commercial_property")
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
        address=row.get("address"),
        city=row.get("city"),
        state=row.get("state"),
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
    cache = _CACHE.resolve()
    if not target.is_relative_to(cache):
        raise ValueError(f"path outside the cache directory: {path}")
    if not target.is_file():
        raise FileNotFoundError(f"not cached: {path}")
    return target.read_bytes()

