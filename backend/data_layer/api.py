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
  file is mid-switch, and answers workplan R4: search works before `D7`, which only
  adds radius ranking on top.
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

_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "specs" / "examples"
_CACHE = _ROOT / "data" / "cache"

_EARTH_RADIUS_M = 6_371_000.0

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
) -> list[PropertySummary]:
    """Stage S1. Matches on name, address and city; `use_type="office"` means CoStar
    property type 5 once `D1` is live. Ordering is deterministic: golden properties
    first, in folder order, then the rest of `search_results.json` as written."""
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

    out = [PropertySummary.model_validate(r) for r in rows]

    if q:
        needle = q.casefold()
        out = [
            s for s in out
            if needle in s.name.casefold()
            or needle in (s.address or "").casefold()
            or needle in (s.city or "").casefold()
        ]
    if segment is not None:
        out = [s for s in out if s.segment == segment]
    if use_type is not None:
        out = [s for s in out if s.use_type == use_type]
    if lat is not None and lon is not None and radius_m is not None:
        out = [s for s in out if _within(s, lat, lon, radius_m)]
    return out[: max(0, limit)]


def get_property_summary(sid: str) -> PropertySummary:
    """Stage S1, workplan R3. Answers `GET /api/properties/{sid}`."""
    return PropertySummary.model_validate(_load(_folder_for_sid(sid), "property_summary.json"))


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
        return PropertyBundle.model_validate_json(cached.read_text())

    bundle = _assemble(sid)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(bundle.model_dump_json())
    return bundle


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


_USE_TYPE_BY_COSTAR: dict[str, UseType] = {
    "Office": "office",
    "GeneralRetail": "retail",
    "Multifamily": "multifamily_unit",
    "Detached": "single_family",
    "Townhouse": "single_family",
}


def _summary_from(sid, matterport, costar, row) -> PropertySummary:
    geo = matterport.georeference
    commercial = bool(row.get("property_id")) or (
        costar is not None and costar.kind == "commercial_property")
    use_type: UseType = "unknown"
    if costar and costar.property_type:
        use_type = _USE_TYPE_BY_COSTAR.get(costar.property_type, "other")
    return PropertySummary(
        sid=sid,
        name=row.get("address") or sid,
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


def detect_roof_elements(sid: str, labels: Optional[list[str]] = None) -> list[VexcelDetection]:
    """Vexcel `elements/detect` with SAM 3; the live code is `D8`. Lives in this lane
    because it is a network call and SPEC 14 requires analysis to run without one.

    `specs/data-integration.md` 4.4 measured the label quality: use `"roof"`, not
    `"roof plane"`, which returns nothing, and a detection threshold near 0.3 rather
    than the quickstart's 0.5. Roof obstruction counts should come from the Vexcel
    precomputed `roof-objects` attributes, not from these masks.
    """
    bundle = get_property_bundle(sid)
    found = list(bundle.vexcel.detections) if bundle.vexcel else []
    if labels is not None:
        wanted = {l.casefold() for l in labels}
        found = [d for d in found if d.label.casefold() in wanted]
    return found


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


# ---------- helpers ----------

def _within(summary: PropertySummary, lat: float, lon: float, radius_m: float) -> bool:
    if summary.lat is None or summary.lon is None:
        return False
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(summary.lat - lat)
    dlon = radians(summary.lon - lon)
    h = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(summary.lat)) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(sqrt(h)) <= radius_m
