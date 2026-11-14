from pathlib import Path

import pytest

from backend.agent.narrative import check_narrative, extract_numbers
from backend.schema import RunResult

EX = Path(__file__).resolve().parents[4] / "specs" / "examples"


def run(flavor):
    return RunResult.model_validate_json((EX / flavor / "run_result.json").read_text())


@pytest.mark.parametrize("flavor", ["house", "office"])
def test_fixture_narrative_passes(flavor):
    r = run(flavor)
    assert check_narrative(r.narrative_md, r) == []


def test_changing_one_number_fails():
    r = run("house")
    bad = r.narrative_md.replace("$9,302", "$9,402")
    assert bad != r.narrative_md
    msgs = check_narrative(bad, r)
    assert len(msgs) == 1 and msgs[0].startswith("9,402")


def test_every_number_is_checked_one_by_one():
    r = run("house")
    for written, *_ in extract_numbers(r.narrative_md):
        n = written.replace(",", "")
        if n.isdigit() and int(n) > 1900:
            bumped = r.narrative_md.replace(written, f"{int(n) + 7:,}" if "," in written else str(int(n) + 7), 1)
            assert check_narrative(bumped, r), written


def test_number_in_no_result_fails():
    r = run("house")
    assert check_narrative("Solar saves 98,765 kWh.", r) == ["98,765: no structured result has this value"]


def test_years_and_headings_are_not_quantities():
    r = run("house")
    assert check_narrative("# 2027 plan\nCredits ended in 2025.", r) == []


def test_percent_and_decimals():
    r = run("house")
    assert check_narrative("Rate is 0.31337 of nothing.", r) != []


# ---- numbers from the bundle, the building model and the address ----

def bundle(flavor):
    from backend.schema import PropertyBundle
    return PropertyBundle.model_validate_json((EX / flavor / "property_bundle.json").read_text())


def test_bundle_value_is_accepted_only_when_the_bundle_is_passed():
    from backend.agent.narrative.narrative import _walk
    r, b = run("house"), bundle("house")
    in_result = set(_walk(r.model_dump(mode="json", exclude={"narrative_md"})))
    only_bundle = next(v for v in sorted(set(_walk(b.model_dump(mode="json"))))
                       if v not in in_result and v != int(v) and round(v, 2) == v and 0 < v < 1000
                       and not any(abs(v - w) < 0.005 for w in in_result))
    text = f"The bundle reports {only_bundle} here."
    assert check_narrative(text, r) != []
    assert check_narrative(text, r, b) == []


def test_address_numbers_are_accepted():
    r = run("house")
    moved = r.model_copy(update={"property": r.property.model_copy(update={"address": "98712 Test St, 90038"})})
    assert check_narrative("Visit 98712 in 90038.", r) != []
    assert check_narrative("Visit 98712 in 90038.", moved) == []


def test_building_model_value_is_accepted_only_when_the_model_is_passed():
    r = run("house")
    model = r.building_model.model_copy(deep=True)
    a = model.assumptions[0]
    a.value = a.value.model_copy(update={"low": 123.4, "expected": 123.4, "high": 123.4})
    r2 = r                                              # the run's own model does not hold 123.4
    assert check_narrative("The value is 123.4 here.", r2) != []
    assert check_narrative("The value is 123.4 here.", r2, model=model) == []


def test_a_number_in_no_source_still_fails_with_every_source_passed():
    r, b = run("house"), bundle("house")
    assert check_narrative("Solar saves 98,765 kWh.", r, b, r.building_model) == [
        "98,765: no structured result has this value"]
