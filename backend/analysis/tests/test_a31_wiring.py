"""A31 wiring: the benchmark checks reach the public door's results (issue #319).

The checks themselves are tested in `backend/analysis/model/benchmark/tests/`. These tests are
about the wiring: that the door runs them on the real pipeline, that their findings reach the
object a caller reads, and - the property that matters most - that a check never moves a number.
"""
import socket
from pathlib import Path

import pytest

from backend.analysis import api
from backend.schema import PropertyBundle, RunRequest

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"
FLAVORS = sorted(p.name for p in EX.iterdir() if (p / "run_result.json").is_file())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def load(flavor):
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    request = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    return bundle, request


#: Each fixture bundle's `weather_path` points into `data/cache/`, and `_climate` reads that file
#: when it exists and substitutes the committed example year when it does not. So a machine with a
#: populated cache and a clean one produce different baselines from the same fixture - the house
#: warns on one and not the other, which is how the first version of these tests passed here and
#: failed in the lead's review. Pointing `weather_path` at a path that cannot exist forces the
#: committed example year everywhere, so these tests measure the same thing on every machine.
_NO_SITE_FILE = "data/cache/__not_a_cached_site__/weather/typical_year_hourly.csv"


def on_the_committed_weather(bundle):
    return bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"weather_path": _NO_SITE_FILE})})


def pv_card(bundle, request):
    bundle = on_the_committed_weather(bundle)
    observed, flags = api.observe_interior(bundle)
    model = api.build_building_model(bundle, observed, flags, request.overrides)
    return model, api.evaluate_measure(bundle, model, "PV_ROOF", request.role)


def crosscheck_warnings(card):
    return [w for w in card.warnings if "PVGIS" in w]


def benchmark_warnings(baseline):
    """The baseline's warnings minus the weather-source note (#328), which every bundle here
    carries because they all pin the weather to a path that cannot exist."""
    return [w for w in baseline.warnings if "weather year is not on this machine" not in w]


# ---- PV-10, the yield against PVGIS ----

def test_a_yield_that_disagrees_with_pvgis_warns_on_the_card():
    """The wiring is only observable when the check fails, so this is the test that proves it runs:
    PVGIS is halved for this site, which the design cannot know about, and the card must say so."""
    bundle, request = load("house")
    _, plain = pv_card(bundle, request)
    assert crosscheck_warnings(plain) == []                      # the real design agrees with the real PVGIS

    stored = bundle.climate.pvgis_annual_kwh_per_kw
    off = bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"pvgis_annual_kwh_per_kw": stored / 2.0})})
    _, warned = pv_card(off, request)
    found = crosscheck_warnings(warned)
    assert len(found) == 1 and "above PVGIS" in found[0]
    assert "tolerance" in found[0]


def test_the_cross_check_changes_no_number_on_the_card():
    """PV-10 is a check, not a model. Everything a reader acts on must be identical with and
    without the disagreement; only `warnings` may differ."""
    bundle, request = load("house")
    _, plain = pv_card(bundle, request)
    off = bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"pvgis_annual_kwh_per_kw": bundle.climate.pvgis_annual_kwh_per_kw / 2.0})})
    _, warned = pv_card(off, request)

    assert crosscheck_warnings(warned) and not crosscheck_warnings(plain)
    assert warned.model_dump(exclude={"warnings"}) == plain.model_dump(exclude={"warnings"})
    assert warned.warnings[:len(plain.warnings)] == plain.warnings        # appended, never replaced


def test_a_site_with_no_pvgis_figure_is_not_cross_checked_and_says_so():
    """Missing inputs are reported, not raised and not silently skipped (physics 01 PV-10)."""
    bundle, request = load("house")
    off = bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"pvgis_annual_kwh_per_kw": None})})
    _, card = pv_card(off, request)
    assert len(crosscheck_warnings(card)) == 1
    assert card.solar is not None and card.solar.annual_kwh.expected > 0


def test_a_card_with_no_panels_is_not_cross_checked():
    """An office suite whose roof the design cannot use has no yield to disagree about; a
    'could not cross-check' line there would be noise, not a finding."""
    bundle, request = load("house")
    empty = bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"pvgis_annual_kwh_per_kw": None})})
    _, card = pv_card(empty, request)
    stripped = card.model_copy(update={"solar": card.solar.model_copy(update={"panels": []})})
    assert api._cross_checked_pv(empty, pv_card(empty, request)[0], stripped).warnings == stripped.warnings


