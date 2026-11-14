"""D14: the incorporated-place lookup.

Every number asserted here was measured live against the US Census Bureau geocoder on
2026-11-14 and is recorded in `specs/data-integration.md`. The payloads below are the
real response *shape* with only the fields this module reads; a place name and a
county name are public facts, not sponsor data.

Nothing here touches the network - every test injects its transport, which also means
the D4 cache stays out of the way.
"""
from __future__ import annotations

import typing

import pytest

from backend.data_layer import cache, places
from backend.schema import FetchRecord


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_LAYER_CACHE_DIR", str(tmp_path / "cache"))


def _payload(city: str | None, county: str | None, state: str = "06") -> dict:
    """The geocoder's shape. An unincorporated point returns an **empty** places list
    while still returning a county - that is the answer, not a failure."""
    geographies: dict = {"Counties": [], "Incorporated Places": []}
    if county:
        geographies["Counties"] = [{"NAME": county, "STATE": state}]
    if city:
        geographies["Incorporated Places"] = [{"NAME": city, "STATE": state}]
    return {"result": {"geographies": geographies}}


def _getter(payload, calls=None):
    def get(url, params):
        if calls is not None:
            calls.append(params)
        return payload
    return get


def _raiser(exc=RuntimeError("connection reset")):
    def get(url, params):
        raise exc
    return get


# ---------- the request ----------

def test_longitude_goes_in_x():
    """WKT and this geocoder are both longitude-first. Swapping them queries the sea
    and returns a plausible-looking empty answer rather than an error."""
    calls = []
    places.lookup(34.0934, -118.3171, get=_getter(_payload("Los Angeles city", "Los Angeles County"), calls))
    assert calls[0]["x"] == -118.3171
    assert calls[0]["y"] == 34.0934


def test_both_layers_are_requested_in_one_call():
    """The county is needed as well as the city: the lead's rule scopes SCE to Los
    Angeles County, and one call returns both."""
    calls = []
    places.lookup(34.0, -118.0, get=_getter(_payload("x", "y"), calls))
    assert "Incorporated Places" in calls[0]["layers"]
    assert "Counties" in calls[0]["layers"]
    assert len(calls) == 1


def test_the_vintage_is_pinned():
    """A cached answer has to keep meaning what it meant when it was written."""
    calls = []
    places.lookup(34.0, -118.0, get=_getter(_payload("x", "y"), calls))
    assert calls[0]["benchmark"] == places.BENCHMARK == "Public_AR_Current"
    assert calls[0]["vintage"] == places.VINTAGE == "Current_Current"


# ---------- parsing ----------

def test_an_unincorporated_point_is_an_answer_not_a_failure():
    place, record = places.lookup(29.98, -95.52, get=_getter(_payload(None, "Harris County", "48")))
    assert place is not None, "a successful call must not return None"
    assert place.city is None
    assert place.county == "Harris County"
    assert record.status == "ok"
    assert "unincorporated" in record.detail


def test_a_point_off_land_parses_without_raising():
    """Verified live in the Pacific: HTTP 200 with no place and no county."""
    place, record = places.lookup(33.5, -119.5, get=_getter(_payload(None, None)))
    assert place is not None and place.city is None and place.county is None
    assert record.status == "missing"


def test_a_failed_lookup_returns_none_for_the_place():
    place, record = places.lookup(34.0, -118.0, get=_raiser())
    assert place is None, "a transport failure must be distinguishable from a real answer"
    assert record.status == "error"
    assert "connection reset" in record.detail


# ---------- PACE ----------

def test_the_houston_golden_office_is_in_a_pace_region():
    inside, record = places.in_pace_region(
        29.7460487, -95.4576844, "TX", get=_getter(_payload("Houston city", "Harris County", "48")))
    assert inside is True
    assert record.status == "ok" and "Houston city" in record.detail


def test_unincorporated_harris_county_is_not_a_pace_region():
    """Measured: 6 of 16 CoStar-"Houston" properties are here, and Texas PACE lists the
    city, not the county around it."""
    inside, record = places.in_pace_region(
        29.98, -95.52, "TX", get=_getter(_payload(None, "Harris County", "48")))
    assert inside is False
    assert "not on the Texas PACE administrator's list" in record.detail


def test_a_different_city_is_not_a_pace_region():
    """1 of the 16 was Nassau Bay city, which CoStar also labels "Houston"."""
    inside, _ = places.in_pace_region(
        29.54, -95.08, "TX", get=_getter(_payload("Nassau Bay city", "Harris County", "48")))
    assert inside is False


