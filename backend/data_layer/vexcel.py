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
  inside `features[0].properties`, not at the top level.
- **`404` means no parcel at that point and is a normal outcome**, reported as a
  `FetchRecord` rather than raised. **`429` is retried with exponential backoff.**
- Parcel geometry can be a **`MultiPolygon`**, so the largest ring is taken.
- **`primary-structure` picks the building**: the golden house parcel holds two.
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


def get_vexcel_data_with_notes(
    wkt: str, *, layers: str = DEFAULT_LAYERS, stories: Optional[int] = None,
    get: Optional[Getter] = None,
) -> tuple[Optional[VexcelData], list[FetchRecord]]:
    """Parcel attributes and geometry for one point or area.

    Returns `(None, [FetchRecord])` when there is no parcel or the service stayed
    rate-limited, because both are normal outcomes for this lane rather than faults.
    """
    status, body = (get or _default_get)("property/extract", {
        "wkt": wkt,
        "srid": 4326,
        # One call: `calculated` alone cannot be joined back to the precomputed
        # structures, and `precomputed` alone leaves every height null.
        "include": "precomputed,calculated",
        "layer": layers,
    })
    if status == 403:
        return None, [FetchRecord(layer="vexcel", what="property/extract", status="missing",
                                  detail=f"outside the licensed coverage: {wkt}")]
    if status == 404:
        return None, [FetchRecord(layer="vexcel", what="property/extract", status="missing",
                                  detail=f"no parcel at {wkt}")]
    if status == 429:
        return None, [FetchRecord(layer="vexcel", what="property/extract", status="error",
                                  detail="rate limited after retries")]
    features = (body or {}).get("features") or []
    if not features:
        return None, [FetchRecord(layer="vexcel", what="property/extract", status="missing",
                                  detail="response carried no features")]

    feature = features[0]
    props = feature.get("properties") or {}
    data = VexcelData(
        collection=props.get("metadata.collection") or props.get("parcel-source"),
        parcel_wkt=largest_ring_wkt(feature.get("geometry")),
        attributes={k: v for k, v in props.items() if k != "structures"},
        structures=_structures(props),
    )
    notes = [FetchRecord(layer="vexcel", what="property/extract", status="ok")]
    primary = primary_structure(data)
    if not plausible_building_height(primary.attributes if primary else {}, stories):
        notes.append(FetchRecord(
            layer="vexcel", what="roof-characteristics.height", status="fallback",
            detail="implausible as a building height; use CoStar numStoriesAboveGrade",
        ))
    return data, notes


def get_vexcel_data(
    wkt: str, *, layers: str = DEFAULT_LAYERS, stories: Optional[int] = None,
    get: Optional[Getter] = None,
) -> VexcelData:
    """As above, but raises `NoParcel` instead of returning notes."""
    data, notes = get_vexcel_data_with_notes(wkt, layers=layers, stories=stories, get=get)
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