@pytest.mark.parametrize("flavor", FLAVORS)
def test_every_golden_example_is_cross_checked_against_its_own_weather_year(flavor):
    """The check must read the same weather file the model was run on, so a disagreement is about
    the design and not about two different years. `_weather_csv` is that file."""
    bundle, _ = load(flavor)
    path = api._weather_csv(bundle)
    assert path is not None and Path(path).is_file()


def test_the_pv_warning_names_the_numbers_a_reader_needs_to_act_on():
    bundle, request = load("house")
    off = bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"pvgis_annual_kwh_per_kw": bundle.climate.pvgis_annual_kwh_per_kw / 2.0})})
    _, card = pv_card(off, request)
    warning = crosscheck_warnings(card)[0]
    for part in ("kWh/kW", "transposition ratio", "loss ratio", "tolerance"):
        assert part in warning, warning


# ---- BEN-01 to BEN-03, the baseline against the federal surveys ----

def baseline_of(flavor):
    bundle, request = load(flavor)
    bundle = on_the_committed_weather(bundle)
    observed, flags = api.observe_interior(bundle)
    model = api.build_building_model(bundle, observed, flags, request.overrides)
    return bundle, model, api.run_baseline(bundle, model)


def test_a_baseline_outside_the_band_warns_on_the_result():
    """Houston's office gas intensity is far below the surveyed offices of its size on either
    weather year, so the door must say so on the object a caller reads. Deliberately not the
    house: its gas sits near the band edge and which side it falls on depends on the weather."""
    _, _, baseline = baseline_of("office_houston")
    gas = [w for w in benchmark_warnings(baseline) if "Gas use intensity" in w]
    assert len(gas) == 1
    assert "percentile" in gas[0] and "CBECS2018" in gas[0]
    assert "water heating" in gas[0], "the warning names the end uses to look at (BEN-03)"


def test_a_baseline_inside_the_band_is_silent():
    """80 percent of real comparable buildings are inside the band, so a model that is must not
    be warned about - otherwise the warning means nothing."""
    _, _, baseline = baseline_of("office")
    assert [w for w in benchmark_warnings(baseline) if "intensity" in w] == []


def test_the_benchmark_changes_no_number_in_the_baseline():
    bundle, model, baseline = baseline_of("office_houston")
    bare = api._simulate_baseline(bundle, model)
    assert baseline.warnings and not bare.warnings
    assert baseline.model_dump(exclude={"warnings"}) == bare.model_dump(exclude={"warnings"})


def test_a_property_with_no_climate_zone_is_not_benchmarked_and_says_so():
    """Missing inputs are reported, never raised (physics 02 section 13: `not_checked` with one
    warning naming what was missing)."""
    bundle, request = load("house")
    pinned = on_the_committed_weather(bundle)
    off = pinned.model_copy(update={"climate": pinned.climate.model_copy(update={"climate_zone": None})})
    observed, flags = api.observe_interior(off)
    model = api.build_building_model(off, observed, flags, request.overrides)
    baseline = api.run_baseline(off, model)
    said = benchmark_warnings(baseline)
    assert len(said) == 1 and "climate zone" in said[0].lower()


def test_an_office_is_benchmarked_against_its_whole_building_not_its_suite():
    """BEN-02: the CBECS size class is the gross area of the building (CoStar), not the scanned
    suite. Houston's suite is 898 m2 inside a 15,101 m2 building, which is a different cut."""
    bundle, request = load("office_houston")
    bundle = on_the_committed_weather(bundle)
    observed, flags = api.observe_interior(bundle)
    model = api.build_building_model(bundle, observed, flags, request.overrides)
    with_costar = api.run_baseline(bundle, model).warnings
    without = api.run_baseline(bundle.model_copy(update={"costar": None}), model).warnings
    assert with_costar != without, "the building area must reach the cut"


def test_the_house_is_typical_on_the_committed_weather_year():
    """Guards the lead's finding in #324: on the committed NOAA year the house's gas lands inside
    the band and the baseline is silent. It warned on the Open-Meteo year, and it still warns on a
    machine that has that older file cached at the fixture's `weather_path` - which is why every
    test here pins the weather rather than trusting whatever the machine happens to hold."""
    _, _, baseline = baseline_of("house")
    assert benchmark_warnings(baseline) == []


def test_the_measures_engine_baseline_is_not_benchmarked():
    """The benchmark belongs on the baseline a person is shown, not on each internal variant the
    measures engine simulates; a warning per variant would flood the result."""
    bundle, model, _ = baseline_of("house")
    assert api._simulate_baseline(bundle, model).warnings == []
