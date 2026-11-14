"""Occupancy and market data from the CoStar datasets the spec never used (package D10).

`CostarData.occupancy` and `.market` were always `None`, which had two consequences:
`Plan.value_uplift` (A30, VAL-01) never fired on live data, because
`plan_value_uplift` returns `None` without a cap rate and at least ten comparables;
and office plug loads, lighting schedules and occupancy-driven HVAC were inferred from
vintage defaults while real tenancy data sat in the kit.

Five datasets, all measured on the mirror 2026-11-14:

| dataset | records | what it gives |
|---|---|---|
| `commercial-sale-comp` | 6,120 | cap rates and sale prices |
| `location-occupancy` | 74,093 | who is in the building, since when, how much space |
| `company-detail` | 49,575 | employee counts and industry per tenant |
| `apartment-listing` | 1,747 | asking rents for multifamily |

**Three traps, each measured rather than assumed:**

1. **Cap rates are stored in percent, not as fractions.** Median 6.5, range 0.75 to
   23.58. The contract documents `cap_rate` as "fraction per year", so these are
   divided by 100. Passing the raw number through would overstate value uplift by a
   hundredfold and nothing would error.
2. **The comp window decides whether A30 can run at all.** Comps with a cap rate that
   sold since 2015: LA office 12, Houston office 27. Since **2020**: LA office **1**,
   Houston office 9 - both below `MIN_COMPS = 10`. So a tighter window silently turns
   value uplift off for both golden offices, and a looser one reaches back to 1983.
   2015 is the window that works, and it is a judgement, not a fact.
3. **"Still in place" means no `toDate`.** Not `expirationReason == 0`: that enum
   explains why a tenancy *ended* and its zero value is "Unknown". No record in either
   golden office has a `toDate` in the future, so the kit marks a current tenancy by
   leaving the field out.

Sanity checks that passed, and which are the reason to trust the above: current
occupancy comes to **81 % of RBA at the Los Angeles office and 71 % at the Houston
one**, and the median cap rate is **4.85 % in Los Angeles against 7.90 % in Houston** -
Houston above Los Angeles, which is the right market structure for a riskier market
with cheaper assets.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from backend.schema import FetchRecord, MarketData, OccupancyData, Ranged, Tenancy

from . import costar

#: Sales from this year on count as market evidence. See trap 2: 2020 leaves one
#: usable Los Angeles office comp, and no window reaching back far enough to gather
#: ten is also recent enough to be a current market signal. The count travels on
#: `MarketData.comp_count` so a reader can judge the evidence.
MARKET_SINCE_YEAR = 2015

#: The kit stores cap rates as percentages; the contract wants a fraction per year.
PERCENT_TO_FRACTION = 0.01

#: Below this there is no distribution worth quoting a range from. A30 applies its own
#: `MIN_COMPS = 10` on top, which is the binding one.
MIN_COMPS_FOR_A_RANGE = 3

#: `propertyType` 5 is Office, 11 Multifamily. A comp is comparable when it shares the
#: subject's city **and** property type - the kit has no submarket geometry to do
#: better, and mixing an office cap rate into a multifamily valuation would be worse
#: than returning nothing.
_COMMERCIAL = "commercial-property"


# ---------- indexes, one pass each ----------

@lru_cache(maxsize=1)
def property_facts() -> dict[str, tuple[Optional[str], Optional[int], Optional[float]]]:
    """`PropertyId` -> `(city, propertyType, rentable_area_m2)`.

    Measured at 0.88 s over 3,339 records, so an in-memory index is enough and nothing
    here needs the D4 disk cache.
    """
    out: dict[str, tuple[Optional[str], Optional[int], Optional[float]]] = {}
    for rec in costar.iter_records(_COMMERCIAL):
        addr = rec.get("primaryAddress") or {}
        rba = rec.get("rentableBuildingAreaSquareFeet") or rec.get("grossBuildingAreaSquareFeet")
        out[str(rec["id"])] = (
            costar.normalise_city(addr.get("city")),
            rec.get("propertyType"),
            float(rba) * costar.SQFT_TO_M2 if isinstance(rba, (int, float)) else None,
        )
    return out


@lru_cache(maxsize=1)
def sale_comps() -> tuple[dict, ...]:
    """Every sale comp trimmed to what a valuation needs, with its market attached.

    A comp carries the cap rate at the top level or on one of its `entities`; both
    `capitalizationRateActual` and `...ProForma` occur, and actual is preferred because
    pro-forma is the seller's projection.
    """
    facts = property_facts()
    out: list[dict] = []
    for rec in costar.iter_records("commercial-sale-comp"):
        rate = rec.get("capitalizationRateActual") or rec.get("capitalizationRateProForma")
        property_id = None
        for entity in rec.get("entities") or []:
            rate = rate or entity.get("capitalizationRateActual") or entity.get("capitalizationRateProForma")
            property_id = property_id or (str(entity["propertyId"]) if entity.get("propertyId") else None)
        if property_id is None or property_id not in facts:
            continue        # 367 of 6,120 reference a property the kit does not ship
        city, property_type, area_m2 = facts[property_id]
        year = str(rec.get("soldDate") or "")[:4]
        price = rec.get("soldForPrice")
        out.append({
            "property_id": property_id,
            "city": city,
            "property_type": property_type,
            "year": int(year) if year.isdigit() else None,
            "cap_rate": float(rate) * PERCENT_TO_FRACTION if isinstance(rate, (int, float)) and rate > 0 else None,
            "price_usd_per_m2": (float(price) / area_m2) if (
                isinstance(price, (int, float)) and price > 0 and area_m2) else None,
        })
    return tuple(out)


@lru_cache(maxsize=1)
def companies() -> dict[int, dict]:
    """`company-detail.id` -> the record. Joined from `location-occupancy`'s
    `tenantLocationId`; 224 of the Houston office's 225 tenants matched."""
    return {c["id"]: c for c in costar.iter_records("company-detail") if c.get("id") is not None}


