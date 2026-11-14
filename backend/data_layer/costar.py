"""CoStar data-kit reader (package D1).

Reads the mirrored kit under `data/cache/costar/kit/`. Every rule here is a
verified finding from `specs/data-integration.md` section 2; the short version:

- The join is the kit's **own** starter CSVs, not `models_index.csv`.
- `commercial-property.jsonl` is 193 MB, so records are found by **streaming**.
- `propertyType == 5` is Office. Enum names come from `schemas/enums.json`.
- Commercial `yearBuilt` is **not** a scalar: it lives in `constructionEvents[]`.
  Residential `yearBuilt` **is** a scalar, and residential area is a *range*.
- `grossBuildingAreaSquareFeet` (GBA) is the envelope area;
  `rentableBuildingAreaSquareFeet` (RBA) is for leasing only.
- `City` and `State` are dirty and are normalised here.
"""
from __future__ import annotations

import csv
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional

from backend.schema import CostarData

_ROOT = Path(__file__).resolve().parents[2]

SQFT_TO_M2 = 0.09290304
OFFICE_PROPERTY_TYPE = 5
_CONSTRUCTION_COMPLETE = 2
_RENOVATION_FINISHED = 4
_RENOVATION_BEGUN = 3

_STATES = {
    "ca": "CA", "calif": "CA", "california": "CA",
    "tx": "TX", "texas": "TX",
}


class KitMissing(FileNotFoundError):
    """The kit mirror is not on disk. It is git-ignored and must be fetched once."""


def kit_dir() -> Path:
    """Where the extracted kit lives. `COSTAR_KIT_DIR` overrides for tests."""
    override = os.environ.get("COSTAR_KIT_DIR")
    base = Path(override) if override else _ROOT / "data" / "cache" / "costar" / "kit"
    if not (base / "commercial-properties.csv").is_file():
        raise KitMissing(
            f"CoStar kit not found at {base}. It is git-ignored (49 MB zip, 404 MB "
            "extracted); mirror it once from COSTAR_KIT_URL, or set COSTAR_KIT_DIR."
        )
    return base


# ---------- enums and normalisation ----------

@lru_cache(maxsize=1)
def enums() -> dict[str, dict[str, str]]:
    return json.loads((kit_dir() / "schemas" / "enums.json").read_text())


