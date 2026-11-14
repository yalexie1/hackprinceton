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
    assert check_narrative("It is 0.07 of nothing.", r) != []
