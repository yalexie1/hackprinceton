"""Portfolio screening over the property index, filtered by Vexcel attributes (D13).

SPEC 1035 asks to "rank many properties by retrofit return using Vexcel filters and
CoStar records". Three measurements decided how this is built, all live on 2026-11-14.

**One area query returns hundreds of parcels, so screening is cheap.** A ~330 m box
returns 164 features in about 3 s, and every structure carries the full 92-key
attribute set - `roof-characteristics.*`, `building-type.class`, `footprint.area`,
`primary-structure`. Screening therefore costs roughly one call per *area*, not one per
property. (`vexcel.get_vexcel_data_with_notes` deliberately reads only `features[0]`,
which is correct for a point query and would throw away 440 parcels here.)

**There is a hard cap of 500 features and nothing says so.** Boxes of 880 m, 1.8 km
and 4.4 km all return exactly 500. A city-wide screen would silently miss most of the
city and report a confident answer, so this tiles the area and **subdivides any tile
that comes back at exactly the cap**, recording it either way.

**Screen index-first, not Vexcel-first.** Of 441 parcels in one box only **4** matched
a scanned property within 25 m, and the tolerance barely mattered - 4 at 25 m, 4 at
100 m - so matches are unambiguous but sparse. Starting from the D7 index instead,
**5 of 6 indexed properties** in a box matched a parcel from a single call. A property
with no Matterport scan cannot be audited by this tool, so screening unscanned parcels
is work thrown away.

**What this does not claim.** Ranking by *retrofit return* needs the baseline and the
measures, which is the analysis lane's job. This ranks by a measured proxy - usable
roof area, since that is what bounds PV and cool-roof savings - names the proxy on
every result, and hands back the attributes so a caller can rank differently. A
"return" score computed here without the physics would be a number with no model
behind it.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from backend.schema import FetchRecord, PropertySummary, Segment, UseType

from . import cache, index, vexcel

#: The undocumented ceiling on `property/extract` features. A tile returning exactly
#: this many is assumed truncated and is subdivided.
FEATURE_CAP = 500

#: Side length at which a tile reliably stays under the cap: a ~330 m box measured 164
#: features in a dense Los Angeles neighbourhood, an ~880 m box hit 500.
SAFE_TILE_M = 400.0

#: How far a parcel centroid may sit from an indexed property and still be it. The
#: measured match count was identical at 25 m and 100 m, so this is not a tuning knob -
#: beyond a few tens of metres there is simply nothing to match.
MATCH_TOLERANCE_M = 40.0

#: Recursion limit on subdivision, so a pathological area cannot fan out without end.
MAX_SUBDIVISIONS = 3

_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON = 111_320.0
_NUM = re.compile(r"-?\d+\.?\d*")


@dataclass(frozen=True)
class Filters:
    """Predicates over **measured** attributes. Every one is optional; the default
    screens nothing out.

    `roof_condition_min` and `_max` take the raw 1-to-5 value rather than a
    "bad roof" flag, **on purpose**. `roof-characteristics.condition` is the rounded
    `...condition.precise-value`, and the kit ships no legend for its direction. The
    1920s golden house grades 5 while the maintained 1974 office grades 3, which
    suggests higher is worse - but that is an inference from two properties, so the
    guess is not baked into an API that callers would then trust. [P]
    """
    roof_shape: Optional[frozenset[str]] = None
    roof_material: Optional[frozenset[str]] = None
    roof_condition_min: Optional[float] = None
    roof_condition_max: Optional[float] = None
    min_footprint_m2: Optional[float] = None
    max_footprint_m2: Optional[float] = None
    #: `True` keeps only roofs with no detected solar - the PV candidates. `False`
    #: keeps only those that already have it. `None` does not filter.
    solar_absent: Optional[bool] = None
    building_type: Optional[frozenset[str]] = None
    #: From the index, not from Vexcel: CoStar's property type is authoritative for
    #: use, and `building-type.class` is null on residential lots (finding 4.2).
    use_type: Optional[frozenset[str]] = None
    segment: Optional[Segment] = None


# ---------- geometry ----------

def _centroid(structure: dict) -> Optional[tuple[float, float]]:
    """`(lat, lon)` of a structure's roof centroid. WKT is longitude first."""
    wkt = structure.get("roof-characteristics.centroid.wkt")
    if not isinstance(wkt, str):
        return None
    nums = [float(v) for v in _NUM.findall(wkt)]
    return (nums[1], nums[0]) if len(nums) >= 2 else None


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metres between two points. The longitude scale uses the **mean** latitude, so
    the function is symmetric; taking the first point's latitude made `d(a,b)` and
    `d(b,a)` differ, which a test caught."""
    return math.hypot(
        (a[0] - b[0]) * _M_PER_DEG_LAT,
        (a[1] - b[1]) * _M_PER_DEG_LON * math.cos(math.radians((a[0] + b[0]) / 2.0)),
    )


def contains(wkt: Optional[str], lat: float, lon: float) -> bool:
    """Whether a footprint ring encloses a point. Ray casting on the ring as given.

    Needed because **nearest centroid is not the same as "the building at this
    address"**: at the Los Angeles office the nearest centroid is 18 m away and the
    structure that actually contains the address point is a different one, with a
    different solar flag.
    """
    if not wkt:
        return False
    nums = [float(v) for v in _NUM.findall(wkt)]
    points = list(zip(nums[0::2], nums[1::2]))        # (lon, lat)
    if len(points) < 4:
        return False
    inside = False
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        if (y1 > lat) != (y2 > lat):
            crossing = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < crossing:
                inside = not inside
    return inside


def containing_structure(lat: float, lon: float, *, half_m: float = 100.0, get=None):
    """The smallest primary structure whose footprint encloses the point, or `None`.

    Smallest, because overlapping structures are normal on a commercial parcel - the
    Houston office has six containing it - and the smallest enclosing one is the
    building rather than the block.
    """
    structures, notes = parcels_in_box(lat, lon, half_m, get=get)
    enclosing = [s for s in structures if contains(s.get("footprint.wkt"), lat, lon)]
    enclosing.sort(key=lambda s: s.get("footprint.area") or 0.0)
    return (enclosing[0] if enclosing else None), notes


def box_wkt(lat: float, lon: float, half_m: float) -> str:
    """An axis-aligned box of `half_m` either side of a point, as WKT."""
    dlat = half_m / _M_PER_DEG_LAT
    dlon = half_m / (_M_PER_DEG_LON * max(0.01, math.cos(math.radians(lat))))
    ring = [
        (lon - dlon, lat - dlat), (lon + dlon, lat - dlat),
        (lon + dlon, lat + dlat), (lon - dlon, lat + dlat), (lon - dlon, lat - dlat),
    ]
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


# ---------- fetching parcels ----------

def parcels_in_box(
    lat: float, lon: float, half_m: float, *, get=None, depth: int = 0
) -> tuple[list[dict], list[FetchRecord]]:
    """Primary structures in a box, subdividing when the 500-feature cap is hit.

    Returns the structures, each with `_centroid` attached, and a record per tile. The
    cap is the reason this is not one call: a tile that comes back at exactly 500 is
    **assumed truncated**, because the service gives no other signal and a silent
    truncation would make a screen quietly incomplete.
    """
    wkt = box_wkt(lat, lon, half_m)
    status, body = (get or vexcel._default_get)("property/extract", {
        "wkt": wkt, "srid": 4326,
        "include": "precomputed,calculated", "layer": vexcel.DEFAULT_LAYERS,
    })
    if status == 429:
        return [], [cache.record("vexcel.rate_limited", "property/extract (screening)")]
    if status in (403, 404) or not body:
        return [], [cache.record(
            "vexcel.outside_coverage" if status == 403 else "vexcel.no_parcel",
            f"screening tile at {lat:.4f},{lon:.4f}")]

    features = body.get("features") or []
    if len(features) >= FEATURE_CAP and depth < MAX_SUBDIVISIONS:
        # Truncated. Split into four and recurse; the halves overlap slightly at the
        # seams, which is why the caller dedupes by centroid.
        notes = [FetchRecord(
            layer="vexcel", what="property/extract:truncated", status="fallback",
            detail=(f"tile at {lat:.4f},{lon:.4f} returned the {FEATURE_CAP}-feature cap, "
                    f"so it is subdivided (depth {depth + 1})"),
        )]
        out: list[dict] = []
        quarter = half_m / 2.0
        for dlat, dlon in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            sub_lat = lat + dlat * quarter / _M_PER_DEG_LAT
            sub_lon = lon + dlon * quarter / (_M_PER_DEG_LON * math.cos(math.radians(lat)))
            sub, sub_notes = parcels_in_box(sub_lat, sub_lon, quarter, get=get, depth=depth + 1)
            out += sub
            notes += sub_notes
        return out, notes

    structures = []
    for feature in features:
        for structure in (feature.get("properties") or {}).get("structures") or []:
            if not structure.get("primary-structure"):
                continue
            centre = _centroid(structure)
            if centre is None:
                continue
            structures.append({**structure, "_centre": centre})

    note = FetchRecord(
        layer="vexcel", what="property/extract:area", status="ok",
        detail=f"{len(features)} parcels, {len(structures)} primary structures in a "
               f"{2 * half_m:.0f} m box at {lat:.4f},{lon:.4f}",
    )
    if len(features) >= FEATURE_CAP:
        note = FetchRecord(
            layer="vexcel", what="property/extract:truncated", status="fallback",
            detail=(f"tile at {lat:.4f},{lon:.4f} is at the {FEATURE_CAP}-feature cap and "
                    f"subdivision is exhausted at depth {depth}; the screen is incomplete here"),
        )
    return structures, [note]


# ---------- filtering ----------

def _value(structure: dict, key: str):
    """Read an attribute whichever way it is shaped.

    Vexcel returns **flat dotted keys** - `roof-characteristics.shape.value` - and
    carries the scalar directly on some keys (`footprint.area`) and under a `.value`
    suffix on others (`roof-characteristics.shape.value`). A nested dict is also
    accepted, because the same attributes arrive that way from some endpoints and
    silently reading `None` would turn every filter into "no match".
    """
    direct = structure.get(key)
    if isinstance(direct, dict):
        return direct.get("value")
    if direct is not None:
        return direct
    return structure.get(f"{key}.value")


def passes(structure: dict, filters: Filters) -> bool:
    """Whether one structure satisfies the Vexcel half of the filters.

    An attribute that is **absent** fails a filter that asks about it. Screening is a
    positive claim - "these properties match" - so a property we cannot evaluate does
    not belong in the result.
    """
    if filters.roof_shape is not None:
        shape = _value(structure, "roof-characteristics.shape")
        if not isinstance(shape, str) or shape.casefold() not in {s.casefold() for s in filters.roof_shape}:
            return False
    if filters.roof_material is not None:
        material = _value(structure, "roof-characteristics.material.class")
        if not isinstance(material, str) or material.casefold() not in {
                m.casefold() for m in filters.roof_material}:
            return False
    if filters.roof_condition_min is not None or filters.roof_condition_max is not None:
        condition = _value(structure, "roof-characteristics.condition.precise-value")
        if not isinstance(condition, (int, float)):
            return False
        if filters.roof_condition_min is not None and condition < filters.roof_condition_min:
            return False
        if filters.roof_condition_max is not None and condition > filters.roof_condition_max:
            return False
    if filters.min_footprint_m2 is not None or filters.max_footprint_m2 is not None:
        area = _value(structure, "footprint.area")
        if not isinstance(area, (int, float)):
            return False
        if filters.min_footprint_m2 is not None and area < filters.min_footprint_m2:
            return False
        if filters.max_footprint_m2 is not None and area > filters.max_footprint_m2:
            return False
    if filters.solar_absent is not None:
        solar = _value(structure, "roof-objects.solar")
        if solar is None:
            return False
        has_solar = bool(solar) and str(solar).casefold() not in ("false", "0", "none")
        if has_solar is filters.solar_absent:
            return False
    if filters.building_type is not None:
        kind = _value(structure, "building-type.class")
        if not isinstance(kind, str) or kind.casefold() not in {
                b.casefold() for b in filters.building_type}:
            return False
    return True


@dataclass
class Screened:
    """One property that passed, with the evidence it passed on."""
    summary: PropertySummary
    roof_area_m2: Optional[float] = None
    roof_shape: Optional[str] = None
    roof_material: Optional[str] = None
    roof_condition: Optional[float] = None
    has_solar: Optional[bool] = None
    distance_m: float = 0.0
    attributes: dict = field(default_factory=dict)


def screen(
    lat: float, lon: float, radius_m: float, *,
    filters: Optional[Filters] = None,
    limit: int = 50,
    get=None,
) -> tuple[list[Screened], list[FetchRecord]]:
    """Scanned properties within `radius_m` whose parcel satisfies `filters`.

    Index first: the candidates are properties that have a Matterport model, because
    one that does not cannot be audited by this tool. Their parcels then come from as
    few Vexcel area calls as the 500-feature cap allows.

    **Ranked by usable roof area, largest first** - the measured proxy, since roof area
    is what bounds both PV and cool-roof savings. It is not a retrofit return, and
    `Screened.roof_area_m2` says what the ordering means.
    """
    filters = filters or Filters()

    nearby = [
        s for s in index.summaries()
        if s.lat is not None and s.lon is not None
        and _metres((lat, lon), (s.lat, s.lon)) <= radius_m
        and (filters.segment is None or s.segment == filters.segment)
        and (filters.use_type is None or s.use_type in filters.use_type)
    ]
    # `index.collapse` is the lane's one-row-per-property rule, reused rather than
    # re-implemented, so screening and search agree on which scan represents a
    # building - and the golden sids win their group.
    candidates = {
        index.property_key(s): s for s in index.collapse(nearby, prefer=_GOLDEN_SIDS)
    }

    if not candidates:
        return [], [FetchRecord(
            layer="costar", what="screening:candidates", status="missing",
            detail=f"no scanned property within {radius_m:.0f} m of {lat:.4f},{lon:.4f} "
                   f"matches the index-side filters",
        )]

    notes = [FetchRecord(
        layer="costar", what="screening:candidates", status="ok",
        detail=f"{len(candidates)} scanned properties within {radius_m:.0f} m",
    )]

    # **Tile around the candidates, not around the whole radius.** Index-first means
    # the points of interest are known, so a 500 m screen with six scanned properties
    # costs a handful of calls instead of covering 0.8 km2 of parcels nobody can
    # audit. Measured: 102 s covering the radius, against a few seconds this way.
    structures: list[dict] = []
    for tile_lat, tile_lon, half in _tiles_for(list(candidates.values())):
        found, tile_notes = parcels_in_box(tile_lat, tile_lon, half, get=get)
        structures += found
        notes += tile_notes
    # Tiles overlap at the seams, so dedupe on the centroid.
    seen: set[tuple[float, float]] = set()
    unique = []
    for structure in structures:
        key = (round(structure["_centre"][0], 6), round(structure["_centre"][1], 6))
        if key not in seen:
            seen.add(key)
            unique.append(structure)

    out: list[Screened] = []
    unmatched = 0
    for summary in candidates.values():
        point = (summary.lat, summary.lon)
        # Containment first, nearest centroid only as a fallback. At the Los Angeles
        # office the nearest centroid is 18 m away and encloses the address, while a
        # different structure is nearer the Matterport georeference - and they carry
        # different solar flags, so proximity alone picks the wrong building.
        enclosing = [s for s in unique if contains(s.get("footprint.wkt"), *point)]
        if enclosing:
            enclosing.sort(key=lambda s: s.get("footprint.area") or 0.0)
            best = enclosing[0]
            best_m = _metres(point, best["_centre"])
        else:
            best, best_m = None, MATCH_TOLERANCE_M
            for structure in unique:
                metres = _metres(point, structure["_centre"])
                if metres <= best_m:
                    best, best_m = structure, metres
        if best is None:
            unmatched += 1
            continue
        if not passes(best, filters):
            continue
        out.append(Screened(
            summary=summary,
            roof_area_m2=_value(best, "footprint.area"),
            roof_shape=_value(best, "roof-characteristics.shape"),
            roof_material=_value(best, "roof-characteristics.material.class"),
            roof_condition=_value(best, "roof-characteristics.condition.precise-value"),
            has_solar=_as_bool(_value(best, "roof-objects.solar")),
            distance_m=best_m,
            attributes={k: v for k, v in best.items() if not k.startswith("_")},
        ))

    out.sort(key=lambda s: (-(s.roof_area_m2 or 0.0), s.summary.sid))
    notes.append(FetchRecord(
        layer="vexcel", what="screening:matched", status="ok",
        detail=(f"{len(out)} of {len(candidates)} candidates passed; {unmatched} had no parcel "
                f"within {MATCH_TOLERANCE_M:.0f} m; ranked by roof area, which is a proxy for "
                f"PV and cool-roof potential and not a retrofit return"),
    ))
    return out[: max(0, limit)], notes


def _as_bool(value) -> Optional[bool]:
    if value is None:
        return None
    return bool(value) and str(value).casefold() not in ("false", "0", "none")


#: Golden sids, so screening names the same scan the user audited rather than a
#: sibling suite of the same tower. Read from the **example folders** - one summary
#: each - not from `search_results.json`, which carries three suites of the Los
#: Angeles tower and so cannot discriminate between them. Discovered rather than
#: hard-coded, because folders get repointed.
def _golden_sids() -> frozenset[str]:
    from . import api

    try:
        return frozenset(
            api._load(folder, "property_summary.json")["sid"] for folder in api._folders()
        )
    except Exception:
        return frozenset()


_GOLDEN_SIDS = _golden_sids()


def _tiles_for(candidates: list[PropertySummary]) -> list[tuple[float, float, float]]:
    """One box per cluster of candidates, deduped.

    Candidates are snapped to a `SAFE_TILE_M` grid so neighbours share a tile, and the
    half-size stays under the feature cap. A property at a tile edge is still found,
    because its own grid cell is centred on it within half a tile.
    """
    half = SAFE_TILE_M / 2.0
    cells: dict[tuple[int, int], tuple[float, float]] = {}
    for summary in candidates:
        lat, lon = summary.lat, summary.lon
        row = int(round(lat * _M_PER_DEG_LAT / SAFE_TILE_M))
        col = int(round(lon * _M_PER_DEG_LON * math.cos(math.radians(lat)) / SAFE_TILE_M))
        cells.setdefault((row, col), (lat, lon))
    return [(lat, lon, half) for lat, lon in cells.values()]


def summaries_only(screened: list[Screened]) -> list[PropertySummary]:
    """The workplan's declared output shape: `PropertySummary[]`."""
    return [s.summary for s in screened]
