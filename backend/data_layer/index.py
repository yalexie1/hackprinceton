"""Property index over the whole CoStar kit (package D7).

`api.search_properties` answered from `specs/examples/` alone until this module
landed: three golden properties plus whatever `search_results.json` held. That was
the explicit pre-D7 answer to workplan R4. This package is the real index.

What it is, and what it is not:

- **One pass, not 14,932 scans.** `costar.get_costar_data` finds a record by
  streaming `commercial-property.jsonl` and stopping at the first match, which is
  right for one property and hopeless for all of them. Here each dataset is read
  exactly once (3,339 + 2,120 records, about 1.1 s together) and trimmed down to the
  dozen fields a `PropertySummary` needs.
- **The join is by model, and a model can have several parents.** The starter CSVs
  carry 15,371 rows for 14,932 distinct Matterport models (see
  `costar.rows_by_model`). The index emits **one summary per model**, choosing the
  primary parent by the same documented rule `get_costar_data` uses, so a scan
  attached to thirteen property records does not appear thirteen times.
- **Scan statistics are not in the kit.** `pano_count`, `room_count`,
  `floor_count`, `has_splat` and `has_defurnished` come from Matterport, and
  filling them for 14,932 models would mean 14,932 GraphQL calls against a key
  shared with every other team. They keep their contract defaults here; they get
  real values when the property's bundle is fetched. A caller must not read a zero
  from search as "this scan has no panoramas".
- **`use_type` comes from the property record, never from which CSV the row was
  in.** 2,765 of the kit's 3,339 commercial properties are Multifamily and only 289
  are Office, so "commercial" and "office" are very different questions.

The index is cached to `data/cache/costar/index/` because a cold server boot should
not repeat the pass, and the cache is invalidated by the size and mtime of the four
source files rather than by hand.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from backend.schema import PropertySummary, Segment, UseType

from . import costar

#: Trimmed-summary layout. Bumping this invalidates every cache built by an older
#: version, which matters more than it sounds: a stale cache would silently answer
#: searches with fields that no longer mean what the caller thinks.
INDEX_VERSION = 1

#: `PropertyType` -> `UseType`. Counts are the kit's, measured 2026-11-14.
#:
#: `Multifamily` (2,765 properties) maps to `multifamily_unit` because a Matterport
#: scan of a multifamily property is a scan of one unit; the contract has no
#: "multifamily building" use type, and `UseType` is what the analysis lane switches
#: templates on. `Flex`, `Industrial`, `Hospitality`, `Healthcare`, `Land` and
#: `Specialty` are real buildings we have no template for, so they are `other`
#: rather than `unknown` - we know what they are, we just do not model them.
PROPERTY_TYPE_USE: dict[int, UseType] = {
    0: "unknown",     # Unknown
    1: "other",       # Hospitality, 55
    2: "other",       # Industrial, 122
    3: "other",       # Land, 5
    5: "office",      # Office, 289
    6: "retail",      # GeneralRetail, 65
    7: "other",       # Flex, 31
    8: "other",       # SportsAndEntertainment
    9: "other",       # MixedUse
    10: "other",      # Specialty, 5
    11: "multifamily_unit",   # Multifamily, 2765
    13: "other",      # Healthcare, 2
    14: "unknown",    # PropertyTypeUnknown
    15: "other",      # Residential; does not occur in this kit
    16: "other",      # Homes; does not occur in this kit
}

#: `ListingPropertyType` -> `UseType`. Counts are the kit's residential listings.
#:
#: The enum's values are powers of two, so it reads like a flag set, but every one of
#: the 2,120 records carries a single flag (1, 2, 4, 16, 64 or 0). A composite value
#: would therefore be new data, and is reported as `unknown` instead of being guessed
#: at by picking a bit.
#:
#: `Townhouse` is `single_family`: a townhouse is one dwelling with party walls, and
#: the party wall is an adjacency the analysis lane handles on the surface, not a
#: different use type. `Condo` and `MultiFamily` are units in a larger building.
LISTING_TYPE_USE: dict[int, UseType] = {
    0: "unknown",             # None, 4
    1: "single_family",       # Detached, 1624
    2: "single_family",       # Townhouse, 168
    4: "multifamily_unit",    # Condo, 252
    8: "other",               # Other
    16: "multifamily_unit",   # MultiFamily, 70
    32: "other",              # LotsLands
    64: "single_family",      # MobileManufactured, 2
    128: "other",             # Commercial
    256: "multifamily_unit",  # Coop
    512: "multifamily_unit",  # Duplex
    1024: "multifamily_unit",  # Triplex
    2048: "multifamily_unit",  # Quadruplex
}

_COMMERCIAL_DATASET = "commercial-property"
_RESIDENTIAL_DATASET = "residential-listings"


def use_type_for(kind: str, code: Optional[int]) -> UseType:
    """`CostarData.property_type_code` -> `UseType`, for the whole lane.

    `api._assemble` and the index both have to answer this, and two tables that must
    agree are a table that will eventually disagree, so there is one.
    """
    if code is None:
        return "unknown"
    table = PROPERTY_TYPE_USE if kind == "commercial_property" else LISTING_TYPE_USE
    return table.get(code, "unknown")


def index_dir() -> Path:
    """Where the built index lives. Inside `data/cache/`, which is git-ignored:
    this is derived sponsor data and is never committed."""
    return costar.kit_dir().parent / "index"


def kit_available() -> bool:
    """Whether the kit mirror is on disk. A teammate's checkout has no mirror - the
    kit is 49 MB of licensed sponsor data - so every caller must cope with `False`."""
    try:
        base = costar.kit_dir()
    except costar.KitMissing:
        return False
    return (base / "commercial-properties.csv").is_file() and (
        base / "data" / f"{_COMMERCIAL_DATASET}.jsonl"
    ).is_file()


# ---------- trimming the records ----------

def _as_state(value) -> Optional[str]:
    return costar.normalise_state(value if isinstance(value, str) else None)


def _commercial_entry(rec: dict) -> dict:
    addr = rec.get("primaryAddress") or {}
    code = rec.get("propertyType")
    return {
        "name": (rec.get("buildingName") or "").strip() or None,
        "address": (addr.get("fullStreetAddress") or "").strip() or None,
        "city": costar.normalise_city(addr.get("city")),
        "state": _as_state(addr.get("state")),
        "lat": addr.get("latitude"),
        "lon": addr.get("longitude"),
        "use_type": use_type_for("commercial_property", code),
        "property_type_code": code,
    }


def _residential_entry(rec: dict) -> dict:
    prop = rec.get("property") or {}
    addr = prop.get("address") or {}
    # `listingPropertyType` and not `property.propertyType`: on the golden house the
    # latter is 1, which under PropertyResidentialType means ApartmentCommunity and
    # contradicts the record's own "Single Family Residence". Same finding as D1.
    code = prop.get("listingPropertyType")
    return {
        "name": None,   # residential listings carry no building name; the address is the name
        "address": (addr.get("fullStreetAddress") or "").strip() or None,
        "city": costar.normalise_city(addr.get("city")),
        "state": _as_state(addr.get("state")),
        "lat": addr.get("latitude"),
        "lon": addr.get("longitude"),
        "use_type": use_type_for("residential_listing", code),
        "property_type_code": code,
        # Kept only to pick the primary listing of a home marketed more than once.
        "list_date": str(rec.get("listDate") or ""),
    }


# ---------- building ----------

def _source_signature() -> dict:
    """Size and mtime of the four files the index is derived from. Cheap to compute
    and enough to notice a re-mirrored kit, which a row count would not."""
    base = costar.kit_dir()
    names = [
        "commercial-properties.csv",
        "residential-listings.csv",
        f"data/{_COMMERCIAL_DATASET}.jsonl",
        f"data/{_RESIDENTIAL_DATASET}.jsonl",
    ]
    out = {}
    for name in names:
        st = (base / name).stat()
        out[name] = [st.st_size, int(st.st_mtime)]
    return {"index_version": INDEX_VERSION, "sources": out}


def _build_rows() -> list[dict]:
    """One summary dict per Matterport model, in CSV order."""
    commercial = {
        str(rec["id"]): _commercial_entry(rec)
        for rec in costar.iter_records(_COMMERCIAL_DATASET)
    }
    residential = {
        str(rec["id"]): _residential_entry(rec)
        for rec in costar.iter_records(_RESIDENTIAL_DATASET)
    }

    rows: list[dict] = []
    for sid, model_rows in costar.rows_by_model().items():
        kind = model_rows[0]["kind"]
        if kind == "commercial_property":
            # The documented primary rule: first row in CSV order whose record exists.
            chosen = next(
                (
                    (row, commercial[row["property_id"]])
                    for row in model_rows
                    if row.get("property_id") in commercial
                ),
                None,
            )
            segment: Segment = "commercial"
        else:
            # The documented primary rule: latest `listDate`, ties by CSV order.
            candidates = [
                (row, residential[row["listing_id"]])
                for row in model_rows
                if row.get("listing_id") in residential
            ]
            chosen = max(candidates, key=lambda pair: pair[1]["list_date"]) if candidates else None
            segment = "residential"

        if chosen is None:
            # The CSV row points at a record the kit does not ship. The row's own
            # address is still real data, so the property stays findable; its use
            # type is the one thing we genuinely do not know.
            row, entry = model_rows[0], {}
        else:
            row, entry = chosen

        address = entry.get("address") or row.get("address")
        rows.append({
            "sid": sid,
            "name": entry.get("name") or address or sid,
            "segment": segment,
            "use_type": entry.get("use_type", "unknown"),
            "address": address,
            "city": entry.get("city") or row.get("city"),
            "state": entry.get("state") or row.get("state"),
            "lat": entry.get("lat"),
            "lon": entry.get("lon"),
            "costar_property_id": row.get("property_id"),
            "costar_listing_id": row.get("listing_id"),
            "costar_residential_listing_id": row.get("residential_listing_id"),
        })
    return rows


def build_index(force: bool = False) -> Path:
    """Build (or reuse) the on-disk index and return the path to it.

    Raises `costar.KitMissing` when there is no mirror - callers that must survive a
    checkout without one should ask `kit_available()` first.
    """
    out = index_dir() / "summaries.jsonl"
    meta_path = index_dir() / "meta.json"
    signature = _source_signature()
    if not force and out.is_file() and meta_path.is_file():
        try:
            if json.loads(meta_path.read_text()).get("signature") == signature:
                return out
        except json.JSONDecodeError:
            pass   # a truncated cache is a cache miss, not a crash

    rows = _build_rows()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".jsonl.tmp")
    with tmp.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(out)   # atomic, so a killed build cannot leave a half file behind
    meta_path.write_text(json.dumps({"signature": signature, "rows": len(rows)}, indent=2))
    return out


@lru_cache(maxsize=1)
def summaries() -> tuple[PropertySummary, ...]:
    """Every indexed property, in CSV order. Empty when there is no kit mirror."""
    if not kit_available():
        return ()
    path = build_index()
    return tuple(
        PropertySummary.model_validate(json.loads(line))
        for line in path.read_text().splitlines()
        if line.strip()
    )


# ---------- searching ----------

@lru_cache(maxsize=1)
def by_sid() -> dict[str, PropertySummary]:
    """`sid` -> its indexed summary. Lets a caller skip a scan of 14,932 rows."""
    return {s.sid: s for s in summaries()}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    h = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6_371_000.0 * asin(sqrt(h))


def _matches(summary: PropertySummary, needle: str) -> bool:
    return any(
        needle in (field or "").casefold()
        for field in (summary.name, summary.address, summary.city)
    )


def filter_summaries(
    rows: Iterable[PropertySummary],
    q: Optional[str] = None,
    segment: Optional[Segment] = None,
    use_type: Optional[UseType] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_m: Optional[float] = None,
) -> list[PropertySummary]:
    """The shared filter. `api.search_properties` applies it to the fixtures and to
    the index alike, so one rule governs both and they cannot drift apart."""
    out = list(rows)
    if q:
        needle = q.casefold()
        out = [s for s in out if _matches(s, needle)]
    if segment is not None:
        out = [s for s in out if s.segment == segment]
    if use_type is not None:
        out = [s for s in out if s.use_type == use_type]
    if lat is not None and lon is not None and radius_m is not None:
        # A property with no coordinates cannot be shown to be inside the radius, so
        # it is excluded rather than assumed near.
        out = [
            s for s in out
            if s.lat is not None and s.lon is not None
            and _haversine_m(lat, lon, s.lat, s.lon) <= radius_m
        ]
    return out


def property_key(summary: PropertySummary) -> str:
    """What makes two summaries the same *property* rather than the same scan.

    `PropertySummary.sid` is a Matterport model, and a property usually has several:
    the kit's 14,932 models collapse to 5,098 properties, and one apartment complex
    carries 32 unit scans. `costar_residential_listing_id` is the kit's own grouping
    for "the listings of one sale or rental", so it is the residential key; a model
    with neither parent is its own property.
    """
    return (
        summary.costar_property_id
        or summary.costar_residential_listing_id
        or summary.sid
    )


def collapse(
    rows: Iterable[PropertySummary],
    prefer: Optional[set[str]] = None,
) -> list[PropertySummary]:
    """One summary per property, keeping input order.

    Without this a search for offices in Houston returns "333 Northbelt" five times
    and a search near downtown LA returns "Eighth & Grand" five times - the same
    building, once per scan. That is correct data and a useless answer.

    `prefer` names sids that must win their group. The door passes the golden sids,
    because a fixture summary carries real room and panorama counts and a sibling
    scan of the same building does not.
    """
    prefer = prefer or set()
    chosen: dict[str, PropertySummary] = {}
    order: list[str] = []
    for row in rows:
        key = property_key(row)
        if key not in chosen:
            chosen[key] = row
            order.append(key)
        elif row.sid in prefer and chosen[key].sid not in prefer:
            chosen[key] = row
    return [chosen[key] for key in order]


def search(
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
    """Search the kit index alone. `api.search_properties` is the public door; this
    is here so the index can be tested without the fixtures in the way.

    Collapsing happens **after** filtering and **before** ranking, so the
    representative scan of a property does not change with the query point.
    """
    out = filter_summaries(summaries(), q, segment, use_type, lat, lon, radius_m)
    if not all_scans:
        out = collapse(out)
    out = rank(out, lat=lat, lon=lon)
    return out[: max(0, limit)]


def rank(
    rows: list[PropertySummary],
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> list[PropertySummary]:
    """Nearest first when a point is given, otherwise input order.

    Ordering has to be total and deterministic: with 14,932 properties behind a
    `limit`, two identical queries returning different pages would look like missing
    data. `sid` breaks every tie.
    """
    if lat is None or lon is None:
        return rows
    return sorted(
        rows,
        key=lambda s: (
            s.lat is None or s.lon is None,
            _haversine_m(lat, lon, s.lat, s.lon) if s.lat is not None and s.lon is not None else 0.0,
            s.sid,
        ),
    )


def stats() -> dict:
    """Lane bookkeeping: what the index actually holds. Used by `/data-status`."""
    rows = summaries()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.use_type] = counts.get(row.use_type, 0) + 1
    return {
        "models": len(rows),
        "properties": len({property_key(r) for r in rows}),
        "with_coordinates": sum(1 for r in rows if r.lat is not None and r.lon is not None),
        "by_use_type": dict(sorted(counts.items())),
        "office_properties": len({property_key(r) for r in rows if r.use_type == "office"}),
    }