@lru_cache(maxsize=1)
def tenancies_by_property() -> dict[str, tuple[dict, ...]]:
    """`PropertyId` -> its `location-occupancy` records, in file order."""
    out: dict[str, list[dict]] = {}
    for rec in costar.iter_records("location-occupancy"):
        pid = rec.get("propertyId")
        if pid is not None:
            out.setdefault(str(pid), []).append(rec)
    return {k: tuple(v) for k, v in out.items()}


@lru_cache(maxsize=1)
def apartment_listings() -> dict[str, dict]:
    """`PropertyId` -> its apartment community record, for multifamily asking rent."""
    out = {}
    for rec in costar.iter_records("apartment-listing"):
        pid = rec.get("propertyId")
        if pid is not None:
            out[str(pid)] = rec
    return out


# ---------- statistics ----------

def _ranged(values: list[float], unit: str) -> Optional[Ranged]:
    """A quartile range. `low` and `high` are the 25th and 75th percentiles of real
    comparable sales, not a modelled confidence interval, and `expected` is the median
    rather than the mean so one distressed sale cannot drag it."""
    if len(values) < MIN_COMPS_FOR_A_RANGE:
        return None
    ordered = sorted(values)
    def at(q: float) -> float:
        return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * q)))]
    low, mid, high = at(0.25), at(0.5), at(0.75)
    # The contract requires low <= expected <= high; quartiles of a short list can tie.
    return Ranged(low=min(low, mid), expected=mid, high=max(high, mid), unit=unit)


# ---------- the contract objects ----------

def market_data(
    property_id: Optional[str], *, since_year: int = MARKET_SINCE_YEAR
) -> tuple[Optional[MarketData], list[FetchRecord]]:
    """`MarketData` for the subject property's market, or `(None, [record])`.

    Comparable means **same city and same property type**, sold in or after
    `since_year`. The kit has no submarket geometry, so city is the finest honest
    grain; mixing an office cap rate into a multifamily valuation would be worse than
    returning nothing.
    """
    if not property_id:
        return None, [FetchRecord(layer="costar", what="market", status="missing",
                                  detail="no PropertyId, so no market can be identified")]
    facts = property_facts()
    if property_id not in facts:
        return None, [FetchRecord(layer="costar", what="market", status="missing",
                                  detail=f"property {property_id} is not in the kit")]

    city, property_type, _ = facts[property_id]
    peers = [
        c for c in sale_comps()
        if c["city"] == city and c["property_type"] == property_type
        and c["year"] is not None and c["year"] >= since_year
    ]
    # One observation per property, most recent first, so a single building that
    # trades often cannot dominate the distribution. Measured: this takes the Houston
    # office market from 27 comps to 25 and leaves Los Angeles at 12, both still above
    # A30's `MIN_COMPS = 10`.
    rates: dict[str, float] = {}
    for comp in sorted(peers, key=lambda c: c["year"] or 0, reverse=True):
        if comp["cap_rate"] is not None and comp["property_id"] not in rates:
            rates[comp["property_id"]] = comp["cap_rate"]

    market = MarketData(
        cap_rate=_ranged(list(rates.values()), "fraction/yr"),
        # Deliberately not supplied - see `SALE_PRICE_NOTE`.
        sale_price_usd_per_m2=None,
        asking_rent_usd_per_m2_year=_asking_rent(property_id),
        # The count A30 tests against is the number of **properties** with a cap rate,
        # not the number of sales in the market: the latter would overstate the
        # evidence, and counting repeat sales of one building would overstate it twice.
        comp_count=len(rates),
    )
    type_name = costar.enum_name("PropertyType", property_type) or str(property_type)
    detail = (f"{len(rates)} comparable properties with a cap rate in {city}, {type_name}, "
              f"since {since_year} (of {len(peers)} sales in that market); "
              f"no sale price per m2 - see SALE_PRICE_NOTE")
    return market, [FetchRecord(
        layer="costar", what="market",
        status="ok" if market.cap_rate is not None else "missing",
        detail=detail if market.cap_rate is not None else f"no cap rate available: {detail}",
    )]


