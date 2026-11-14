"""Which place a property is in, and therefore which utility serves it (package D14).

Two questions in the lane depend on a boundary that **no sponsor source answers**:

1. **Is this property inside the incorporated City of Houston?** Texas PACE lists the
   city, not Harris County around it, so A28's `cpace_scenario` refuses eligibility
   until something shows the property is in a PACE region.
2. **Which electric utility serves the meter?** `SPEC.md` 6.6 switches the export
   regime, the CPUC solar consumer guide and commercial prevailing wage on
   `Tariff.utility`; `specs/legal/california.md` selects contract clauses from it; and
   the incentive registry keys 8 LADWP and 4 CenterPoint entries on it.

**CoStar's `City` cannot answer either, and it is wrong often enough to matter.**
Measured 2026-11-14 against the Census `Incorporated Places` layer:

| CoStar `City` | sample | actually |
|---|---|---|
| `"Houston"`, TX | 16 | **9 Houston city, 6 unincorporated, 1 Nassau Bay city** |
| `"Los Angeles"`, CA | 14 | **14 Los Angeles city** |

So the field is a *mailing* city. It is reliable for Los Angeles and wrong 44 % of the
time for Houston - and the one Houston property the PACE work first caught
(`240022`, CoStar `cityId` 5316 "Houston") is unincorporated. A sample is not a
census; these numbers justify the lookup, they are not the kit's true error rate.

The US Census Bureau geocoder answers both from one keyless call. Verified live:
`Incorporated Places` and `Counties` come back together, a point off land returns no
place rather than an error, and the three Los Angeles County cities that run their own
electric utilities - Burbank, Glendale and Pasadena - return their own names, which is
what lets this module decline to guess for them.

**The rule here is the lead's, from the board, not invented:** City of Los Angeles
gives `LADWP`; elsewhere in Los Angeles County gives `SCE` with a record flagged as
needing confirmation; outside California the utility is left as it was. The *price*
always stays on the EIA fallback - `Tariff.source` carries the price provenance and
`utility` names who serves the meter.

**A failed lookup returns `None`, never `False`.** "We could not check" must not read
as "not eligible" or "not LADWP"; those are answers, and an outage is not.
"""
from __future__ import annotations

from typing import Callable, Optional

from backend.schema import FetchRecord

from . import cache

#: Which `FetchRecord.layer` these records carry. @yalexie1 added `"place"` in
#: contract 0.3.3 for exactly this: an incorporated-place or program-area lookup is
#: none of the other five layers, and labelling a Census fact `"tariff"` or
#: `"costar"` would misreport where it came from in a provenance field. A test
#: asserts this is a layer the contract permits, so it cannot drift.
PLACE_LAYER = "place"

GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"

#: Pinned so a cached answer keeps meaning what it meant. `Current_Current` tracks the
#: latest vintage, which is right for "who serves this meter today".
BENCHMARK = "Public_AR_Current"
VINTAGE = "Current_Current"
LAYERS = "Incorporated Places,Counties"

#: Five decimal places is about a metre, far finer than any municipal boundary, and it
#: keeps the cache key stable against floating-point noise in a georeference.
_PRECISION = 5

#: The city whose own department is the utility. LADWP serves the City of Los Angeles;
#: the surrounding unincorporated county and most other cities are Edison territory.
CITY_OF_LA = "Los Angeles city"
LA_COUNTY = "Los Angeles County"

#: Texas PACE regions this lane can positively confirm. Houston is the one the demo
#: needs; `specs/legal/texas.md` 6.4 is the administrator's list, and a place not on it
#: is not eligible *until confirmed*, which is a different claim from "not eligible".
TX_PACE_PLACES = {"Houston city"}

#: Los Angeles County cities that run their own electric utility.
#: `specs/legal/california.md:1001` is explicit that these must not be assumed to be
#: LADWP **or** SCE, so this module returns no utility for them rather than a guess.
#: Their interconnection rules have not been read.
MUNICIPAL_UTILITY_CITIES = {
    "Burbank city": "Burbank Water and Power",
    "Glendale city": "Glendale Water and Power",
    "Pasadena city": "Pasadena Water and Power",
    "Vernon city": "Vernon Public Utilities",
    "Azusa city": "Azusa Light and Water",
    "Cerritos city": "Cerritos Electric Utility",
}

Getter = Callable[[str, dict], dict]


def _default_get(url: str, params: dict) -> dict:
    import httpx  # lazy so offline tests need no transport

    resp = httpx.get(url, params=params, timeout=60.0)
    resp.raise_for_status()
    return resp.json()


def _params(lat: float, lon: float) -> dict:
    return {
        "x": lon, "y": lat,          # x is longitude. Swapping them queries the sea.
        "benchmark": BENCHMARK,
        "vintage": VINTAGE,
        "layers": LAYERS,
        "format": "json",
    }


class Place:
    """What the geocoder said about one point."""

    def __init__(self, city: Optional[str], county: Optional[str], state_fips: Optional[str]):
        self.city = city          # e.g. "Houston city"; None when unincorporated
        self.county = county      # e.g. "Harris County"
        self.state_fips = state_fips

    def __repr__(self) -> str:    # pragma: no cover - debugging aid
        return f"Place(city={self.city!r}, county={self.county!r})"


def _parse(payload: dict) -> Place:
    geo = ((payload or {}).get("result") or {}).get("geographies") or {}
    places = geo.get("Incorporated Places") or []
    counties = geo.get("Counties") or []
    first = places[0] if places else {}
    return Place(
        city=(first.get("NAME") or None),
        county=((counties[0].get("NAME") if counties else None) or None),
        state_fips=(first.get("STATE") or (counties[0].get("STATE") if counties else None)),
    )


