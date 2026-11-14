"""Document 6, the C-PACE package (L6) and its checks (L7), California and Texas.

Drafted from `specs/legal.md` section 20's 14-section outline and section 15's shared
frame, with every statutory fact and programme rule taken from the `CA-PACE-*` table of
`specs/legal/california.md` section 8 and the `TX-PACE-*` table of
`specs/legal/texas.md` section 6. Our own wording; no published form copied.

The three properties these tests exist to hold, because each is a way the package could
mislead someone about money:

1. **statute and programme rule never read alike** - every Texas rule from `TX-PACE-30`
   up comes from the Texas PACE Authority guide, not Chapter 399;
2. **an incomplete test is not a passed test** - California's 5 per cent tax-burden cap
   needs two inputs the owner supplies;
3. **a failed savings test is reported, not hidden** - Texas requires a programme SIR of
   at least 1, and a project below it still gets a package saying so.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.legal import api as legal
from backend.legal.checks import cpace
from backend.legal.engine import engine
from backend.schema import DocumentRequest, RunResult

SPEC = Path(__file__).resolve().parents[5] / "specs"
HERE = Path(__file__).resolve().parents[1]

#: Every id section 20 lists as a check for this document, per state.
SECTION_20 = {
    "TX": [f"TX-PACE-{n:02d}" for n in list(range(1, 18)) + list(range(30, 43))],
    "CA": [f"CA-PACE-{n:02d}" for n in range(1, 18)],
}
FLAVOR = {"TX": "office_houston", "CA": "office"}


def _draft(state: str, fields: dict | None = None):
    legal._registry.cache_clear()
    run = RunResult.model_validate_json(
        (SPEC / "examples" / FLAVOR[state] / "run_result.json").read_text())
    return legal.fill_template(
        DocumentRequest(run_id="run_x", doc_type="cpace_package", state=state,
                        measure_ids=["ENV_ATTIC"], fields=fields or {}), run)


def _says(draft, phrase: str) -> bool:
    """Whether the document says something, ignoring where the lines happen to wrap.

    The templates are hard-wrapped, so a phrase can straddle a newline and a plain `in`
    test fails on text that is plainly there. `checks/cpace.py` normalises for the same
    reason; the tests have to as well or they assert the line breaks instead of the words.
    """
    return " ".join(phrase.lower().split()) in " ".join(draft.markdown.lower().split())


def _check(state: str, requirement_id: str, fields: dict | None = None):
    return next(c for c in legal.check_document(_draft(state, fields))
                if c.requirement_id == requirement_id)


# ---------- what is offered ----------

@pytest.mark.parametrize("state", ["CA", "TX"])
def test_the_package_is_offered_to_commercial_only(state):
    """C-PACE is for commercial property (in Texas, or residential of five or more
    units). A house gets the reason, not a package."""
    assert "cpace_package" in legal.list_templates(state, "commercial")
    assert "cpace_package" not in legal.list_templates(state, "residential")


@pytest.mark.parametrize("state", ["CA", "TX"])
def test_both_states_have_a_template(state):
    assert ("cpace_package", state) in legal._registry()


# ---------- every id is checked ----------

@pytest.mark.parametrize("state", ["CA", "TX"])
def test_every_id_section_20_lists_has_a_check(state):
    checked = {c.requirement_id for c in legal.check_document(_draft(state))}
    missing = [i for i in SECTION_20[state] if i not in checked]
    assert not missing, f"{state}: no check for {missing}"


@pytest.mark.parametrize("state", ["CA", "TX"])
def test_the_cited_ids_exist_in_the_state_file(state):
    """Section 21 promises every cited id is matched against the state file. Repeating it
    here means a renamed id fails rather than leaving a section citing nothing."""
    state_file = (SPEC / "legal" / ("california.md" if state == "CA" else "texas.md")).read_text()
    template = next(p for p in HERE.glob("*.md")
                    if engine.load_template(p.read_text()).state == state)
    cited = set(re.findall(r"(?:CA|TX)-PACE-\d+", template.read_text()))
    assert cited, "the template cites no ids"
    missing = sorted(i for i in cited if f"| {i} " not in state_file)
    assert not missing, f"cited but not in the state file: {missing}"


# ---------- statute versus programme rule ----------

def test_texas_programme_rules_are_labelled_as_programme_rules():
    """Chapter 399 does not contain the SIR test, the fee share, the loan-to-value limit
    or the uniform closing documents. Presenting a guide rule as law would make a
    programme's discretion look like a legal bar."""
    checks = legal.check_document(_draft("TX"))
    labelled = {c.requirement_id for c in checks if cpace.PROGRAMME in c.requirement}
    for guide_id in ("TX-PACE-30", "TX-PACE-32", "TX-PACE-38", "TX-PACE-39"):
        assert guide_id in labelled, f"{guide_id} is a Program Guide rule and must say so"
    for statute_id in ("TX-PACE-01", "TX-PACE-08", "TX-PACE-14", "TX-PACE-17"):
        assert statute_id not in labelled, f"{statute_id} is statute and must not be labelled"


