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


def pv_card(bundle, request):
    observed, flags = api.observe_interior(bundle)
    model = api.build_building_model(bundle, observed, flags, request.overrides)
    return model, api.evaluate_measure(bundle, model, "PV_ROOF", request.role)


def crosscheck_warnings(card):
    return [w for w in card.warnings if "PVGIS" in w]


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