def lookup(
    lat: float, lon: float, *, get: Optional[Getter] = None, refresh: bool = False
) -> tuple[Optional[Place], FetchRecord]:
    """The place at a point, or `(None, record)` if the lookup could not be made.

    `None` for the *place object* means the call failed. A successful call that finds
    no incorporated place returns a `Place` whose `city` is `None` - that is the
    "unincorporated" answer, and it is real data.

    Cached through D4, since a municipal boundary does not move; an injected `get`
    bypasses the cache both ways.
    """
    identifier = f"{round(lat, _PRECISION)},{round(lon, _PRECISION)}"
    shape = {"benchmark": BENCHMARK, "vintage": VINTAGE, "layers": LAYERS}
    try:
        payload, from_cache = cache.cached_json(
            "census-place", identifier,
            lambda: (get or _default_get)(GEOCODER, _params(lat, lon)),
            shape, use_cache=get is None, refresh=refresh,
        )
    except Exception as exc:
        return None, FetchRecord(
            layer=PLACE_LAYER, what="census/geographies", status="error",
            detail=f"place lookup failed for {identifier}: {str(exc)[:120]}",
        )

    place = _parse(payload)
    where = place.city or f"unincorporated {place.county or 'area'}"
    return place, FetchRecord(
        layer=PLACE_LAYER, what="census/geographies",
        status="ok" if place.county or place.city else "missing",
        detail=(f"{where}"
                + (f", {place.county}" if place.city and place.county else "")
                + ("; served from the cache" if from_cache else "")),
    )


def in_pace_region(
    lat: float, lon: float, state: str, *, get: Optional[Getter] = None
) -> tuple[Optional[bool], FetchRecord]:
    """Whether the property sits in a PACE region, for A28's `in_pace_region`.

    Three distinct answers, and conflating any two of them is the bug this exists to
    avoid:

    - `True`  - positively inside a place on the administrator's list.
    - `False` - positively somewhere else: unincorporated, or a different city.
    - `None`  - **we could not check.** A28 treats anything other than `True` as not
      eligible, which is the right default, but the record has to say which of the
      two it was so a reader can tell a refusal from an outage.
    """
    place, record = lookup(lat, lon, get=get)
    if place is None:
        return None, record

    if state.upper() == "TX":
        inside = place.city in TX_PACE_PLACES
        if inside:
            return True, FetchRecord(
                layer=PLACE_LAYER, what="pace/region", status="ok",
                detail=f"{place.city} is a Texas PACE region (texas.md 6.4)",
            )
        return False, FetchRecord(
            layer=PLACE_LAYER, what="pace/region", status="missing",
            detail=(f"{place.city or 'unincorporated ' + (place.county or 'area')} is not on the "
                    f"Texas PACE administrator's list; not eligible until confirmed"),
        )

    # California's programmes are per-county and per-city and were not read, so this
    # lane does not assert eligibility there. A28 already keeps CA hypothetical until
    # `ca_programme_confirmed`, so returning None changes nothing and claims nothing.
    return None, FetchRecord(
        layer=PLACE_LAYER, what="pace/region", status="missing",
        detail=f"no PACE region list was read for {state.upper()}; "
               f"the place is {place.city or 'unincorporated'}",
    )


def utility_for(
    lat: float, lon: float, state: str, *, get: Optional[Getter] = None
) -> tuple[Optional[str], FetchRecord]:
    """The electric utility serving the meter, on the lead's rule.

    Returns `None` when it should not be guessed, which the caller must treat as
    "leave the existing value" rather than "no utility". Per the lead's board post,
    a `utility` without a utility name is **unconfirmed, not LADWP**.
    """
    place, record = lookup(lat, lon, get=get)
    if place is None:
        return None, record

    if state.upper() != "CA":
        # CenterPoint is the Houston wires utility but its delivery area is not a city
        # boundary, so an incorporation test is the wrong instrument: it would say
        # nothing about a property in unincorporated Harris County that CenterPoint
        # does serve. Texas keeps whatever the caller already had.
        return None, FetchRecord(
            layer=PLACE_LAYER, what="utility", status="missing",
            detail=(f"no utility rule for {state.upper()}: a service territory is not a city "
                    f"boundary, so the place ({place.city or 'unincorporated'}) does not decide it"),
        )

    if place.city == CITY_OF_LA:
        return "LADWP", FetchRecord(
            layer=PLACE_LAYER, what="utility", status="ok",
            detail=("inside the City of Los Angeles, so LADWP: its own net metering, the LADWP "
                    "rebates, and no CPUC solar guide (SPEC 6.6; california.md CA-SOL-25)"),
        )

    if place.city in MUNICIPAL_UTILITY_CITIES:
        return None, FetchRecord(
            layer=PLACE_LAYER, what="utility", status="missing",
            detail=(f"{place.city} runs its own electric utility "
                    f"({MUNICIPAL_UTILITY_CITIES[place.city]}); its rules were not read, so this "
                    f"is neither LADWP nor SCE (california.md open question C11)"),
        )

    if place.county == LA_COUNTY:
        return "SCE", FetchRecord(
            layer=PLACE_LAYER, what="utility", status="fallback",
            detail=(f"{place.city or 'unincorporated Los Angeles County'} is outside the City of "
                    f"Los Angeles and not a known municipal utility, so Southern California "
                    f"Edison - **needs confirmation**: SCE means the Net Billing Tariff, the "
                    f"signed CPUC guide on a residential job, and prevailing wage on commercial PV"),
        )

    return None, FetchRecord(
        layer=PLACE_LAYER, what="utility", status="missing",
        detail=(f"{place.city or 'unincorporated area'} in {place.county or 'an unknown county'} "
                f"is outside Los Angeles County; California has about forty publicly owned "
                f"utilities and the rule was only read for LA County"),
    )