#: Why `MarketData.sale_price_usd_per_m2` is left unset.
#:
#: `soldForPrice` is the price of **whatever was sold** - which is often a single
#: condominium unit or a partial interest - while the only area the kit gives is the
#: whole building's. Dividing one by the other is not a price per square metre of
#: anything. Measured on the Los Angeles office market: 86 priced sales over just **29
#: distinct properties**, one of which contributed **43** of them, spanning **6 to
#: 40,025 USD/m2**. A 6,600-fold spread is not a market, and deduplicating to one sale
#: per property still leaves Houston spanning 73 to 81,685.
#:
#: `value.py:60` would multiply this straight into `value_of_property` and cap the
#: uplift with it, so a wrong figure here produces a confidently wrong valuation.
#: `plan_value_uplift` already handles `None` - it simply omits the cap - so leaving it
#: unset costs a refinement and avoids a fabrication.
#:
#: The **cap rate is unaffected**: a yield is intrinsic to the transaction whatever
#: slice of the building sold, and those comps are one per property (12 and 25).
SALE_PRICE_NOTE = (
    "not supplied: soldForPrice covers whatever was sold, often one unit or a partial "
    "interest, while the kit's only area is the whole building's - the quotient spans "
    "6 to 40,025 USD/m2 across 29 Los Angeles office properties"
)


def _asking_rent(property_id: str) -> Optional[Ranged]:
    """Asking rent per square metre per year, for a multifamily community.

    `minRent` and `maxRent` are **monthly** rents for the smallest and largest unit, so
    this annualises and divides by the matching floor area rather than an average of
    the two, which would mix a one-bedroom rent with a three-bedroom area.
    """
    listing = apartment_listings().get(property_id)
    if not listing:
        return None
    pairs = [
        (listing.get("minRent"), listing.get("minSquareFeet")),
        (listing.get("maxRent"), listing.get("maxSquareFeet")),
    ]
    values = [
        (rent * 12.0) / (sqft * costar.SQFT_TO_M2)
        for rent, sqft in pairs
        if isinstance(rent, (int, float)) and isinstance(sqft, (int, float)) and rent > 0 and sqft > 0
    ]
    if not values:
        return None
    low, high = min(values), max(values)
    return Ranged(low=low, expected=(low + high) / 2.0, high=high, unit="USD/m2/yr")


def occupancy_data(property_id: Optional[str]) -> tuple[Optional[OccupancyData], list[FetchRecord]]:
    """Current tenancies, their employees and the occupied area.

    **Current means no `toDate`.** Not `expirationReason == 0`: that enum says why a
    tenancy ended and its zero value is "Unknown". Neither golden office has a single
    record with a `toDate` in the future, so the kit marks a sitting tenant by leaving
    the field out.

    Historic tenancies are dropped rather than returned with a `move_out`, because
    `OccupancyData.employees_total` and `.occupied_area_m2` describe the building
    *now* - summing over everyone who was ever there would double-count every floor.
    """
    if not property_id:
        return None, [FetchRecord(layer="costar", what="occupancy", status="missing",
                                  detail="no PropertyId, so no tenancy records")]

    records = tenancies_by_property().get(property_id, ())
    if not records:
        return None, [FetchRecord(layer="costar", what="occupancy", status="missing",
                                  detail=f"no tenancy records for property {property_id}")]

    firms = companies()
    tenants: list[Tenancy] = []
    employees = 0
    employees_known = 0
    area_total = 0.0
    for rec in records:
        if rec.get("toDate"):
            continue
        company = firms.get(rec.get("tenantLocationId")) or {}
        spaces = rec.get("spaces") or []
        area = sum(s.get("squareFeetOccupied") or 0 for s in spaces) * costar.SQFT_TO_M2
        count = company.get("numEmployees")
        if isinstance(count, int):
            employees += count
            employees_known += 1
        area_total += area
        tenants.append(Tenancy(
            tenant_name=company.get("name"),
            industry=costar.enum_name("IndustryType", rec.get("industryType")),
            employees=count if isinstance(count, int) else None,
            area_m2=area or None,
            floor=(spaces[0].get("suite") or "").strip() or None if spaces else None,
            move_in=_iso(rec.get("moveInDate") or rec.get("fromDate")),
            move_out=None,          # by definition: these are the sitting tenants
        ))

    data = OccupancyData(
        tenancies=tenants,
        employees_total=employees if employees_known else None,
        occupied_area_m2=area_total or None,
    )
    _, _, rentable = property_facts().get(property_id, (None, None, None))
    share = f", {area_total / rentable:.0%} of rentable area" if rentable else ""
    return data, [FetchRecord(
        layer="costar", what="occupancy", status="ok" if tenants else "missing",
        detail=(f"{len(tenants)} sitting tenants of {len(records)} on record, "
                f"{employees_known} with an employee count, {area_total:,.0f} m2 occupied{share}"),
    )]


def _iso(value) -> Optional[str]:
    """The kit's timestamps are ISO strings with an offset; the contract wants a date."""
    return str(value)[:10] if value else None