def test_a_lookup_failure_is_none_and_never_false():
    """The whole point. A28 treats anything but `True` as not eligible, which is the
    right default - but "we could not check" must not be reported to a user as "your
    property is not in a PACE region"."""
    inside, record = places.in_pace_region(29.74, -95.45, "TX", get=_raiser())
    assert inside is None
    assert inside is not False
    assert record.status == "error"


def test_california_pace_is_not_asserted_by_this_lane():
    """California's programmes are per-county and per-city and were not read. A28
    already keeps CA hypothetical, so `None` claims nothing it should not."""
    inside, record = places.in_pace_region(
        34.0934, -118.3171, "CA", get=_getter(_payload("Los Angeles city", "Los Angeles County")))
    assert inside is None
    assert "no PACE region list was read" in record.detail


# ---------- the utility ----------

def test_the_city_of_los_angeles_is_ladwp():
    utility, record = places.utility_for(
        34.0934, -118.3171, "CA", get=_getter(_payload("Los Angeles city", "Los Angeles County")))
    assert utility == "LADWP"
    assert record.status == "ok"
    assert "CPUC" in record.detail, "the record should say what LADWP implies"


def test_elsewhere_in_la_county_is_sce_and_flagged_unconfirmed():
    utility, record = places.utility_for(
        34.0195, -118.4912, "CA", get=_getter(_payload("Santa Monica city", "Los Angeles County")))
    assert utility == "SCE"
    assert record.status == "fallback", "SCE is the lead's default, not a verified fact"
    assert "needs confirmation" in record.detail


def test_unincorporated_la_county_is_sce():
    utility, _ = places.utility_for(
        34.0, -118.08, "CA", get=_getter(_payload(None, "Los Angeles County")))
    assert utility == "SCE"


@pytest.mark.parametrize("city", ["Burbank city", "Glendale city", "Pasadena city"])
def test_a_city_with_its_own_utility_is_neither_ladwp_nor_sce(city):
    """`specs/legal/california.md:1001` is explicit that these must not be assumed to
    be either. Returning SCE for Burbank would pick the wrong CPUC clauses and the
    wrong export regime."""
    utility, record = places.utility_for(
        34.18, -118.31, "CA", get=_getter(_payload(city, "Los Angeles County")))
    assert utility is None
    assert record.status == "missing"
    assert "its own electric utility" in record.detail


def test_california_outside_la_county_is_not_guessed():
    """California has about forty publicly owned utilities; the rule was read for Los
    Angeles County only."""
    utility, record = places.utility_for(
        32.7157, -117.1611, "CA", get=_getter(_payload("San Diego city", "San Diego County")))
    assert utility is None
    assert "outside Los Angeles County" in record.detail


def test_texas_utility_is_not_decided_by_a_city_boundary():
    """CenterPoint is the Houston wires utility but its delivery area is not the city
    limit, so an incorporation test is the wrong instrument - it says nothing about a
    property in unincorporated Harris County that CenterPoint does serve."""
    utility, record = places.utility_for(
        29.746, -95.4577, "TX", get=_getter(_payload("Houston city", "Harris County", "48")))
    assert utility is None
    assert "not a city boundary" in record.detail


def test_a_failed_lookup_leaves_the_utility_alone():
    utility, record = places.utility_for(34.09, -118.31, "CA", get=_raiser())
    assert utility is None
    assert record.status == "error"


# ---------- plumbing ----------

def test_the_fetch_record_layer_is_one_the_contract_permits():
    """`"place"` has been requested as an additive value. Until it lands these records
    ride on an existing layer, and this test is what notices when the contract
    changes - in either direction."""
    allowed = typing.get_args(FetchRecord.model_fields["layer"].annotation)
    assert places.PLACE_LAYER in allowed, (
        f"PLACE_LAYER={places.PLACE_LAYER!r} is not in {allowed}; if 'place' was added, use it"
    )
    for record in (
        places.lookup(34.0, -118.0, get=_getter(_payload("x", "y")))[1],
        places.utility_for(34.0, -118.0, "CA", get=_getter(_payload("x", "Los Angeles County")))[1],
        places.in_pace_region(29.7, -95.4, "TX", get=_getter(_payload("Houston city", "Harris County")))[1],
    ):
        FetchRecord.model_validate(record.model_dump(mode="json"))


