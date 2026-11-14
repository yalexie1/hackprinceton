"""The data lane's provenance reaches the run (issue #319, lead's handoff of 2026-11-14).

A bundle has always carried a `FetchRecord` for everything the data lane could not get, and
nothing read them, so a run could rest on a state-average tariff or on three obliques out of four
without saying so. `fallback` and `error` become a run event and a warning; `missing` and `locked`
do not - a layer that does not exist for a property is not a degraded run.
"""
import json
from pathlib import Path

import pytest

from backend.agent.graph import provenance_fallbacks, provenance_warnings
from backend.schema import FetchRecord, PropertyBundle

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"
FLAVORS = sorted(p.name for p in EX.iterdir() if (p / "run_result.json").is_file())


def bundle_of(flavor):
    return PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())


def with_provenance(flavor, records):
    return bundle_of(flavor).model_copy(update={"provenance": records})


def test_a_fallback_and_an_error_are_both_reported():
    bundle = with_provenance("house", [
        FetchRecord(layer="tariff", what="electricity price", status="fallback",
                    detail="EIA state average, not a looked-up tariff"),
        FetchRecord(layer="vexcel", what="oblique west", status="error",
                    detail="HTTP 429 after three retries"),
    ])
    events = provenance_fallbacks(bundle)
    assert [e.type for e in events] == ["fallback", "fallback"]
    assert [e.payload["status"] for e in events] == ["fallback", "error"]
    assert [e.payload["layer"] for e in events] == ["tariff", "vexcel"]
    assert all(e.stage == "ingest" for e in events)


def test_the_detail_is_carried_into_the_message_a_person_reads():
    bundle = with_provenance("house", [
        FetchRecord(layer="tariff", what="electricity price", status="fallback",
                    detail="EIA state average retail price, CA RES, 2026-08"),
    ])
    message = provenance_fallbacks(bundle)[0].message
    assert "tariff" in message and "electricity price" in message
    assert "EIA state average retail price, CA RES, 2026-08" in message, "the detail is the useful part"


@pytest.mark.parametrize("status", ["ok", "missing", "locked"])
def test_what_simply_is_not_there_is_not_a_warning(status):
    """A property with no CoStar record is modelled differently, and the bundle says so in its own
    fields; repeating it as a run warning would train a reader to ignore the warnings."""
    bundle = with_provenance("house", [FetchRecord(layer="costar", what="listing", status=status)])
    assert provenance_fallbacks(bundle) == [] and provenance_warnings(bundle) == []


def test_a_record_with_no_detail_still_reports():
    bundle = with_provenance("house", [
        FetchRecord(layer="place", what="incorporated place", status="error")])
    assert len(provenance_fallbacks(bundle)) == 1
    assert provenance_warnings(bundle) == ["place incorporated place (error)"]


def test_one_warning_line_per_event_in_the_same_order():
    bundle = bundle_of("office")
    assert provenance_warnings(bundle) == [e.message for e in provenance_fallbacks(bundle)]


@pytest.mark.parametrize("flavor", FLAVORS)
def test_every_golden_bundle_reports_exactly_its_fallback_and_error_records(flavor):
    """Pinned against the bundle itself rather than a count, so a data-lane change that adds or
    removes a record moves this test with it instead of breaking it."""
    raw = json.loads((EX / flavor / "property_bundle.json").read_text())
    expected = [r for r in raw.get("provenance", []) if r["status"] in ("fallback", "error")]
    events = provenance_fallbacks(bundle_of(flavor))
    assert len(events) == len(expected) > 0
    assert [e.payload["what"] for e in events] == [r["what"] for r in expected]