def test_the_texas_package_says_which_is_which_in_its_own_text():
    body = _draft("TX").markdown
    assert "not from Chapter" in body and "does not present it as law" in body


def test_no_california_check_is_labelled_a_programme_rule():
    """The California ids are all statute or agency fact; the label is a Texas device."""
    checks = legal.check_document(_draft("CA"))
    assert not [c for c in checks if cpace.PROGRAMME in c.requirement]


# ---------- the three refusals ----------

def test_the_california_tax_burden_test_is_incomplete_not_passed():
    """CA-PACE-07 caps total annual taxes and assessments at 5 per cent of market value.
    Without the tax bill and the market value there is no answer, and "no answer" must
    not render as "within the cap"."""
    without = _check("CA", "CA-PACE-07")
    assert without.satisfied is False
    assert "incomplete, not passed" in (without.note or "")

    passing = _check("CA", "CA-PACE-07",
                     {"annual_property_tax_usd": "40000", "market_value_usd": "4000000"})
    assert passing.satisfied is True and "within the 5% cap" in (passing.note or "")

    failing = _check("CA", "CA-PACE-07",
                     {"annual_property_tax_usd": "400000", "market_value_usd": "1000000"})
    assert failing.satisfied is False and "above the 5% cap" in (failing.note or "")


def test_a_texas_project_below_the_sir_minimum_is_reported_not_withheld():
    """Yale's instruction for Houston: a property that fails the savings test must show
    that honestly rather than have the package hidden. The check fails and says why; the
    document is still produced."""
    low = _check("TX", "TX-PACE-30", {"program_sir": "0.6"})
    assert low.satisfied is False
    assert "below the programme minimum" in (low.note or "")
    assert "reports the shortfall rather than withholding" in (low.note or "")
    assert _draft("TX", {"program_sir": "0.6"}).markdown, "the package is still produced"

    ok = _check("TX", "TX-PACE-30", {"program_sir": "1.4"})
    assert ok.satisfied is True and "meets the minimum" in (ok.note or "")


def test_california_lien_priority_is_not_asserted():
    """`california.md` CA-PACE-10 records that the priority provisions were not opened.
    A package that told an owner where this lien ranks against their mortgage, on
    unread provisions, would be the most expensive sentence in the document."""
    check = _check("CA", "CA-PACE-10")
    assert check.satisfied is False
    assert "priority not asserted" in (check.note or "")
    assert "were not opened" in (check.note or "")
    assert _says(_draft("CA"), "Do not rely on any statement about where this lien ranks")


# ---------- California availability ----------

def test_the_california_package_is_hypothetical_until_a_programme_is_named():
    """CA-PACE-15 and -16: Los Angeles County ended its programme in 2020 and the
    Treasurer's list shows its programmes inactive. So the honest output for an LA
    office is a package that says it is hypothetical, with the agency blank."""
    draft = _draft("CA")
    assert _says(draft, "hypothetical until a programme is confirmed")
    for name in ("programme_name", "programme_agency", "programme_administrator"):
        assert name in draft.unfilled_placeholders, f"{name} must not be invented"

    check = _check("CA", "CA-PACE-15")
    assert check.satisfied is False and "hypothetical" in (check.note or "")


