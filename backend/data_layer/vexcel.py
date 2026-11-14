"""Vexcel client (package D3): parcel attributes and geometry.

Imagery bytes and SAM 3 detection are D8, not here. Every rule below is a verified
finding from `specs/data-integration.md` section 4:

- Base `https://api.vexcelgroup.com/v2`, header `X-API-KEY`. **WKT is longitude
  first**, always `srid=4326`. Coverage is Houston and Los Angeles only.
- **One call, `include=precomputed,calculated`.** `include=calculated` on its own
  returns a *disjoint* two-key set per structure with no `primary-structure` and no
  structure id, so on a multi-structure parcel it cannot be joined back to the
  precomputed structures at all.
- The response is a **GeoJSON `FeatureCollection`**; the flat dotted attributes sit
  inside a feature's `properties`, not at the top level.
- **One response holds one feature per capture collection, and `features[0]` is not
  the newest.** A single point returned 5 features on the golden house, 4 on the Los
  Angeles office and 6 on the Houston office - the same parcel as seen by different
  flights, every ring containing the point. Which one is read changes the footprint,
  the rooftop AC count and the solar flag. `locate.py` (D16) chooses; nothing here may
  go back to `features[0]`.
- **`404` means no parcel at that point and is a normal outcome**, reported as a
  `FetchRecord` rather than raised. **`429` is retried with exponential backoff.**
- Parcel geometry can be a **`MultiPolygon`**, so the largest ring is taken.
- **`primary-structure` does not reliably pick the building.** It is right on the
  golden house, which holds two structures, and wrong on both golden offices: at the
  Los Angeles office the flagged structure is one the address point is not inside. It
  is kept in `attributes` and `VexcelStructure.primary` now carries D16's choice.
- **`roof-characteristics.height` must not be used for building height.** Across
  three lots its magnitude equals `|roof - ground|` but its sign came out +, -, +
  with no pattern, and on both towers the magnitude is wrong (15.5 m and 15.7 m
  against 44-47 m expected) because the detected footprint is 1.7x and 4.6x the
  CoStar floor plate - Vexcel outlines a podium, not the tower. `roof_rise_m()`
  returns the absolute value and `plausible_building_height` says whether it can be
  believed at all.
- **`building-type.class` is unreliable**: `"commercial"` on one lot, `null` on the
  house and on the Los Angeles office. Never require it.
- **The `layer` set changes the answer, so it is pinned and recorded.** Verified on
  the Los Angeles office 2026-11-14: `layer=urban` selects collection
  `us-ca-losangeles-2023` and decomposes the parcel into **1** structure of
  2,207.43 m2, while `layer=urban,urban-r,wide-area,urban-g` selects
  `us-ca-losangeles_rf08-2023` and gives **2** structures with a primary of
  2,473.94 m2 - different footprints, roof elevations and heights. Coverage is
  Houston and Los Angeles, both urban, and obliques exist only in `urban`, so
  `urban` is the default and the collection is carried on `VexcelData.collection`
  so a result can be traced to the flight it came from.
- **The calculated roof elevation and height are not reproducible.** The same point
  with the same parameters returned -15.497, then -15.338; the house returned 0.4254
  then 0.3639. Never assert equality on them and never derive a dimension from them.
- **`403` means outside the licensed coverage**, as distinct from `404` meaning no
  parcel inside it. Both are normal outcomes reported as `FetchRecord`s.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

from backend.schema import FetchRecord, VexcelData, VexcelStructure

from . import cache

BASE = "https://api.vexcelgroup.com/v2"

#: Obliques exist only in `urban`, and the layer set changes which collection is
#: selected and therefore every attribute, so `urban` is the pinned default.
DEFAULT_LAYERS = "urban"
#: Wider coverage, a different collection, and a different parcel decomposition.
ALL_LAYERS = "urban,urban-r,wide-area,urban-g"
OBLIQUE_LAYER = "urban"
OBLIQUE_DIRECTIONS = ("oblique-north", "oblique-south", "oblique-east", "oblique-west")

#: A standing building shorter than this is a failed measurement, not a short
#: building.
MIN_PLAUSIBLE_HEIGHT_M = 2.5
#: Shortest floor-to-floor worth believing, for checking a rise against a storey
#: count. Both golden towers report ~15.5 m for 16-17 storeys, which fails this.
MIN_FLOOR_TO_FLOOR_M = 2.2

MAX_RETRIES = 4
BACKOFF_BASE_S = 0.5

#: `(status_code, json_or_none)`
Getter = Callable[[str, dict], tuple[int, Optional[dict]]]


class VexcelAuthMissing(RuntimeError):
    pass


class NoParcel(LookupError):
    """HTTP 404: no parcel at that point. A normal outcome, not a fault."""


def api_key(key_set: str = "") -> str:
    suffix = f"_{key_set.upper().lstrip('_')}" if key_set else ""
    key = os.environ.get(f"VEXCEL_API_KEY{suffix}")
    if not key:
        raise VexcelAuthMissing(f"VEXCEL_API_KEY{suffix} must be set")
    return key


def point_wkt(lat: float, lon: float) -> str:
    """WKT is **longitude first**. Getting this backwards silently queries the wrong
    hemisphere rather than failing."""
    return f"POINT({lon} {lat})"


# ---------- transport ----------

def _default_get(path: str, params: dict) -> tuple[int, Optional[dict]]:
    import httpx  # lazy so offline tests need no transport

    delay = BACKOFF_BASE_S
    for attempt in range(MAX_RETRIES):
        resp = httpx.get(
            f"{BASE}/{path}",
            params=params,
            headers={"X-API-KEY": api_key(os.environ.get("VEXCEL_KEY_SET", ""))},
            timeout=180.0,
        )
        if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code in (403, 404):
            # 403 = outside the licensed coverage, 404 = no parcel inside it.
            return resp.status_code, None
        resp.raise_for_status()
        return resp.status_code, resp.json()
    return 429, None


# ---------- height ----------

def roof_rise_m(structure_attrs: dict) -> Optional[float]:
    """`|roof - ground|` from `roof-characteristics.height`, sign discarded.

    The sign is unreliable: measured +0.364, -15.497 and +15.710 on three lots with
    no pattern. The magnitude is consistent, so the absolute value is the only usable
    reading.
    """
    h = structure_attrs.get("roof-characteristics.height")
    return abs(float(h)) if isinstance(h, (int, float)) else None


def plausible_building_height(structure_attrs: dict, stories: Optional[int] = None) -> bool:
    """Whether the Vexcel rise can be believed as this building's height.

    Without `stories` only the absolute floor applies, which catches the golden
    house (0.36 m for a gabled house) but not a tower. **Pass `stories` from CoStar
    `numStoriesAboveGrade` to catch the podium case**: both golden towers report
    ~15.5 m for 16-17 storeys, far below the floor-to-floor minimum, because Vexcel
    outlines a podium rather than the tower.
    """
    rise = roof_rise_m(structure_attrs)
    if rise is None or rise < MIN_PLAUSIBLE_HEIGHT_M:
        return False
    if stories and stories > 1:
        return rise >= stories * MIN_FLOOR_TO_FLOOR_M
    return True


# ---------- geometry ----------

def largest_ring_wkt(geometry: Optional[dict]) -> Optional[str]:
    """A parcel can be a `MultiPolygon` (the golden house is). Take the largest ring.

    Returning a bare point instead makes a later `elements/detect` call answer 404.
    """
    if not geometry:
        return None
    kind, coords = geometry.get("type"), geometry.get("coordinates") or []
    if kind == "Polygon":
        ring = coords[0] if coords else None
    elif kind == "MultiPolygon":
        ring = max((p[0] for p in coords if p), key=len, default=None)
    else:
        return None
    if not ring:
        return None
    return "POLYGON ((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


# ---------- mapping ----------

def _structures(props: dict) -> list[VexcelStructure]:
    out = []
    for s in props.get("structures") or []:
        out.append(VexcelStructure(
            primary=bool(s.get("primary-structure")),
            footprint_wkt=s.get("footprint.wkt"),
            footprint_area_m2=s.get("footprint.area"),
            attributes={k: v for k, v in s.items() if k != "footprint.wkt"},
        ))
    return out


def _chosen_first(structures: list[VexcelStructure], index: int) -> list[VexcelStructure]:
    """Put the chosen structure first and make it the only `primary` one.

    Every consumer picks the building the same two ways - the first structure flagged
    `primary`, or a sort on `not primary` - so satisfying both is what makes the choice
    in `locate.py` actually reach A2, A11, A12, A14 and A19 without a contract change.

    **Vexcel's own flag is not lost**: `_structures` keeps every raw key except the
    footprint WKT, so `attributes["primary-structure"]` still reports what the service
    said. `VexcelStructure.primary` now means "the building this bundle is about",
    which is what every caller already read it as.
    """
    if not structures or not (0 <= index < len(structures)):
        return structures
    ordered = [structures[index]] + [s for i, s in enumerate(structures) if i != index]
    return [s.model_copy(update={"primary": i == 0}) for i, s in enumerate(ordered)]


def primary_structure(data: VexcelData) -> Optional[VexcelStructure]:
    """The building on the parcel. Falls back to the only structure when no flag is
    set, and otherwise to the largest footprint, so a caller always gets something
    deterministic."""
    if not data.structures:
        return None
    flagged = [s for s in data.structures if s.primary]
    if flagged:
        return flagged[0]
    if len(data.structures) == 1:
        return data.structures[0]
    return max(data.structures, key=lambda s: s.footprint_area_m2 or 0.0)


#: What goes into the D4 cache key besides the point. `include=precomputed` and
#: `include=precomputed,calculated` return different key sets for the same parcel
#: (finding 4.3), so sharing an entry would serve a caller asking for roof height a
#: payload that has none, silently.
def _query_shape(layers: str) -> dict:
    return {"include": "precomputed,calculated", "layer": layers, "srid": 4326}


def get_vexcel_data_with_notes(
    wkt: str, *, layers: str = DEFAULT_LAYERS, stories: Optional[int] = None,
    at: Optional[tuple[float, float]] = None, floor_plate_m2: Optional[float] = None,
    locator: str = "address",
    get: Optional[Getter] = None, refresh: bool = False,
) -> tuple[Optional[VexcelData], list[FetchRecord]]:
    """Parcel attributes and geometry for one point or area.

    Returns `(None, [FetchRecord])` when there is no parcel or the service stayed
    rate-limited, because both are normal outcomes for this lane rather than faults.

    **One response holds several captures of the same parcel, and the first is not the
    newest.** `at` and `floor_plate_m2` are how a caller says which building it means;
    `locate.py` carries the rule and the measurements behind it. Without them this
    still prefers the newest capture over `features[0]`, because `features[0]` is
    whatever the service happened to order first - at the Los Angeles office, a 2022
    capture of a building the address is not inside.

    Cached by D4 when the default transport is used; **an injected `get` bypasses the
    cache**. The HTTP status is cached with the body, because "no parcel here" is a
    stable fact about coverage and worth not re-asking - but a 429 is not, since it
    says nothing about the parcel and everything about the last few seconds.
    """
    def fetch():
        status, body = (get or _default_get)("property/extract", {
            "wkt": wkt,
            "srid": 4326,
            # One call: `calculated` alone cannot be joined back to the precomputed
            # structures, and `precomputed` alone leaves every height null.
            "include": "precomputed,calculated",
            "layer": layers,
        })
        return {"status": status, "body": body}

    shape = _query_shape(layers)
    payload, from_cache = cache.cached_json(
        "vexcel", wkt, fetch, shape, use_cache=get is None, refresh=refresh)
    status, body = payload.get("status"), payload.get("body")

    if status == 429:
        # Never cache a rate limit: it describes the service's last few seconds, not
        # this parcel, and a cached 429 would poison the point until the key changed.
        if get is None and not from_cache:
            cache.path_for("vexcel", wkt, shape).unlink(missing_ok=True)
        return None, [cache.record("vexcel.rate_limited", wkt)]
    if status == 403:
        return None, [cache.record("vexcel.outside_coverage", wkt)]
    if status == 404:
        return None, [cache.record("vexcel.no_parcel", wkt)]
    features = (body or {}).get("features") or []
    if not features:
        return None, [cache.record("vexcel.no_features", wkt)]

    from . import locate as d16

    chosen, choice_notes = d16.choose(features, at=at, plate_m2=floor_plate_m2,
                                      locator=locator)
    # A parcel with no structure in any capture is still a parcel: it has a polygon,
    # which `elements/detect` needs, and attributes. Keep the newest capture of it and
    # let the record say there was no building to choose.
    index = chosen.feature if chosen is not None else d16.newest_feature(features)
    feature = features[index]
    props = feature.get("properties") or {}
    structures = _structures(props)
    data = VexcelData(
        collection=props.get("metadata.collection") or props.get("parcel-source"),
        parcel_wkt=largest_ring_wkt(feature.get("geometry")),
        attributes={k: v for k, v in props.items() if k != "structures"},
        structures=(_chosen_first(structures, chosen.structure)
                    if chosen is not None else structures),
    )
    notes = [FetchRecord(layer="vexcel", what="property/extract", status="ok")]
    notes += choice_notes
    if get is None:
        notes.append(cache.cache_note("vexcel", "property/extract", hit=from_cache))
    primary = primary_structure(data)
    if not plausible_building_height(primary.attributes if primary else {}, stories):
        notes.append(FetchRecord(
            layer="vexcel", what="roof-characteristics.height", status="fallback",
            detail="implausible as a building height; use CoStar numStoriesAboveGrade",
        ))
    return data, notes


def get_vexcel_data(
    wkt: str, *, layers: str = DEFAULT_LAYERS, stories: Optional[int] = None,
    at: Optional[tuple[float, float]] = None, floor_plate_m2: Optional[float] = None,
    get: Optional[Getter] = None,
) -> VexcelData:
    """As above, but raises `NoParcel` instead of returning notes."""
    data, notes = get_vexcel_data_with_notes(wkt, layers=layers, stories=stories,
                                             at=at, floor_plate_m2=floor_plate_m2, get=get)
    if data is None:
        raise NoParcel(notes[0].detail or "no parcel")
    return data


# ---------- obliques, for D8 ----------

def oblique_directions(wkt: str, *, get: Optional[Getter] = None) -> list[str]:
    """Which oblique directions exist here, from the newest collection only.

    Obliques live only in the `urban` layer, and even there not every direction
    exists. Asking the coverage service beats trying each and failing.
    """
    status, body = (get or _default_get)("oriented/collections", {
        "wkt": wkt,
        "srid": 4326,
        "layer": OBLIQUE_LAYER,
        "product-type": "oblique",
        "include": "product-type,collection,last-capture-date",
    })
    if status != 200 or not body:
        return []
    feats = body.get("features") or []
    dates = [(f.get("properties") or {}).get("last-capture-date") for f in feats]
    newest = max((d for d in dates if d), default=None)
    if newest is None:
        return []
    available = {
        (f.get("properties") or {}).get("product-type")
        for f in feats
        if (f.get("properties") or {}).get("last-capture-date") == newest
    }
    return [d for d in OBLIQUE_DIRECTIONS if d in available]