def test_every_record_names_the_geocoder_or_the_rule():
    """These records sit in a bundle's provenance beside Matterport and Vexcel ones, so
    a reader has to be able to tell where the fact came from."""
    _, record = places.lookup(34.0, -118.0, get=_getter(_payload("x", "y")))
    assert record.what.startswith("census/")


def test_an_injected_transport_is_not_cached():
    calls = []
    payload = _payload("Los Angeles city", "Los Angeles County")
    places.lookup(34.0934, -118.3171, get=_getter(payload, calls))
    places.lookup(34.0934, -118.3171, get=_getter(payload, calls))
    assert len(calls) == 2, "an injected transport was cached"
    shape = {"benchmark": places.BENCHMARK, "vintage": places.VINTAGE, "layers": places.LAYERS}
    assert cache.read_json("census-place", "34.0934,-118.3171", shape) is None


def test_the_default_transport_is_cached(monkeypatch):
    """A municipal boundary does not move, so one lookup per point is enough - and the
    geocoder is a courtesy service we should not hammer."""
    calls = []
    payload = _payload("Houston city", "Harris County", "48")
    monkeypatch.setattr(places, "_default_get", lambda url, params: (calls.append(params) or payload))
    first, _ = places.lookup(29.7460487, -95.4576844)
    second, _ = places.lookup(29.7460487, -95.4576844)
    assert len(calls) == 1, "the default transport was not cached"
    assert first.city == second.city == "Houston city"


def test_coordinates_are_rounded_into_the_cache_key(monkeypatch):
    """Five decimals is about a metre - far finer than any boundary - so trailing
    float noise in a georeference must not cause a second call."""
    calls = []
    payload = _payload("Houston city", "Harris County", "48")
    monkeypatch.setattr(places, "_default_get", lambda url, params: (calls.append(params) or payload))
    places.lookup(29.74604870000001, -95.45768440000002)
    places.lookup(29.746048700000_02, -95.457684400000_01)
    assert len(calls) == 1


# ---------- live, opt-in ----------

@pytest.mark.skipif(
    __import__("os").environ.get("RUN_LIVE_NETWORK") != "1",
    reason="set RUN_LIVE_NETWORK=1",
)
def test_live_the_golden_properties_resolve():
    assert places.utility_for(34.093471, -118.317082, "CA")[0] == "LADWP"
    assert places.utility_for(34.0361802, -118.4428766, "CA")[0] == "LADWP"
    assert places.in_pace_region(29.7460487, -95.4576844, "TX")[0] is True


# ---------- the two call sites the lead approved ----------
#
# These assert behaviour in @yalexie1's and @Sri-SriPod's files. The code changes were
# approved on the board; the tests live here, in my own file, so I am not also writing
# their test suites. Say the word and I will move them.

def test_incentives_prefer_a_resolved_utility_over_the_city_field():
    """8 LADWP and 4 CenterPoint registry entries key on this value, so a wrong
    utility hands a property rebates it is not eligible for."""
    from backend.analysis.finance.costs import utility_of
    from backend.schema import PropertySummary

    # A mailing city of "Los Angeles" on a property the lookup placed in Burbank.
    mislabelled = PropertySummary(sid="x", name="x", segment="residential",
                                  use_type="single_family", city="Los Angeles", state="CA")
    assert utility_of(mislabelled, "LADWP") == "LADWP"
    # The resolved value wins, and an unnamed utility is unconfirmed - not LADWP.
    assert utility_of(mislabelled, "CA state average (RES)") is None


def test_the_city_fallback_warns_so_it_cannot_be_used_silently():
    from backend.analysis.finance.costs import utility_of
    from backend.schema import PropertySummary

    summary = PropertySummary(sid="x", name="x", segment="commercial", use_type="office",
                              city="Houston", state="TX")
    with pytest.warns(UserWarning, match="mailing city"):
        assert utility_of(summary) == "CenterPoint"


def test_the_utility_name_set_is_read_from_the_registry_not_hard_coded():
    """So it cannot drift from `incentives.json`."""
    from backend.analysis.finance.costs.incentives import utility_regions

    names = utility_regions()
    assert "LADWP" in names and "CenterPoint" in names
    assert "US" not in names and "CA" not in names and "TX" not in names


def test_cpace_region_is_unknown_offline_and_never_asserted_as_false():
    """SPEC 14: the analysis lane runs with no network, so the lookup cannot be made
    offline. A28 then reports not-eligible, which is right - but the data lane must
    hand it `None`, not `False`, so the note distinguishes the two."""
    from backend.data_layer import api

    assert api.in_pace_region("L3266YcPPvd", live=False) is None
