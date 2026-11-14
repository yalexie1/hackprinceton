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

#: Census state FIPS to USPS code. The geocoder returns `STATE` as a two-digit FIPS
#: string on both the place and the county record - **there is no state abbreviation
#: anywhere in the response**, so the mapping has to live here.
#:
#: This exists because `PropertySummary.state` came back empty on a machine with no
#: CoStar kit mirror, and `get_tariff` then fell back to a hard-coded `"CA"`. In
#: Houston that is not a near miss: it swaps a 0.0896 USD/kWh commercial price for
#: 0.3002, changes the eGRID subregion from ERCT to CAMX, and selects California
#: contract clauses for a Texas building. Reported by @Sri-SriPod from a live run.
#:
#: The whole table and not just CA and TX: Vexcel's coverage is Los Angeles and
#: Houston, but the EIA price, the emissions factor and the legal templates all key on
#: the state, and a property outside Vexcel coverage still gets a tariff. A partial
#: table would silently resolve to `None` and land back on the `"CA"` default, which
#: is the bug this fixes.
STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY",
    # Territories. The geocoder covers them; the EIA price tables largely do not, so a
    # tariff there will fall back and say so rather than quoting a mainland number.
    "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}

#: The Census appends a legal/statistical area description to the place name -
#: "Los Angeles city", "Nassau Bay city", "Houston city". `PropertySummary.city` wants
#: the name a person would write on an envelope, so the suffix is stripped. The full
#: name is kept everywhere the *boundary* matters (`CITY_OF_LA`, `TX_PACE_PLACES`),
#: because "Los Angeles city" and "Los Angeles County" are different places and
#: collapsing them is how a county property would be handed LADWP.
_LSAD_SUFFIXES = (" city", " town", " village", " borough", " municipality", " CDP")

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


def state_for(
    lat: float, lon: float, *, get: Optional[Getter] = None
) -> tuple[Optional[str], FetchRecord]:
    """The USPS state code at a point, or `(None, record)`.

    For `PropertySummary.state` when there is no CoStar kit to read it from. Derived
    from the Census `STATE` FIPS, which arrives on the same cached call D14 already
    makes for the utility - so this costs nothing extra on the bundle path.

    `None` means the lookup failed or returned a FIPS this table does not know, never
    "not in a state". A caller must not substitute a default for it: handing Houston
    `"CA"` is what this exists to stop.
    """
    place, record = lookup(lat, lon, get=get)
    if place is None:
        return None, record
    if not place.state_fips:
        return None, FetchRecord(
            layer=PLACE_LAYER, what="census/state", status="missing",
            detail=(f"the geocoder answered for {place.city or place.county or 'the point'} "
                    f"but carried no state FIPS"),
        )
    code = STATE_FIPS.get(str(place.state_fips).zfill(2))
    if code is None:
        return None, FetchRecord(
            layer=PLACE_LAYER, what="census/state", status="missing",
            detail=f"state FIPS {place.state_fips!r} is not in the USPS table",
        )
    return code, FetchRecord(
        layer=PLACE_LAYER, what="census/state", status="ok",
        detail=(f"{code} from Census state FIPS {place.state_fips}"
                f"{f' ({place.county})' if place.county else ''}; the CoStar kit "
                f"carried no state for this property"),
    )


def city_for(
    lat: float, lon: float, *, get: Optional[Getter] = None
) -> tuple[Optional[str], FetchRecord]:
    """The incorporated place name at a point, without its Census suffix.

    `None` for an unincorporated address, which is a real answer: 6 of the 16 kit
    properties CoStar labels `"Houston"` are not in any incorporated place. This is
    only used to fill `PropertySummary.city` when the kit is absent, and it is
    *better* than CoStar's field rather than a substitute for it - CoStar's is a
    mailing city, measured wrong 7 times in 16 in Houston.
    """
    place, record = lookup(lat, lon, get=get)
    if place is None:
        return None, record
    if not place.city:
        return None, FetchRecord(
            layer=PLACE_LAYER, what="census/city", status="missing",
            detail=(f"the point is in no incorporated place"
                    f"{f' ({place.county})' if place.county else ''}, so there is no city "
                    f"name to give - which is itself the answer, not a failure"),
        )
    name = place.city
    for suffix in _LSAD_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.strip() or None, FetchRecord(
        layer=PLACE_LAYER, what="census/city", status="ok",
        detail=f"{name.strip()} from the Census incorporated-place layer ({place.city})",
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