def test_the_california_route_is_asked_rather_than_assumed():
    """Route A is a contractual assessment; Route B a community facilities district a
    parcel joins only by unanimous owner approval. The programme decides which."""
    assert "pace_route" in _draft("CA").unfilled_placeholders
    assert _check("CA", "CA-PACE-12").satisfied is False


# ---------- Texas specifics ----------

def test_the_fee_share_limit_is_stated_and_enforced():
    """TX-PACE-38 states it plainly: other fees and costs are limited to no more than
    20 per cent of the total assessment. I first wrote this off as unverified."""
    assert cpace.TX_FEE_SHARE_LIMIT == 0.20
    assert _says(_draft("TX"), "20 per cent of the total assessment")
    assert _check("TX", "TX-PACE-38", {"fee_share": "12"}).satisfied is True
    over = _check("TX", "TX-PACE-38", {"fee_share": "30"})
    assert over.satisfied is False and "above the 20% limit" in (over.note or "")


def test_the_loan_to_value_limit_is_left_open_because_the_guide_disagrees_with_itself():
    """TX-PACE-32: two passages of the guide give different variances. Picking one would
    be inventing a programme rule."""
    check = _check("TX", "TX-PACE-32")
    assert check.satisfied is False
    assert "disagree on the variance" in (check.note or "")


def test_the_region_comes_from_the_incorporated_place_not_the_mailing_city():
    """The data lane's own finding: 6 of 16 kit properties with a Houston mailing city
    are not in the incorporated city, so the region cannot be read off an address."""
    draft = _draft("TX")
    assert _says(draft, "not from a mailing city")
    assert _says(draft, "may be in unincorporated Harris County")
    assert _check("TX", "TX-PACE-04").satisfied is False
    assert "incorporated place" in (_check("TX", "TX-PACE-04").note or "")


def test_the_lien_consequences_are_spelled_out():
    """TX-PACE-14 and -15. An owner signing this needs to know the lien is first and
    prior, runs with the land, and survives a tax foreclosure."""
    draft = _draft("TX")
    for phrase in ("first and prior lien", "runs with the land", "not eliminated"):
        assert phrase in draft.markdown
    assert _check("TX", "TX-PACE-14").satisfied is True


@pytest.mark.parametrize("state", ["CA", "TX"])
def test_the_package_says_it_is_not_the_programmes_contract(state):
    """Section 20: the package never replaces the owner contract, the lender contract or
    the lien notice (TX-PACE-39, CA-PACE-05)."""
    assert _says(_draft(state), "not the programme's contract")


@pytest.mark.parametrize("state", ["CA", "TX"])
def test_nothing_is_invented_that_only_the_owner_can_supply(state):
    """A legal description and a parcel number are never derived from an address."""
    draft = _draft(state)
    for name in ("legal_description", "parcel_number"):
        assert name in draft.unfilled_placeholders


@pytest.mark.parametrize("state", ["CA", "TX"])
def test_rate_and_term_are_never_defaulted(state):
    """Section 20: they are user quotes and the package prints nothing for them if the
    scenario has none. A default here would invent the cost of money."""
    draft = _draft(state)
    assert "rate" in draft.unfilled_placeholders and "term_years" in draft.unfilled_placeholders


@pytest.mark.parametrize("state", ["CA", "TX"])
def test_the_notice_is_top_and_bottom(state):
    draft = _draft(state)
    assert draft.markdown.count("NOT LEGAL ADVICE") >= 2


def test_no_statutory_placeholder_is_optional():
    """Same guard as the commercial template: a required notice declared optional
    resolves to an empty string and its check reads the silence as content."""
    for path in HERE.glob("*.md"):
        template = engine.load_template(path.read_text())
        optional_stats = [n for n in template.optional if n.startswith("stat_")]
        assert not optional_stats, f"{path.name}: statutory text may not be optional"