def enum_name(enum: str, value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    return enums().get(enum, {}).get(str(value))


def normalise_city(city: Optional[str]) -> Optional[str]:
    """`LOS ANGELES` and `houston` both appear in the CSVs."""
    return " ".join(w.capitalize() for w in city.split()) if city and city.strip() else None


def normalise_state(state: Optional[str]) -> Optional[str]:
    """`TX`, `Texas`, `Tx`, `CA`, `Ca`, `California` and blanks all appear."""
    if not state or not state.strip():
        return None
    return _STATES.get(state.strip().casefold())


def _sqft_to_m2(v) -> Optional[float]:
    # No rounding: this is a data layer, and presentation rounds.
    return float(v) * SQFT_TO_M2 if isinstance(v, (int, float)) else None


# ---------- the starter CSVs ----------

@lru_cache(maxsize=1)
def rows_by_model() -> dict[str, list[dict]]:
    """`MatterportModelId` -> **every** row for it, normalised, in CSV order.

    A model id is **not** unique to one parent. Measured on the real kit
    2026-11-14: of 12,994 commercial models, 55 carry more than one `PropertyId`
    (multi-building complexes; one scan at 2121 Brittmoore Rd is attached to 13
    property records), and of the residential models 252 carry more than one
    `ListingId` - 202 being one sale marketed through several MLSs and 50 being
    separate sales or rentals over time. Keying this by model and keeping only the
    last row silently discarded 387 rows, so every row is kept and
    `get_costar_data` chooses a primary by a documented rule.

    Rows with an empty `MatterportModelId` (51 commercial, 1 residential) are skipped.
    """
    base = kit_dir()
    out: dict[str, list[dict]] = {}
    for name, kind in (
        ("commercial-properties.csv", "commercial_property"),
        ("residential-listings.csv", "residential_listing"),
    ):
        with (base / name).open(newline="") as fh:
            for row in csv.DictReader(fh):
                sid = (row.get("MatterportModelId") or "").strip()
                if not sid:
                    continue
                out.setdefault(sid, []).append({
                    "kind": kind,
                    "matterport_model_id": sid,
                    "property_id": (row.get("PropertyId") or "").strip() or None,
                    "listing_id": (row.get("ListingId") or "").strip() or None,
                    "residential_listing_id": (row.get("ResidentialListingId") or "").strip() or None,
                    "address": (row.get("Address") or "").strip() or None,
                    "city": normalise_city(row.get("City")),
                    "state": normalise_state(row.get("State")),
                })
    return out


def index_by_model() -> dict[str, dict]:
    """`MatterportModelId` -> its primary row. See `rows_by_model` for the rest."""
    return {sid: rows[0] for sid, rows in rows_by_model().items()}


def parents_for_model(sid: str) -> list[str]:
    """Every parent key a model is attached to: `PropertyId`s for a commercial model,
    `ListingId`s for a residential one. More than one is normal (see `rows_by_model`),
    and callers that care about the ambiguity should look here rather than trusting
    the single `property_id` / `listing_id` on `CostarData`."""
    rows = rows_by_model().get(sid, [])
    return [r["property_id"] or r["listing_id"] for r in rows]


def models_for_property(property_id: str) -> list[str]:
    """Every Matterport model on one commercial property, in CSV order."""
    return [
        sid for sid, rows in rows_by_model().items()
        if any(r.get("property_id") == property_id for r in rows)
    ]


# ---------- streaming record lookup ----------

def iter_records(dataset: str) -> Iterator[dict]:
    """Stream one of the eight JSONL datasets. Public so `index.py` (D7) can make a
    single pass over a whole dataset instead of one `_find_record` scan per row."""
    with (kit_dir() / "data" / f"{dataset}.jsonl").open() as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _find_record(dataset: str, record_id: str) -> Optional[dict]:
    """Stream the file and stop at the first match. `commercial-property.jsonl` is
    193 MB, so the cheap substring test avoids parsing every line as JSON."""
    needle = f'"id":{record_id}'
    needle_spaced = f'"id": {record_id}'
    path = kit_dir() / "data" / f"{dataset}.jsonl"
    with path.open() as fh:
        for line in fh:
            if needle not in line and needle_spaced not in line:
                continue
            rec = json.loads(line)
            if str(rec.get("id")) == str(record_id):
                return rec
    return None


def is_office(record: dict) -> bool:
    """The office flow selects on `propertyType == 5`, never on the index segment:
    2,765 of the kit's 3,339 properties are Multifamily."""
    return record.get("propertyType") == OFFICE_PROPERTY_TYPE


# ---------- mapping to the contract ----------

def _construction_years(record: dict) -> tuple[Optional[int], Optional[str], Optional[int]]:
    """Commercial years live in `constructionEvents[]`, not in a `yearBuilt` field.

    Prefers `ConstructionComplete`; falls back to the earliest event with a year so
    the caller still gets a vintage, and always reports which event was used.
    """
    events = [e for e in (record.get("constructionEvents") or []) if e.get("year")]
    if not events:
        return None, None, None
    built = next((e for e in events if e.get("eventType") == _CONSTRUCTION_COMPLETE), None)
    if built is None:
        built = min(events, key=lambda e: e["year"])
    renovated = [
        e["year"] for e in events
        if e.get("eventType") in (_RENOVATION_FINISHED, _RENOVATION_BEGUN)
    ]
    return (
        int(built["year"]),
        enum_name("ConstructionEventType", built.get("eventType")),
        max(renovated) if renovated else None,
    )


def _commercial(row: dict, rec: dict) -> CostarData:
    year, event, renovated = _construction_years(rec)
    return CostarData(
        kind="commercial_property",
        matterport_model_id=row["matterport_model_id"],
        property_id=row.get("property_id"),
        record_id=str(rec["id"]),
        raw=rec,
        property_type=enum_name("PropertyType", rec.get("propertyType")),
        property_type_code=rec.get("propertyType"),
        year_built=year,
        year_built_event=event,
        year_renovated=renovated,
        building_class=enum_name("BuildingClass", rec.get("buildingClass")),
        building_area_m2=_sqft_to_m2(rec.get("grossBuildingAreaSquareFeet")),
        rentable_area_m2=_sqft_to_m2(rec.get("rentableBuildingAreaSquareFeet")),
        stories=rec.get("numStoriesAboveGrade"),
        # No owner name exists on a property record: the kit has only
        # `isOwnerOccupied` and `apartmentOwnershipType`. `compOwners` is on sale
        # comps, which is D10.
        owner_name=None,
    )


def _residential(row: dict, rec: dict) -> CostarData:
    prop = rec.get("property") or {}
    lo, hi = prop.get("sqftMin"), prop.get("sqftMax")
    area = hi if lo == hi else (None if lo is None or hi is None else (lo + hi) / 2)
    # `property.propertyType` is ambiguous: on the golden house it is 1, which under
    # PropertyResidentialType means ApartmentCommunity and contradicts the record's
    # own mlsPropertyType of "Single Family Residence". `listingPropertyType` is 1
    # under ListingPropertyType = Detached, which agrees. Use that one.
    return CostarData(
        kind="residential_listing",
        matterport_model_id=row["matterport_model_id"],
        listing_id=row.get("listing_id"),
        residential_listing_id=row.get("residential_listing_id"),
        record_id=str(rec["id"]),
        raw=rec,
        property_type=enum_name("ListingPropertyType", prop.get("listingPropertyType")),
        property_type_code=prop.get("listingPropertyType"),
        year_built=prop.get("yearBuilt"),
        year_built_event="yearBuilt" if prop.get("yearBuilt") else None,
        building_area_m2=_sqft_to_m2(area),
        stories=prop.get("stories"),
    )


def _list_date(rec: dict) -> str:
    return str(rec.get("listDate") or "")


def get_costar_data(matterport_model_id: str) -> CostarData:
    """The lane's `CostarData` for one Matterport model.

    When a model has several parents (see `rows_by_model`) the primary is chosen by a
    documented, deterministic rule:

    - **commercial**: the first row in CSV order whose property record exists;
    - **residential**: among rows whose listing records exist, the one with the latest
      `listDate`, which is the most recent marketing of that home and so what a user
      searching today expects. Ties fall back to CSV order.

    `parents_for_model` exposes the alternatives, because `CostarData` carries only one
    `property_id` / `listing_id`.

    Raises `LookupError` when the model is not on the kit's list, or when none of its
    rows points at a record the datasets contain.
    """
    rows = rows_by_model().get(matterport_model_id)
    if not rows:
        raise LookupError(f"model not on the CoStar kit list: {matterport_model_id}")

    if rows[0]["kind"] == "commercial_property":
        for row in rows:
            rec = _find_record("commercial-property", row["property_id"])
            if rec is not None:
                return _commercial(row, rec)
        raise LookupError(
            "no commercial-property record for any PropertyId of "
            f"{matterport_model_id}: {[r['property_id'] for r in rows]}"
        )

    found = [(row, rec) for row in rows
             if (rec := _find_record("residential-listings", row["listing_id"])) is not None]
    if not found:
        raise LookupError(
            "no residential-listings record for any ListingId of "
            f"{matterport_model_id}: {[r['listing_id'] for r in rows]}"
        )
    row, rec = max(found, key=lambda pair: _list_date(pair[1]))
    return _residential(row, rec)
