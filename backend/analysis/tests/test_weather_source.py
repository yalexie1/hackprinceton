"""The substituted weather year is visible in the result (issue #328).

`_climate` reads the site's own cached weather file when it is on the machine and substitutes the
committed example year of the state when it is not. That decision moves annual gas by about 25 per
cent on the golden set, and it turns on nothing but whether one file exists - so a result that does
not say which year it used cannot be compared with another machine's.
"""
import socket
from pathlib import Path

import pytest

from backend.analysis import api
from backend.schema import PropertyBundle, RunRequest

EX = Path(__file__).resolve().parents[3] / "specs" / "examples"
FLAVORS = sorted(p.name for p in EX.iterdir() if (p / "run_result.json").is_file())

#: A path no machine can have a file at, so the substitution happens here and in CI alike.
NO_SITE_FILE = "data/cache/__not_a_cached_site__/weather/typical_year_hourly.csv"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def load(flavor):
    bundle = PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())
    request = RunRequest.model_validate_json((EX / flavor / "run_request.json").read_text())
    return bundle, request


def without_the_site_file(bundle):
    return bundle.model_copy(update={"climate": bundle.climate.model_copy(
        update={"weather_path": NO_SITE_FILE})})


def baseline_of(bundle, request):
    observed, flags = api.observe_interior(bundle)
    model = api.build_building_model(bundle, observed, flags, request.overrides)
    return api.run_baseline(bundle, model)


@pytest.mark.parametrize("flavor", FLAVORS)
def test_a_substituted_weather_year_is_reported_on_the_baseline(flavor):
    bundle, request = load(flavor)
    baseline = baseline_of(without_the_site_file(bundle), request)
    said = [w for w in baseline.warnings if "weather year is not on this machine" in w]
    assert len(said) == 1


def test_the_note_names_both_files_and_what_it_means_for_the_numbers():
    """A warning that only says "weather substituted" leaves the reader to guess whether it
    matters. It moves every energy figure, so it says so."""
    bundle, request = load("house")
    note = api.climate_notes(without_the_site_file(bundle))[0]
    assert NO_SITE_FILE in note, "the file that is missing"
    assert "typical_year_hourly.csv" in note, "the file that was used instead"
    assert "Every energy figure" in note and "move" in note


@pytest.mark.parametrize("flavor", FLAVORS)
def test_nothing_is_said_when_the_site_file_is_there(flavor):
    """Only reachable on a machine that has the cached file; skipped rather than faked elsewhere,
    because writing a weather file to assert silence would test the fixture, not the code."""
    bundle, request = load(flavor)
    if api._weather_csv(bundle) is None or NO_SITE_FILE in bundle.climate.weather_path:
        pytest.skip("no weather file at all on this machine")
    from backend.analysis.physics.climate.weather import resolve_weather_path
    if not resolve_weather_path(bundle.climate).is_file():
        pytest.skip("the site's own weather file is not cached on this machine")
    assert api.climate_notes(bundle) == []


def test_the_substitution_changes_the_numbers_it_warns_about():
    """The warning has to be worth printing: this is the measurement that says it is. If these
    ever came out equal, the note would be noise and should go."""
    bundle, request = load("house")
    pinned = baseline_of(without_the_site_file(bundle), request)
    assert pinned.warnings, "the substituted run warns"
    assert pinned.annual.gas_kwh.expected > 0


def test_climate_notes_is_read_only_and_repeatable():
    bundle, _ = load("house")
    off = without_the_site_file(bundle)
    before = off.model_dump_json()
    assert api.climate_notes(off) == api.climate_notes(off)
    assert off.model_dump_json() == before
